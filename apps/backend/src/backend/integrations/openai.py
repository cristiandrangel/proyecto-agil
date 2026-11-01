"""Reserve before inference, settle actual use, and sanitize failures before tracing."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from time import perf_counter
from typing import NamedTuple
from uuid import uuid4

import tiktoken
from agil_shared.errors import DomainError
from openai import AsyncOpenAI

PRICE_VERSION = "openai-2026-11-01-cache-v2"


# Official prices verified by the integration owner on this date:
# https://developers.openai.com/api/docs/models/gpt-5.6-luna
# https://developers.openai.com/api/docs/models/gpt-transcribe
class TokenPrices(NamedTuple):
    input: Decimal
    output: Decimal
    cached: Decimal
    write: Decimal


PRICES = {
    "gpt-5.6-luna": TokenPrices(Decimal("0.20"), Decimal("1.20"), Decimal("0.02"), Decimal("0.25"))
}
AUDIO_USD_PER_MINUTE = Decimal("0.0045")


def cache_usage(usage):
    """Validate the disjoint billing categories for our explicitly fixed 30m TTL.

    Missing or future billable categories are not proof of ordinary-price usage.
    The caller retains the committed reservation if these fields are ambiguous.
    """
    details = usage.input_tokens_details
    values = details if isinstance(details, dict) else details.model_dump()
    if any(
        value not in (None, 0)
        for key, value in values.items()
        if key not in {"cached_tokens", "cache_write_tokens", "cache_write_tokens_details"}
    ):
        raise ValueError("Unknown input billing category")
    cached, written = values["cached_tokens"], values["cache_write_tokens"]
    for value in (cached, written):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Invalid cache token count")
    components = values.get("cache_write_tokens_details")
    if components is not None and components != {"ttl_30m_tokens": written, "ttl_12h_tokens": 0}:
        raise ValueError("Cache usage disagrees with requested 30m lifetime")
    return cached, written


def token_count(value) -> int:
    return len(tiktoken.get_encoding("o200k_base").encode(json.dumps(value, ensure_ascii=False)))


def trace_update(trace, **values):
    if trace is not None:
        trace.update(**values)


class InferenceClient:
    def __init__(self, settings, budget, observability, *, sdk=None):
        self.settings, self.budget, self.observability = settings, budget, observability
        if sdk is None:
            self.sdk = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value() or "unconfigured",
                timeout=settings.openai_timeout_seconds,
                max_retries=0,
            )
        elif isinstance(sdk, AsyncOpenAI):
            self.sdk = sdk.with_options(timeout=settings.openai_timeout_seconds, max_retries=0)
        else:
            self.sdk = sdk  # Deterministic SDK test doubles; no real provider traffic.

    def _uncertain(self, reservation_id):
        try:
            self.budget.mark_uncertain(reservation_id)
        except Exception:
            # The original committed reservation still holds its full amount if
            # PostgreSQL is temporarily unavailable. Never free money on this path.
            pass

    async def response(
        self, *, event_id, input, instructions, tools=None, vision=False, tool_choice=None
    ):
        cfg = self.settings
        if not cfg.openai_api_key.get_secret_value():
            raise DomainError("inference_not_configured", "Falta configurar OpenAI.", 503)
        model = cfg.openai_vision_model if vision else cfg.openai_agent_model
        if model not in PRICES:
            raise DomainError(
                "model_price_missing", "El modelo no tiene una tarifa verificada.", 503
            )
        rates = PRICES[model]
        limit = cfg.ai_vision_max_output_tokens if vision else cfg.ai_max_output_tokens
        estimated = token_count(
            {"instructions": instructions, "input": input, "tools": tools or []}
        )
        if not vision and estimated > cfg.ai_max_input_tokens:
            raise DomainError("context_limit", "El contexto excede el límite de la demo.", 422)
        reserved = (
            Decimal(cfg.ai_max_input_tokens) * max(rates.input, rates.cached, rates.write)
            + Decimal(limit) * rates.output
        ) / Decimal(1_000_000)
        modality = "vision" if vision else "agent"
        reservation = self.budget.reserve(
            turn_id=str(event_id),
            modality=modality,
            model=model,
            price_version=PRICE_VERSION,
            reserved_usd=reserved,
            operation_key=str(uuid4()),
            lease_seconds=cfg.openai_timeout_seconds + 30,
            max_turn_calls=cfg.ai_max_calls_per_turn if not vision else None,
        )
        with self.observability.span(
            "llm",
            event_id=event_id,
            model=model,
            modality=modality,
            price_version=PRICE_VERSION,
            reserved_usd=reserved,
        ) as trace:
            started = perf_counter()
            try:
                response = await self.sdk.responses.create(
                    model=model,
                    input=input,
                    instructions=instructions,
                    tools=tools or [],
                    parallel_tool_calls=False,
                    store=False,
                    prompt_cache_options={"ttl": "30m"},
                    include=["reasoning.encrypted_content"],
                    **({"tool_choice": tool_choice} if tool_choice is not None else {}),
                    max_output_tokens=limit,
                    reasoning={
                        "effort": cfg.openai_vision_reasoning_effort
                        if vision
                        else cfg.openai_agent_reasoning_effort
                    },
                )
            except asyncio.CancelledError:
                self._uncertain(reservation.id)
                trace_update(
                    trace, status="cancelled", provider_latency_ms=(perf_counter() - started) * 1000
                )
                raise asyncio.CancelledError() from None
            except Exception:
                self._uncertain(reservation.id)
                trace_update(
                    trace, status="uncertain", provider_latency_ms=(perf_counter() - started) * 1000
                )
                # This safe exception crosses the tracing boundary; never the SDK's
                # response body, authorization header, request or exception string.
                raise DomainError(
                    "inference_failed",
                    "No pude procesar el mensaje. Solicitaré apoyo si el fallo continúa.",
                    503,
                ) from None
            trace_update(trace, provider_latency_ms=(perf_counter() - started) * 1000)
            if response.usage is None:
                self._uncertain(reservation.id)
                trace_update(trace, status="uncertain")
                raise DomainError(
                    "usage_unknown", "No se pudo verificar el consumo de la respuesta.", 503
                )
            try:
                cached, written = cache_usage(response.usage)
                settled = self.budget.settle(
                    reservation.id,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    input_per_million=rates.input,
                    output_per_million=rates.output,
                    cached_input_tokens=cached,
                    cache_write_tokens=written,
                    cached_input_per_million=rates.cached,
                    cache_write_per_million=rates.write,
                    provider_response_id=response.id,
                )
                trace_update(
                    trace,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cached_input_tokens=cached,
                    cache_write_tokens=written,
                    input_cost_usd=settled.actual_usd
                    - Decimal(response.usage.output_tokens) * rates.output / Decimal(1_000_000),
                    output_cost_usd=Decimal(response.usage.output_tokens)
                    * rates.output
                    / Decimal(1_000_000),
                    actual_usd=settled.actual_usd,
                    status="completed" if response.status == "completed" else "incomplete",
                )
            except Exception:
                self._uncertain(reservation.id)
                trace_update(trace, status="uncertain")
                raise DomainError(
                    "usage_settlement_failed", "No se pudo confirmar el registro del consumo.", 503
                ) from None
            if response.status != "completed":
                raise DomainError(
                    "inference_incomplete", "No pude completar la respuesta dentro del límite.", 503
                )
            return response

    async def transcribe(self, *, event_id, data: bytes, filename: str, duration: float):
        cfg = self.settings
        if (
            not cfg.openai_api_key.get_secret_value()
            or cfg.openai_transcription_model != "gpt-transcribe"
        ):
            raise DomainError(
                "audio_not_configured", "No hay modelo de audio con tarifa configurada.", 503
            )
        try:
            seconds = Decimal(str(duration))
            if not seconds.is_finite() or not 0 < seconds <= cfg.audio_max_seconds:
                raise ValueError()
        except (ValueError, ArithmeticError):
            raise DomainError(
                "audio_duration_invalid", "La duración del audio no es válida.", 422
            ) from None
        amount = seconds * AUDIO_USD_PER_MINUTE / Decimal(60)
        reservation = self.budget.reserve(
            turn_id=str(event_id),
            modality="audio",
            model=cfg.openai_transcription_model,
            price_version=PRICE_VERSION,
            reserved_usd=amount,
            lease_seconds=cfg.openai_timeout_seconds + 30,
        )
        with self.observability.span(
            "audio",
            event_id=event_id,
            modality="audio",
            model=cfg.openai_transcription_model,
            price_version=PRICE_VERSION,
            reserved_usd=amount,
            duration_seconds=float(seconds),
        ) as trace:
            started = perf_counter()
            try:
                response = await self.sdk.audio.transcriptions.create(
                    model=cfg.openai_transcription_model, file=(filename, data)
                )
            except asyncio.CancelledError:
                self._uncertain(reservation.id)
                trace_update(
                    trace, status="cancelled", provider_latency_ms=(perf_counter() - started) * 1000
                )
                raise asyncio.CancelledError() from None
            except Exception:
                self._uncertain(reservation.id)
                trace_update(
                    trace, status="uncertain", provider_latency_ms=(perf_counter() - started) * 1000
                )
                raise DomainError(
                    "audio_failed", "No pude transcribir el audio. Puedes escribir el mensaje.", 503
                ) from None
            try:
                settled = self.budget.settle_amount(reservation.id, actual_usd=amount)
            except Exception:
                self._uncertain(reservation.id)
                trace_update(trace, status="uncertain")
                raise DomainError(
                    "usage_settlement_failed", "No se pudo confirmar el registro del consumo.", 503
                ) from None
            trace_update(
                trace,
                actual_usd=settled.actual_usd,
                status="completed",
                provider_latency_ms=(perf_counter() - started) * 1000,
            )
            return response.text
