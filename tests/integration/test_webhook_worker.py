"""Real queue/checkpoint integration, signed webhook fixtures and mocked providers."""

import asyncio
import hashlib
import hmac
import json
import os
import time
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from agil_shared.errors import DomainError
from backend.api.webhooks import router
from backend.persistence.checkpoints import checkpointer, thread_config
from backend.persistence.models import (
    Base,
    ConversationJob,
    InboxEvent,
    Outbox,
    utcnow,
)
from backend.persistence.outbox import OutboxStore
from backend.persistence.queue import Queue, thread_lock
from backend.services.events import EventService
from backend.services.handoff import HandoffService
from backend.services.identity import IdentityService, decode_protected
from backend.worker import process_job, send_outputs
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def worker_store():
    url = os.getenv("TEST_MEMORY_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_MEMORY_DATABASE_URL for real PostgreSQL webhook/worker tests")
    schema = "webhook_worker_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(scoped)
    conninfo = (
        make_url(url)
        .set(drivername="postgresql")
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    yield sessionmaker(scoped, expire_on_commit=False), conninfo
    scoped.dispose()
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


class Central:
    def __init__(self):
        self.customer = uuid4()
        self.candidate = uuid4()
        self.calls = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/identity/locate":
            return {
                "candidate_count": 1,
                "candidates": [
                    {"candidate_reference": str(self.candidate), "masked_hint": "F*** · CC ***001"}
                ],
            }
        if path == "/identity/verify":
            return {
                "customer_id": str(self.customer),
                "grant_token": "PRIVATE-RUNTIME-GRANT",
                "expires_at": (utcnow() + timedelta(minutes=20)).isoformat(),
            }
        if path == "/identity/revoke":
            return {"revoked": True}
        raise AssertionError(path)


class Channel:
    def __init__(self):
        self.status = "pending"
        self.sent = []
        self.reads = []
        self.failure = None

    async def conversation(self, conversation_id):
        self.reads.append(str(conversation_id))
        return {"id": int(conversation_id), "inbox_id": 7, "status": self.status, "can_reply": True}

    async def send_message(self, conversation_id, content, *, private=False):
        self.sent.append((str(conversation_id), content, private))
        if self.failure:
            raise self.failure
        return {"id": len(self.sent)}

    async def set_open(self, conversation_id):
        self.status = "open"
        return {"id": "status-open"}


class Output(SimpleNamespace):
    def model_dump(self, **_):
        return dict(vars(self))


class Inference:
    def __init__(self):
        self.settings = SimpleNamespace(
            ai_max_calls_per_turn=5, ai_max_input_tokens=12000, history_visible_messages=20
        )
        self.calls = []

    async def response(self, **kwargs):
        self.calls.append(kwargs)
        reply = "Respuesta ficticia " + str(len(self.calls))
        return SimpleNamespace(
            output=[
                Output(
                    type="message",
                    id="msg_" + uuid4().hex,
                    role="assistant",
                    status="completed",
                    content=[{"type": "output_text", "text": reply, "annotations": []}],
                )
            ],
            output_text=reply,
        )


@pytest.fixture
def runtime(worker_store):
    sessions, conninfo = worker_store
    settings = SimpleNamespace(
        session_secret=SecretStr("fictional-webhook-worker-session" * 2),
        chatwoot_webhook_secret=SecretStr("fictional-webhook-signature"),
        chatwoot_webhook_auth_mode="hmac",
        chatwoot_webhook_tolerance_seconds=300,
        chatwoot_account_id=9,
        chatwoot_inbox_id=7,
        memory_conninfo=conninfo,
        public_base_url="http://demo.example",
        app_env="test",
        enable_local_message_endpoint=True,
    )
    central = Central()
    instance = SimpleNamespace(
        settings=settings,
        sessions=sessions,
        central=central,
        channel=Channel(),
        inference=Inference(),
        queue=Queue(sessions),
        outbox=OutboxStore(sessions),
        maintenance=lambda: False,
        observability=SimpleNamespace(span=lambda *a, **kw: nullcontext()),
    )
    instance.identity = IdentityService(settings, sessions, central)
    instance.handoff = HandoffService(settings, sessions)
    instance.events = EventService(None, sessions)
    return instance


@pytest.fixture
def webapp(runtime):
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router)

    @app.exception_handler(DomainError)
    async def errors(request, exc):
        return JSONResponse(exc.as_dict(), status_code=exc.status)

    return app


