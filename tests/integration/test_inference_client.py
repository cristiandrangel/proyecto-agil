"""No provider or Langfuse requests: fake SDKs plus the real PostgreSQL ledger."""

from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_budget
from agil_shared.errors import DomainError
from backend.integrations.observability import Observability, mask_payload
from backend.integrations.openai import InferenceClient
from backend.persistence.models import InferenceReservation
from backend.services.budget import BudgetService
from pydantic import SecretStr
from sqlalchemy import select

budget_store = test_budget.budget_store
PRIVATE = (
    "Authorization: Bearer sk-fictional-secret PIN=519826 grant=private-grant phone=+15551234567"
)


def settings(**overrides):
    values = dict(
        openai_api_key=SecretStr("sk-fictional-secret"),
        openai_timeout_seconds=2,
        openai_agent_model="gpt-5.6-luna",
        openai_vision_model="gpt-5.6-luna",
        openai_transcription_model="gpt-transcribe",
        ai_max_calls_per_turn=5,
        ai_max_input_tokens=12000,
        ai_max_output_tokens=4096,
        ai_vision_max_output_tokens=400,
        openai_agent_reasoning_effort="high",
        openai_vision_reasoning_effort="none",
        audio_max_seconds=60,
        langfuse_enabled=False,
        langfuse_public_key=SecretStr(""),
        langfuse_secret_key=SecretStr(""),
        langfuse_base_url="http://not-used.invalid",
    )
    return SimpleNamespace(**{**values, **overrides})


class FakeLangfuse:
    def __init__(self):
        self.starts, self.updates, self.automatic_errors = [], [], []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.starts.append(kwargs)
        raw = SimpleNamespace(update=lambda **values: self.updates.append(values))
        try:
            yield raw
        except BaseException as error:
            # Mirrors the dangerous default OTEL exception serialization boundary.
            self.automatic_errors.append(str(error))
            raise


class FakeSDK:
    def __init__(self, sessions, *, error=None, usage=True, status="completed", input_details=None):
        self.sessions, self.error, self.usage, self.status = sessions, error, usage, status
        self.input_details = input_details or {"cached_tokens": 0, "cache_write_tokens": 0}
        self.calls = []
        self.responses = SimpleNamespace(create=self.create)
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.transcribe))

    def reserved_before_call(self):
        with self.sessions() as session:
            assert (
                session.scalar(
                    select(InferenceReservation).where(InferenceReservation.state == "reserved")
                )
                is not None
            )

    async def create(self, **kwargs):
        self.reserved_before_call()
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            id="response-fixture",
            status=self.status,
            usage=SimpleNamespace(
                input_tokens=1000, output_tokens=250, input_tokens_details=self.input_details
            )
            if self.usage
            else None,
            output_text=PRIVATE,
        )

    async def transcribe(self, **kwargs):
        self.reserved_before_call()
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=PRIVATE)


def client(sessions, **options):
    cfg = settings(**options.pop("config", {}))
    traces = FakeLangfuse()
    observation = Observability(cfg)
    observation.client = traces
    sdk = FakeSDK(sessions, **options)
    return InferenceClient(cfg, BudgetService(sessions), observation, sdk=sdk), sdk, traces


def assert_no_private_trace(traces):
    output = json.dumps(
        {"starts": traces.starts, "updates": traces.updates, "errors": traces.automatic_errors},
        default=str,
    )
    for private in (
        "sk-fictional-secret",
        "519826",
        "private-grant",
        "+15551234567",
        "Authorization",
        "Bearer",
    ):
        assert private not in output
    assert traces.automatic_errors == []


