"""Local scenario reset. Provider consumption and uncertain amounts are immutable."""

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert

from backend.persistence.database import get_session_factory
from backend.persistence.models import (
    BusinessEvent,
    Campaign,
    CampaignRecipient,
    CentralCursor,
    ChannelBinding,
    ChannelDeliveryEvent,
    ConversationJob,
    HumanCase,
    Outbox,
    ResetMetadata,
    VerifiedContext,
    utcnow,
)


def reset_operational(*, event_cutoff: int, session_factory=None, operation_key: str | None = None):
    """Run with workers paused, after checkpoint deletion and central fixture reset.

    InferenceReservation is intentionally not imported or touched. No key mutation.
    Uncertain/sending outbox rows remain for reconciliation, with their source events.
    """
    sessions = session_factory or get_session_factory()
    with sessions.begin() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(74210001)"))
        metadata = session.get(ResetMetadata, "demo", with_for_update=True)
        if (
            operation_key
            and metadata is not None
            and metadata.reset_operation_key == operation_key
            and metadata.reset_stage in {"operational_reset", "completed"}
        ):
            return
        if session.scalar(
            select(ConversationJob.id)
            .where(ConversationJob.state == "processing", ConversationJob.lease_until > utcnow())
            .limit(1)
        ):
            from agil_shared.errors import DomainError

            raise DomainError(
                "reset_busy", "Pause workers and wait for active jobs before reset", status=409
            )
        session.execute(
            update(Outbox)
            .where(Outbox.state == "sending")
            .values(state="uncertain", lease_until=None)
        )
        session.execute(update(Outbox).where(Outbox.state == "queued").values(state="cancelled"))
        # Keep historical inbox/outbox destination references and completed jobs as audit.
        session.execute(
            update(ConversationJob)
            .where(ConversationJob.state.in_(["queued", "retry", "processing"]))
            .values(state="cancelled", claim_token=None, lease_until=None)
        )
        session.execute(delete(VerifiedContext))
        session.execute(delete(HumanCase))
        session.execute(delete(ChannelDeliveryEvent))
        session.execute(delete(BusinessEvent))
        session.execute(delete(CampaignRecipient))
        session.execute(delete(Campaign))
        session.execute(delete(ChannelBinding))
        session.execute(update(CentralCursor).values(last_sequence=event_cutoff))
        session.execute(
            insert(ResetMetadata)
            .values(key="demo", epoch=1, event_cutoff=event_cutoff, reset_at=utcnow())
            .on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "epoch": ResetMetadata.epoch + 1,
                    "event_cutoff": event_cutoff,
                    "reset_at": utcnow(),
                },
            )
        )

        if operation_key:
            metadata = session.get(ResetMetadata, "demo", populate_existing=True)
            metadata.reset_operation_key = operation_key
            metadata.reset_stage = "operational_reset"