def payload(
    source=" whatsapp:CO.DEMO#opaque ", *, message=101, conversation=11, content="Hola ficticio"
):
    return {
        "event": "message_created",
        "id": message,
        "account": {"id": 9},
        "inbox": {"id": 7},
        "message_type": "incoming",
        "private": False,
        "content": content,
        "source_id": "TOP-LEVEL-EXTERNAL-MESSAGE-ID-NOT-THREAD",
        "conversation": {
            "id": conversation,
            "account_id": 9,
            "inbox_id": 7,
            "contact_inbox": {"source_id": source},
        },
    }


def signed(runtime, body):
    raw = json.dumps(body, ensure_ascii=False, indent=2).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        runtime.settings.chatwoot_webhook_secret.get_secret_value().encode(),
        timestamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return raw, {
        "Content-Type": "application/json",
        "X-Chatwoot-Timestamp": timestamp,
        "X-Chatwoot-Signature": "sha256=" + signature,
    }


async def post(client, runtime, body):
    raw, headers = signed(runtime, body)
    return await client.post("/webhooks/chatwoot", content=raw, headers=headers)


@pytest.mark.asyncio
async def test_webhook_literal_source_durable_ack_and_duplicate_without_llm(runtime, webapp):
    body = payload()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json() == {"accepted": True, "duplicate": False}
        assert (await post(client, runtime, body)).json() == {"accepted": True, "duplicate": True}
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 1
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 1
        event = session.scalar(select(InboxEvent))
        assert event.thread_id == body["conversation"]["contact_inbox"]["source_id"]
        assert event.thread_id != body["source_id"] and event.conversation_id == "11"
        assert (
            decode_protected(event.normalized_content, runtime.settings.session_secret)[
                "agent_message"
            ]
            == "Hola ficticio"
        )
    assert not runtime.inference.calls


@pytest.mark.asyncio
async def test_wrong_inbox_private_outgoing_and_unsigned_never_enqueue(runtime, webapp):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        bad = payload()
        bad["inbox"]["id"] = 999
        assert (await post(client, runtime, bad)).status_code == 403
        for changes in (
            {"private": True},
            {"message_type": "outgoing"},
            {"event": "conversation_status_changed"},
        ):
            body = {**payload(), **changes}
            assert (await post(client, runtime, body)).json()["accepted"] is False
        assert (await client.post("/webhooks/chatwoot", json=payload())).status_code == 401
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0
    assert not runtime.channel.reads and not runtime.inference.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"conversation": "invalid"},
        {"conversation": {"id": 11, "contact_inbox": "invalid"}},
        {"message_type": ["incoming"]},
        {"id": True},
        {"content": ["invalid"]},
        {"created_at": {"invalid": "timestamp"}},
    ],
)
async def test_malformed_signed_events_are_safe_client_errors(runtime, webapp, change):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        response = await post(client, runtime, {**payload(), **change})
    assert response.status_code in {200, 403, 422}
    assert "Traceback" not in response.text and not runtime.inference.calls
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0


