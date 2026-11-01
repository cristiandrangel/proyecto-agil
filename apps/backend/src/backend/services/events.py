"""Durable central-event reconciliation and deduplicated business milestones."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.persistence.database import get_session_factory
from backend.persistence.models import (
    BusinessEvent,
    Campaign,
    CampaignRecipient,
    CentralCursor,
    ChannelBinding,
    utcnow,
)
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert


def as_time(value):
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def as_uuid(value):
    return UUID(str(value)) if value is not None else None


class EventService:
    def __init__(self, central_client=None, session_factory=None, *, consumer="business-events"):
        self.central = central_client
        self.sessions = session_factory or get_session_factory()
        self.consumer = consumer

    @staticmethod
    def _campaign_for(session, customer_id, debt_id, occurred_at):
        rows = session.execute(
            select(CampaignRecipient, Campaign)
            .join(Campaign)
            .where(
                CampaignRecipient.customer_id == customer_id,
                CampaignRecipient.send_status == "sent",
            )
            .order_by(Campaign.launched_at.desc())
        ).all()
        for recipient, campaign in rows:
            if recipient.sent_at is None or occurred_at < recipient.sent_at:
                continue
            limits = [
                value
                for value in (campaign.closed_at, campaign.followup_until)
                if value is not None
            ]
            cutoff = min(limits) if limits else None
            if cutoff is not None and occurred_at > cutoff:
                continue
            if debt_id is not None and str(debt_id) not in recipient.selected_debt_ids:
                continue
            return campaign.id
        return None

    @staticmethod
    def _save(
        session,
        *,
        source_key,
        event_type,
        customer_id,
        debt_id=None,
        occurred_at=None,
        thread_id=None,
        account_id=None,
        inbox_id=None,
        conversation_id=None,
        payload=None,
        campaign_id=None,
    ):
        timestamp = as_time(occurred_at)
        customer_id, debt_id = as_uuid(customer_id), as_uuid(debt_id)
        if customer_id is None:
            return False
        # Attribution uses the customer actually authorized, never a recipient's old identity.
        if campaign_id is None:
            campaign_id = EventService._campaign_for(session, customer_id, debt_id, timestamp)
        return (
            session.execute(
                insert(BusinessEvent)
                .values(
                    id=uuid4(),
                    source_key=source_key,
                    event_type=event_type,
                    campaign_id=as_uuid(campaign_id),
                    customer_id=customer_id,
                    debt_id=debt_id,
                    thread_id=thread_id,
                    account_id=str(account_id) if account_id is not None else None,
                    inbox_id=str(inbox_id) if inbox_id is not None else None,
                    conversation_id=str(conversation_id) if conversation_id is not None else None,
                    occurred_at=timestamp,
                    payload=payload or {},
                )
                .on_conflict_do_nothing(index_elements=["source_key"])
                .returning(BusinessEvent.id)
            ).scalar_one_or_none()
            is not None
        )

    async def record_incoming(self, event):
        """Count a reply to a real campaign without asserting authenticated identity.

        Ingress must already validate incoming/public and channel scope. This mapping
        is exclusively contactability, never a financial customer grant or candidate.
        Chatwoot may expose Phone/BSUID bindings for one sent conversation; matching
        that scoped destination is enough here. Cross-conversation replies still
        require the exact recorded raw source, without rewriting message identity.
        """
        with self.sessions.begin() as session:
            candidates = session.execute(
                select(CampaignRecipient, Campaign)
                .join(Campaign)
                .where(
                    CampaignRecipient.send_status == "sent",
                    CampaignRecipient.delivery_mode == "live",
                    or_(
                        CampaignRecipient.conversation_id == event.conversation_id,
                        CampaignRecipient.thread_id == event.thread_id,
                    ),
                    CampaignRecipient.account_id == event.account_id,
                    CampaignRecipient.inbox_id == event.inbox_id,
                )
                .order_by(Campaign.launched_at.desc())
            ).all()
            for recipient, campaign in candidates:
                if recipient.sent_at is None or event.received_at < recipient.sent_at:
                    continue
                limits = [v for v in (campaign.closed_at, campaign.followup_until) if v is not None]
                if limits and event.received_at > min(limits):
                    continue
                return self._save(
                    session,
                    source_key=f"reply:{event.account_id}:{event.message_id}",
                    event_type="first_response",
                    customer_id=recipient.customer_id,
                    occurred_at=event.received_at,
                    thread_id=event.thread_id,
                    account_id=event.account_id,
                    inbox_id=event.inbox_id,
                    conversation_id=event.conversation_id,
                    campaign_id=campaign.id,
                    payload={"attribution": "channel_recipient_only"},
                )
            return False

    async def record_channel(
        self,
        *,
        source_key,
        event_type,
        customer_id=None,
        debt_id=None,
        occurred_at=None,
        thread_id=None,
        account_id=None,
        inbox_id=None,
        conversation_id=None,
        payload=None,
        campaign_id=None,
    ):
        with self.sessions.begin() as session:
            return self._save(
                session,
                source_key=source_key,
                event_type=event_type,
                customer_id=customer_id,
                debt_id=debt_id,
                occurred_at=occurred_at,
                thread_id=thread_id,
                account_id=account_id,
                inbox_id=inbox_id,
                conversation_id=conversation_id,
                payload=payload,
                campaign_id=campaign_id,
            )

    async def consume_once(self, *, limit=100):
        if self.central is None:
            return 0
        with self.sessions.begin() as session:
            session.execute(
                insert(CentralCursor)
                .values(consumer=self.consumer, last_sequence=0)
                .on_conflict_do_nothing(index_elements=["consumer"])
            )
            after = session.get(CentralCursor, self.consumer).last_sequence
        response = await self.central.request(
            "GET", "/events", params={"after": after, "limit": limit}
        )
        items = response.get("items", [])
        processed = 0
        with self.sessions.begin() as session:
            cursor = session.get(CentralCursor, self.consumer, with_for_update=True)
            for event in sorted(items, key=lambda item: int(item["sequence"])):
                sequence = int(event["sequence"])
                if sequence <= cursor.last_sequence:
                    continue
                if event["event_type"] == "contact_changed" and event.get("customer_id"):
                    for binding in session.scalars(
                        select(ChannelBinding).where(
                            ChannelBinding.customer_id == as_uuid(event["customer_id"])
                        )
                    ):
                        binding.valid = False
                self._save(
                    session,
                    source_key=f"central:{event['id']}",
                    event_type=event["event_type"],
                    customer_id=event.get("customer_id"),
                    debt_id=event.get("debt_id"),
                    occurred_at=event.get("created_at"),
                    payload={
                        **event.get("payload", {}),
                        "order_id": event.get("order_id"),
                        "sequence": sequence,
                    },
                )
                cursor.last_sequence = sequence
                processed += 1
            # Never jump across events not actually saved in this transaction.
        return processed
