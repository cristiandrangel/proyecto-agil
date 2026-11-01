"""Scope delivery evidence to an exact accepted campaign message, without inference."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from agil_shared.errors import DomainError
from backend.persistence.database import get_session_factory
from backend.persistence.models import CampaignRecipient, ChannelDeliveryEvent, Outbox, utcnow
from backend.services.events import EventService
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

STATUS = {0: "sent", 1: "delivered", 2: "read", 3: "failed"}
OPERATION = re.compile(r"campaign:([0-9a-f-]{36}):recipient:([0-9a-f-]{36})\Z")


def exact_status(body):
    """Installed AgentBot payload lacks top-level status; nested last message must match."""
    raw = body.get("status")
    exact = None
    conversation = body.get("conversation") or {}
    messages = conversation.get("messages") or []
    if not isinstance(messages, list):
        messages = []
    for message in messages:
        if (
            isinstance(message, dict)
            and type(message.get("id")) is int
            and message["id"] == body["id"]
        ):
            exact = message
            for field, allowed in (
                ("account_id", body["account"]["id"]),
                ("inbox_id", body["inbox"]["id"]),
                ("conversation_id", conversation["id"]),
            ):
                if message.get(field) is not None and str(message[field]) != str(allowed):
                    raise DomainError(
                        "delivery_scope_mismatch",
                        "El estado del mensaje no corresponde al canal.",
                        403,
                    )
            break
    if raw is None and exact is not None:
        raw = exact.get("status")
    status = STATUS.get(raw) if type(raw) is int else raw
    if not isinstance(status, str) or status not in {"sent", "delivered", "read", "failed"}:
        status = "unknown"
    # Message.created_at is NOT a delivery timestamp. Use an exact status update
    # timestamp when present, otherwise the receipt time (never original creation).
    timestamp = body.get("updated_at") or (exact or {}).get("updated_at")
    try:
        occurred = (
            datetime.fromtimestamp(timestamp, timezone.utc)
            if type(timestamp) in {int, float}
            else datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        )
        if occurred.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError, OverflowError, AttributeError):
        occurred = utcnow()
    return status, occurred


class DeliveryService:
    def __init__(self, session_factory=None):
        self.sessions = session_factory or get_session_factory()

    def record(self, body):
        conversation = body.get("conversation") or {}
        if (
            type(body.get("id")) is not int
            or body["id"] <= 0
            or type(conversation.get("id")) is not int
            or conversation["id"] <= 0
        ):
            raise DomainError(
                "invalid_delivery_event", "Identificador de estado de mensaje inválido.", 422
            )
        # Scope was authenticated/validated in ingress; copy only required IDs.
        account, inbox = str(body["account"]["id"]), str(body["inbox"]["id"])
        status, occurred_at = exact_status(body)
        if status == "sent":
            return {"accepted": False, "reason": "not_delivery_change"}
        with self.sessions.begin() as session:
            inserted = session.execute(
                insert(ChannelDeliveryEvent)
                .values(
                    id=uuid4(),
                    account_id=account,
                    inbox_id=inbox,
                    conversation_id=str(conversation["id"]),
                    message_id=str(body["id"]),
                    delivery_status=status,
                    occurred_at=occurred_at,
                    pending_reason="status_missing"
                    if status == "unknown"
                    else "awaiting_message_mapping",
                )
                .on_conflict_do_nothing(
                    index_elements=["account_id", "message_id", "delivery_status"]
                )
                .returning(ChannelDeliveryEvent.id)
            ).scalar_one_or_none()
            row = session.scalar(
                select(ChannelDeliveryEvent)
                .where(
                    ChannelDeliveryEvent.account_id == account,
                    ChannelDeliveryEvent.message_id == str(body["id"]),
                    ChannelDeliveryEvent.delivery_status == status,
                )
                .with_for_update()
            )
            if row.inbox_id != inbox or row.conversation_id != str(conversation["id"]):
                raise DomainError(
                    "delivery_scope_mismatch", "El estado del mensaje no corresponde al canal.", 403
                )
            self._reconcile(session, row)
            return {
                "accepted": True,
                "duplicate": inserted is None,
                "processed": row.processed_at is not None,
                "pending": row.processed_at is None,
            }

    @staticmethod
    def _reconcile(session, receipt):
        if receipt.processed_at is not None or receipt.delivery_status == "unknown":
            return False
        candidates = list(
            session.scalars(
                select(Outbox).where(
                    Outbox.account_id == receipt.account_id,
                    Outbox.inbox_id == receipt.inbox_id,
                    Outbox.conversation_id == receipt.conversation_id,
                    Outbox.channel_message_id == receipt.message_id,
                    Outbox.kind == "template",
                    Outbox.state == "sent",
                )
            )
        )
        if len(candidates) != 1:
            receipt.pending_reason = (
                "awaiting_message_mapping" if not candidates else "ambiguous_message_mapping"
            )
            return False
        outbox = candidates[0]
        match = OPERATION.fullmatch(outbox.operation_key)
        if not match:
            receipt.pending_reason = "unrecognized_campaign_operation"
            return False
        recipient = session.get(CampaignRecipient, UUID(match[2]))
        if (
            recipient is None
            or str(recipient.campaign_id) != match[1]
            or recipient.delivery_mode != "live"
            or recipient.send_status not in {"sent", "uncertain"}
            or any(
                str(getattr(recipient, field)) != getattr(receipt, field)
                for field in ("account_id", "inbox_id", "conversation_id")
            )
            or recipient.thread_id != outbox.thread_id
        ):
            receipt.pending_reason = "campaign_scope_mismatch"
            return False
        EventService._save(
            session,
            source_key=f"delivery:{receipt.account_id}:{receipt.message_id}:{receipt.delivery_status}",
            event_type="delivery_failed"
            if receipt.delivery_status == "failed"
            else receipt.delivery_status,
            customer_id=recipient.customer_id,
            campaign_id=recipient.campaign_id,
            account_id=receipt.account_id,
            inbox_id=receipt.inbox_id,
            conversation_id=receipt.conversation_id,
            thread_id=outbox.thread_id,
            occurred_at=receipt.occurred_at,
            payload={"channel_message_id": receipt.message_id, "status": receipt.delivery_status},
        )
        receipt.outbox_id = outbox.id
        receipt.processed_at = utcnow()
        receipt.pending_reason = None
        return True

    def reconcile_pending(self, *, limit=100):
        with self.sessions.begin() as session:
            rows = list(
                session.scalars(
                    select(ChannelDeliveryEvent)
                    .where(
                        ChannelDeliveryEvent.processed_at.is_(None),
                        ChannelDeliveryEvent.delivery_status != "unknown",
                    )
                    .order_by(ChannelDeliveryEvent.received_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            return sum(self._reconcile(session, row) for row in rows)