@pytest.mark.asyncio
async def test_pin_never_persisted_in_real_queue_or_checkpoint(runtime, webapp):
    source = " whatsapp:CO.DEMO-PIN "
    await runtime.identity.locate(
        source, {"document_type": "CC", "document_number": "10000001"}, "lookup"
    )
    await runtime.identity.intercept(source, "sí", False, "confirm")
    body = payload(source, content="246810")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json()["accepted"]
        assert (await post(client, runtime, body)).json()["duplicate"]
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    job = runtime.queue.claim("fixture-worker")
    assert "246810" not in job.event.normalized_content
    assert (
        decode_protected(job.event.normalized_content, runtime.settings.session_secret)[
            "agent_message"
        ]
        == "identity_verified"
    )
    await process_job(runtime, job)
    assert "246810" not in json.dumps(runtime.inference.calls, default=str)
    async with checkpointer(runtime.settings.memory_conninfo) as saver:
        saved = await saver.aget_tuple(thread_config(source))
        assert "246810" not in str(saved.checkpoint)
        assert "PRIVATE-RUNTIME-GRANT" not in str(saved.checkpoint)
    with runtime.sessions() as session:
        event = session.get(InboxEvent, job.event_id)
        assert event.status == "completed" and "246810" not in event.normalized_content


@pytest.mark.asyncio
async def test_same_thread_two_conversations_keep_distinct_outbox_destinations(runtime, webapp):
    source = " raw-source:two-conversations "
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for number, conversation in [(101, 11), (102, 22)]:
            assert (
                await post(
                    client, runtime, payload(source, message=number, conversation=conversation)
                )
            ).status_code == 200
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    for _ in range(2):
        await process_job(runtime, runtime.queue.claim("fixture-worker"))
    with runtime.sessions() as session:
        outputs = list(session.scalars(select(Outbox).order_by(Outbox.created_at)))
        assert len(outputs) == 2 and outputs[0].source_event_id != outputs[1].source_event_id
        assert [row.conversation_id for row in outputs] == ["11", "22"]
        assert all(
            row.thread_id == source and row.account_id == "9" and row.inbox_id == "7"
            for row in outputs
        )
    await send_outputs(runtime)
    assert [(conversation, content) for conversation, content, _ in runtime.channel.sent] == [
        ("11", "Respuesta ficticia 1"),
        ("22", "Respuesta ficticia 2"),
    ]
    assert "Respuesta ficticia 1" in json.dumps(runtime.inference.calls[1]["input"])


