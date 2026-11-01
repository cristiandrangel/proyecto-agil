"""Real sent cohorts, independent milestones, and current results by debt."""

from uuid import UUID

from agil_shared.errors import DomainError
from backend.persistence.database import get_session_factory
from backend.persistence.models import (
    BusinessEvent,
    Campaign,
    CampaignRecipient,
    HumanCase,
    InboxEvent,
    utcnow,
)
from backend.services.events import as_time
from sqlalchemy import select


class MetricsService:
    def __init__(self, session_factory=None):
        self.sessions = session_factory or get_session_factory()

    async def get(self, campaign_id):
        try:
            ident = UUID(str(campaign_id))
        except (TypeError, ValueError):
            raise DomainError("campaign_not_found", "Campaña no encontrada.", status=404) from None
        with self.sessions() as session:
            campaign = session.get(Campaign, ident)
            if campaign is None:
                raise DomainError("campaign_not_found", "Campaña no encontrada.", status=404)
            recipients = list(
                session.scalars(
                    select(CampaignRecipient).where(CampaignRecipient.campaign_id == ident)
                )
            )
            cutoff = min(
                [utcnow()]
                + [v for v in (campaign.closed_at, campaign.followup_until) if v is not None]
            )
            events = list(
                session.scalars(
                    select(BusinessEvent).where(
                        BusinessEvent.campaign_id == ident, BusinessEvent.occurred_at <= cutoff
                    )
                )
            )
            cases = session.execute(
                select(HumanCase, InboxEvent.received_at)
                .join(InboxEvent, HumanCase.source_event_id == InboxEvent.id)
                .where(InboxEvent.received_at <= cutoff)
            ).all()
        real = {
            str(r.customer_id): r
            for r in recipients
            if r.send_status == "sent" and r.delivery_mode == "live"
        }
        events = [
            e
            for e in events
            if str(e.customer_id) in real
            and (not e.debt_id or str(e.debt_id) in real[str(e.customer_id)].selected_debt_ids)
        ]
        replied = {
            str(e.customer_id)
            for e in events
            if e.event_type in {"first_response", "reply", "response_received"}
        }
        delivered = {str(e.customer_id) for e in events if e.event_type in {"delivered", "read"}}
        failed = {
            str(recipient.customer_id)
            for recipient in recipients
            if recipient.send_status == "failed"
        }
        failed.update(
            str(event.customer_id) for event in events if event.event_type == "delivery_failed"
        )
        balances = {}
        for recipient in real.values():
            for debt, cents in (
                (recipient.destination_binding or {}).get("debt_balances", {}).items()
            ):
                if debt in recipient.selected_debt_ids:
                    balances[debt] = int(cents)
        settlements, agreements, paid_debts = {}, {}, set()
        human_milestones, automatic = set(), set()
        for event in sorted(events, key=lambda e: (e.occurred_at, str(e.id))):
            data, person = event.payload or {}, str(event.customer_id)
            debt = str(event.debt_id) if event.debt_id else None
            if event.event_type == "payment_applied":
                # One settlement per debt in this scope; publication retries cannot add money.
                key = debt or str(
                    data.get("settlement_id") or data.get("order_id") or event.source_key
                )
                settlements[key] = {
                    "received": int(data.get("received_cents", 0)),
                    "forgiven": int(data.get("forgiven_cents", 0)),
                    "agreement_id": data.get("agreement_id"),
                    "person": person,
                }
                if debt:
                    balances[debt] = 0
                    if settlements[key]["forgiven"] == 0:
                        paid_debts.add(debt)
            if event.event_type in {
                "agreement_quoted",
                "agreement_accepted",
                "agreement_fulfilled",
                "agreement_expired",
            }:
                key = str(data.get("agreement_id") or debt or event.source_key)
                old = agreements.get(key, {})
                states = {
                    "agreement_quoted": "quoted",
                    "agreement_accepted": "accepted",
                    "agreement_fulfilled": "fulfilled",
                    "agreement_expired": "expired",
                }
                agreements[key] = {
                    "state": states[event.event_type],
                    "accepted": old.get("accepted", False)
                    or event.event_type in {"agreement_accepted", "agreement_fulfilled"},
                    "debt_id": debt,
                    "person": person,
                    "expires_at": data.get("expires_at") or old.get("expires_at"),
                }
            if event.event_type in {"human_requested", "human_request"}:
                human_milestones.add(person)
            if event.event_type in {"automatic_escalation", "escalated"}:
                automatic.add(person)
            if event.event_type == "debt_adjusted" and debt:
                balances[debt] = int(data.get("balance_cents", balances.get(debt, 0)))
                for agreement in agreements.values():
                    if agreement["debt_id"] == debt and agreement["state"] in {
                        "quoted",
                        "accepted",
                    }:
                        agreement["state"] = "expired"
        for key, agreement in agreements.items():
            payment = settlements.get(agreement["debt_id"])
            if payment:
                agreement["state"] = (
                    "fulfilled"
                    if str(payment.get("agreement_id")) == key and payment["forgiven"] > 0
                    else "expired"
                )
            elif (
                agreement["expires_at"]
                and as_time(agreement["expires_at"]) <= cutoff
                and agreement["state"] in {"quoted", "accepted"}
            ):
                agreement["state"] = "expired"
        active_cases = []
        for case, created_at in cases:
            person = str(case.customer_id) if case.customer_id else None
            recipient = real.get(person)
            if recipient is None or recipient.sent_at is None or created_at < recipient.sent_at:
                continue
            if case.status in {"open", "transferred"}:
                active_cases.append(case)
        closed = campaign.status == "closed" or (
            campaign.followup_until is not None and utcnow() >= campaign.followup_until
        )
        outcomes, categories = [], {}
        for person, recipient in real.items():
            for debt in recipient.selected_debt_ids:
                if debt in settlements:
                    category = (
                        "paid_full" if settlements[debt]["forgiven"] == 0 else "agreement_fulfilled"
                    )
                elif any(
                    str(c.customer_id) == person and (c.debt_id is None or str(c.debt_id) == debt)
                    for c in active_cases
                ):
                    category = "human_active"
                elif any(
                    a["debt_id"] == debt and a["accepted"] and a["state"] == "accepted"
                    for a in agreements.values()
                ):
                    category = "agreement_pending"
                elif person not in replied:
                    category = "no_response"
                elif closed:
                    category = "no_result_closed"
                else:
                    category = "ongoing"
                outcomes.append({"customer_id": person, "debt_id": debt, "category": category})
                categories.setdefault(category, set()).add(person)
        total = len(recipients)
        processed = sum(r.send_status != "queued" for r in recipients)
        return {
            "campaign_id": str(ident),
            "as_of": cutoff.isoformat(),
            "cohort": {
                "scope": "real_sent",
                "persons": len(real),
                "debt_count": len(balances),
                "amounts_currency": "USD",
            },
            "recipients_total": total,
            "recipients_processed": processed,
            "recipients_pending": total - processed,
            "simulated_sends": sum(r.send_status == "simulated" for r in recipients),
            "messages_sent": len(real),
            "delivered_known": len(delivered),
            "failed": len(failed),
            "uncertain": sum(r.send_status == "uncertain" for r in recipients),
            "skipped": sum(r.send_status == "skipped" for r in recipients),
            "unique_sent": len(real),
            "unique_replied": len(replied),
            "contactability_pct": round(len(replied) * 100 / len(real), 2) if real else None,
            "paid_full_without_discount": len(paid_debts),
            "agreements_accepted": sum(a["accepted"] for a in agreements.values()),
            "agreements_pending": sum(
                a["accepted"] and a["state"] == "accepted" for a in agreements.values()
            ),
            "agreements_fulfilled": sum(
                a["accepted"] and a["state"] == "fulfilled" for a in agreements.values()
            ),
            "agreements_expired": sum(
                a["accepted"] and a["state"] == "expired" for a in agreements.values()
            ),
            "human_requests": len(human_milestones),
            "automatic_escalations": len(automatic),
            "human_active": len(categories.get("human_active", set())),
            "ongoing": len(categories.get("ongoing", set())),
            "no_response": len(categories.get("no_response", set())),
            "no_result_closed": len(categories.get("no_result_closed", set())),
            "outcomes_by_debt": outcomes,
            "unique_persons_by_category": {k: len(v) for k, v in categories.items()},
            "received_cents": sum(s["received"] for s in settlements.values()),
            "forgiven_cents": sum(s["forgiven"] for s in settlements.values()),
            "outstanding_cents": sum(balances.values()),
        }
