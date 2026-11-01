from datetime import timedelta
from uuid import uuid4

import pytest
import test_campaigns
from backend.persistence.models import (
    BusinessEvent,
    Campaign,
    CampaignRecipient,
    CentralCursor,
    utcnow,
)
from backend.services.events import EventService
from backend.services.metrics import MetricsService
from sqlalchemy import select

campaign_store = test_campaigns.campaign_store


async def real_cohort(sessions):
    now = utcnow()
    with sessions.begin() as session:
        campaign = Campaign(
            filter_snapshot={},
            template_snapshot={},
            status="completed",
            launched_at=now - timedelta(minutes=5),
            followup_until=now + timedelta(hours=1),
        )
        session.add(campaign)
        session.flush()
        people = [uuid4(), uuid4(), uuid4()]
        debts = [uuid4(), uuid4(), uuid4()]
        for pos, (person, debt) in enumerate(zip(people, debts, strict=True)):
            session.add(
                CampaignRecipient(
                    campaign_id=campaign.id,
                    customer_id=person,
                    selected_debt_ids=[str(debt)],
                    contact_version=1,
                    position=pos,
                    delivery_mode="simulated" if pos == 2 else "live",
                    send_status="simulated" if pos == 2 else "sent",
                    sent_at=now - timedelta(minutes=2) if pos != 2 else None,
                    destination_binding={"debt_balances": {str(debt): 10000}},
                    active=True,
                )
            )
        return campaign.id, people, debts


@pytest.mark.asyncio
async def test_metrics_real_cohort_dedup_money_agreement_and_human_milestones(campaign_store):
    campaign_id, people, debts = await real_cohort(campaign_store)
    service = EventService(session_factory=campaign_store)

    async def record(key, kind, person=0, debt=True, payload=None):
        return await service.record_channel(
            source_key=key,
            event_type=kind,
            customer_id=people[person],
            debt_id=debts[person] if debt else None,
            payload=payload,
        )

    assert await record("response", "first_response", debt=False)
    assert not await record("response", "first_response", debt=False)
    await record("delivered", "delivered", debt=False)
    await record("quote", "agreement_quoted", payload={"agreement_id": "agreement"})
    await record("accept", "agreement_accepted", payload={"agreement_id": "agreement"})
    await record(
        "paid",
        "payment_applied",
        payload={
            "order_id": "order",
            "settlement_id": "settlement",
            "agreement_id": "agreement",
            "received_cents": 9000,
            "forgiven_cents": 1000,
        },
    )
    # A second publication of the same settlement cannot add money again.
    await record(
        "paid-again",
        "payment_applied",
        payload={
            "order_id": "order",
            "settlement_id": "settlement",
            "agreement_id": "agreement",
            "received_cents": 9000,
            "forgiven_cents": 1000,
        },
    )
    await record("human", "human_requested", person=1, debt=False)
    await record("automatic", "automatic_escalation", person=1, debt=False)
    await record("simulated-response", "first_response", person=2, debt=False)
    await record(
        "simulated-pay",
        "payment_applied",
        person=2,
        payload={"received_cents": 999999, "forgiven_cents": 0},
    )
    result = await MetricsService(campaign_store).get(campaign_id)
    assert result["messages_sent"] == 2
    assert result["simulated_sends"] == 1
    assert result["unique_replied"] == 1
    assert result["contactability_pct"] == 50
    assert result["received_cents"] == 9000
    assert result["forgiven_cents"] == 1000
    assert result["outstanding_cents"] == 10000
    assert result["agreements_accepted"] == 1
    assert result["agreements_fulfilled"] == 1
    assert result["human_requests"] == 1
    assert result["automatic_escalations"] == 1
    assert result["ongoing"] == 0


@pytest.mark.asyncio
async def test_preparation_response_wrong_identity_and_post_cut_events_not_attributed(
    campaign_store,
):
    campaign_id, people, debts = await real_cohort(campaign_store)
    service = EventService(session_factory=campaign_store)
    await service.record_channel(
        source_key="before-send",
        event_type="first_response",
        customer_id=people[0],
        occurred_at=utcnow() - timedelta(minutes=4),
    )
    await service.record_channel(
        source_key="wrong-person", event_type="first_response", customer_id=uuid4()
    )
    await service.record_channel(
        source_key="wrong-debt",
        event_type="payment_applied",
        customer_id=people[0],
        debt_id=uuid4(),
        payload={"received_cents": 20000},
    )
    with campaign_store.begin() as session:
        campaign = session.get(Campaign, campaign_id)
        campaign.status = "closed"
        campaign.closed_at = utcnow()
    await service.record_channel(
        source_key="after-close",
        event_type="first_response",
        customer_id=people[1],
        occurred_at=utcnow() + timedelta(seconds=1),
    )
    result = await MetricsService(campaign_store).get(campaign_id)
    assert result["unique_replied"] == 0
    assert result["received_cents"] == 0
    assert result["no_result_closed"] == 0
    assert result["no_response"] == 2
    assert result["ongoing"] == 0