@pytest.mark.asyncio
async def test_revision_fence_discards_queued_old_identity_before_inference(runtime, webapp):
    body = payload()
    source = body["conversation"]["contact_inbox"]["source_id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).status_code == 200
    await runtime.identity.invalidate(source)
    job = runtime.queue.claim("fixture-worker")
    await process_job(runtime, job)
    assert not runtime.inference.calls
    with runtime.sessions() as session:
        assert session.get(InboxEvent, job.event_id).status == "completed"
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0


@pytest.mark.asyncio
async def test_busy_thread_retries_delivery_without_persisting_pin(runtime, webapp):
    body = payload(content="246810")
    source = body["conversation"]["contact_inbox"]["source_id"]
    with runtime.sessions() as session, thread_lock(session, source):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(webapp), base_url="http://testserver"
        ) as client:
            response = await post(client, runtime, body)
    assert response.status_code == 429 and response.json()["retryable"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0


@pytest.mark.asyncio
async def test_sender_rechecks_pending_cancels_and_never_repeats_uncertain(runtime):
    source = "literal-send-source"
    snapshot = runtime.identity.snapshot(source)
    rows = []
    for message, conversation in [(101, 11), (102, 22)]:
        event, _ = runtime.queue.enqueue(
            account_id="9",
            inbox_id="7",
            conversation_id=str(conversation),
            message_id=str(message),
            source_id=source,
        )
        rows.append(
            runtime.outbox.enqueue(
                event_id=event.id,
                identity_revision=snapshot["identity_revision"],
                kind="message",
                payload={"content": "Demo response"},
                operation_key="send-" + str(message),
            )
        )
    runtime.channel.status = "open"
    await send_outputs(runtime)
    assert not runtime.channel.sent
    with runtime.sessions() as session:
        assert all(session.get(Outbox, row.id).state == "cancelled" for row in rows)
    event, _ = runtime.queue.enqueue(
        account_id="9", inbox_id="7", conversation_id="33", message_id="103", source_id=source
    )
    row = runtime.outbox.enqueue(
        event_id=event.id,
        identity_revision=0,
        kind="message",
        payload={"content": "Uncertain response"},
        operation_key="uncertain-send",
    )
    runtime.channel.status = "pending"
    runtime.channel.failure = DomainError("channel_uncertain", "Provider result uncertain", 503)
    await send_outputs(runtime)
    await send_outputs(runtime)
    assert len(runtime.channel.sent) == 1 and runtime.channel.sent[0][0] == "33"
    with runtime.sessions() as session:
        assert session.get(Outbox, row.id).state == "uncertain"


@pytest.mark.asyncio
async def test_local_handoff_scope_explicitly_allowed_but_denied_in_production(runtime):
    event, _ = runtime.queue.enqueue(
        account_id="local",
        inbox_id="local",
        conversation_id="local-demo",
        message_id="local-scope",
        source_id="literal-local-source",
    )
    assert not (await runtime.handoff.reconcile_control(event, "pending"))["thread_blocked"]
    await runtime.handoff.request(event, "requested", "Local simulated request")
    assert runtime.handoff.blocked(event.thread_id)
    runtime.settings.app_env = "production"
    with pytest.raises(DomainError) as caught:
        await runtime.handoff.reconcile_control(event, "pending")
    assert caught.value.status == 403
    runtime.settings.app_env = "test"
    runtime.settings.enable_local_message_endpoint = False
    with pytest.raises(DomainError):
        await runtime.handoff.reconcile_control(event, "pending")


@pytest.mark.asyncio
async def test_job_heartbeat_renews_lease_and_stops_after_completion(runtime, monkeypatch):
    import backend.worker as worker

    event, _ = runtime.queue.enqueue(
        account_id="local",
        inbox_id="local",
        conversation_id="demo",
        message_id="heartbeat",
        source_id="heartbeat-source",
    )
    job = runtime.queue.claim("fixture-worker")
    calls = []
    original = runtime.queue.heartbeat

    def heartbeat(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    async def processing(runtime, job):
        await asyncio.sleep(0.035)
        runtime.queue.complete(job.id, job.claim_token)

    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "_process_job", processing)
    monkeypatch.setattr(runtime.queue, "heartbeat", heartbeat)
    await worker.process_job(runtime, job)
    assert len(calls) >= 2 and all(call["lease_seconds"] == 600 for call in calls)
    count = len(calls)
    await asyncio.sleep(0.025)
    assert len(calls) == count


@pytest.mark.asyncio
async def test_lost_heartbeat_claim_cancels_processing_before_effects(runtime, monkeypatch):
    import backend.worker as worker

    event, _ = runtime.queue.enqueue(
        account_id="local",
        inbox_id="local",
        conversation_id="demo",
        message_id="lost-heartbeat",
        source_id="heartbeat-source",
    )
    job = runtime.queue.claim("fixture-worker")
    cancelled = asyncio.Event()

    def heartbeat(*args, **kwargs):
        raise DomainError("stale_claim", "Claim lost", 409)

    async def processing(runtime, job):
        try:
            await asyncio.sleep(1)
            pytest.fail("Lost worker cannot continue effects")
        finally:
            cancelled.set()

    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "_process_job", processing)
    monkeypatch.setattr(runtime.queue, "heartbeat", heartbeat)
    with pytest.raises(DomainError) as caught:
        await worker.process_job(runtime, job)
    assert caught.value.code == "stale_claim" and cancelled.is_set()


