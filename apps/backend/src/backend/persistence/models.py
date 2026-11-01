"""Backend-owned operational records; no financial source-of-truth tables."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


class Campaign(Record, Base):
    __tablename__ = "campaign"
    filter_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    template_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followup_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    launch_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    __table_args__ = (CheckConstraint("status IN ('draft','running','completed','closed')"),)


class CampaignRecipient(Record, Base):
    __tablename__ = "campaign_recipient"
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaign.id"))
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    selected_debt_ids: Mapped[list] = mapped_column(JSONB, default=list)
    contact_version: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    delivery_mode: Mapped[str] = mapped_column(String(20), default="simulated")
    destination_binding: Mapped[dict | None] = mapped_column(JSONB)
    account_id: Mapped[str | None] = mapped_column(Text)
    inbox_id: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(Text)
    thread_id: Mapped[str | None] = mapped_column(Text)
    send_status: Mapped[str] = mapped_column(String(20), default="queued")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("campaign_id", "customer_id"),
        UniqueConstraint("campaign_id", "position"),
        CheckConstraint("delivery_mode IN ('simulated','live')"),
        CheckConstraint(
            "send_status IN ('queued','simulated','sent','failed','uncertain','skipped')"
        ),
        Index(
            "uq_active_campaign_person",
            "customer_id",
            unique=True,
            postgresql_where=text("active = true"),
        ),
    )


class ChannelBinding(Record, Base):
    __tablename__ = "channel_binding"
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    contact_version: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[str] = mapped_column(Text)
    inbox_id: Mapped[str] = mapped_column(Text)
    contact_id: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str] = mapped_column(Text)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("customer_id", "contact_version", "account_id", "inbox_id"),)


class InboxEvent(Record, Base):
    __tablename__ = "inbox_event"
    account_id: Mapped[str] = mapped_column(Text)
    inbox_id: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str] = mapped_column(Text)
    thread_id: Mapped[str] = mapped_column(Text)
    normalized_content: Mapped[str] = mapped_column(Text, default="")
    identity_revision: Mapped[int] = mapped_column(Integer, default=0)
    attachments: Mapped[list] = mapped_column(JSONB, default=list)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    __table_args__ = (
        UniqueConstraint("account_id", "message_id"),
        CheckConstraint("length(thread_id) > 0"),
    )


class ConversationJob(Record, Base):
    __tablename__ = "conversation_job"
    event_id: Mapped[UUID] = mapped_column(ForeignKey("inbox_event.id"), unique=True)
    thread_id: Mapped[str] = mapped_column(Text, index=True)
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None] = mapped_column(Uuid)
    worker_id: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','processing','retry','completed','failed','cancelled')"
        ),
    )


class VerifiedContext(Base):
    __tablename__ = "verified_context"
    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    identity_revision: Mapped[int] = mapped_column(Integer, default=0)
    candidate_reference: Mapped[str | None] = mapped_column(Text)
    challenge_state: Mapped[str] = mapped_column(String(30), default="none")
    binding_ref: Mapped[UUID] = mapped_column(Uuid, default=uuid4, unique=True)
    customer_id: Mapped[UUID | None] = mapped_column(Uuid)
    central_grant: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    selected_debt_id: Mapped[UUID | None] = mapped_column(Uuid)


class Outbox(Record, Base):
    __tablename__ = "outbox"
    operation_key: Mapped[str] = mapped_column(Text, unique=True)
    source_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("inbox_event.id"))
    thread_id: Mapped[str] = mapped_column(Text, index=True)
    identity_revision: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[str] = mapped_column(Text)
    inbox_id: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))
    payload_private: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    channel_message_id: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None] = mapped_column(Uuid)
    __table_args__ = (
        CheckConstraint("state IN ('queued','sending','sent','uncertain','cancelled','failed')"),
    )


class HumanCase(Record, Base):
    __tablename__ = "human_case"
    thread_id: Mapped[str] = mapped_column(Text, index=True)
    account_id: Mapped[str] = mapped_column(Text)
    inbox_id: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str] = mapped_column(Text)
    source_event_id: Mapped[UUID] = mapped_column(ForeignKey("inbox_event.id"))
    customer_id: Mapped[UUID | None] = mapped_column(Uuid)
    debt_id: Mapped[UUID | None] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(40))
    offer_cents: Mapped[int | None] = mapped_column(BigInteger)
    verification_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    open_observed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("source_event_id", "origin"),)


class BusinessEvent(Record, Base):
    __tablename__ = "business_event"
    source_key: Mapped[str] = mapped_column(Text, unique=True)
    event_type: Mapped[str] = mapped_column(String(50))
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaign.id"))
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    debt_id: Mapped[UUID | None] = mapped_column(Uuid)
    thread_id: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[str | None] = mapped_column(Text)
    inbox_id: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InferenceReservation(Record, Base):
    __tablename__ = "inference_reservation"
    operation_key: Mapped[str] = mapped_column(Text, unique=True)
    turn_id: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(Text)
    price_version: Mapped[str] = mapped_column(Text)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    state: Mapped[str] = mapped_column(String(20), default="reserved")
    provider_response_id: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("reserved_usd > 0"),
        CheckConstraint("actual_usd IS NULL OR actual_usd >= 0"),
        CheckConstraint("state IN ('reserved','settled','uncertain')"),
    )


class CentralCursor(Base):
    __tablename__ = "central_cursor"
    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(BigInteger, default=0)


class ResetMetadata(Base):
    __tablename__ = "reset_metadata"
    key: Mapped[str] = mapped_column(Text, primary_key=True, default="demo")
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    event_cutoff: Mapped[int] = mapped_column(BigInteger, default=0)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    reset_operation_key: Mapped[str | None] = mapped_column(Text)
    reset_stage: Mapped[str | None] = mapped_column(String(40))
    reset_result: Mapped[dict | None] = mapped_column(JSONB)


class ChannelDeliveryEvent(Record, Base):
    """Minimal signed delivery receipt; never raw webhook content or a conversation job."""

    __tablename__ = "channel_delivery_event"
    account_id: Mapped[str] = mapped_column(Text)
    inbox_id: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(20))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    outbox_id: Mapped[UUID | None] = mapped_column(ForeignKey("outbox.id", ondelete="CASCADE"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_reason: Mapped[str | None] = mapped_column(String(60))
    __table_args__ = (
        UniqueConstraint("account_id", "message_id", "delivery_status"),
        CheckConstraint("delivery_status IN ('unknown','delivered','read','failed')"),
        Index("ix_channel_delivery_pending", "processed_at", "received_at"),
    )