@pytest.mark.asyncio
async def test_reserves_before_sdk_settles_actual_and_exports_only_usage(budget_store):
    inference, sdk, traces = client(budget_store)
    event_id = uuid4()
    response = await inference.response(
        event_id=event_id,
        input=[{"role": "user", "content": PRIVATE}],
        instructions=PRIVATE,
        tools=[],
    )
    assert response.status == "completed"
    assert sdk.calls[0]["store"] is False
    assert sdk.calls[0]["parallel_tool_calls"] is False
    assert sdk.calls[0]["max_output_tokens"] == 4096
    assert sdk.calls[0]["reasoning"] == {"effort": "high"}
    with budget_store() as session:
        reservation = session.scalar(select(InferenceReservation))
        assert reservation.state == "settled"
        assert reservation.actual_usd == Decimal("0.0005")
        assert reservation.provider_response_id == "response-fixture"
    metadata = traces.updates[-1]["metadata"]
    assert metadata["input_tokens"] == 1000
    assert metadata["output_tokens"] == 250
    assert Decimal(metadata["actual_usd"]) == Decimal("0.0005")
    assert metadata["provider_latency_ms"] >= 0
    assert metadata["latency_ms"] >= 0
    assert any(
        update.get("usage_details") == {"input": 1000, "output": 250, "total": 1250}
        for update in traces.updates
    )
    assert_no_private_trace(traces)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [RuntimeError, TimeoutError])
async def test_sdk_error_sanitized_before_span_exit_and_never_retried(budget_store, kind):
    inference, sdk, traces = client(budget_store, error=kind(PRIVATE))
    with pytest.raises(DomainError) as error:
        await inference.response(
            event_id=uuid4(), input=[{"role": "user", "content": PRIVATE}], instructions=PRIVATE
        )
    assert error.value.code == "inference_failed"
    assert PRIVATE not in str(error.value)
    assert error.value.__suppress_context__
    assert len(sdk.calls) == 1
    with budget_store() as session:
        reservation = session.scalar(select(InferenceReservation))
        assert reservation.state == "uncertain"
        assert reservation.actual_usd is None
        assert reservation.reserved_usd == Decimal("0.0079152")
    assert_no_private_trace(traces)


@pytest.mark.asyncio
async def test_missing_usage_keeps_full_reservation(budget_store):
    inference, sdk, traces = client(budget_store, usage=False)
    with pytest.raises(DomainError) as error:
        await inference.response(event_id=uuid4(), input=[], instructions="fixture")
    assert error.value.code == "usage_unknown"
    assert len(sdk.calls) == 1
    with budget_store() as session:
        assert session.scalar(select(InferenceReservation)).state == "uncertain"
    assert inference.budget.summary()["charged_usd"] == Decimal("0.0079152")
    assert_no_private_trace(traces)


@pytest.mark.asyncio
async def test_incomplete_output_is_settled_but_not_used_as_success(budget_store):
    inference, sdk, traces = client(budget_store, status="incomplete")
    with pytest.raises(DomainError) as error:
        await inference.response(event_id=uuid4(), input=[], instructions="fixture")
    assert error.value.code == "inference_incomplete"
    with budget_store() as session:
        assert session.scalar(select(InferenceReservation)).state == "settled"
    assert traces.updates[-1]["metadata"]["status"] == "incomplete"
    assert_no_private_trace(traces)


@pytest.mark.asyncio
async def test_unknown_price_and_exhausted_budget_do_not_call_sdk(budget_store):
    inference, sdk, traces = client(budget_store, config={"openai_agent_model": "unknown-model"})
    with pytest.raises(DomainError) as error:
        await inference.response(event_id=uuid4(), input=[], instructions="fixture")
    assert error.value.code == "model_price_missing"
    with budget_store() as session:
        assert list(session.scalars(select(InferenceReservation))) == []
    assert sdk.calls == []
    paid = inference.budget.reserve(
        turn_id="spent",
        modality="audio",
        model="fixture",
        price_version="fixture",
        reserved_usd="4.5",
    )
    inference.budget.settle_amount(paid.id, "4.5")
    inference.settings.openai_agent_model = "gpt-5.6-luna"
    with pytest.raises(DomainError) as error:
        await inference.response(event_id=uuid4(), input=[], instructions="fixture")
    assert error.value.code == "budget_exhausted"
    assert sdk.calls == []


