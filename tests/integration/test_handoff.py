"""Real PostgreSQL ordering, idempotence and human-control races; no live sends."""

import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agil_shared.errors import DomainError
from backend.persistence.models import Base, HumanCase, InboxEvent, Outbox, VerifiedContext, utcnow
from backend.persistence.outbox import OutboxStore
from backend.services.handoff import HandoffService
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def handoff_store():
    url = os.getenv("TEST_MEMORY_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_MEMORY_DATABASE_URL for real PostgreSQL handoff tests")
    schema = "handoff_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(scoped)
    yield sessionmaker(scoped, expire_on_commit=False)
    scoped.dispose()
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


@pytest.fixture
def case_setup(handoff_store):
    customer, debt = uuid4(), uuid4()
    with handoff_store.begin() as session:
        context = VerifiedContext(
            thread_id="literal-source",
            identity_revision=2,
            challenge_state="verified",
            customer_id=customer,
            selected_debt_id=debt,
            central_grant="private-grant-never-in-note",
            expires_at=utcnow() + timedelta(minutes=20),
        )
        event = InboxEvent(
            account_id="demo-account",
            inbox_id="demo-inbox",
            message_id="request-1",
            conversation_id="conversation-one",
            thread_id="literal-source",
            normalized_content="Necesito un asesor",
        )
        session.add_all([context, event])
        session.flush()
    service = HandoffService(
        SimpleNamespace(chatwoot_account_id="demo-account", chatwoot_inbox_id="demo-inbox"),
        handoff_store,
    )
    return service, event, customer, debt


def rows(store):
    with store() as session:
        return {row.kind: row for row in session.scalars(select(Outbox))}


def mark_effect_sent(store, effect, *, pending=True):
    outbox = OutboxStore(store)
    claimed = outbox.prepare(effect.id, pending=pending, identity_revision=2)
    assert claimed is not None
    outbox.mark_sent(claimed.id, "demo-channel-" + effect.kind, claim_token=claimed.claim_token)


def followup(store, *, conversation="conversation-one", message_id="followup-1"):
    with store.begin() as session:
        event = InboxEvent(
            account_id="demo-account",
            inbox_id="demo-inbox",
            message_id=message_id,
            conversation_id=conversation,
            thread_id="literal-source",
            normalized_content="Continuar",
        )
        session.add(event)
        session.flush()
        return event


@pytest.mark.asyncio
async def test_case_persists_before_ordered_effects_and_duplicate_is_idempotent(
    case_setup, handoff_store
):
    service, event, customer, debt = case_setup
    result = await service.request(event, "requested", "Quiero revisar la oferta", "79.99")
    assert result["status"] == "action_pending" and service.blocked(event.thread_id)
    assert await service.request(event, "requested", "Same request reprocessed", "79.99") == result
    with handoff_store() as session:
        cases = list(session.scalars(select(HumanCase)))
        assert len(cases) == 1
        case = cases[0]
        assert case.customer_id == customer and case.debt_id == debt and case.offer_cents == 7999
        assert (case.account_id, case.inbox_id, case.conversation_id) == (
            event.account_id,
            event.inbox_id,
            event.conversation_id,
        )
    effects = rows(handoff_store)
    assert set(effects) == {"private_note", "handoff_notice", "set_open"}
    assert effects["private_note"].payload_private["depends_on"] == []
    assert effects["handoff_notice"].payload_private["depends_on"] == [
        str(effects["private_note"].id)
    ]
    assert effects["set_open"].payload_private["depends_on"] == [
        str(effects["private_note"].id),
        str(effects["handoff_notice"].id),
    ]
    store = OutboxStore(handoff_store)
    assert store.prepare(effects["set_open"].id, pending=True, identity_revision=2) is None
    assert store.prepare(effects["handoff_notice"].id, pending=True, identity_revision=2) is None
    mark_effect_sent(handoff_store, effects["private_note"])
    mark_effect_sent(handoff_store, effects["handoff_notice"])
    mark_effect_sent(handoff_store, effects["set_open"])


@pytest.mark.asyncio
async def test_return_requires_applied_transfer_open_observation_then_new_pending_event(
    case_setup, handoff_store
):
    service, event, _, _ = case_setup
    await service.request(event, "dispute", "Revisión de deuda")
    newer = followup(handoff_store)
    assert (await service.reconcile_control(newer, "pending"))["thread_blocked"]
    assert (await service.reconcile_control(newer, "open"))["thread_blocked"]
    effects = rows(handoff_store)
    for kind in ["private_note", "handoff_notice", "set_open"]:
        mark_effect_sent(handoff_store, effects[kind])
    assert (await service.reconcile_control(newer, "pending"))["thread_blocked"]
    with handoff_store() as session:
        case = session.scalar(select(HumanCase))
        assert case.status == "transferred" and not case.open_observed
    await service.reconcile_control(event, "open")
    assert (await service.reconcile_control(event, "pending"))["thread_blocked"]
    result = await service.reconcile_control(newer, "pending")
    assert not result["thread_blocked"] and not service.blocked(event.thread_id)
    assert result["cases"][0]["case_status"] == "returned"
    with handoff_store() as session:
        assert session.scalar(select(HumanCase)).return_event_id == newer.id
    # A later pending observation must not move the original return marker.
    latest = followup(handoff_store, message_id="another-followup")
    await service.reconcile_control(latest, "pending")
    with handoff_store() as session:
        assert session.scalar(select(HumanCase)).return_event_id == newer.id


