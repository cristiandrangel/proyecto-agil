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


def provider_response_content(response):
    """Serialize provider results for the central content sanitizer, never encrypted state.

    Diagnostic serialization must not change an already-paid response or settlement.
    The central sanitizer removes remaining credentials, PIN and capability URLs.
    """

    def unpack(value):
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if isinstance(value, dict):
            return {key: unpack(item) for key, item in value.items() if key != "encrypted_content"}
        if isinstance(value, (list, tuple)):
            return [unpack(item) for item in value]
        return value

    try:
        if hasattr(response, "model_dump"):
            content = unpack(response)
        else:
            content = {
                key: unpack(getattr(response, key, None))
                for key in (
                    "id",
                    "model",
                    "status",
                    "output",
                    "usage",
                    "incomplete_details",
                    "error",
                )
            }
        content["output_text"] = getattr(response, "output_text", "")
        return content
    except Exception:
        return {"status": getattr(response, "status", None), "serialization_failed": True}


def telemetry_request(request, *, capture_content):
    """Separate telemetry media references from the unchanged provider request."""
    if not capture_content:
        return request

    def convert(value):
        if isinstance(value, dict):
            result = {
                key: convert(item) for key, item in value.items() if key != "encrypted_content"
            }
            url = value.get("image_url")
            if (
                value.get("type") == "input_image"
                and isinstance(url, str)
                and url.startswith("data:image/")
            ):
                from langfuse import LangfuseMedia

                result["image_url"] = LangfuseMedia(base64_data_uri=url)
            return result
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    try:
        return convert(request)
    except Exception:
        # Diagnostics must not stop the provider call or strand a reserved turn.
        # Do not fall back to raw data URIs that trigger automatic SDK uploads.
        return {"capture_error": "media_capture_failed", "model": request.get("model")}


def audio_mime(filename):
    extension = str(filename).rsplit(".", 1)[-1].lower()
    return {
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "opus": "audio/ogg",
        "mp3": "audio/mpeg",
        "webm": "audio/webm",
    }.get(extension, "application/octet-stream")


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
        request = {
            "model": model,
            "input": input,
            "instructions": instructions,
            "tools": tools or [],
            "parallel_tool_calls": False,
            "store": False,
            "prompt_cache_options": {"ttl": "30m"},
            "include": ["reasoning.encrypted_content"],
            "max_output_tokens": limit,
            "reasoning": {
                "effort": cfg.openai_vision_reasoning_effort
                if vision
                else cfg.openai_agent_reasoning_effort
            },
            **({"tool_choice": tool_choice} if tool_choice is not None else {}),
        }
        with self.observability.span(
            "llm",
            event_id=event_id,
            model=model,
            modality=modality,
            price_version=PRICE_VERSION,
            reserved_usd=reserved,
            input=telemetry_request(
                request, capture_content=getattr(self.observability, "capture_content", False)
            ),
        ) as trace:
            started = perf_counter()
            try:
                response = await self.sdk.responses.create(**request)
            except asyncio.CancelledError as exc:
                self._uncertain(reservation.id)
                trace_update(
                    trace,
                    status="cancelled",
                    error=exc,
                    provider_latency_ms=(perf_counter() - started) * 1000,
                )
                raise asyncio.CancelledError() from None
            except Exception as exc:
                self._uncertain(reservation.id)
                trace_update(
                    trace,
                    status="uncertain",
                    error=exc,
                    provider_latency_ms=(perf_counter() - started) * 1000,
                )
                # This safe exception crosses the tracing boundary; never the SDK's
                # response body, authorization header, request or exception string.
                raise DomainError(
                    "inference_failed",
                    "No pude procesar el mensaje. Solicitaré apoyo si el fallo continúa.",
                    503,
                ) from None
            trace_update(
                trace,
                output=provider_response_content(response),
                provider_latency_ms=(perf_counter() - started) * 1000,
            )
            if response.usage is None:
                self._uncertain(reservation.id)
                trace_update(trace, status="uncertain", error={"code": "usage_unknown"})
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
            except Exception as exc:
                self._uncertain(reservation.id)
                trace_update(trace, status="uncertain", error=exc)
                raise DomainError(
                    "usage_settlement_failed", "No se pudo confirmar el registro del consumo.", 503
                ) from None
            if response.status != "completed":
                trace_update(
                    trace,
                    error={
                        "code": "inference_incomplete",
                        "details": getattr(response, "incomplete_details", None),
                    },
                )
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
        audio_input = {
            "model": cfg.openai_transcription_model,
            "filename": filename,
            "mime_type": audio_mime(filename),
            "duration_seconds": float(seconds),
            "size_bytes": len(data),
        }
        if getattr(self.observability, "capture_content", False):
            try:
                from langfuse import LangfuseMedia

                audio_input["asset"] = LangfuseMedia(
                    content_bytes=data, content_type=audio_mime(filename)
                )
            except Exception:
                audio_input["capture_error"] = "media_capture_failed"
        with self.observability.span(
            "audio",
            event_id=event_id,
            modality="audio",
            model=cfg.openai_transcription_model,
            price_version=PRICE_VERSION,
            reserved_usd=amount,
            duration_seconds=float(seconds),
            input=audio_input,
        ) as trace:
            started = perf_counter()
            try:
                response = await self.sdk.audio.transcriptions.create(
                    model=cfg.openai_transcription_model, file=(filename, data)
                )
            except asyncio.CancelledError as exc:
                self._uncertain(reservation.id)
                trace_update(
                    trace,
                    status="cancelled",
                    error=exc,
                    provider_latency_ms=(perf_counter() - started) * 1000,
                )
                raise asyncio.CancelledError() from None
            except Exception as exc:
                self._uncertain(reservation.id)
                trace_update(
                    trace,
                    status="uncertain",
                    error=exc,
                    provider_latency_ms=(perf_counter() - started) * 1000,
                )
                raise DomainError(
                    "audio_failed", "No pude transcribir el audio. Puedes escribir el mensaje.", 503
                ) from None
            trace_update(trace, output={"text": response.text})
            try:
                settled = self.budget.settle_amount(reservation.id, actual_usd=amount)
            except Exception as exc:
                self._uncertain(reservation.id)
                trace_update(trace, status="uncertain", error=exc)
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
