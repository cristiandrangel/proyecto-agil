"""Real PostgreSQL races: no provider calls, no paid resources."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from agil_shared.errors import DomainError
from backend.persistence.models import Base, InferenceReservation, utcnow
from backend.persistence.reset import reset_operational
from backend.services.budget import BudgetService
from sqlalchemy import create_engine, text, update
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def budget_store():
    url = os.getenv("TEST_MEMORY_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_MEMORY_DATABASE_URL for real PostgreSQL budget tests")
    schema = "budget_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(scoped)
    sessions = sessionmaker(scoped, expire_on_commit=False)
    yield sessions
    scoped.dispose()
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


def reserve(service, amount="0.1", **kwargs):
    return service.reserve(
        turn_id="test-turn",
        modality="text",
        model="fixture-model",
        price_version="test-v1",
        reserved_usd=amount,
        **kwargs,
    )


def test_concurrent_global_call_slots(budget_store):
    barrier = Barrier(8)

    def attempt(_):
        service = BudgetService(budget_store)
        barrier.wait()
        try:
            return reserve(service).id
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count("inference_busy") == 6
    assert BudgetService(budget_store).summary()["active_calls"] == 2


def test_concurrent_budget_cutoff_is_atomic(budget_store):
    barrier = Barrier(6)

    def attempt(_):
        barrier.wait()
        try:
            return reserve(BudgetService(budget_store, limit_usd="4.50"), "3.00").id
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert results.count("budget_exhausted") == 5
    assert BudgetService(budget_store, limit_usd="4.50").summary()["charged_usd"] == Decimal("3")


def test_timeout_preserves_amount_and_expired_lease_only_releases_slot(budget_store):
    service = BudgetService(budget_store, limit_usd="4.50")
    first = reserve(service, "2.00")
    second = reserve(service, "2.00")
    service.mark_uncertain(first.id)
    service.mark_uncertain(second.id)
    with pytest.raises(DomainError, match="concurrency"):
        reserve(service, "0.10")
    with budget_store.begin() as session:
        session.execute(
            update(InferenceReservation).values(lease_until=utcnow() - timedelta(seconds=1))
        )
    assert service.summary()["active_calls"] == 0
    assert service.summary()["charged_usd"] == Decimal("4")
    reserve(service, "0.50")
    with pytest.raises(DomainError) as error:
        reserve(service, "0.0001")
    assert error.value.code == "budget_exhausted"


def test_settlement_actual_tokens_and_idempotency(budget_store):
    service = BudgetService(budget_store)
    reservation = reserve(service, "0.50", operation_key="one-call")
    assert reserve(service, "0.50", operation_key="one-call").id == reservation.id
    settled = service.settle(
        reservation.id,
        input_tokens=1000,
        output_tokens=250,
        input_per_million="2",
        output_per_million="8",
        provider_response_id="fixture",
    )
    assert settled.actual_usd == Decimal("0.004")
    assert service.summary()["active_calls"] == 0
    assert service.summary()["charged_usd"] == Decimal("0.004")
    service.settle(
        reservation.id,
        input_tokens=1000,
        output_tokens=250,
        input_per_million="2",
        output_per_million="8",
        provider_response_id="fixture",
    )
    with pytest.raises(DomainError) as error:
        service.settle(
            reservation.id,
            input_tokens=999,
            output_tokens=250,
            input_per_million="2",
            output_per_million="8",
            provider_response_id="fixture",
        )
    assert error.value.code == "settlement_conflict"


def test_reset_does_not_erase_known_or_uncertain_consumption(budget_store):
    service = BudgetService(budget_store)
    paid = reserve(service, "1")
    service.settle(
        paid.id,
        input_tokens=1_000_000,
        output_tokens=0,
        input_per_million="0.75",
        output_per_million="1",
    )
    uncertain = reserve(service, "2")
    service.mark_uncertain(uncertain.id)
    reset_operational(event_cutoff=100, session_factory=budget_store)
    assert service.summary()["charged_usd"] == Decimal("2.75")
    with budget_store() as session:
        assert session.get(InferenceReservation, uncertain.id).state == "uncertain"


def test_underestimated_usage_is_recorded_and_blocks_future_calls(budget_store):
    service = BudgetService(budget_store, limit_usd="4.50")
    reservation = reserve(service, "0.01")
    service.settle(
        reservation.id,
        input_tokens=1_000_000,
        output_tokens=0,
        input_per_million="4.60",
        output_per_million="0",
    )
    assert service.summary()["charged_usd"] == Decimal("4.60")
    with pytest.raises(DomainError) as error:
        reserve(service)
    assert error.value.code == "budget_exhausted"


def test_duration_priced_settlement_and_idempotent_operational_reset(budget_store):
    from backend.persistence.models import ResetMetadata

    service = BudgetService(budget_store)
    reservation = reserve(service, "0.0045")
    settled = service.settle_amount(reservation.id, "0.00225", "audio-fixture")
    assert settled.input_tokens is None
    assert settled.output_tokens is None
    assert service.summary()["charged_usd"] == Decimal("0.00225")
    reset_operational(event_cutoff=10, session_factory=budget_store, operation_key="reset-test")
    reset_operational(event_cutoff=10, session_factory=budget_store, operation_key="reset-test")
    with budget_store() as session:
        assert session.get(ResetMetadata, "demo").epoch == 1
        assert session.get(ResetMetadata, "demo").reset_stage == "operational_reset"
    assert service.summary()["charged_usd"] == Decimal("0.00225")


def test_cache_categories_are_disjoint_durable_and_settlement_is_idempotent(budget_store):
    service = BudgetService(budget_store)
    reservation = reserve(service)
    usage = dict(
        input_tokens=1000,
        output_tokens=250,
        cached_input_tokens=300,
        cache_write_tokens=600,
        input_per_million="0.20",
        cached_input_per_million="0.02",
        cache_write_per_million="0.25",
        output_per_million="1.20",
        provider_response_id="mixed-usage-fixture",
    )
    row = service.settle(reservation.id, **usage)
    assert row.actual_usd == Decimal("0.000476")
    assert (row.cached_input_tokens, row.cache_write_tokens) == (300, 600)
    assert service.settle(reservation.id, **usage).id == row.id
    assert service.summary()["charged_usd"] == Decimal("0.000476")
    with pytest.raises(DomainError) as error:
        service.settle(reservation.id, **{**usage, "cache_write_tokens": 599})
    assert error.value.code == "settlement_conflict"


@pytest.mark.parametrize(
    "usage",
    [
        {"cached_input_tokens": 1001},
        {"cache_write_tokens": 1},
        {"cache_write_tokens": True},
    ],
)
def test_invalid_or_unpriced_cache_usage_never_releases_money(budget_store, usage):
    service = BudgetService(budget_store)
    reservation = reserve(service)
    with pytest.raises(ValueError):
        service.settle(
            reservation.id,
            input_tokens=1000,
            output_tokens=250,
            input_per_million="0.20",
            output_per_million="1.20",
            **usage,
        )
    assert service.summary()["charged_usd"] == Decimal("0.1")
    with budget_store() as session:
        assert session.get(InferenceReservation, reservation.id).state == "reserved"
