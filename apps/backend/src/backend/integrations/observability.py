"""Allowlisted operational telemetry; prompts, outputs and raw errors stay private."""

from __future__ import annotations

import hashlib
import logging
import math
from contextlib import contextmanager
from decimal import Decimal
from time import perf_counter
from uuid import UUID

logger = logging.getLogger(__name__)
NAMES = {"conversation", "llm", "audio", "tool", "media_normalize", "preflight", "operation"}
LABELS = {
    "model": {"gpt-5.6-luna", "gpt-transcribe"},
    "modality": {"agent", "vision", "audio", "media", "text", "image", "tool"},
    "status": {
        "reserved",
        "settled",
        "uncertain",
        "completed",
        "incomplete",
        "failed",
        "cancelled",
        "ok",
    },
    "tool": {
        "locate_customer",
        "list_debts",
        "select_debt",
        "create_full_payment",
        "quote_agreement",
        "accept_agreement",
        "verify_payment",
        "handoff_human",
    },
    "price_version": {"openai-2026-11-01", "openai-2026-11-01-cache-v2"},
}
COUNTS = {
    "input_tokens",
    "output_tokens",
    "identity_revision",
    "cached_input_tokens",
    "cache_write_tokens",
}
AMOUNTS = {"reserved_usd", "actual_usd", "input_cost_usd", "output_cost_usd"}
DURATIONS = {"latency_ms", "provider_latency_ms", "duration_seconds"}


def configure_logging():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    for name in ("httpx", "httpcore", "openai", "sqlalchemy.engine", "langfuse", "opentelemetry"):
        logging.getLogger(name).setLevel(logging.WARNING)


def opaque_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def safe_metadata(values):
    safe = {}
    for key, value in values.items():
        if key in LABELS and isinstance(value, str) and value in LABELS[key]:
            safe[key] = value
        elif (
            key in COUNTS and isinstance(value, int) and not isinstance(value, bool) and value >= 0
        ):
            safe[key] = value
        elif key in AMOUNTS:
            try:
                number = Decimal(str(value))
                if number.is_finite() and number >= 0:
                    safe[key] = str(number)
            except (ValueError, ArithmeticError):
                pass
        elif (
            key in DURATIONS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        ):
            safe[key] = round(value, 3)
        elif key == "event_id":
            try:
                safe[key] = str(UUID(str(value)))
            except (ValueError, TypeError):
                safe[key] = opaque_id(str(value))
        elif (
            key == "thread_ref"
            and isinstance(value, str)
            and len(value) == 16
            and all(c in "0123456789abcdef" for c in value)
        ):
            safe[key] = value
    return safe


def mask_payload(*, data, **kwargs):
    """SDK defense in depth: arbitrary input/output payloads are discarded."""
    return safe_metadata(data) if isinstance(data, dict) else None


class SafeObservation:
    def __init__(self, raw=None, *, metadata=None):
        self.raw = raw
        self.metadata = safe_metadata(metadata or {})

    def update(self, **metadata):
        self.metadata.update(safe_metadata(metadata))
        if self.raw is None:
            return
        values = {"metadata": dict(self.metadata)}
        if "input_tokens" in self.metadata or "output_tokens" in self.metadata:
            inputs, outputs = (
                self.metadata.get("input_tokens", 0),
                self.metadata.get("output_tokens", 0),
            )
            values["usage_details"] = {
                "input": inputs,
                "output": outputs,
                "total": inputs + outputs,
            }
        if "actual_usd" in self.metadata:
            values["cost_details"] = {"total": float(self.metadata["actual_usd"])}
            for key, label in (("input_cost_usd", "input"), ("output_cost_usd", "output")):
                if key in self.metadata:
                    values["cost_details"][label] = float(self.metadata[key])
        try:
            self.raw.update(**values)
        except Exception:
            logger.warning("telemetry_update_failed")

    def failed(self):
        if self.metadata.get("status") not in {"uncertain", "incomplete", "cancelled"}:
            self.update(status="failed")
        if self.raw is not None:
            try:
                self.raw.update(level="ERROR", status_message="operation_failed")
            except Exception:
                logger.warning("telemetry_update_failed")


class Observability:
    def __init__(self, settings):
        self.client = None
        if (
            settings.langfuse_enabled
            and settings.langfuse_public_key.get_secret_value()
            and settings.langfuse_secret_key.get_secret_value()
        ):
            from langfuse import Langfuse

            try:
                self.client = Langfuse(
                    public_key=settings.langfuse_public_key.get_secret_value(),
                    secret_key=settings.langfuse_secret_key.get_secret_value(),
                    base_url=settings.langfuse_base_url,
                    debug=False,
                    mask=mask_payload,
                )
            except Exception:
                logger.warning("telemetry_initialization_failed")

    @contextmanager
    def span(self, name, *, event_id=None, thread_id=None, **metadata):
        safe = safe_metadata(metadata)
        if event_id is not None:
            safe.update(safe_metadata({"event_id": event_id}))
        if thread_id is not None:
            safe["thread_ref"] = opaque_id(str(thread_id))
        safe_name = name if name in NAMES else "operation"
        manager = None
        raw = None
        if self.client is not None:
            try:
                manager = self.client.start_as_current_observation(
                    name=safe_name,
                    as_type="generation" if safe_name in {"llm", "audio"} else "span",
                    metadata=safe,
                    **({"model": safe["model"]} if "model" in safe else {}),
                )
                raw = manager.__enter__()
            except Exception:
                manager = None
                logger.warning("telemetry_start_failed")
        observation = SafeObservation(raw, metadata=safe)
        error = None
        started = perf_counter()
        try:
            yield observation
        except BaseException as caught:
            # Never pass this exception to the SDK context manager. Its default
            # OpenTelemetry recording can export str(error), traceback and locals.
            error = caught
            observation.failed()
        finally:
            observation.update(latency_ms=(perf_counter() - started) * 1000)
            if manager is not None:
                try:
                    manager.__exit__(None, None, None)
                except Exception:
                    logger.warning("telemetry_end_failed")
        if error is not None:
            raise error

    def flush(self):
        if self.client:
            try:
                self.client.flush()
            except Exception:
                logger.warning("telemetry_flush_failed")