@pytest.mark.asyncio
async def test_five_agent_calls_are_durable_across_clients_and_modalities_separate(budget_store):
    event_id = uuid4()
    for _ in range(5):
        inference, sdk, _ = client(budget_store)
        await inference.response(event_id=event_id, input=[], instructions="fixture")
    resumed, sdk, traces = client(budget_store)
    with pytest.raises(DomainError) as error:
        await resumed.response(event_id=event_id, input=[], instructions="fixture")
    assert error.value.code == "turn_call_limit"
    assert sdk.calls == []
    await resumed.response(event_id=event_id, input=[], instructions="image fixture", vision=True)
    assert sdk.calls[-1]["max_output_tokens"] == 400
    assert sdk.calls[-1]["reasoning"] == {"effort": "none"}
    assert (
        await resumed.transcribe(
            event_id=event_id, data=b"fictitious audio bytes", filename="audio.ogg", duration=30
        )
        == PRIVATE
    )
    with budget_store() as session:
        audio = session.scalar(
            select(InferenceReservation).where(InferenceReservation.modality == "audio")
        )
        assert audio.actual_usd == Decimal("0.00225")
        assert audio.input_tokens is None and audio.output_tokens is None
    assert_no_private_trace(traces)


@pytest.mark.asyncio
async def test_audio_failure_and_task_cancellation_preserve_reservations(budget_store):
    inference, sdk, traces = client(budget_store, error=RuntimeError(PRIVATE))
    with pytest.raises(DomainError) as error:
        await inference.transcribe(
            event_id=uuid4(), data=b"fixture", filename="audio.ogg", duration=60
        )
    assert error.value.code == "audio_failed"
    assert len(sdk.calls) == 1
    assert_no_private_trace(traces)
    cancelled, sdk, traces = client(budget_store, error=asyncio.CancelledError(PRIVATE))
    with pytest.raises(asyncio.CancelledError):
        await cancelled.response(event_id=uuid4(), input=[], instructions="fixture")
    with budget_store() as session:
        assert all(
            row.state == "uncertain" for row in session.scalars(select(InferenceReservation))
        )
    assert_no_private_trace(traces)


def test_durable_turn_cap_is_atomic_under_concurrent_reservation(budget_store):
    service = BudgetService(budget_store)
    for _ in range(4):
        reservation = service.reserve(
            turn_id="same-event",
            modality="agent",
            model="fixture",
            price_version="fixture",
            reserved_usd="0.01",
            max_turn_calls=5,
        )
        service.settle_amount(reservation.id, "0.001")
    barrier = Barrier(6)

    def attempt(_):
        barrier.wait()
        try:
            return service.reserve(
                turn_id="same-event",
                modality="agent",
                model="fixture",
                price_version="fixture",
                reserved_usd="0.01",
                max_turn_calls=5,
            ).id
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert results.count("turn_call_limit") == 5


def test_telemetry_discards_private_metadata_and_automatic_exception_recording():
    observation = Observability(settings())
    traces = FakeLangfuse()
    observation.client = traces
    with pytest.raises(RuntimeError):
        with observation.span(
            PRIVATE,
            event_id=PRIVATE,
            thread_id=PRIVATE,
            pin=PRIVATE,
            model=PRIVATE,
            tool=PRIVATE,
            status=PRIVATE,
        ) as trace:
            trace.update(
                input=PRIVATE,
                output=PRIVATE,
                metadata={"pin": PRIVATE},
                actual_usd=Decimal("0.1"),
                input_tokens=5,
            )
            raise RuntimeError(PRIVATE)
    assert traces.starts[0]["name"] == "operation"
    assert_no_private_trace(traces)
    assert mask_payload(data=[{"content": PRIVATE}]) is None
    assert mask_payload(data={"content": PRIVATE, "pin": PRIVATE, "input_tokens": 1}) == {
        "input_tokens": 1
    }


@pytest.mark.asyncio
async def test_injected_real_sdk_retries_are_forced_off_without_a_request(budget_store):
    from openai import AsyncOpenAI

    original = AsyncOpenAI(api_key="sk-fictional-secret", max_retries=5, timeout=99)
    inference = InferenceClient(
        settings(), BudgetService(budget_store), Observability(settings()), sdk=original
    )
    try:
        assert inference.sdk.max_retries == 0
        assert inference.sdk.timeout == 2
    finally:
        await inference.sdk.close()
        await original.close()


