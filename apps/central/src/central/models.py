import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (
        UniqueConstraint("document_type", "document_number"),
        CheckConstraint("delivery_mode in ('simulated','live')"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_type: Mapped[str] = mapped_column(String(20))
    document_number: Mapped[str] = mapped_column(String(60))
    display_name: Mapped[str] = mapped_column(String(120))
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(200))
    customer_type: Mapped[str] = mapped_column(String(30), default="persona")
    pin_hash: Mapped[str] = mapped_column(String(300))
    delivery_mode: Mapped[str] = mapped_column(String(20), default="simulated")
    test_contact_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    contact_version: Mapped[int] = mapped_column(Integer, default=1)


class Debt(Base):
    __tablename__ = "debt"
    __table_args__ = (
        CheckConstraint("balance_cents >= 0 AND original_cents >= 0 AND dias_mora >= 0"),
        CheckConstraint(
            "(debt_status = 'liquidada' AND balance_cents = 0) OR (debt_status = 'pendiente' AND balance_cents > 0)"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer.id"), index=True)
    contract_reference: Mapped[str] = mapped_column(String(60), unique=True)
    service_type: Mapped[str] = mapped_column(String(50))
    original_cents: Mapped[int] = mapped_column(BigInteger)
    balance_cents: Mapped[int] = mapped_column(BigInteger)
    due_date: Mapped[date] = mapped_column(Date)
    dias_mora: Mapped[int] = mapped_column(Integer)
    debt_status: Mapped[str] = mapped_column(String(20), default="pendiente")
    service_status: Mapped[str] = mapped_column(String(30), default="activo")
    version: Mapped[int] = mapped_column(Integer, default=1)


class IdentitySession(Base):
    __tablename__ = "identity_session"
    __table_args__ = (UniqueConstraint("customer_id", "binding_ref"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer.id"))
    binding_ref: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdentityAttempt(Base):
    __tablename__ = "identity_attempt"
    __table_args__ = (UniqueConstraint("session_id", "source_message_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("identity_session.id"))
    source_message_id: Mapped[str] = mapped_column(String(200))
    success: Mapped[bool] = mapped_column(Boolean)


class Agreement(Base):
    __tablename__ = "agreement"
    __table_args__ = (
        CheckConstraint(
            "offer_cents > 0 AND offer_cents < base_cents AND offer_cents * 100 >= base_cents * 80"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer.id"))
    debt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debt.id"), index=True)
    debt_version: Mapped[int] = mapped_column(Integer)
    base_cents: Mapped[int] = mapped_column(BigInteger)
    offer_cents: Mapped[int] = mapped_column(BigInteger)
    expected_discount_cents: Mapped[int] = mapped_column(BigInteger)
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_message_id: Mapped[str] = mapped_column(String(200))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="propuesto")


class PaymentOrder(Base):
    __tablename__ = "payment_order"
    __table_args__ = (
        CheckConstraint(
            "payable_cents > 0 AND discount_cents >= 0 AND payable_cents + discount_cents = base_cents"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer.id"))
    debt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debt.id"), index=True)
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agreement.id"))
    base_version: Mapped[int] = mapped_column(Integer)
    base_cents: Mapped[int] = mapped_column(BigInteger)
    payable_cents: Mapped[int] = mapped_column(BigInteger)
    discount_cents: Mapped[int] = mapped_column(BigInteger)
    token_nonce: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    receipt_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="vigente")
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)


class PaymentAttempt(Base):
    __tablename__ = "payment_attempt"
    __table_args__ = (CheckConstraint("decision in ('approved','rejected')"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_order.id"))
    decision: Mapped[str] = mapped_column(String(20))
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)


class Settlement(Base):
    __tablename__ = "settlement"
    __table_args__ = (CheckConstraint("received_cents > 0 AND forgiven_cents >= 0"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    debt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("debt.id"), unique=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_order.id"), unique=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_attempt.id"), unique=True)
    received_cents: Mapped[int] = mapped_column(BigInteger)
    forgiven_cents: Mapped[int] = mapped_column(BigInteger)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CentralEvent(Base):
    __tablename__ = "central_event"
    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True)
    event_type: Mapped[str] = mapped_column(String(50))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    debt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommandResult(Base):
    __tablename__ = "command_result"
    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    command_type: Mapped[str] = mapped_column(String(200))
    request_digest: Mapped[str] = mapped_column(String(64))
    result_reference: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdentityCandidate(Base):
    __tablename__ = "identity_candidate"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