@pytest.mark.asyncio
async def test_human_takeover_during_inference_cancels_queued_output(case_setup, handoff_store):
    service, event, _, _ = case_setup
    store = OutboxStore(handoff_store)
    output = store.enqueue(
        event_id=event.id,
        identity_revision=2,
        kind="message",
        payload={"content": "Output produced during inference"},
        operation_key="inference-output",
    )
    await service.reconcile_control(event, "open")
    with handoff_store() as session:
        assert session.get(Outbox, output.id).state == "cancelled"
    assert store.prepare(output.id, pending=False, identity_revision=2) is None
    # A case blocks bot messages even while the channel remains pending before transfer.
    await service.request(event, "requested", "Escalation")
    later = store.enqueue(
        event_id=event.id,
        identity_revision=2,
        kind="message",
        payload={"content": "Late model result"},
        operation_key="late-inference-output",
    )
    assert store.prepare(later.id, pending=True, identity_revision=2) is None


@pytest.mark.asyncio
async def test_uncertain_note_blocks_following_effects_without_resending(case_setup, handoff_store):
    service, event, _, _ = case_setup
    await service.request(event, "technical_failure", "Provider unavailable")
    effects = rows(handoff_store)
    store = OutboxStore(handoff_store)
    note = store.prepare(effects["private_note"].id, pending=True, identity_revision=2)
    store.mark_uncertain(note.id, claim_token=note.claim_token)
    assert store.prepare(note.id, pending=True, identity_revision=2) is None
    assert store.prepare(effects["handoff_notice"].id, pending=True, identity_revision=2) is None
    assert store.prepare(effects["set_open"].id, pending=True, identity_revision=2) is None
    assert (await service.reconcile_control(followup(handoff_store), "pending"))["thread_blocked"]


@pytest.mark.asyncio
async def test_notice_requires_pending_and_tenant_destination_is_immutable(
    case_setup, handoff_store
):
    service, event, _, _ = case_setup
    await service.request(event, "requested", "Solicitud")
    effects = rows(handoff_store)
    mark_effect_sent(handoff_store, effects["private_note"])
    assert (
        OutboxStore(handoff_store).prepare(
            effects["handoff_notice"].id, pending=False, identity_revision=2
        )
        is None
    )
    for row in effects.values():
        assert (row.account_id, row.inbox_id, row.conversation_id, row.source_event_id) == (
            event.account_id,
            event.inbox_id,
            event.conversation_id,
            event.id,
        )
    with handoff_store() as session:
        case = session.scalar(select(HumanCase))
        assert not case.open_observed
    assert (
        await service.reconcile_control(
            followup(handoff_store, conversation="conversation-other"), "pending"
        )
    )["thread_blocked"]


@pytest.mark.asyncio
async def test_private_note_redacts_secrets_and_only_uses_trusted_identity(
    case_setup, handoff_store
):
    service, event, customer, debt = case_setup
    await service.request(
        event,
        "payment_unverified",
        "pin: 246810 private-grant-never-in-note https://demo.invalid/p?token=abc documento 123456789 y teléfono +573001234567",
    )
    note = rows(handoff_store)["private_note"].payload_private["content"]
    assert str(customer) in note and str(debt) in note
    for forbidden in [
        "246810",
        "private-grant-never-in-note",
        "123456789",
        "+573001234567",
        "token=abc",
    ]:
        assert forbidden not in note
    assert "no verificado" in note


@pytest.mark.asyncio
async def test_reason_amount_and_tenant_are_validated(case_setup, handoff_store):
    service, event, _, _ = case_setup
    with pytest.raises(DomainError):
        await service.request(event, "invented", "summary")
    with pytest.raises(DomainError):
        await service.request(event, "below_minimum", "summary", "79.999")
    wrong = HandoffService(SimpleNamespace(chatwoot_account_id="different-account"), handoff_store)
    with pytest.raises(DomainError) as caught:
        await wrong.request(event, "requested", "summary")
    assert caught.value.status == 403
    with handoff_store() as session:
        assert session.scalar(select(HumanCase)) is None


def test_backend_migrations_preserve_legacy_case_and_match_return_event_model(case_setup, handoff_store, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from backend import config as backend_config
    from sqlalchemy.engine import make_url

    _, event, customer, debt = case_setup
    with handoff_store.begin() as db:
        db.add(HumanCase(
            thread_id=event.thread_id, account_id=event.account_id, inbox_id=event.inbox_id,
            conversation_id=event.conversation_id, source_event_id=event.id,
            customer_id=customer, debt_id=debt, reason='dispute', origin='agent',
            status='returned', open_observed=True,
        ))
    engine = handoff_store().get_bind()
    # This fixture starts with current metadata; stamp it, then round-trip 0005/0006.
    # Scoped fixture engine carries its search_path in connect_args; obtain it from PostgreSQL.
    with engine.connect() as connection:
        schema = connection.scalar(text('select current_schema()'))
    url = make_url(os.getenv('TEST_MEMORY_DATABASE_URL') or os.environ['TEST_DATABASE_URL']).update_query_dict({'options': '-csearch_path=' + schema})
    monkeypatch.setattr(backend_config, 'get_settings', lambda: SimpleNamespace(memory_database_url=url.render_as_string(hide_password=False)))
    cfg = Config(str(Path(__file__).resolve().parents[2] / 'migrations/backend/alembic.ini'))
    command.stamp(cfg, 'head')
    command.downgrade(cfg, 'backend_0005')
    command.upgrade(cfg, 'head')
    with handoff_store() as db:
        case = db.scalar(select(HumanCase))
        assert case.status == 'returned' and case.return_event_id is None
        assert case.customer_id == customer and case.debt_id == debt
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