def test_real_langfuse_sdk_exports_no_error_events_or_private_payloads():
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    lf = Langfuse(
        public_key="pk-lf-test-" + uuid4().hex,
        secret_key="sk-lf-fixture",
        base_url="http://127.0.0.1:1",
        tracer_provider=provider,
        span_exporter=exporter,
        mask=mask_payload,
    )
    observation = Observability(settings())
    observation.client = lf
    try:
        with pytest.raises(RuntimeError):
            with observation.span(
                "llm", event_id=uuid4(), thread_id=PRIVATE, model="gpt-5.6-luna", modality="agent"
            ) as trace:
                trace.update(
                    input_tokens=10,
                    output_tokens=3,
                    actual_usd=Decimal("0.00001"),
                    input=PRIVATE,
                    output=PRIVATE,
                )
                raise RuntimeError(PRIVATE)
        lf.flush()
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        serialized = json.dumps(
            {
                "attributes": dict(span.attributes),
                "events": [str(event) for event in span.events],
                "status": span.status.description,
            },
            default=str,
        )
        assert span.events == ()
        assert PRIVATE not in serialized
        assert "sk-fictional-secret" not in serialized
        assert "519826" not in serialized
        assert "private-grant" not in serialized
        assert "+15551234567" not in serialized
        assert "operation_failed" in serialized
        assert any("usage" in key for key in span.attributes)
        assert any("cost" in key for key in span.attributes)
    finally:
        provider.shutdown()


@pytest.mark.asyncio
async def test_authorized_tool_choice_is_passed_through_without_changing_defaults(budget_store):
    inference, sdk, traces = client(budget_store)
    selection = {"type": "function", "name": "list_debts"}
    await inference.response(
        event_id=uuid4(), input=[], instructions="identity verified fixture", tool_choice=selection
    )
    assert sdk.calls[0]["tool_choice"] == selection
    await inference.response(event_id=uuid4(), input=[], instructions="ordinary fixture")
    assert "tool_choice" not in sdk.calls[1]
    assert_no_private_trace(traces)


@pytest.mark.asyncio
@pytest.mark.parametrize("details_kind", ["sdk", "ttl_detail"])
async def test_implicit_cache_write_is_not_ordinary_input_and_reserve_covers_all_writes(
    budget_store, details_kind
):
    # Provider example: 100 ordinary + 300 cached reads + 600 writes, then 250 output.
    from openai.types.responses.response_usage import InputTokensDetails

    details = InputTokensDetails(cached_tokens=300, cache_write_tokens=600)
    if details_kind == "ttl_detail":
        details = {
            "cached_tokens": 300,
            "cache_write_tokens": 600,
            "cache_write_tokens_details": {"ttl_30m_tokens": 600, "ttl_12h_tokens": 0},
        }
    inference, sdk, traces = client(budget_store, input_details=details)
    await inference.response(event_id=uuid4(), input=[], instructions="fixture")
    assert sdk.calls[0]["prompt_cache_options"] == {"ttl": "30m"}
    with budget_store() as session:
        row = session.scalar(select(InferenceReservation))
        assert row.reserved_usd == Decimal("0.0079152")
        assert row.actual_usd == Decimal("0.000476")
        assert row.cached_input_tokens == 300
        assert row.cache_write_tokens == 600
    metadata = traces.updates[-1]["metadata"]
    assert metadata["cached_input_tokens"] == 300
    assert metadata["cache_write_tokens"] == 600
    assert Decimal(metadata["input_cost_usd"]) == Decimal("0.000176")
    assert Decimal(metadata["output_cost_usd"]) == Decimal("0.0003")
    assert_no_private_trace(traces)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "details",
    [
        {"cached_tokens": 0},
        {"cached_tokens": 400, "cache_write_tokens": 700},
        {"cached_tokens": 0, "cache_write_tokens": -1},
        {"cached_tokens": False, "cache_write_tokens": 0},
        {"cached_tokens": 0, "cache_write_tokens": 1, "new_billable_tokens": 1},
        {
            "cached_tokens": 0,
            "cache_write_tokens": 600,
            "cache_write_tokens_details": {"ttl_30m_tokens": 0, "ttl_12h_tokens": 600},
        },
    ],
)
async def test_ambiguous_cache_usage_keeps_reservation_without_retry(budget_store, details):
    inference, sdk, traces = client(budget_store, input_details=details)
    with pytest.raises(DomainError) as error:
        await inference.response(event_id=uuid4(), input=[], instructions=PRIVATE)
    assert error.value.code == "usage_settlement_failed"
    assert len(sdk.calls) == 1
    with budget_store() as session:
        row = session.scalar(select(InferenceReservation))
        assert row.state == "uncertain"
        assert row.actual_usd is None
        assert row.reserved_usd == Decimal("0.0079152")
    assert_no_private_trace(traces)


