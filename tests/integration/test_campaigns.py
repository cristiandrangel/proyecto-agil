import asyncio
import os
from copy import deepcopy
from uuid import uuid4

import pytest
from agil_shared.errors import DomainError
from backend.persistence.models import Base, CampaignRecipient, Outbox
from backend.services.campaigns import CampaignService
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def campaign_store():
    url = os.getenv("TEST_MEMORY_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_MEMORY_DATABASE_URL for real PostgreSQL campaign tests")
    schema = "campaign_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(scoped)
    sessions = sessionmaker(scoped, expire_on_commit=False)
    yield sessions
    scoped.dispose()
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


class FakeCentral:
    def __init__(self, *, live=False):
        self.calls = []
        self.rows = []
        for person in range(2):
            customer_id = str(uuid4())
            for service in range(2 if person == 0 else 1):
                self.rows.append(
                    {
                        "id": str(uuid4()),
                        "customer_id": customer_id,
                        "balance_cents": 10000,
                        "dias_mora": [29, 30, 120][len(self.rows)],
                        "service_type": ["hogar", "telefonia"][service],
                        "debt_status": "pendiente",
                        "customer": {
                            "id": customer_id,
                            "contact_version": 1,
                            "phone_e164": f"+1555000000{person}",
                            "delivery_mode": "live" if live else "simulated",
                            "test_contact_enabled": live,
                        },
                    }
                )

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/debts":
            params = kwargs.get("params", {})
            rows = [
                row
                for row in self.rows
                if row["dias_mora"] >= int(params.get("dias_mora_min", 0))
                and row["dias_mora"] <= int(params.get("dias_mora_max", 100000))
                and (
                    not params.get("service_type") or row["service_type"] == params["service_type"]
                )
            ]
            return {"items": deepcopy(rows), "total": len(rows)}
        if path.startswith("/debts/"):
            return deepcopy(next(row for row in self.rows if row["id"] == path.split("/")[-1]))
        if path == "/events":
            return {"items": [], "next_cursor": kwargs["params"]["after"]}
        raise AssertionError(path)


class FakeChannel:
    def __init__(self, *, timeout=False):
        self.calls = []
        self.timeout = timeout
        self.active = 0
        self.max_active = 0

    async def conversation(self, conversation_id):
        return {"status": "pending", "id": conversation_id}

    async def resolve_contact(self, customer):
        self.calls.append(("resolve", customer["id"]))
        await asyncio.sleep(0)
        return {
            "account_id": "a",
            "inbox_id": "i",
            "contact_id": customer["id"],
            "source_id": "  +opaque:" + customer["id"] + "  ",
            "conversation_id": "conversation-" + customer["id"],
        }

    async def send_template(self, binding, template, operation_key):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.calls.append(("send", operation_key))
        try:
            await asyncio.sleep(0)
            if self.timeout:
                raise TimeoutError("simulated unknown delivery")
            return {"message_id": "message-" + operation_key}
        finally:
            self.active -= 1


async def make_campaign(service, filters=None):
    filters = filters or {}
    preview = await service.preview(filters)
    campaign = await service.create(
        {
            "name": "Fixture campaign",
            "filters": filters,
            "preview_id": preview["preview_id"],
            "template_name": "fixture_template",
            "template_language": "es",
        }
    )
    return await service.launch(campaign["id"], "launch-" + campaign["id"])


@pytest.mark.asyncio
async def test_person_dedup_stable_snapshot_and_simulations_never_touch_channel(campaign_store):
    central, channel = FakeCentral(), FakeChannel()
    service = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(service)
    assert campaign["recipients_total"] == 2
    assert sorted(len(r["debt_ids"]) for r in campaign["recipients"]) == [1, 2]
    await service.dispatch_one()
    resumed = CampaignService(central, campaign_store, channel=channel)
    assert (await resumed.get(campaign["id"]))["recipients_processed"] == 1
    await resumed.dispatch_one()
    assert channel.calls == []
    metrics = await service.metrics(campaign["id"])
    assert metrics["simulated_sends"] == 2
    assert metrics["messages_sent"] == 0
    assert metrics["contactability_pct"] is None


@pytest.mark.asyncio
async def test_mora_buckets_boundaries_and_multiple_services(campaign_store):
    service = CampaignService(FakeCentral(), campaign_store)
    assert (await service.preview({"overdue_bucket": "1-29"}))["recipients_total"] == 1
    result = await service.preview({"overdue_bucket": "30-59", "service_type": "telefonia"})
    assert result["recipients_total"] == 1
    assert result["filters"] == {
        "dias_mora_min": 30,
        "dias_mora_max": 59,
        "service_type": "telefonia",
    }
    assert (await service.preview({"overdue_bucket": "120+"}))["recipients_total"] == 1
    with pytest.raises(DomainError):
        await service.preview({"dias_mora_min": 60, "dias_mora_max": 20})


@pytest.mark.asyncio
async def test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination(
    campaign_store,
):
    central, channel = FakeCentral(live=True), FakeChannel()
    first = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(first)
    same = await first.launch(campaign["id"], "launch-" + campaign["id"])
    assert same["recipients_total"] == 2
    second = CampaignService(central, campaign_store, channel=channel)
    await asyncio.gather(first.dispatch_one(), second.dispatch_one())
    await first.dispatch_one()
    assert channel.max_active == 1
    assert len([call for call in channel.calls if call[0] == "send"]) == 2
    with campaign_store() as session:
        recipients = list(
            session.scalars(
                select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign["id"])
            )
        )
        outbox = list(session.scalars(select(Outbox)))
        assert len(outbox) == 2
        assert all(row.state == "sent" for row in outbox)
        assert {row.conversation_id for row in outbox} == {
            row.conversation_id for row in recipients
        }
        assert all(
            row.thread_id.startswith("  +opaque:") and row.thread_id.endswith("  ")
            for row in outbox
        )