@pytest.mark.asyncio
async def test_central_reconciliation_cursor_and_records_commit_atomically(campaign_store):
    campaign_id, people, debts = await real_cohort(campaign_store)
    event_id = str(uuid4())

    class Central:
        async def request(self, method, path, **kwargs):
            return {
                "items": [
                    {
                        "id": event_id,
                        "sequence": 1,
                        "event_type": "payment_applied",
                        "customer_id": str(people[0]),
                        "debt_id": str(debts[0]),
                        "created_at": utcnow().isoformat(),
                        "payload": {"received_cents": 10000, "forgiven_cents": 0},
                    }
                ],
                "next_cursor": 100,
            }

    service = EventService(Central(), campaign_store)
    assert await service.consume_once() == 1
    assert await service.consume_once() == 0
    with campaign_store() as session:
        assert session.get(CentralCursor, "business-events").last_sequence == 1
        assert len(session.scalars(select(BusinessEvent)).all()) == 1
    result = await MetricsService(campaign_store).get(campaign_id)
    assert result["paid_full_without_discount"] == 1
    assert result["received_cents"] == 10000


@pytest.mark.asyncio
async def test_incoming_contactability_uses_channel_recipient_without_identity_grant(
    campaign_store,
):
    from backend.persistence.models import InboxEvent, VerifiedContext

    campaign_id, people, debts = await real_cohort(campaign_store)
    with campaign_store.begin() as session:
        recipient = session.scalar(
            select(CampaignRecipient).where(CampaignRecipient.customer_id == people[0])
        )
        recipient.thread_id, recipient.account_id, recipient.inbox_id = "  +raw:id  ", "a", "i"
        event = InboxEvent(
            account_id="a",
            inbox_id="i",
            message_id="reply",
            conversation_id="new-conversation",
            thread_id="  +raw:id  ",
            normalized_content="redacted PIN",
            attachments=[],
        )
        session.add(event)
        session.flush()
    service = EventService(session_factory=campaign_store)
    assert await service.record_incoming(event)
    assert not await service.record_incoming(event)
    with campaign_store() as session:
        assert session.get(VerifiedContext, event.thread_id) is None
    assert (await MetricsService(campaign_store).get(campaign_id))["unique_replied"] == 1


@pytest.mark.asyncio
async def test_active_human_and_expired_agreement_are_current_results_not_milestones(
    campaign_store,
):
    from backend.persistence.models import HumanCase, InboxEvent

    campaign_id, people, debts = await real_cohort(campaign_store)
    events = EventService(session_factory=campaign_store)
    for person in people[:2]:
        await events.record_channel(
            source_key=f"reply:{person}", event_type="first_response", customer_id=person
        )
    await events.record_channel(
        source_key="accepted",
        event_type="agreement_accepted",
        customer_id=people[1],
        debt_id=debts[1],
        payload={
            "agreement_id": "expired",
            "expires_at": (utcnow() - timedelta(minutes=1)).isoformat(),
        },
    )
    await events.record_channel(
        source_key="human-historical", event_type="human_requested", customer_id=people[0]
    )
    with campaign_store.begin() as session:
        source = InboxEvent(
            account_id="a",
            inbox_id="i",
            message_id="human",
            conversation_id="c",
            thread_id="raw",
            attachments=[],
        )
        session.add(source)
        session.flush()
        case = HumanCase(
            thread_id="raw",
            account_id="a",
            inbox_id="i",
            conversation_id="c",
            source_event_id=source.id,
            customer_id=people[0],
            debt_id=debts[0],
            reason="request",
            origin="cliente",
            status="transferred",
        )
        session.add(case)
        session.flush()
        case_id = case.id
        campaign = session.get(Campaign, campaign_id)
        campaign.status, campaign.closed_at = "closed", utcnow()
    result = await MetricsService(campaign_store).get(campaign_id)
    assert result["human_active"] == 1
    assert result["no_result_closed"] == 1
    assert result["agreements_expired"] == 1
    with campaign_store.begin() as session:
        session.get(HumanCase, case_id).status = "returned"
    result = await MetricsService(campaign_store).get(campaign_id)
    assert result["human_requests"] == 1
    assert result["human_active"] == 0
    assert result["no_result_closed"] == 2
