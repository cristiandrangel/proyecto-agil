"""Financial and identity contracts against isolated schemas on real PostgreSQL 17."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from central.auth import check_pin
from central.config import Settings
from central.main import create_app
from central.models import (
    Agreement,
    Base,
    CommandResult,
    Customer,
    Debt,
    IdentitySession,
    PaymentOrder,
    Settlement,
    utcnow,
)
from central.seed import fixture_id, seed
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url


@pytest.fixture
def central():
    dsn = (
        os.getenv("CENTRAL_TEST_DATABASE_URL")
        or os.getenv("TEST_CENTRAL_DATABASE_URL")
        or os.getenv("TEST_DATABASE_URL")
    )
    if not dsn:
        pytest.skip("Set CENTRAL_TEST_DATABASE_URL to a disposable PostgreSQL 17 database")
    admin = create_engine(dsn)
    if admin.dialect.name != "postgresql":
        pytest.fail("Financial integration tests require real PostgreSQL")
    schema = "central_test_" + uuid.uuid4().hex
    with admin.begin() as conn:
        assert int(conn.scalar(text("SHOW server_version_num"))) // 10000 == 17
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    url = make_url(dsn).update_query_dict({"options": f"-csearch_path={schema}"})
    settings = Settings(
        _env_file=None,
        central_database_url=url.render_as_string(hide_password=False),
        central_operator_token="operator-test-only",
        central_agent_token="agent-test-only",
        payment_signing_key="signing-test-only",
        demo_pin="2468",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory.begin() as db:
        assert seed(db)["seeded"] is True
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app
    app.state.engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin.dispose()


def headers(grant=None, key=None, operator=False):
    result = {
        "Authorization": "Bearer operator-test-only" if operator else "Bearer agent-test-only"
    }
    if grant:
        result["X-Customer-Grant"] = grant
    if key:
        result["Idempotency-Key"] = key
    return result


def auth(client, document="10000001", binding=None):
    locate = client.post(
        "/internal/v1/identity/locate",
        headers=headers(),
        json={"document_type": "CC", "document_number": document},
    )
    assert locate.status_code == 200, locate.text
    candidate = locate.json()["candidate_reference"]
    verification = client.post(
        "/internal/v1/identity/verify",
        headers=headers(),
        json={
            "candidate_reference": candidate,
            "pin": "2468",
            "binding_ref": binding or str(uuid.uuid4()),
            "source_message_id": str(uuid.uuid4()),
            "confirmed": True,
        },
    )
    assert verification.status_code == 200, verification.text
    return verification.json()["grant_token"]


def order(client, grant, name="ana-hogar", key=None):
    result = client.post(
        "/internal/v1/orders",
        headers=headers(grant, key or str(uuid.uuid4())),
        json={"debt_id": str(fixture_id(name)), "expected_version": 1},
    )
    assert result.status_code == 200, result.text
    return result.json()


def pay(client, value, decision="approved", key=None):
    return client.post(
        f"/internal/v1/orders/{value['id']}/attempts",
        headers=headers(key=key or str(uuid.uuid4())),
        json={"capability": value["capability"], "decision": decision},
    )


def test_masked_identity_pin_lock_and_retry_deduplication(central):
    client, app = central
    located = client.post(
        "/internal/v1/identity/locate", headers=headers(), json={"phone_e164": "+1 (555) 000-1001"}
    )
    assert located.status_code == 200
    result = located.json()
    assert result["candidate_count"] == 1
    assert result["masked_hint"] == "Nombre: A•a\nDocumento: CC 10000001"
    assert all(
        secret not in located.text
        for secret in ["Ana Martínez López", "2468", "balance_cents", "pin_hash"]
    )
    body = {
        "candidate_reference": result["candidate_reference"],
        "pin": "0000",
        "binding_ref": str(uuid.uuid4()),
        "source_message_id": "pin-1",
    }
    assert (
        client.post("/internal/v1/identity/verify", headers=headers(), json=body).status_code == 401
    )
    assert (
        client.post("/internal/v1/identity/verify", headers=headers(), json=body).status_code == 401
    )
    # New backend bindings cannot evade the per-customer attempt limit.
    body.update(binding_ref=str(uuid.uuid4()), source_message_id="pin-2")
    assert (
        client.post("/internal/v1/identity/verify", headers=headers(), json=body).status_code == 401
    )
    body.update(binding_ref=str(uuid.uuid4()), source_message_id="pin-3")
    assert (
        client.post("/internal/v1/identity/verify", headers=headers(), json=body).status_code == 423
    )
    body.update(pin="2468", source_message_id="pin-4")
    assert (
        client.post("/internal/v1/identity/verify", headers=headers(), json=body).status_code == 423
    )
    assert client.get("/internal/v1/debts", headers=headers()).status_code == 401
    with app.state.session_factory() as db:
        customer = db.get(Customer, fixture_id("ana"))
        assert customer.pin_hash != "2468" and check_pin("2468", customer.pin_hash)
        assert sum(db.scalars(select(IdentitySession.failed_attempts))) == 3


def test_customer_grants_isolate_debts_and_switch_revokes_prior(central):
    client, app = central
    binding = str(uuid.uuid4())
    grant = auth(client, binding=binding)
    debts = client.get("/internal/v1/debts", headers=headers(grant))
    assert debts.status_code == 200 and debts.json()["total"] == 2
    assert {row["balance_cents"] for row in debts.json()["items"]} == {10000, 6000}
    foreign = client.get(f"/internal/v1/debts/{fixture_id('bruno-hogar')}", headers=headers(grant))
    absent = client.get(f"/internal/v1/debts/{uuid.uuid4()}", headers=headers(grant))
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json()["code"] == absent.json()["code"]
    new_grant = auth(client, document="10000002", binding=binding)
    assert client.get("/internal/v1/debts", headers=headers(grant)).status_code == 401
    assert client.get("/internal/v1/debts", headers=headers(new_grant)).json()["total"] == 1
    assert client.get("/internal/v1/events", headers=headers(new_grant)).status_code == 403


def test_full_payment_rejected_then_applied_idempotently_and_reference_isolated(central):
    client, app = central
    grant = auth(client)
    value = order(client, grant, key="order-one")
    repeated = order(client, grant, key="order-one")
    assert repeated == value
    denied = pay(client, value, "rejected")
    assert denied.status_code == 200 and denied.json()["balance_cents"] == 10000
    accepted = pay(client, value, key="payment-one")
    assert accepted.status_code == 200, accepted.text
    receipt = accepted.json()
    assert receipt["received_cents"] == 10000 and receipt["forgiven_cents"] == 0
    assert pay(client, value, key="payment-one").json() == receipt
    assert pay(client, value, "rejected", key="payment-one").status_code == 409
    assert (
        client.get(
            f"/internal/v1/debts/{fixture_id('ana-telefonia')}", headers=headers(grant)
        ).json()["balance_cents"]
        == 6000
    )
    verified = client.get(
        "/internal/v1/payments/verify",
        params={
            "debt_id": str(fixture_id("ana-hogar")),
            "payment_reference": receipt["payment_reference"],
        },
        headers=headers(grant),
    )
    assert verified.json()["status"] == "applied"
    bruno = auth(client, "10000002")
    unrelated = client.get(
        "/internal/v1/payments/verify",
        params={
            "debt_id": str(fixture_id("bruno-hogar")),
            "payment_reference": receipt["payment_reference"],
        },
        headers=headers(bruno),
    )
    assert unrelated.json()["status"] == "absent"
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Settlement)) == 1
        saved = db.get(CommandResult, "order-one").result_reference
        assert "capability" not in saved


def test_concurrent_orders_settle_exactly_once(central):
    client, app = central
    grant = auth(client)
    values = [order(client, grant), order(client, grant)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: pay(client, value), values))
    assert sorted(response.status_code for response in results) in ([200, 409], [200, 410])
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Settlement)) == 1
        assert db.get(Debt, fixture_id("ana-hogar")).balance_cents == 0
    events = client.get("/internal/v1/events", headers=headers(operator=True)).json()["items"]
    assert sum(event["event_type"] == "payment_applied" for event in events) == 1


def test_stale_balance_invalidates_order_and_quote(central):
    client, app = central
    grant = auth(client)
    value = order(client, grant)
    changed = client.patch(
        f"/internal/v1/debts/{fixture_id('ana-hogar')}",
        headers=headers(key="adjust-one", operator=True),
        json={"expected_version": 1, "balance_cents": 9500},
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert pay(client, value).status_code == 410
    stale = client.post(
        "/internal/v1/orders",
        headers=headers(grant, "stale-order"),
        json={"debt_id": str(fixture_id("ana-hogar")), "expected_version": 1},
    )
    assert stale.status_code == 409
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Settlement)) == 0


@pytest.mark.parametrize(
    "amount,status", [("90.00", "propuesto"), ("80", "propuesto"), ("79.99", "requires_human")]
)
def test_discount_boundaries_and_accept_only_subsequent_message(central, amount, status):
    client, app = central
    grant = auth(client)
    quoted = client.post(
        "/internal/v1/agreements/quote",
        headers=headers(grant, "quote-one"),
        json={
            "debt_id": str(fixture_id("ana-hogar")),
            "expected_version": 1,
            "offer_amount_usd": amount,
            "source_message_id": "offer-message",
        },
    )
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["status"] == status
    if status == "requires_human":
        return
    ident = quoted.json()["id"]
    same_message = client.post(
        f"/internal/v1/agreements/{ident}/accept",
        headers=headers(grant, "accept-same"),
        json={"expected_version": 1, "source_message_id": "offer-message"},
    )
    assert same_message.status_code == 409
    accepted = client.post(
        f"/internal/v1/agreements/{ident}/accept",
        headers=headers(grant, "accept-later"),
        json={"expected_version": 1, "source_message_id": "later-message"},
    )
    assert accepted.status_code == 200, accepted.text
    with app.state.session_factory() as db:
        assert db.get(Debt, fixture_id("ana-hogar")).balance_cents == 10000
    value = accepted.json()
    receipt = pay(client, value)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["received_cents"] == quoted.json()["offer_cents"]
    assert receipt.json()["forgiven_cents"] == 10000 - quoted.json()["offer_cents"]


@pytest.mark.parametrize("amount", ["0", "-1", "100", "100.01", "80.001", "1e2", 80.0])
def test_invalid_discount_amounts_do_not_create_orders(central, amount):
    client, app = central
    grant = auth(client)
    result = client.post(
        "/internal/v1/agreements/quote",
        headers=headers(grant, str(uuid.uuid4())),
        json={
            "debt_id": str(fixture_id("ana-hogar")),
            "expected_version": 1,
            "offer_amount_usd": amount,
            "source_message_id": "offer",
        },
    )
    assert result.status_code == 422, result.text
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(PaymentOrder)) == 0


def test_paid_receipt_survives_charge_expiry_but_no_new_attempt(central):
    client, app = central
    grant = auth(client)
    value = order(client, grant)
    receipt = pay(client, value, key="receipt-paid").json()
    # Move time forward without changing the signed expiry payload.
    import central.orders
    import central.payments

    future = utcnow() + timedelta(minutes=31)
    from unittest.mock import patch

    with (
        patch.object(central.orders, "utcnow", return_value=future),
        patch.object(central.payments, "utcnow", return_value=future),
    ):
        result = client.get(
            f"/internal/v1/orders/{value['id']}",
            params={"capability": value["capability"]},
            headers=headers(),
        )
        assert (
            result.status_code == 200
            and result.json()["payment_reference"] == receipt["payment_reference"]
        )
        assert pay(client, value).status_code == 410
        assert pay(client, value, key="receipt-paid").json() == receipt
    with patch.object(central.orders, "utcnow", return_value=utcnow() + timedelta(hours=25)):
        assert (
            client.get(
                f"/internal/v1/orders/{value['id']}",
                params={"capability": value["capability"]},
                headers=headers(),
            ).status_code
            == 410
        )


def test_operator_contact_shared_version_mora_and_seed_never_overwrites(central):
    client, app = central
    changed = client.patch(
        f"/internal/v1/customers/{fixture_id('ana')}",
        headers=headers(key="contact-edit", operator=True),
        json={
            "expected_contact_version": 1,
            "phone_e164": "+1 555 999 9999",
            "delivery_mode": "live",
            "test_contact_enabled": True,
        },
    )
    assert changed.status_code == 200 and changed.json()["contact_version"] == 2
    rows = client.get(
        "/internal/v1/debts", headers=headers(operator=True), params={"document_number": "10000001"}
    ).json()["items"]
    assert len(rows) == 2 and {row["phone_e164"] for row in rows} == {"+15559999999"}
    assert (
        client.post(
            "/internal/v1/demo/seed", headers=headers(key="seed-after-edit", operator=True)
        ).json()["seeded"]
        is False
    )
    for days in (0, 29, 30, 59, 60, 89, 90, 119, 120):
        rows = client.get(
            "/internal/v1/debts",
            headers=headers(operator=True),
            params={"dias_mora_min": days, "dias_mora_max": days},
        ).json()["items"]
        assert rows and all(row["dias_mora"] == days for row in rows)
    events = client.get("/internal/v1/events", headers=headers(operator=True)).json()["items"]
    assert any(event["event_type"] == "contact_changed" for event in events)
    assert "15559999999" not in str(events)


def test_event_cursor_never_advances_past_uncommitted_earlier_event(central):
    """Sequence allocation must follow commit order across independent debts."""
    from concurrent.futures import TimeoutError

    from central.models import CentralEvent

    client, app = central
    first = app.state.session_factory()
    first.add(CentralEvent(event_type="first_pending", payload={}))
    first.flush()

    def publish_second():
        with app.state.session_factory.begin() as db:
            db.add(CentralEvent(event_type="second_committed", payload={}))

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish_second)
            try:
                future.result(timeout=0.25)
            except TimeoutError:
                pass
            try:
                visible = client.get("/internal/v1/events", headers=headers(operator=True)).json()[
                    "items"
                ]
            finally:
                first.commit()
            future.result(timeout=5)
    finally:
        first.close()
    assert visible == []
    events = client.get("/internal/v1/events", headers=headers(operator=True)).json()["items"]
    assert [event["event_type"] for event in events] == ["first_pending", "second_committed"]


def test_revoking_binding_immediately_removes_old_customer_authorization(central):
    client, app = central
    binding = str(uuid.uuid4())
    grant = auth(client, binding=binding)
    response = client.post(
        "/internal/v1/identity/revoke",
        headers=headers(key="revoke-binding"),
        json={"binding_ref": binding},
    )
    assert response.status_code == 200 and response.json()["revoked"] is True
    assert client.get("/internal/v1/debts", headers=headers(grant)).status_code == 401


@pytest.mark.asyncio
async def test_recoverable_two_database_reset_clears_real_checkpoints_preserves_spend(central):
    from decimal import Decimal
    from types import SimpleNamespace

    import httpx
    from agil_shared.errors import DomainError
    from backend.integrations.central import CentralClient
    from backend.persistence.checkpoints import checkpointer
    from backend.persistence.models import Base as MemoryBase
    from backend.persistence.models import InferenceReservation, ResetMetadata, VerifiedContext
    from backend.services.demo import DemoService
    from langgraph.checkpoint.base import empty_checkpoint
    from sqlalchemy.orm import sessionmaker

    client, app = central
    admin = create_engine(os.environ["CENTRAL_TEST_DATABASE_URL"])
    schema = "reset_memory_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    url = make_url(os.environ["CENTRAL_TEST_DATABASE_URL"]).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = create_engine(url)
    MemoryBase.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    settings = SimpleNamespace(
        demo_mode=True,
        central_api_url="http://central.test",
        central_operator_token=app.state.settings.central_operator_token,
        memory_conninfo=url.set(drivername="postgresql").render_as_string(hide_password=False),
    )
    actual = CentralClient(settings, role="operator", transport=httpx.ASGITransport(app=app))

    class FlakyCentral:
        calls = 0

        async def request(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise DomainError(
                    "central_unavailable", "Central unavailable", status=503, retryable=True
                )
            return await actual.request(*args, **kwargs)

    service = DemoService(settings, FlakyCentral(), session_factory=sessions)
    source = "opaque Literal/Meta-001"
    try:
        with sessions.begin() as db:
            db.add(VerifiedContext(thread_id=source, binding_ref=uuid.uuid4(), identity_revision=1))
            db.add(
                InferenceReservation(
                    operation_key="private-spend-test",
                    turn_id="turn",
                    modality="text",
                    model="fixture",
                    price_version="test",
                    reserved_usd=Decimal("0.25"),
                    actual_usd=Decimal("0.20"),
                    state="settled",
                    lease_until=utcnow(),
                )
            )
        async with checkpointer(settings.memory_conninfo, setup=True) as saver:
            await saver.aput(
                {"configurable": {"thread_id": source, "checkpoint_ns": ""}},
                empty_checkpoint(),
                {"source": "input", "step": 0, "parents": {}},
                {},
            )
            assert await saver.aget_tuple({"configurable": {"thread_id": source}})
        operation = str(uuid.uuid4())
        payload = {"confirmation": "RESET_DEMO", "operation_key": operation}
        with pytest.raises(DomainError, match="unavailable"):
            await service.reset(payload)
        assert (await service.status())["maintenance_mode"] is True
        with sessions() as db:
            assert db.get(ResetMetadata, "demo").reset_stage == "checkpoints_cleared"
        result = await service.reset(payload)
        assert result["status"] == "complete" and result["epoch"] == 1
        assert await service.reset(payload) == result
        assert (await service.status())["maintenance_mode"] is False
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(VerifiedContext)) == 0
            spend = db.scalar(select(InferenceReservation))
            assert spend.actual_usd == Decimal("0.20")
            assert db.get(ResetMetadata, "demo").epoch == 1
        async with checkpointer(settings.memory_conninfo) as saver:
            assert await saver.aget_tuple({"configurable": {"thread_id": source}}) is None
        assert (
            client.get("/internal/v1/debts", headers=headers(operator=True)).json()["total"] == 14
        )
        assert result["event_cutoff"] > 0
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_order_capability_can_be_regenerated_only_under_owner_grant(central):
    client, app = central
    grant = auth(client)
    value = order(client, grant)
    authorized = client.get(f"/internal/v1/orders/{value['id']}", headers=headers(grant))
    assert authorized.json()["capability"] == value["capability"]
    public = client.get(
        f"/internal/v1/orders/{value['id']}",
        headers=headers(),
        params={"capability": value["capability"]},
    )
    assert public.status_code == 200 and "capability" not in public.json()
    assert "capability" not in client.get("/internal/v1/debts", headers=headers(grant)).text
    another = order(client, grant, name="ana-telefonia")
    assert (
        client.get(
            f"/internal/v1/orders/{another['id']}",
            headers=headers(),
            params={"capability": value["capability"]},
        ).status_code
        == 404
    )
    bruno = auth(client, "10000002")
    assert (
        client.get(f"/internal/v1/orders/{value['id']}", headers=headers(bruno)).status_code == 404
    )


def test_frozen_alembic_upgrade_downgrade_matches_models(central, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from central import config as central_config
    from sqlalchemy import inspect

    admin = create_engine(os.environ["CENTRAL_TEST_DATABASE_URL"])
    schema = "central_migration_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    url = make_url(os.environ["CENTRAL_TEST_DATABASE_URL"]).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    settings = Settings(
        _env_file=None, central_database_url=url.render_as_string(hide_password=False)
    )
    monkeypatch.setattr(central_config, "get_settings", lambda: settings)
    cfg = Config(str(Path(__file__).resolve().parents[2] / "apps/central/alembic.ini"))
    engine = create_engine(url)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        command.downgrade(cfg, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_expired_pin_lock_restores_three_attempts_across_bindings(central):
    client, app = central
    located = client.post(
        "/internal/v1/identity/locate",
        headers=headers(),
        json={"document_type": "CC", "document_number": "10000001"},
    ).json()
    for index, status in enumerate((401, 401, 423)):
        body = {
            "candidate_reference": located["candidate_reference"],
            "pin": "0000",
            "binding_ref": str(uuid.uuid4()),
            "source_message_id": f"first-{index}",
        }
        assert (
            client.post("/internal/v1/identity/verify", headers=headers(), json=body).status_code
            == status
        )
    with app.state.session_factory.begin() as db:
        for session in db.scalars(select(IdentitySession)):
            if session.locked_until:
                session.locked_until = utcnow() - timedelta(seconds=1)
    for index, status in enumerate((401, 401, 423)):
        body = {
            "candidate_reference": located["candidate_reference"],
            "pin": "0000",
            "binding_ref": str(uuid.uuid4()),
            "source_message_id": f"after-expiry-{index}",
        }
        assert (
            client.post("/internal/v1/identity/verify", headers=headers(), json=body).status_code
            == status
        )


def test_unpaid_order_expiry_blocks_capability_and_projects_expired_to_owner(central):
    from unittest.mock import patch

    import central.orders as order_module

    client, app = central
    grant = auth(client)
    value = order(client, grant)
    with patch.object(order_module, "utcnow", return_value=utcnow() + timedelta(minutes=31)):
        private = client.get(f"/internal/v1/orders/{value['id']}", headers=headers(grant))
        assert private.status_code == 200 and private.json()["status"] == "vencida"
        public = client.get(
            f"/internal/v1/orders/{value['id']}",
            headers=headers(),
            params={"capability": value["capability"]},
        )
        assert public.status_code == 410


def test_clean_seed_uses_eight_digit_documents_and_stable_customer_ids(central):
    import re

    _, app = central
    expected = {
        "ana": ("10000001", "Ana Martínez López", "3c6045ba-2f74-5954-bf0b-554e0fb35a82"),
        "bruno": ("10000002", "Bruno Torres Gómez", "aa02c859-7209-5383-8da7-e1b630d4d348"),
        "pagado": ("10000003", "Carla Rojas Díaz", "73e4baa4-9114-542a-a1ca-786a2149721f"),
        "cambiado": ("10000004", "Diego Castro Ruiz", "63f8d212-6057-5935-add1-ab6246527574"),
    }
    mora_names = [
        "Mariana Vargas Ruiz",
        "Pablo Herrera León",
        "Lucía Mendoza Ríos",
        "Santiago Ramírez Soto",
        "Valentina Suárez Gil",
        "Andrés Morales Vega",
        "Camila Ortiz Peña",
        "Daniel Navarro Cruz",
        "Sofía Medina Lara",
    ]
    with app.state.session_factory() as db:
        people = list(db.scalars(select(Customer)))
        assert len(people) == 13
        assert all(re.fullmatch(r"[0-9]{8}", person.document_number) for person in people)
        for key, (document, name, ident) in expected.items():
            person = db.get(Customer, uuid.UUID(ident))
            assert str(fixture_id(key)) == ident
            assert (person.document_number, person.display_name) == (document, name)
            assert check_pin("2468", person.pin_hash)
        for days, name in zip((0, 29, 30, 59, 60, 89, 90, 119, 120), mora_names, strict=True):
            person = db.get(Customer, fixture_id(f"mora-{days}"))
            assert person.document_number == str(20000000 + days)
            assert person.display_name == name
        assert db.get(Debt, fixture_id("ana-hogar")).contract_reference == "DEMO-ANA-HOGAR"
        assert db.get(Debt, fixture_id("ana-telefonia")).balance_cents == 6000


def test_global_catalogs_are_operator_only_complete_sorted_and_minimal(central):
    client, app = central
    grant = auth(client)
    with app.state.session_factory.begin() as db:
        base = db.get(Customer, fixture_id("ana"))
        extra = Customer(
            id=uuid.uuid4(),
            document_type="PAS",
            document_number="30000001",
            display_name="Zulma Herrera León",
            phone_e164="+15550009901",
            pin_hash=base.pin_hash,
        )
        db.add(extra)
        db.flush()
        db.add(
            Debt(
                customer_id=extra.id,
                contract_reference="TEST-CATALOG-EXTRA",
                service_type="electricidad",
                original_cents=4200,
                balance_cents=4200,
                due_date=db.get(Debt, fixture_id("ana-hogar")).due_date,
                dias_mora=120,
                debt_status="pendiente",
            )
        )
    assert client.get("/internal/v1/catalogs").status_code == 401
    assert client.get("/internal/v1/catalogs", headers=headers(grant)).status_code == 403
    filtered = client.get(
        "/internal/v1/debts",
        headers=headers(operator=True),
        params={"service_type": "hogar", "page_size": 1},
    ).json()
    assert len(filtered["items"]) == 1 and filtered["items"][0]["service_type"] == "hogar"
    response = client.get("/internal/v1/catalogs", headers=headers(operator=True))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "service_types": ["electricidad", "hogar", "telefonia", "television"],
        "document_types": ["CC", "PAS"],
    }
    assert "30000001" not in response.text and "Zulma" not in response.text



def recovered_quote(client, grant, *, accept=True):
    value = client.post(
        "/internal/v1/agreements/quote", headers=headers(grant, "recover-quote"),
        json={"debt_id": str(fixture_id("bruno-hogar")), "expected_version": 1,
              "offer_amount_usd": "190", "source_message_id": "original-quote"},
    )
    assert value.status_code == 200, value.text
    quoted = value.json()
    if not accept:
        return quoted, None
    response = client.post(
        f"/internal/v1/agreements/{quoted['id']}/accept",
        headers=headers(grant, "recover-accept"),
        json={"expected_version": 1, "source_message_id": "later-confirmation"},
    )
    assert response.status_code == 200, response.text
    return quoted, response.json()


@pytest.mark.parametrize("accepted", [False, True])
def test_agreement_recovered_after_logout_switch_and_reauthentication(central, accepted):
    client, app = central
    binding = str(uuid.uuid4())
    grant = auth(client, "10000002", binding)
    quoted, original_order = recovered_quote(client, grant, accept=accepted)
    response = client.post(
        "/internal/v1/identity/revoke", headers=headers(key="recover-logout"),
        json={"binding_ref": binding},
    )
    assert response.status_code == 200
    assert client.get("/internal/v1/debts", headers=headers(grant)).status_code == 401
    ana = auth(client, binding=binding)
    ana_debts = client.get("/internal/v1/debts", headers=headers(ana)).json()["items"]
    assert all(debt["active_agreement"] is None for debt in ana_debts)
    assert client.get(
        f"/internal/v1/debts/{fixture_id('bruno-hogar')}", headers=headers(ana)
    ).status_code == 404
    fresh = auth(client, "10000002", binding)
    detail = client.get(
        f"/internal/v1/debts/{fixture_id('bruno-hogar')}", headers=headers(fresh)
    )
    recovered = detail.json()["active_agreement"]
    assert recovered["agreement_id"] == quoted["id"]
    assert recovered["status"] == ("aceptado" if accepted else "propuesto")
    assert recovered["offer_cents"] == 19000 and recovered["discount_cents"] == 1000
    assert recovered["expires_at"] == quoted["expires_at"]
    assert recovered["order_id"] == (original_order["id"] if accepted else None)
    listed = client.get("/internal/v1/debts", headers=headers(fresh))
    assert listed.json()["items"][0]["active_agreement"] == recovered
    for response in (detail, listed):
        assert all(secret not in response.text for secret in ("capability", "token_nonce", "grant"))
    # Reads do not create orders, alter the balance, or extend the quote.
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(PaymentOrder)) == int(accepted)
        assert db.get(Debt, fixture_id("bruno-hogar")).balance_cents == 20000
    if not accepted:
        same_message = client.post(
            f"/internal/v1/agreements/{quoted['id']}/accept",
            headers=headers(fresh, "recover-too-early"),
            json={"expected_version": 1, "source_message_id": "original-quote"},
        )
        assert same_message.status_code == 409
        later = client.post(
            f"/internal/v1/agreements/{quoted['id']}/accept",
            headers=headers(fresh, "recover-later"),
            json={"expected_version": 1, "source_message_id": "fresh-confirmation"},
        )
        assert later.status_code == 200
    else:
        # The recovered reference pays the original terms, without another discount.
        receipt = pay(client, original_order)
        assert receipt.status_code == 200
        assert receipt.json()["received_cents"] == 19000
        assert receipt.json()["forgiven_cents"] == 1000
        assert client.get(
            f"/internal/v1/debts/{fixture_id('bruno-hogar')}", headers=headers(fresh)
        ).json()["active_agreement"] is None


@pytest.mark.parametrize("invalid", ["expiry", "version", "balance", "owner", "status"])
def test_recovery_omits_ineligible_agreements(central, invalid):
    client, app = central
    grant = auth(client, "10000002")
    quoted, _ = recovered_quote(client, grant)
    with app.state.session_factory.begin() as db:
        agreement = db.get(Agreement, uuid.UUID(quoted["id"]))
        if invalid == "expiry":
            agreement.expires_at = utcnow() - timedelta(seconds=1)
        elif invalid == "version":
            agreement.debt_version += 1
        elif invalid == "balance":
            db.get(Debt, fixture_id("bruno-hogar")).balance_cents += 1
        elif invalid == "owner":
            agreement.customer_id = fixture_id("ana")
        else:
            agreement.status = "cumplido"
    assert client.get("/internal/v1/debts", headers=headers(grant)).json()["items"][0][
        "active_agreement"
    ] is None


@pytest.mark.parametrize("invalid", ["expiry", "owner", "version", "balance", "status"])
def test_recovery_never_reuses_invalid_order_or_replaces_it(central, invalid):
    client, app = central
    grant = auth(client, "10000002")
    quoted, value = recovered_quote(client, grant)
    with app.state.session_factory.begin() as db:
        saved = db.get(PaymentOrder, uuid.UUID(value["id"]))
        if invalid == "expiry":
            saved.expires_at = utcnow() - timedelta(seconds=1)
        elif invalid == "owner":
            saved.customer_id = fixture_id("ana")
        elif invalid == "version":
            saved.base_version += 1
        elif invalid == "balance":
            saved.base_cents += 1
            saved.discount_cents += 1
        else:
            saved.status = "vencida"
    recovered = client.get("/internal/v1/debts", headers=headers(grant)).json()["items"][0][
        "active_agreement"
    ]
    assert recovered["status"] == "aceptado" and recovered["order_id"] is None
    response = client.post(
        f"/internal/v1/agreements/{quoted['id']}/accept",
        headers=headers(grant, "no-replacement"),
        json={"expected_version": 1, "source_message_id": "fresh-confirmation"},
    )
    assert response.status_code == 410
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(PaymentOrder)) == 1



def test_listing_batches_agreement_lookup_and_prefers_accepted_terms(central):
    client, app = central
    grant = auth(client, "10000002")
    quoted, _ = recovered_quote(client, grant)
    # A later proposal must not hide a still valid accepted agreement.
    response = client.post(
        "/internal/v1/agreements/quote", headers=headers(grant, "later-proposal"),
        json={"debt_id": str(fixture_id("bruno-hogar")), "expected_version": 1,
              "offer_amount_usd": "180", "source_message_id": "new-offer"},
    )
    assert response.status_code == 200
    queries = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", capture)
    try:
        result = client.get("/internal/v1/debts", headers=headers(operator=True))
    finally:
        event.remove(app.state.engine, "before_cursor_execute", capture)
    assert result.status_code == 200 and len(result.json()["items"]) == 14
    assert len(queries) == 3  # Count, page, and one agreement/order projection for the page.
    bruno = next(d for d in result.json()["items"] if d["id"] == str(fixture_id("bruno-hogar")))
    assert bruno["active_agreement"]["agreement_id"] == quoted["id"]