@pytest.fixture
def real_trace_exporter():
    """Exercise actual SDK context propagation; every export remains in memory."""
    import httpx
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    requests = []

    def reject_request(request):
        requests.append(request)
        raise AssertionError("Observability tests must never make HTTP requests")

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    transport = httpx.Client(transport=httpx.MockTransport(reject_request))
    sdk = Langfuse(
        public_key="pk-lf-fictional-" + uuid4().hex,
        secret_key="sk-lf-fictional-no-provider-access",
        base_url="http://not-used.invalid",
        httpx_client=transport,
        tracer_provider=provider,
        span_exporter=exporter,
        mask=mask_payload,
    )
    observation = Observability(settings())
    observation.client = sdk
    try:
        yield observation, exporter
    finally:
        sdk.flush()
        provider.shutdown()
        transport.close()
        assert requests == []


def exported_attribute(span, suffix):
    # OTel/Langfuse versions use both session.id and session_id spellings.
    matches = [
        value
        for key, value in span.attributes.items()
        if key.replace(".", "_").endswith(suffix)
    ]
    assert len(matches) == 1, (span.name, suffix, span.attributes)
    return matches[0]


def assert_private_values_absent_from_spans(spans):
    serialized = json.dumps([json.loads(span.to_json()) for span in spans], default=str)
    for private in (
        PRIVATE,
        "source-private-",
        "sk-fictional-secret",
        "519826",
        "private-grant",
        "+15551234567",
        "raw-error-private",
        "raw-input-private",
        "raw-output-private",
    ):
        assert private not in serialized
    assert all(not span.events for span in spans)


def test_real_observability_nested_spans_inherit_session_and_export_safe_tool_name(
    real_trace_exporter,
):
    from backend.integrations.observability import opaque_id

    observation, exporter = real_trace_exporter
    raw_thread = "source-private-" + PRIVATE
    event_id = uuid4()
    with observation.span("conversation", event_id=event_id, thread_id=raw_thread):
        with observation.span("agent", event_id=event_id):
            with pytest.raises(RuntimeError, match="raw-error-private"):
                with observation.span(
                    "llm", model="gpt-5.6-luna", modality="agent", pin=PRIVATE, secret=PRIVATE
                ) as generation:
                    generation.update(
                        input_tokens=10,
                        output_tokens=2,
                        input="raw-input-private",
                        output="raw-output-private",
                    )
                    raise RuntimeError("raw-error-private " + PRIVATE)
            with observation.span("tool", tool="locate_customer", input=PRIVATE) as tool:
                tool.update(output=PRIVATE, pin=PRIVATE, source_id=raw_thread)
    observation.flush()
    spans = exporter.get_finished_spans()
    assert len(spans) == 4
    by_name = {span.name: span for span in spans}
    assert set(by_name) == {"conversation", "agent", "llm", "tool.locate_customer"}
    root, agent, generation, tool = (
        by_name[name] for name in ("conversation", "agent", "llm", "tool.locate_customer")
    )
    assert root.parent is None
    assert agent.parent.span_id == root.context.span_id
    assert generation.parent.span_id == agent.context.span_id
    assert tool.parent.span_id == agent.context.span_id
    assert len({span.context.trace_id for span in spans}) == 1
    assert all(exported_attribute(span, "session_id") == opaque_id(raw_thread) for span in spans)
    assert exported_attribute(agent, "observation_type") == "agent"
    assert exported_attribute(generation, "observation_type") == "generation"
    assert exported_attribute(tool, "observation_type") == "tool"
    # Langfuse serializes metadata values as JSON inside OTel attributes.
    assert json.loads(exported_attribute(generation, "metadata_status")) == "failed"
    assert json.loads(exported_attribute(tool, "metadata_status")) == "ok"
    assert_private_values_absent_from_spans(spans)


