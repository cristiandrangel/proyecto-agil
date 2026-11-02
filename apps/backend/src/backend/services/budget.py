"""Global PostgreSQL-backed spending guard. Reset must never delete this ledger."""

from datetime import timedelta
from decimal import ROUND_CEILING, Decimal
from uuid import uuid4

from agil_shared.errors import DomainError
from backend.persistence.database import get_session_factory
from backend.persistence.models import InferenceReservation, ResetMetadata, utcnow
from sqlalchemy import func, select, text

PRECISION = Decimal("0.0000000001")


def usd(value) -> Decimal:
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        raise ValueError("USD amounts must be finite and nonnegative")
    return value.quantize(PRECISION, rounding=ROUND_CEILING)


class BudgetService:
    def __init__(self, session_factory=None, *, limit_usd="10.00", max_active_calls=2):
        self.sessions = session_factory or get_session_factory()
        self.limit_usd = usd(limit_usd)
        self.max_active_calls = max_active_calls
        if self.limit_usd > Decimal("10.00") or max_active_calls > 2 or max_active_calls < 1:
            raise ValueError("The local safety cap is USD 10 and two concurrent calls")

    @staticmethod
    def _lock(session):
        session.execute(text("SELECT pg_advisory_xact_lock(74210002)"))

    @staticmethod
    def _totals(session):
        charged = session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            InferenceReservation.actual_usd, InferenceReservation.reserved_usd
                        )
                    ),
                    0,
                )
            )
        )
        active = session.scalar(
            select(func.count())
            .select_from(InferenceReservation)
            .where(
                InferenceReservation.state.in_(["reserved", "uncertain"]),
                InferenceReservation.lease_until > utcnow(),
            )
        )
        return charged, active

    def reserve(
        self,
        *,
        turn_id: str,
        modality: str,
        model: str,
        price_version: str,
        reserved_usd,
        operation_key: str | None = None,
        lease_seconds: int = 120,
        max_turn_calls: int | None = None,
    ) -> InferenceReservation:
        amount = usd(reserved_usd)
        if not amount or lease_seconds <= 0 or not model or not price_version:
            raise ValueError("Positive reservation/lease and explicit model/price_version required")
        if max_turn_calls is not None and (
            isinstance(max_turn_calls, bool)
            or not isinstance(max_turn_calls, int)
            or not 1 <= max_turn_calls <= 5
        ):
            raise ValueError("Agent turn call cap must be between one and five")
        key = operation_key or str(uuid4())
        with self.sessions.begin() as session:
            self._lock(session)
            existing = session.scalar(
                select(InferenceReservation).where(InferenceReservation.operation_key == key)
            )
            if existing:
                if (
                    existing.turn_id,
                    existing.modality,
                    existing.model,
                    existing.price_version,
                    existing.reserved_usd,
                ) != (str(turn_id), modality, model, price_version, amount):
                    raise DomainError(
                        "reservation_conflict",
                        "Reservation key has different parameters",
                        status=409,
                    )
                return existing
            metadata = session.get(ResetMetadata, "demo")
            if metadata is not None and metadata.maintenance_mode:
                raise DomainError(
                    "maintenance", "Demo reset is in progress", status=503, retryable=True
                )
            if max_turn_calls is not None and modality == "agent":
                calls = session.scalar(
                    select(func.count())
                    .select_from(InferenceReservation)
                    .where(
                        InferenceReservation.turn_id == str(turn_id),
                        InferenceReservation.modality == "agent",
                    )
                )
                if calls >= max_turn_calls:
                    raise DomainError(
                        "turn_call_limit",
                        "The agent reached the durable call limit for this turn",
                        status=429,
                    )
            charged, active = self._totals(session)
            if charged + amount > self.limit_usd:
                raise DomainError(
                    "budget_exhausted", "Local inference budget exhausted", status=429
                )
            if active >= self.max_active_calls:
                raise DomainError(
                    "inference_busy",
                    "Global inference concurrency reached",
                    status=429,
                    retryable=True,
                )
            reservation = InferenceReservation(
                operation_key=key,
                turn_id=str(turn_id),
                modality=modality,
                model=model,
                price_version=price_version,
                reserved_usd=amount,
                lease_until=utcnow() + timedelta(seconds=lease_seconds),
            )
            session.add(reservation)
            session.flush()
            return reservation

    def settle(
        self,
        reservation_id,
        *,
        input_tokens: int,
        output_tokens: int,
        input_per_million,
        output_per_million,
        provider_response_id: str | None = None,
        cached_input_tokens: int = 0,
        cache_write_tokens: int = 0,
        cached_input_per_million=None,
        cache_write_per_million=None,
    ):
        counts = (input_tokens, output_tokens, cached_input_tokens, cache_write_tokens)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        ):
            raise ValueError("Usage tokens must be nonnegative integers")
        ordinary = input_tokens - cached_input_tokens - cache_write_tokens
        if ordinary < 0:
            raise ValueError("Input usage categories must not overlap or exceed total input")
        if (cached_input_tokens and cached_input_per_million is None) or (
            cache_write_tokens and cache_write_per_million is None
        ):
            raise ValueError("Cache usage requires an explicit verified rate")
        actual = usd(
            (
                Decimal(ordinary) * usd(input_per_million)
                + Decimal(cached_input_tokens) * usd(cached_input_per_million or 0)
                + Decimal(cache_write_tokens) * usd(cache_write_per_million or 0)
                + Decimal(output_tokens) * usd(output_per_million)
            )
            / Decimal(1_000_000)
        )
        with self.sessions.begin() as session:
            self._lock(session)
            reservation = session.get(InferenceReservation, reservation_id, with_for_update=True)
            if reservation is None:
                raise DomainError("reservation_not_found", "Reservation does not exist", status=404)
            if reservation.state == "settled":
                if (
                    reservation.input_tokens,
                    reservation.output_tokens,
                    reservation.cached_input_tokens,
                    reservation.cache_write_tokens,
                    reservation.actual_usd,
                    reservation.provider_response_id,
                ) != (
                    input_tokens,
                    output_tokens,
                    cached_input_tokens,
                    cache_write_tokens,
                    actual,
                    provider_response_id,
                ):
                    raise DomainError(
                        "settlement_conflict", "Usage was already settled differently", status=409
                    )
                return reservation
            reservation.actual_usd = actual
            reservation.input_tokens = input_tokens
            reservation.output_tokens = output_tokens
            reservation.cached_input_tokens = cached_input_tokens
            reservation.cache_write_tokens = cache_write_tokens
            reservation.provider_response_id = provider_response_id
            reservation.state = "settled"
            reservation.lease_until = utcnow()
            # Actual usage can exceed the estimate. Record it honestly and block future calls.
            session.flush()
            return reservation

    def settle_amount(self, reservation_id, actual_usd, provider_response_id=None):
        """Duration-priced modalities settle money directly; no invented token usage."""
        actual = usd(actual_usd)
        with self.sessions.begin() as session:
            self._lock(session)
            reservation = session.get(InferenceReservation, reservation_id, with_for_update=True)
            if reservation is None:
                raise DomainError("reservation_not_found", "Reservation does not exist", status=404)
            if reservation.state == "settled":
                if (reservation.actual_usd, reservation.provider_response_id) != (
                    actual,
                    provider_response_id,
                ):
                    raise DomainError(
                        "settlement_conflict", "Usage was already settled differently", status=409
                    )
                return reservation
            reservation.actual_usd = actual
            reservation.provider_response_id = provider_response_id
            reservation.state = "settled"
            reservation.lease_until = utcnow()
            session.flush()
            return reservation

    def mark_uncertain(self, reservation_id):
        with self.sessions.begin() as session:
            self._lock(session)
            reservation = session.get(InferenceReservation, reservation_id, with_for_update=True)
            if reservation is None:
                raise DomainError("reservation_not_found", "Reservation does not exist", status=404)
            if reservation.state != "settled":
                reservation.state = "uncertain"
            return reservation

    def summary(self):
        with self.sessions() as session:
            charged, active = self._totals(session)
            return {
                "charged_usd": charged,
                "remaining_usd": max(Decimal(0), self.limit_usd - charged),
                "active_calls": active,
                "limit_usd": self.limit_usd,
            }
