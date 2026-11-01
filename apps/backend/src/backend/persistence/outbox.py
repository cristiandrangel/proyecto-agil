"""External sends are never retried automatically after an ambiguous outcome."""

from datetime import timedelta
from uuid import uuid4

from agil_shared.errors import DomainError
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from backend.integrations.observability import current_trace_context
from backend.persistence.database import get_session_factory
from backend.persistence.models import (
    HumanCase,
    InboxEvent,
    Outbox,
    ResetMetadata,
    VerifiedContext,
    utcnow,
)


class OutboxStore:
    def __init__(self, session_factory=None):
        self.sessions = session_factory or get_session_factory()

    def enqueue(
        self, *, event_id, identity_revision: int, kind: str, payload: dict, operation_key: str
    ) -> Outbox:
        payload = {key: value for key, value in payload.items() if key != "_trace_context"}
        trace_context = current_trace_context()
        if trace_context:
            payload["_trace_context"] = trace_context
        with self.sessions.begin() as session:
            event = session.get(InboxEvent, event_id)
            if event is None:
                raise DomainError("event_not_found", "Source event not found", status=404)
            return self._insert(
                session,
                operation_key=operation_key,
                source_event_id=event.id,
                thread_id=event.thread_id,
                identity_revision=identity_revision,
                account_id=event.account_id,
                inbox_id=event.inbox_id,
                conversation_id=event.conversation_id,
                kind=kind,
                payload_private=payload,
            )

    def enqueue_destination(
        self,
        *,
        operation_key,
        thread_id,
        identity_revision,
        account_id,
        inbox_id,
        conversation_id,
        kind,
        payload,
    ) -> Outbox:
        """For a campaign's already resolved and version-validated binding only."""
        if not isinstance(thread_id, str) or not thread_id:
            raise DomainError("invalid_source_id", "Literal source_id is required")
        with self.sessions.begin() as session:
            return self._insert(
                session,
                operation_key=operation_key,
                thread_id=thread_id,
                identity_revision=identity_revision,
                account_id=str(account_id),
                inbox_id=str(inbox_id),
                conversation_id=str(conversation_id),
                kind=kind,
                payload_private=payload,
            )

    @staticmethod
    def _insert(session, **values):
        session.execute(
            insert(Outbox)
            .values(id=uuid4(), **values)
            .on_conflict_do_nothing(index_elements=["operation_key"])
        )
        existing = session.scalar(
            select(Outbox).where(Outbox.operation_key == values["operation_key"])
        )
        for field, value in values.items():
            actual = getattr(existing, field)
            if field == "payload_private":
                # Retry correlation must not change the business idempotency key.
                # Keep the first persisted parent, even after a worker restart.
                actual = {k: v for k, v in actual.items() if k != "_trace_context"}
                value = {k: v for k, v in value.items() if k != "_trace_context"}
            if actual != value:
                raise DomainError(
                    "outbox_conflict",
                    "Operation key has different content or destination",
                    status=409,
                )
        return existing

    def prepare(
        self, outbox_id, *, pending: bool, identity_revision: int, lease_seconds: int = 60
    ) -> Outbox | None:
        """Call immediately after re-reading pending on THIS row's destination.

        Commits `sending` before the HTTP call. A crash afterwards becomes uncertain,
        never queued. Only reconciliation with a known channel ID may resolve it.
        """
        with self.sessions.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(74210001)"))
            metadata = session.get(ResetMetadata, "demo")
            if metadata is not None and metadata.maintenance_mode:
                return None
            row = session.get(Outbox, outbox_id, with_for_update=True)
            if row is None:
                raise DomainError("outbox_not_found", "Output not found", status=404)
            if row.state == "sending" and row.lease_until <= utcnow():
                row.state = "uncertain"
            if row.state != "queued":
                return None
            for dependency_id in (row.payload_private or {}).get("depends_on", []):
                from uuid import UUID

                dependency = session.get(Outbox, UUID(str(dependency_id)))
                if dependency is None or dependency.state != "sent":
                    return None
            context = session.get(VerifiedContext, row.thread_id)
            stale = identity_revision != row.identity_revision or (
                context is not None and context.identity_revision != row.identity_revision
            )
            controlled = (
                session.scalar(
                    select(HumanCase.id)
                    .where(
                        HumanCase.thread_id == row.thread_id,
                        HumanCase.status.in_(["open", "transferred"]),
                    )
                    .limit(1)
                )
                is not None
            )
            is_bot_message = row.kind not in {
                "private_note",
                "set_open",
                "handoff_note",
                "handoff_status",
            }
            if stale or (
                is_bot_message and (not pending or (controlled and row.kind != "handoff_notice"))
            ):
                row.state = "cancelled"
                return None
            row.state = "sending"
            row.attempts += 1
            row.claim_token = uuid4()
            row.lease_until = utcnow() + timedelta(seconds=lease_seconds)
            session.flush()
            return row

    def mark_sent(self, outbox_id, channel_message_id: str, *, claim_token=None):
        with self.sessions.begin() as session:
            row = session.get(Outbox, outbox_id, with_for_update=True)
            if row is None:
                raise DomainError("outbox_not_found", "Output not found", status=404)
            if row.state == "sent" and row.channel_message_id == str(channel_message_id):
                return row
            if row.state not in {"sending", "uncertain"} or (
                claim_token is not None and row.claim_token != claim_token
            ):
                raise DomainError("stale_send", "Output cannot be marked sent", status=409)
            row.state = "sent"
            row.channel_message_id = str(channel_message_id)
            row.lease_until = None
            return row

    def mark_uncertain(self, outbox_id, *, claim_token=None):
        with self.sessions.begin() as session:
            row = session.get(Outbox, outbox_id, with_for_update=True)
            if (
                row
                and row.state == "sending"
                and (claim_token is None or row.claim_token == claim_token)
            ):
                row.state = "uncertain"
                row.lease_until = None

    def mark_failed(self, outbox_id, *, claim_token=None):
        """Only when the provider definitively rejected before applying any effect."""
        with self.sessions.begin() as session:
            row = session.get(Outbox, outbox_id, with_for_update=True)
            if (
                row
                and row.state == "sending"
                and (claim_token is None or row.claim_token == claim_token)
            ):
                row.state = "failed"
                row.lease_until = None

    def recover_expired(self):
        with self.sessions.begin() as session:
            return session.execute(
                update(Outbox)
                .where(Outbox.state == "sending", Outbox.lease_until <= utcnow())
                .values(state="uncertain", lease_until=None)
            ).rowcount

    def cancel_thread(self, thread_id: str, *, before_revision: int | None = None):
        with self.sessions.begin() as session:
            query = update(Outbox).where(Outbox.thread_id == thread_id, Outbox.state == "queued")
            if before_revision is not None:
                query = query.where(Outbox.identity_revision < before_revision)
            return session.execute(query.values(state="cancelled")).rowcount

    def queued(self, *, limit=20):
        self.recover_expired()
        with self.sessions() as session:
            return list(
                session.scalars(
                    select(Outbox)
                    .where(Outbox.state == "queued")
                    .order_by(Outbox.created_at, Outbox.id)
                    .limit(limit)
                )
            )