def test_real_observability_separate_turns_share_only_hashed_session(real_trace_exporter):
    from backend.integrations.observability import opaque_id

    observation, exporter = real_trace_exporter
    threads = ["source-private-first", "source-private-first", "source-private-second"]
    for raw_thread in threads:
        with observation.span("conversation", event_id=uuid4(), thread_id=raw_thread):
            with observation.span("agent"):
                pass
    observation.flush()
    spans = exporter.get_finished_spans()
    roots = [span for span in spans if span.name == "conversation"]
    assert len(roots) == 3
    assert len({span.context.trace_id for span in roots}) == 3
    assert all(span.parent is None for span in roots)
    assert [exported_attribute(span, "session_id") for span in roots] == [
        opaque_id(thread) for thread in threads
    ]
    assert exported_attribute(roots[0], "session_id") != exported_attribute(roots[2], "session_id")
    for span in spans:
        root = next(root for root in roots if root.context.trace_id == span.context.trace_id)
        assert exported_attribute(span, "session_id") == exported_attribute(root, "session_id")
    assert_private_values_absent_from_spans(spans)


def test_real_observability_delivery_resumes_valid_context_after_root_has_closed(
    real_trace_exporter,
):
    from backend.integrations.observability import current_trace_context

    observation, exporter = real_trace_exporter
    assert current_trace_context() is None
    with observation.span("conversation", thread_id="source-private-first") as root:
        root_context = root.export_context()
        assert current_trace_context() == root_context
        assert set(root_context) == {"trace_id", "parent_span_id"}
        assert re.fullmatch(r"[0-9a-f]{32}", root_context["trace_id"])
        assert re.fullmatch(r"[0-9a-f]{16}", root_context["parent_span_id"])
        with observation.span("agent") as agent:
            agent_context = agent.export_context()
            assert current_trace_context() == agent_context
            assert agent_context["trace_id"] == root_context["trace_id"]
            assert agent_context["parent_span_id"] != root_context["parent_span_id"]
        assert current_trace_context() == root_context
    assert current_trace_context() is None
    # Outbox delivery happens later, after the worker's original context is gone.
    with observation.span(
        "delivery", thread_id="source-private-first", trace_context=root_context
    ) as delivery:
        delivery_context = delivery.export_context()
        assert current_trace_context() == delivery_context
        assert delivery_context["trace_id"] == root_context["trace_id"]
        assert delivery_context["parent_span_id"] != root_context["parent_span_id"]
    assert current_trace_context() is None
    observation.flush()
    spans = exporter.get_finished_spans()
    root_span = next(span for span in spans if span.name == "conversation")
    delivered_span = next(span for span in spans if span.name == "delivery")
    assert delivered_span.context.trace_id == root_span.context.trace_id
    assert delivered_span.parent.span_id == root_span.context.span_id
    assert_private_values_absent_from_spans(spans)


@pytest.mark.parametrize(
    "invalid_context",
    [
        PRIVATE,
        {"trace_id": PRIVATE, "parent_span_id": "a" * 16},
        {"trace_id": "a" * 31, "parent_span_id": "b" * 16},
        {"trace_id": "a" * 32, "parent_span_id": "b" * 15},
        {"trace_id": "0" * 32, "parent_span_id": "0" * 16},
        {"trace_id": "a" * 32, "parent_span_id": "b" * 16, "secret": PRIVATE},
    ],
)
def test_real_observability_rejects_invalid_external_trace_context(
    real_trace_exporter, invalid_context
):
    observation, exporter = real_trace_exporter
    with observation.span("delivery", trace_context=invalid_context):
        pass
    observation.flush()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].parent is None
    assert spans[0].context.trace_id != int("a" * 32, 16)
    assert_private_values_absent_from_spans(spans)


def test_observability_context_helpers_fail_safe_without_sdk(caplog):
    from backend.integrations.observability import current_trace_context

    observation = Observability(settings())
    assert current_trace_context() is None
    with observation.span("conversation", thread_id=PRIVATE) as trace:
        assert trace.export_context() is None
        assert current_trace_context() is None

    class BrokenTelemetry:
        def start_as_current_observation(self, **kwargs):
            raise RuntimeError(PRIVATE)

    observation.client = BrokenTelemetry()
    with observation.span("agent", thread_id=PRIVATE) as trace:
        assert trace.export_context() is None
        trace.update(input=PRIVATE, output=PRIVATE)
    assert current_trace_context() is None
    assert PRIVATE not in caplog.text
    assert "telemetry_start_failed" in caplog.text
