"""Durable FIFO by literal source_id with bounded retry and fenced leases."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from agil_shared.errors import DomainError
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from backend.persistence.database import get_session_factory
from backend.persistence.models import ConversationJob, InboxEvent, ResetMetadata, utcnow


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    event_id: UUID
    thread_id: str
    claim_token: UUID
    attempts: int
    event: InboxEvent


def validate_source_id(source_id: str) -> str:
    if not isinstance(source_id, str) or not source_id:
        raise DomainError("invalid_source_id", "A nonempty literal source_id is required")
    return source_id


@contextmanager
def thread_lock(session, thread_id: str):
    """Session-level lock held for the whole turn, without an idle transaction.

    Hashing addresses PostgreSQL locks ONLY; memory still uses the literal key.
    A dedicated connection prevents application rollbacks from leaking pool locks.
    """
    validate_source_id(thread_id)
    with session.get_bind().engine.connect() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(hashtextextended(:thread, 7421))"),
            {"thread": thread_id},
        ).scalar_one()
        connection.commit()
        if not acquired:
            raise DomainError(
                "thread_busy", "Thread is already processing", status=409, retryable=True
            )
        try:
            yield
        finally:
            try:
                connection.rollback()
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:thread, 7421))"),
                    {"thread": thread_id},
                )
                connection.commit()
            except Exception:
                # A broken connection must be closed, never returned with a session lock.
                connection.invalidate()
                raise


class Queue:
    def __init__(self, session_factory=None, *, max_attempts: int = 3):
        self.sessions = session_factory or get_session_factory()
        self.max_attempts = max_attempts

    def enqueue(
        self,
        *,
        account_id: str,
        inbox_id: str,
        message_id: str,
        conversation_id: str,
        source_id: str,
        content: str = "",
        attachments: list | None = None,
        identity_revision: int = 0,
    ) -> tuple[InboxEvent, bool]:
        """Content must already have PINs/secrets removed by ingress."""
        validate_source_id(source_id)
        with self.sessions.begin() as session:
            event_id = uuid4()
            inserted = session.execute(
                insert(InboxEvent)
                .values(
                    id=event_id,
                    account_id=str(account_id),
                    inbox_id=str(inbox_id),
                    message_id=str(message_id),
                    conversation_id=str(conversation_id),
                    thread_id=source_id,
                    normalized_content=content,
                    identity_revision=identity_revision,
                    attachments=attachments or [],
                )
                .on_conflict_do_nothing(index_elements=["account_id", "message_id"])
                .returning(InboxEvent.id)
            ).scalar_one_or_none()
            if inserted is None:
                event = session.scalar(
                    select(InboxEvent).where(
                        InboxEvent.account_id == str(account_id),
                        InboxEvent.message_id == str(message_id),
                    )
                )
                return event, False
            session.add(ConversationJob(event_id=event_id, thread_id=source_id))
            session.flush()
            return session.get(InboxEvent, event_id), True

    def claim(self, worker_id: str, *, lease_seconds: int = 120) -> ClaimedJob | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self.sessions.begin() as session:
            # Serializes short claim transactions; workers process distinct threads concurrently.
            session.execute(text("SELECT pg_advisory_xact_lock(74210001)"))
            metadata = session.get(ResetMetadata, "demo")
            if metadata is not None and metadata.maintenance_mode:
                return None
            now = utcnow()
            expired = session.scalars(
                select(ConversationJob)
                .where(ConversationJob.state == "processing", ConversationJob.lease_until <= now)
                .with_for_update()
            ).all()
            for job in expired:
                job.state = "failed" if job.attempts >= self.max_attempts else "retry"
                job.next_attempt_at = now
                job.claim_token = None
                job.lease_until = None
                job.last_error = "worker_lease_expired"
                session.get(InboxEvent, job.event_id).status = job.state
            session.flush()
            candidates = session.scalars(
                select(ConversationJob)
                .join(InboxEvent, InboxEvent.id == ConversationJob.event_id)
                .where(
                    ConversationJob.state.in_(["queued", "retry"]),
                    ConversationJob.next_attempt_at <= now,
                )
                .order_by(InboxEvent.received_at, InboxEvent.id)
                .with_for_update(of=ConversationJob, skip_locked=True)
            ).all()
            for job in candidates:
                # The earliest outstanding event blocks later events, including during backoff.
                head = session.scalar(
                    select(ConversationJob.id)
                    .join(InboxEvent, InboxEvent.id == ConversationJob.event_id)
                    .where(
                        ConversationJob.thread_id == job.thread_id,
                        ConversationJob.state.in_(["queued", "retry", "processing"]),
                    )
                    .order_by(InboxEvent.received_at, InboxEvent.id)
                    .limit(1)
                )
                if head != job.id:
                    continue
                if not session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtextextended(:thread, 7421))"),
                    {"thread": job.thread_id},
                ).scalar_one():
                    continue
                job.state = "processing"
                job.attempts += 1
                job.claim_token = uuid4()
                job.worker_id = worker_id
                job.lease_until = now + timedelta(seconds=lease_seconds)
                event = session.get(InboxEvent, job.event_id)
                event.status = "processing"
                session.flush()
                return ClaimedJob(
                    job.id, job.event_id, job.thread_id, job.claim_token, job.attempts, event
                )
        return None

    def _owned(self, session, job_id, claim_token):
        job = session.get(ConversationJob, job_id, with_for_update=True)
        if (
            job is None
            or job.state != "processing"
            or job.claim_token != claim_token
            or job.lease_until <= utcnow()
        ):
            raise DomainError("stale_claim", "Worker claim is no longer valid", status=409)
        return job

    def heartbeat(self, job_id, claim_token, *, lease_seconds=120):
        with self.sessions.begin() as session:
            job = self._owned(session, job_id, claim_token)
            job.lease_until = utcnow() + timedelta(seconds=lease_seconds)

    def complete(self, job_id, claim_token):
        with self.sessions.begin() as session:
            job = self._owned(session, job_id, claim_token)
            job.state = "completed"
            job.lease_until = None
            session.get(InboxEvent, job.event_id).status = "completed"

    def fail(self, job_id, claim_token, error: str, *, retryable=True):
        with self.sessions.begin() as session:
            job = self._owned(session, job_id, claim_token)
            job.state = "retry" if retryable and job.attempts < self.max_attempts else "failed"
            job.next_attempt_at = utcnow() + timedelta(seconds=min(60, 2**job.attempts))
            # Error codes only: do not persist raw exception messages with secrets.
            job.last_error = error[:100]
            job.lease_until = None
            job.claim_token = None
            session.get(InboxEvent, job.event_id).status = job.state