def accepted_template(runtime, *, message_id="555", state="sent", mode="live"):
    from backend.persistence.models import Campaign, CampaignRecipient

    with runtime.sessions.begin() as session:
        campaign = Campaign(
            status="completed",
            filter_snapshot={},
            template_snapshot={"name": "delivery fixture"},
            launched_at=utcnow() - timedelta(minutes=1),
            followup_until=utcnow() + timedelta(hours=1),
        )
        session.add(campaign)
        session.flush()
        customer, debt, recipient_id = uuid4(), uuid4(), uuid4()
        recipient = CampaignRecipient(
            id=recipient_id,
            campaign_id=campaign.id,
            customer_id=customer,
            selected_debt_ids=[str(debt)],
            contact_version=1,
            position=0,
            delivery_mode=mode,
            destination_binding={"debt_balances": {str(debt): 10000}},
            account_id="9",
            inbox_id="7",
            conversation_id="11",
            thread_id="literal-delivery-scope",
            send_status="sent" if state == "sent" else "uncertain",
            sent_at=utcnow() - timedelta(seconds=20),
        )
        output = Outbox(
            operation_key=f"campaign:{campaign.id}:recipient:{recipient_id}",
            thread_id=recipient.thread_id,
            identity_revision=0,
            account_id="9",
            inbox_id="7",
            conversation_id="11",
            kind="template",
            payload_private={},
            state=state,
            channel_message_id=message_id if state == "sent" else None,
            lease_until=utcnow() + timedelta(seconds=60),
        )
        session.add_all([recipient, output])
        session.flush()
        return campaign.id, recipient.id, output.id


def delivery_payload(status=None, *, message=555, conversation=11):
    body = payload(
        message=message,
        conversation=conversation,
        content="PIN 246810 https://demo.example/p/x?token=PRIVATE-CAPABILITY",
    )
    body.update(event="message_updated", message_type="outgoing", updated_at=utcnow().isoformat())
    body["conversation"].pop("contact_inbox")
    if status is not None:
        body["status"] = status
    return body


@pytest.mark.asyncio
async def test_delivery_exact_message_dedup_metrics_without_new_turn_or_raw_payload(
    runtime, webapp
):
    from backend.persistence.models import BusinessEvent, ChannelDeliveryEvent, VerifiedContext
    from backend.services.metrics import MetricsService

    campaign_id, _, _ = accepted_template(runtime)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for status in ("delivered", "read", "read", "failed", "failed"):
            response = await post(client, runtime, delivery_payload(status))
            assert response.status_code == 200 and response.json()["processed"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ChannelDeliveryEvent)) == 3
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 3
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
        assert session.scalar(select(func.count()).select_from(VerifiedContext)) == 0
        for receipt in session.scalars(select(ChannelDeliveryEvent)):
            assert "246810" not in str(vars(receipt)) and "PRIVATE-CAPABILITY" not in str(
                vars(receipt)
            )
    metrics = await MetricsService(runtime.sessions).get(campaign_id)
    assert (
        metrics["messages_sent"],
        metrics["unique_sent"],
        metrics["delivered_known"],
        metrics["failed"],
        metrics["unique_replied"],
    ) == (1, 1, 1, 1, 0)
    assert not runtime.inference.calls and not runtime.channel.sent and not runtime.channel.reads


@pytest.mark.asyncio
async def test_delivery_early_receipt_survives_restart_until_message_id_mapping(runtime, webapp):
    from backend.persistence.models import BusinessEvent, CampaignRecipient, ChannelDeliveryEvent
    from backend.services.delivery import DeliveryService

    _, recipient_id, outbox_id = accepted_template(runtime, state="sending")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        response = await post(client, runtime, delivery_payload("delivered"))
    assert response.json()["pending"] and not response.json()["processed"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(ChannelDeliveryEvent)).outbox_id is None
    runtime.outbox.mark_sent(outbox_id, "555")
    with runtime.sessions.begin() as session:
        session.get(CampaignRecipient, recipient_id).send_status = "sent"
    resumed = DeliveryService(runtime.sessions)
    assert resumed.reconcile_pending() == 1 and resumed.reconcile_pending() == 0
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 1
        assert session.scalar(select(ChannelDeliveryEvent)).processed_at is not None


