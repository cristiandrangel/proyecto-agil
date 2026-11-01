"""Operational traces with optional content capture and mandatory secret removal."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import traceback
from contextlib import contextmanager
from decimal import Decimal
from time import perf_counter
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from backend.integrations.telemetry_transport import langfuse_http_client

logger = logging.getLogger(__name__)
NAMES = {
    "conversation", "agent", "llm", "audio", "tool", "media_normalize", "preflight",
    "operation", "identity_gate", "response_enqueue", "delivery",
}
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
        "handled", "passed", "queued", "sent", "deferred",
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
    "phase": {"identify", "select_debt", "discuss_payment", "confirm_agreement",
              "await_payment", "payment_verified", "handoff_requested"},
    "result_status": {"applied", "pending", "absent", "requires_human", "action_pending",
                      "transferred", "returned", "proposed", "accepted", "expired"},
}
COUNTS = {
    "input_tokens",
    "output_tokens",
    "identity_revision",
    "cached_input_tokens",
    "cache_write_tokens",
    "candidate_count",
    "debt_count",
}
AMOUNTS = {"reserved_usd", "actual_usd", "input_cost_usd", "output_cost_usd"}
DURATIONS = {"latency_ms", "provider_latency_ms", "duration_seconds"}
UNSET = object()
REDACTED = "[REDACTED]"


class ContentSanitizer:
    """Preserve conversation content, never infrastructure/authentication material.

    Limits are explicit markers, rather than silently returning incomplete content.
    PIN challenge input is excluded at its identity-gate source: an unlabelled
    number can also be a legitimate document or monetary amount.
    """

    def __init__(self, settings=None, *, max_text=1_000_000, max_depth=40, max_items=20_000):
        self.max_text, self.max_depth, self.max_items = max_text, max_depth, max_items
        self.secrets = []
        try:
            for value in vars(settings).values() if settings is not None else ():
                getter = getattr(value, "get_secret_value", None)
                if callable(getter):
                    secret = getter()
                    if isinstance(secret, str) and secret:
                        self.secrets.append(secret)
        except Exception:
            logger.warning("telemetry_secret_inventory_failed")
        self.secrets.sort(key=len, reverse=True)

    @staticmethod
    def secret_key(key):
        normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
        return (
            normalized in {
                "authorization", "proxyauthorization", "cookie", "setcookie",
                "pin", "pincode", "verificationcode", "otp", "capability", "grant",
                "credential", "credentials", "encryptedcontent", "privatekey",
            }
            or normalized.endswith(("token", "password", "passwd", "secret", "apikey",
                                    "signature", "credential", "authorization"))
        )

    def text(self, value):
        # Function-call arguments and tool results commonly arrive as JSON text.
        # Keep their original string type, but sanitize their structured secrets.
        if value.lstrip().startswith(("{", "[")):
            try:
                decoded = json.loads(value)
                if isinstance(decoded, (dict, list)):
                    value = json.dumps(self._sanitize(decoded, 0, set(), [0]), ensure_ascii=False)
            except (ValueError, TypeError, RecursionError):
                pass
        for secret in self.secrets:
            value = value.replace(secret, REDACTED)
        value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer " + REDACTED, value)
        value = re.sub(
            r"(?i)\b(authorization|proxy-authorization)\s*[:=]\s*Basic\s+[^\s,;]+",
            lambda match: match.group(1) + "=" + REDACTED,
            value,
        )
        value = re.sub(r"\b(?:sk|pk)-(?:[A-Za-z0-9_-]{8,})", REDACTED, value)
        value = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", REDACTED, value)

        def clean_url(match):
            raw = match.group(0)
            try:
                parsed = urlsplit(raw)
                host = parsed.netloc.rsplit("@", 1)[-1]
                if "@" in parsed.netloc:
                    host = REDACTED + "@" + host
                query = [
                    (key, REDACTED if self.secret_key(key) else item)
                    for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                ]
                fragment = "" if self.secret_key(parsed.fragment.partition("=")[0]) else parsed.fragment
                return urlunsplit((parsed.scheme, host, parsed.path, urlencode(query), fragment))
            except Exception:
                return "[REDACTED:unparseable_url]"

        value = re.sub(r"(?:https?|postgresql(?:\+psycopg)?|redis)://[^\s\"'<>]+", clean_url, value)
        value = re.sub(
            r"(?i)\b(pin(?:_code)?|otp|grant(?:_token)?|capability|(?:api[_-]?(?:access[_-]?)?token)|"
            r"api[_-]?key|access[_-]?token|token|password|secret|authorization)[\"']?\s*[:=]\s*"
            r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&<>]+)",
            lambda match: match.group(1) + "=" + REDACTED,
            value,
        )
        value = re.sub(r"(?i)\b(PIN|OTP)(\s+)(\d{4,8})\b", r"\1\2" + REDACTED, value)
        if len(value) > self.max_text:
            value = value[:self.max_text] + f"[TRUNCATED:original_chars={len(value)}]"
        return value

    def sanitize(self, value):
        try:
            return self._sanitize(value, 0, set(), [0])
        except Exception:
            logger.warning("telemetry_content_sanitization_failed")
            return "[UNAVAILABLE:sanitization_failed]"

    def _sanitize(self, value, depth, seen, count):
        count[0] += 1
        if count[0] > self.max_items:
            return "[TRUNCATED:max_items]"
        if depth > self.max_depth:
            return "[TRUNCATED:max_depth]"
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else str(value)
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, (Decimal, UUID)):
            return self.text(str(value))
        if callable(getattr(value, "get_secret_value", None)):
            return REDACTED
        if isinstance(value, bytes):
            return f"[BINARY:{len(value)}bytes; use LangfuseMedia]"
        identity = id(value)
        if identity in seen:
            return "[CIRCULAR]"
        seen.add(identity)
        try:
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    if count[0] > self.max_items:
                        result["_capture_limit"] = "[TRUNCATED:max_items]"
                        break
                    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                    if normalized.endswith("encryptedcontent"):
                        continue
                    result[self.text(str(key))] = (
                        REDACTED if self.secret_key(key)
                        else self._sanitize(item, depth + 1, seen, count)
                    )
                return result
            if isinstance(value, (list, tuple)):
                result = []
                for item in value:
                    result.append(self._sanitize(item, depth + 1, seen, count))
                    if count[0] > self.max_items:
                        break
                return result
            # Only SDK-created media objects are preserved; arbitrary objects are
            # not introspected or stringified (their repr may contain secrets).
            from langfuse import LangfuseMedia

            if isinstance(value, LangfuseMedia):
                return LangfuseMedia(
                    content_bytes=value._content_bytes,
                    content_type=value._content_type,
                    obj=self._sanitize(value.obj, depth + 1, seen, count),
                )
            dump = getattr(value, "model_dump", None)
            if callable(dump):
                return self._sanitize(dump(mode="python"), depth + 1, seen, count)
            isoformat = getattr(value, "isoformat", None)
            if callable(isoformat):
                return self.text(isoformat())
            return "[UNSUPPORTED:" + type(value).__name__ + "]"
        finally:
            seen.discard(identity)

    def error(self, error):
        try:
            if isinstance(error, BaseException):
                data = {
                    "type": type(error).__name__,
                    "message": str(error),
                    "traceback": "".join(traceback.format_list(traceback.extract_tb(error.__traceback__))),
                }
                code = getattr(error, "code", None)
                if isinstance(code, (str, int)):
                    data["code"] = code
            else:
                data = error
            return self.sanitize(data)
        except Exception:
            logger.warning("telemetry_error_sanitization_failed")
            return {"type": "unavailable", "message": "[UNAVAILABLE:sanitization_failed]"}

    def mask(self, *, data, **kwargs):
        return self.sanitize(data)


def validated_trace_context(value):
    if not isinstance(value, dict) or set(value) != {"trace_id", "parent_span_id"}:
        return None
    for key, size in (("trace_id", 32), ("parent_span_id", 16)):
        item = value[key]
        if not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{%d}" % size, item) or int(item, 16) == 0:
            return None
    return dict(value)


def current_trace_context():
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if not context.is_valid:
            return None
        return {"trace_id": f"{context.trace_id:032x}", "parent_span_id": f"{context.span_id:016x}"}
    except Exception:
        return None


def configure_logging():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    for name in ("httpx", "httpcore", "openai", "sqlalchemy.engine", "langfuse", "opentelemetry"):
        logging.getLogger(name).setLevel(logging.WARNING)


def opaque_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _safe_metadata(values):
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


def safe_metadata(values):
    try:
        return _safe_metadata(values)
    except Exception:
        logger.warning("telemetry_metadata_sanitization_failed")
        return {}


def mask_payload(*, data, **kwargs):
    """SDK defense in depth: arbitrary input/output payloads are discarded."""
    return safe_metadata(data) if isinstance(data, dict) else None


class SafeObservation:
    def __init__(self, raw=None, *, metadata=None, capture_content=False, sanitizer=None):
        self.raw = raw
        self.metadata = safe_metadata(metadata or {})
        self.capture_content = capture_content
        self.sanitizer = sanitizer or ContentSanitizer()
        self.content = {}

    def export_context(self):
        if self.raw is None:
            return None
        try:
            return validated_trace_context({
                "trace_id": getattr(self.raw, "trace_id", None),
                "parent_span_id": getattr(self.raw, "id", None),
            })
        except Exception:
            return None

    def update(self, *, input=UNSET, output=UNSET, error=UNSET, **metadata):
        try:
            self._update(input=input, output=output, error=error, **metadata)
        except Exception:
            logger.warning("telemetry_update_failed")

    def _update(self, *, input=UNSET, output=UNSET, error=UNSET, **metadata):
        self.metadata.update(safe_metadata(metadata))
        values = {"metadata": dict(self.metadata)}
        if self.capture_content:
            for key, value in (("input", input), ("output", output)):
                if value is not UNSET:
                    self.content[key] = self.sanitizer.sanitize(value)
                    values[key] = self.content[key]
            if error is not UNSET:
                details = self.sanitizer.error(error)
                self.content["error"] = details
                # Error details are content, never unallowlisted telemetry metadata.
                values["output"] = {**self.content, "error": details}
                values["level"] = "ERROR"
                values["status_message"] = self.sanitizer.text(
                    details.get("message", "operation_failed")
                    if isinstance(details, dict) else str(details)
                )
        if self.raw is None:
            return
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

    def failed(self, error=None):
        if self.metadata.get("status") not in {"uncertain", "incomplete", "cancelled"}:
            self.update(status="failed")
        if self.raw is not None:
            try:
                if self.capture_content and error is not None:
                    # Provider adapters may record the original exception before
                    # translating it to DomainError. Keep that diagnostic cause.
                    if "error" not in self.content:
                        self.update(error=error)
                else:
                    self.raw.update(level="ERROR", status_message="operation_failed")
            except Exception:
                logger.warning("telemetry_update_failed")


class Observability:
    def __init__(self, settings):
        self.client = None
        self.capture_content = bool(getattr(settings, "langfuse_capture_content", False))
        self.sanitizer = ContentSanitizer(settings)
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
                    mask=self.sanitizer.mask if self.capture_content else mask_payload,
                    httpx_client=langfuse_http_client(settings),
                )
            except Exception:
                logger.warning("telemetry_initialization_failed")

    def sanitize_content(self, value):
        return self.sanitizer.sanitize(value) if self.capture_content else None

    @contextmanager
    def span(self, name, *, event_id=None, thread_id=None, trace_context=None,
             input=UNSET, output=UNSET, **metadata):
        safe = safe_metadata(metadata)
        try:
            if event_id is not None:
                safe.update(safe_metadata({"event_id": event_id}))
            if thread_id is not None:
                safe["thread_ref"] = opaque_id(str(thread_id))
        except Exception:
            logger.warning("telemetry_context_sanitization_failed")
        safe_name = name if isinstance(name, str) and name in NAMES else "operation"
        if safe_name == "tool" and "tool" in safe:
            safe_name = "tool." + safe["tool"]
        manager = None
        propagation = None
        raw = None
        if self.client is not None:
            try:
                if thread_id is not None:
                    from langfuse import propagate_attributes

                    propagation = propagate_attributes(session_id=safe["thread_ref"])
                    propagation.__enter__()
                context = validated_trace_context(trace_context)
                manager = self.client.start_as_current_observation(
                    name=safe_name,
                    as_type=("generation" if safe_name in {"llm", "audio"} else
                             "agent" if safe_name == "agent" else
                             "tool" if safe_name.startswith("tool.") else "span"),
                    metadata=safe,
                    **({"model": safe["model"]} if "model" in safe else {}),
                    **({"trace_context": context} if context else {}),
                    **({"input": self.sanitize_content(input)}
                       if self.capture_content and input is not UNSET else {}),
                    **({"output": self.sanitize_content(output)}
                       if self.capture_content and output is not UNSET else {}),
                )
                raw = manager.__enter__()
            except Exception:
                manager = None
                logger.warning("telemetry_start_failed")
        observation = SafeObservation(
            raw, metadata=safe, capture_content=self.capture_content, sanitizer=self.sanitizer
        )
        if self.capture_content:
            for key, value in (("input", input), ("output", output)):
                if value is not UNSET:
                    observation.content[key] = self.sanitize_content(value)
        error = None
        started = perf_counter()
        try:
            yield observation
            if "status" not in observation.metadata:
                observation.update(status="ok")
        except BaseException as caught:
            # Never pass this exception to the SDK context manager. Its default
            # OpenTelemetry recording can export str(error), traceback and locals.
            error = caught
            observation.failed(caught)
        finally:
            observation.update(latency_ms=(perf_counter() - started) * 1000)
            if manager is not None:
                try:
                    manager.__exit__(None, None, None)
                except Exception:
                    logger.warning("telemetry_end_failed")
            if propagation is not None:
                try:
                    propagation.__exit__(None, None, None)
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