@pytest.mark.asyncio
async def test_changed_contact_is_skipped_and_unknown_delivery_is_not_resent(campaign_store):
    central, channel = FakeCentral(live=True), FakeChannel(timeout=True)
    service = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(service)
    customer = campaign["recipients"][0]["customer_id"]
    for row in central.rows:
        if row["customer_id"] == customer:
            row["customer"]["contact_version"] = 2
    assert (await service.dispatch_one())["status"] == "skipped"
    assert channel.calls == []
    assert (await service.dispatch_one())["status"] == "uncertain"
    assert await service.dispatch_one() is None
    assert len([call for call in channel.calls if call[0] == "send"]) == 1
    with campaign_store() as session:
        assert session.scalar(select(Outbox)).state == "uncertain"


@pytest.mark.asyncio
async def test_active_person_excluded_and_close_stops_pending_dispatch(campaign_store):
    service = CampaignService(FakeCentral(), campaign_store)
    first = await make_campaign(service)
    other = await service.preview({})
    assert all(r["exclusion_reason"] == "active_campaign" for r in other["recipients"])
    await service.close(first["id"])
    assert await service.dispatch_one() is None
    assert (await service.preview({}))["eligible_total"] == 2


@pytest.mark.asyncio
async def test_eligibility_is_rechecked_if_mora_changes_after_preview(campaign_store):
    central, channel = FakeCentral(live=True), FakeChannel()
    service = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(service, {"overdue_bucket": "30-59"})
    assert campaign["recipients_total"] == 1
    for debt in central.rows:
        if debt["dias_mora"] == 30:
            debt["dias_mora"] = 60
    assert (await service.dispatch_one())["status"] == "skipped"
    assert channel.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case_status", ["open", "transferred"])
async def test_active_human_case_blocks_template_even_if_channel_pending(
    campaign_store, case_status
):
    from uuid import UUID

    from backend.persistence.models import HumanCase, InboxEvent

    central, channel = FakeCentral(live=True), FakeChannel()
    service = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(service)
    customer = campaign["recipients"][0]["customer_id"]
    source = "  +opaque:" + customer + "  "
    with campaign_store.begin() as session:
        event = InboxEvent(
            account_id="a",
            inbox_id="i",
            conversation_id="conversation-" + customer,
            message_id="human-fixture",
            thread_id=source,
            normalized_content="safe fixture",
        )
        session.add(event)
        session.flush()
        session.add(
            HumanCase(
                thread_id=source,
                account_id="a",
                inbox_id="i",
                conversation_id=event.conversation_id,
                source_event_id=event.id,
                customer_id=UUID(customer),
                reason="requested",
                origin="agent",
                status=case_status,
            )
        )
    assert (await service.dispatch_one())["status"] == "skipped"
    assert not any(call[0] == "send" for call in channel.calls)
    assert (await service.get(campaign["id"]))["recipients"][0]["reason"] == "human_control"


@pytest.mark.asyncio
async def test_contact_change_during_resolve_excludes_old_destination(campaign_store):
    central, channel = FakeCentral(live=True), FakeChannel()
    original = channel.resolve_contact

    async def changes_contact(customer):
        binding = await original(customer)
        for debt in central.rows:
            if debt["customer_id"] == customer["id"]:
                debt["customer"]["contact_version"] = 2
                debt["customer"]["phone_e164"] = "+15550000999"
        return binding

    channel.resolve_contact = changes_contact
    service = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(service)
    assert (await service.dispatch_one())["status"] == "skipped"
    assert not any(call[0] == "send" for call in channel.calls)
    assert (await service.get(campaign["id"]))["recipients"][0]["reason"] == "contact_changed"


@pytest.mark.asyncio
async def test_busy_literal_thread_defers_campaign_without_sending(campaign_store):
    from backend.persistence.queue import thread_lock

    central, channel = FakeCentral(live=True), FakeChannel()
    service = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(service)
    source = "  +opaque:" + campaign["recipients"][0]["customer_id"] + "  "
    with campaign_store() as session, thread_lock(session, source):
        assert (await service.dispatch_one())["status"] == "deferred"
    assert not any(call[0] == "send" for call in channel.calls)
    assert (await service.get(campaign["id"]))["recipients"][0]["status"] == "queued"
    assert (await service.dispatch_one())["status"] == "sent"


@pytest.mark.asyncio
async def test_campaign_rechecks_pending_and_records_actual_identity_revision(campaign_store):
    from backend.persistence.models import VerifiedContext

    central, channel = FakeCentral(live=True), FakeChannel()
    service = CampaignService(central, campaign_store, channel=channel)
    campaign = await make_campaign(service)
    source = "  +opaque:" + campaign["recipients"][0]["customer_id"] + "  "
    with campaign_store.begin() as session:
        session.add(VerifiedContext(thread_id=source, identity_revision=6))
    assert (await service.dispatch_one())["status"] == "sent"
    with campaign_store() as session:
        sent = session.scalar(select(Outbox).where(Outbox.thread_id == source))
        assert sent.identity_revision == 6

    async def human_conversation(_):
        return {"status": "open"}

    channel.conversation = human_conversation
    assert (await service.dispatch_one())["status"] == "skipped"
    assert len([call for call in channel.calls if call[0] == "send"]) == 1