@pytest.mark.asyncio
async def test_installed_payload_nested_status_requires_exact_updated_message_id(runtime, webapp):
    from backend.persistence.models import BusinessEvent, ChannelDeliveryEvent

    accepted_template(runtime)
    nested = delivery_payload()
    nested["conversation"]["messages"] = [
        {"id": 555, "account_id": 9, "inbox_id": 7, "conversation_id": 11, "status": "read"}
    ]
    other = delivery_payload(message=556)
    other["conversation"]["messages"] = [
        {"id": 555, "account_id": 9, "inbox_id": 7, "conversation_id": 11, "status": "delivered"}
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, nested)).json()["processed"]
        assert (await post(client, runtime, other)).json()["pending"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 1
        unknown = session.scalar(
            select(ChannelDeliveryEvent).where(ChannelDeliveryEvent.message_id == "556")
        )
        assert (
            unknown.delivery_status == "unknown"
            and unknown.pending_reason == "status_missing"
            and unknown.processed_at is None
        )


@pytest.mark.asyncio
async def test_delivery_scope_private_incoming_simulated_and_wrong_mapping_cannot_attribute(
    runtime, webapp
):
    from backend.persistence.models import BusinessEvent

    accepted_template(runtime, mode="simulated")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for changes in ({"private": True}, {"message_type": "incoming"}):
            response = await post(client, runtime, {**delivery_payload("read"), **changes})
            assert not response.json()["accepted"]
        wrong = delivery_payload("read")
        wrong["inbox"]["id"] = 999
        assert (await post(client, runtime, wrong)).status_code == 403
        assert (await post(client, runtime, delivery_payload("read"))).json()["pending"]
        assert (await post(client, runtime, delivery_payload("read", message=999))).json()[
            "pending"
        ]
        mismatch = delivery_payload()
        mismatch["conversation"]["messages"] = [{"id": 555, "status": "read", "inbox_id": 999}]
        assert (await post(client, runtime, mismatch)).status_code == 403
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
    assert not runtime.inference.calls and not runtime.channel.sent


@pytest.mark.asyncio
async def test_delivery_receipts_clear_on_reset_and_migration_roundtrip_matches_metadata(runtime):
    import runpy
    from pathlib import Path

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from backend.persistence.models import ChannelDeliveryEvent
    from backend.persistence.reset import reset_operational
    from backend.services.delivery import DeliveryService

    accepted_template(runtime)
    assert DeliveryService(runtime.sessions).record(delivery_payload("read"))["processed"]
    reset_operational(event_cutoff=0, session_factory=runtime.sessions)
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ChannelDeliveryEvent)) == 0
    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "migrations/backend/versions/0003_channel_delivery_receipts.py"
        )
    )
    with runtime.sessions().get_bind().begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration["downgrade"]()
            migration["upgrade"]()
        assert compare_metadata(context, Base.metadata) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reply_source", ["literal-delivery-scope", "opaque-BSUID-source"])
async def test_human_control_reply_counts_once_without_queue_content_or_identity(
    runtime, webapp, reply_source
):
    from backend.persistence.models import BusinessEvent, VerifiedContext
    from backend.services.metrics import MetricsService

    campaign_id, _, _ = accepted_template(runtime)
    runtime.channel.status = "open"
    body = payload(source=reply_source, message=900, content="Mi PIN 246810")
    body["created_at"] = utcnow().isoformat()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for _ in range(2):
            response = await post(client, runtime, body)
            assert response.status_code == 200 and response.json()["reason"] == "human_control"
    with runtime.sessions() as session:
        rows = session.scalars(select(BusinessEvent)).all()
        assert len(rows) == 1 and rows[0].event_type == "first_response"
        assert rows[0].source_key == "reply:9:900"
        assert rows[0].thread_id == reply_source
        assert "246810" not in str(vars(rows[0])) and "Mi PIN" not in str(vars(rows[0]))
        for model in (InboxEvent, ConversationJob, VerifiedContext):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert (await MetricsService(runtime.sessions).get(campaign_id))["unique_replied"] == 1
    # The worker sees the same public message metadata later; it cannot add a milestone.
    assert not await runtime.events.record_incoming(
        SimpleNamespace(
            id=uuid4(),
            account_id="9",
            inbox_id="7",
            conversation_id="11",
            message_id="900",
            thread_id=reply_source,
            received_at=utcnow(),
        )
    )
    assert not runtime.inference.calls and not runtime.channel.sent


@pytest.mark.asyncio
async def test_human_reply_must_follow_real_send_and_valid_scope(runtime, webapp):
    from backend.persistence.models import BusinessEvent, CampaignRecipient, ResetMetadata

    _, recipient_id, _ = accepted_template(runtime)
    runtime.channel.status = "open"
    with runtime.sessions.begin() as session:
        sent_at = session.get(CampaignRecipient, recipient_id).sent_at
        session.add(ResetMetadata(key="demo", reset_at=sent_at - timedelta(minutes=1)))
    before_send = payload(source="opaque-BSUID-source", message=901, content="246810")
    before_send["created_at"] = (sent_at - timedelta(seconds=1)).isoformat()
    before_reset = {
        **before_send,
        "id": 902,
        "created_at": (sent_at - timedelta(minutes=2)).isoformat(),
    }
    wrong_source = payload(source="unrelated-contact", conversation=99, message=903)
    invalid_content = {**payload(source="literal-delivery-scope", message=904), "content": []}
    private = {**payload(source="literal-delivery-scope", message=905), "private": True}
    wrong_inbox = {**payload(source="literal-delivery-scope", message=906), "inbox": {"id": 999}}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, before_send)).json()["reason"] == "human_control"
        assert (await post(client, runtime, before_reset)).json()["reason"] == "before_reset"
        assert (await post(client, runtime, wrong_source)).json()["reason"] == "human_control"
        assert (await post(client, runtime, invalid_content)).status_code == 422
        assert (await post(client, runtime, private)).json()["accepted"] is False
        assert (await post(client, runtime, wrong_inbox)).status_code == 403
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,send_status", [("simulated", "simulated"), ("live", "queued")])
async def test_human_reply_does_not_count_prepared_or_simulated_campaign(
    runtime, webapp, mode, send_status
):
    from backend.persistence.models import BusinessEvent, CampaignRecipient

    _, recipient_id, _ = accepted_template(runtime)
    with runtime.sessions.begin() as session:
        recipient = session.get(CampaignRecipient, recipient_id)
        recipient.delivery_mode, recipient.send_status = mode, send_status
    runtime.channel.status = "open"
    body = payload(source="opaque-BSUID-source", content="Mi PIN 246810")
    body["created_at"] = utcnow().isoformat()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json()["reason"] == "human_control"
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
    assert not runtime.inference.calls and not runtime.channel.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("cutoff_field", ["closed_at", "followup_until"])
async def test_alternate_source_reply_still_respects_campaign_cutoff(runtime, webapp, cutoff_field):
    from backend.persistence.models import BusinessEvent, Campaign

    campaign_id, _, _ = accepted_template(runtime)
    with runtime.sessions.begin() as session:
        setattr(session.get(Campaign, campaign_id), cutoff_field, utcnow() - timedelta(seconds=1))
    runtime.channel.status = "open"
    body = payload(source="opaque-BSUID-source", message=907, content="Mi PIN 246810")
    body["created_at"] = utcnow().isoformat()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json()["reason"] == "human_control"
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
