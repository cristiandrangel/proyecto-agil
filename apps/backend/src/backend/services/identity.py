"""Phase-scoped PIN gate with encrypted ingress and deterministic worker verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from agil_shared.errors import DomainError
from backend.integrations.central import CentralClient
from backend.persistence.database import get_session_factory
from backend.persistence.models import ChannelBinding, InboxEvent, Outbox, VerifiedContext, utcnow
from backend.persistence.queue import thread_lock, validate_source_id
from backend.services.auth_transport import seal_auth, unseal_auth
from cryptography.fernet import InvalidToken
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

PREFIX = "agil.identity.v1."
PIN = re.compile(r"[0-9]{4,8}\Z")
AUTH_PROMPT = (
    "Para autenticarte, escribe únicamente tu PIN de acceso en el siguiente mensaje. "
    "No incluyas texto, audio ni imágenes."
)
PIN_INSTRUCTIONS = AUTH_PROMPT


def _secret(value):
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


def encode_protected(result, session_secret):
    """Only a backend-signed envelope can request deterministic identity handling."""
    data = {
        "handled": bool(result["handled"]),
        "response": result.get("response"),
        "agent_message": result.get("agent_message"),
    }
    if "sealed_auth" in result:
        data["sealed_auth"] = result["sealed_auth"]
    if "auth_result_revision" in result:
        data["auth_result_revision"] = result["auth_result_revision"]
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(
        _secret(session_secret).encode(), encoded.encode(), hashlib.sha256
    ).hexdigest()
    return PREFIX + encoded + "." + signature


def decode_protected(content, session_secret):
    if not isinstance(content, str) or not content.startswith(PREFIX):
        return None
    try:
        encoded, signature = content[len(PREFIX) :].rsplit(".", 1)
        expected = hmac.new(
            _secret(session_secret).encode(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return None
        data = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if (
            not isinstance(data, dict)
            or set(data)
            not in (
                {"handled", "response", "agent_message"},
                {"handled", "response", "agent_message", "sealed_auth"},
                {"handled", "response", "agent_message", "auth_result_revision"},
            )
            or type(data["handled"]) is not bool
        ):
            return None
        if any(
            data[key] is not None and not isinstance(data[key], str)
            for key in ("response", "agent_message")
        ):
            return None
        if "sealed_auth" in data and (
            not isinstance(data["sealed_auth"], str)
            or data["handled"]
            or data["response"] is not None
            or data["agent_message"] is not None
        ):
            return None
        if "auth_result_revision" in data and (
            type(data["auth_result_revision"]) is not int
            or data["auth_result_revision"] < 0
            or data["handled"]
            or data["response"] is not None
            or data["agent_message"] not in {"identity_verified", "auth_attempts_exhausted"}
        ):
            return None
        return data
    except (ValueError, UnicodeError, TypeError):
        return None


def _result(handled=False, response=None, agent_message=None):
    return {"handled": handled, "response": response, "agent_message": agent_message}


def _datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


class IdentityService:
    def __init__(self, settings=None, session_factory=None, central=None, *, clear_context=None):
        if settings is None:
            from backend.config import get_settings

            settings = get_settings()
        self.settings = settings
        self.sessions = session_factory or get_session_factory()
        self.central = central or CentralClient(settings, role="agent")
        self.clear_context = clear_context

    def _context(self, session, thread_id):
        validate_source_id(thread_id)
        session.execute(
            insert(VerifiedContext)
            .values(
                thread_id=thread_id,
                identity_revision=0,
                binding_ref=uuid4(),
                challenge_state="none",
            )
            .on_conflict_do_nothing(index_elements=["thread_id"])
        )
        return session.scalar(
            select(VerifiedContext).where(VerifiedContext.thread_id == thread_id).with_for_update()
        )

    def _clear(self, session, context):
        context.identity_revision += 1
        context.customer_id = None
        context.central_grant = None
        context.expires_at = None
        context.candidate_reference = None
        context.challenge_state = "none"
        context.auth_failures = 0
        context.selected_debt_id = None
        # Sending may have crossed the external boundary; never convert it to a retry.
        session.execute(
            update(Outbox)
            .where(Outbox.thread_id == context.thread_id, Outbox.state == "queued")
            .values(state="cancelled")
        )

    def _expire(self, session, context):
        if context.expires_at is not None and _datetime(context.expires_at) <= utcnow():
            self._clear(session, context)
            return True
        return False

    def snapshot(self, thread_id):
        """Private runtime snapshot. Never include this dict in prompts/checkpoints/traces."""
        with self.sessions.begin() as session:
            context = self._context(session, thread_id)
            self._expire(session, context)
            return {
                "thread_id": context.thread_id,
                "identity_revision": context.identity_revision,
                "candidate_reference": context.candidate_reference,
                "challenge_state": context.challenge_state,
                "auth_failures": context.auth_failures,
                "binding_ref": str(context.binding_ref),
                "customer_id": str(context.customer_id) if context.customer_id else None,
                "grant_token": context.central_grant,
                "central_grant": context.central_grant,
                "expires_at": context.expires_at,
                "selected_debt_id": str(context.selected_debt_id)
                if context.selected_debt_id
                else None,
                "verified": bool(
                    context.central_grant
                    and context.customer_id
                    and context.challenge_state == "verified"
                ),
            }

    get_snapshot = snapshot

    async def invalidate(self, thread_id):
        with self.sessions.begin() as session:
            context = self._context(session, thread_id)
            old_grant, binding, revision = (
                context.central_grant,
                str(context.binding_ref),
                context.identity_revision,
            )
            self._clear(session, context)
        # Backend authorization is revoked before touching any external service.
        # Revoke is a central-owned operation; failure keeps this backend fail-closed.
        if old_grant:
            await self.central.request(
                "POST",
                "/identity/revoke",
                json={"binding_ref": binding},
                grant=old_grant,
                idempotency_key=f"revoke-{binding}-{revision}",
            )
        if self.clear_context:
            result = self.clear_context(thread_id)
            if inspect.isawaitable(result):
                await result

    async def locate(self, thread_id, args, message_id):
        await self.invalidate(thread_id)
        if not isinstance(args, dict) or set(args) - {
            "phone_e164",
            "document_type",
            "document_number",
        }:
            raise DomainError(
                "invalid_identity_lookup", "Usa teléfono o tipo y número de documento.", status=422
            )
        phone = bool(args.get("phone_e164"))
        document = bool(args.get("document_type") and args.get("document_number"))
        if phone == document or (
            phone and (args.get("document_type") or args.get("document_number"))
        ):
            raise DomainError(
                "invalid_identity_lookup",
                "Usa teléfono o tipo y número de documento, por separado.",
                status=422,
            )
        data = await self.central.request(
            "POST", "/identity/locate", json=args, idempotency_key="locate-" + str(message_id)
        )
        candidates = data.get("candidates", [])
        if data.get("candidate_count") == 1:
            candidate = candidates[0] if candidates else data
            reference = candidate.get("candidate_reference")
            if not reference:
                raise DomainError(
                    "invalid_identity_response", "No se pudo preparar la validación.", status=503
                )
            with self.sessions.begin() as session:
                context = self._context(session, thread_id)
                context.candidate_reference = reference
                context.challenge_state = "awaiting_confirmation"
                context.expires_at = utcnow() + timedelta(minutes=10)
            return {
                "candidate_count": 1,
                "candidate_reference": reference,
                "masked_hint": candidate.get("masked_hint", "Registro encontrado"),
                "requires_confirmation": True,
            }
        return {
            "candidate_count": data.get("candidate_count", len(candidates)),
            "candidates": [
                {
                    "candidate_reference": c.get("candidate_reference"),
                    "masked_hint": c.get("masked_hint"),
                }
                for c in candidates
            ],
            "requires_document": True,
        }

    async def manage(self, thread_id, action):
        """Apply an agent-selected identity transition; only PIN verification grants access."""
        if action == "change_customer":
            await self.invalidate(thread_id)
            return {"challenge_state": "none", "requires_document": True, "verified": False}
        if action not in {"confirm_candidate", "reject_candidate"}:
            raise DomainError(
                "invalid_identity_action", "Acción de identidad inválida.", status=422
            )
        self.snapshot(thread_id)  # Expiration revokes authority durably before any transition.
        with self.sessions.begin() as session:
            context = self._context(session, thread_id)
            if (
                not context.candidate_reference
                or context.challenge_state not in {"awaiting_confirmation", "awaiting_pin"}
                or context.expires_at is None
                or _datetime(context.expires_at) <= utcnow()
            ):
                raise DomainError(
                    "candidate_unavailable",
                    "Localiza un registro vigente antes de confirmarlo.",
                    status=409,
                )
            if action == "confirm_candidate":
                if context.challenge_state != "awaiting_pin":
                    context.auth_failures = 0
                context.challenge_state = "awaiting_pin"
                return {
                    "challenge_state": "awaiting_pin",
                    "requires_pin": True,
                    "verified": False,
                    "pin_instructions": PIN_INSTRUCTIONS,
                    "response": AUTH_PROMPT,
                }
        await self.invalidate(thread_id)
        return {"challenge_state": "none", "requires_document": True, "verified": False}

    async def _clear_auth_history(self, thread_id, result):
        if result.get("agent_message") == "auth_attempts_exhausted" and self.clear_context:
            cleared = self.clear_context(thread_id)
            if inspect.isawaitable(cleared):
                await cleared

    def _save_auth_result(self, session, context, event, result):
        if event is not None:
            stored = session.get(InboxEvent, event.id, with_for_update=True)
            if stored is None:
                raise DomainError("auth_event_missing", "Mensaje de validación no disponible.", 409)
            # The counter and erased ciphertext commit atomically. Event routing
            # and its original identity revision are immutable (backend_0002).
            if result.get("agent_message") in {"identity_verified", "auth_attempts_exhausted"}:
                result = {**result, "auth_result_revision": context.identity_revision}
            stored.normalized_content = encode_protected(result, self.settings.session_secret)
            stored.attachments = []
            session.flush()
            event.normalized_content = stored.normalized_content
            event.attachments = []
        return result

    async def _authenticate(
        self,
        thread_id,
        content,
        has_attachments,
        message_id,
        *,
        event=None,
        expected_revision=None,
        expected_candidate=None,
    ):
        snapshot = self.snapshot(thread_id)
        if snapshot["challenge_state"] != "awaiting_pin" or (
            expected_revision is not None
            and (
                snapshot["identity_revision"] != expected_revision
                or snapshot["candidate_reference"] != expected_candidate
            )
        ):
            result = _result(
                True,
                "La validación venció o cambió. Indica tipo y número de documento para comenzar de nuevo.",
            )
            if event is not None:
                with self.sessions.begin() as session:
                    context = self._context(session, thread_id)
                    self._save_auth_result(session, context, event, result)
            return result
        content = content if isinstance(content, str) else ""
        numeric_pin = PIN.fullmatch(content.strip())
        verified = None
        unavailable = False
        temporary_failure = False
        locked = False
        if not has_attachments and numeric_pin:
            try:
                verified = await self.central.request(
                    "POST",
                    "/identity/verify",
                    json={
                        "candidate_reference": snapshot["candidate_reference"],
                        "confirmed": True,
                        "pin": content.strip(),
                        "binding_ref": snapshot["binding_ref"],
                        "source_message_id": str(message_id),
                    },
                    idempotency_key="verify-" + str(message_id),
                )
            except DomainError as exc:
                unavailable = exc.status in {404, 409, 410}
                temporary_failure = exc.status not in {401, 403, 404, 409, 410, 422, 423}
                locked = exc.status == 423
        with self.sessions.begin() as session:
            context = self._context(session, thread_id)
            self._expire(session, context)
            if (
                context.identity_revision != snapshot["identity_revision"]
                or context.challenge_state != "awaiting_pin"
                or context.candidate_reference != snapshot["candidate_reference"]
            ):
                result = _result(
                    True, "La validación cambió. Comienza de nuevo con el documento del registro."
                )
            elif verified is not None:
                context.customer_id = UUID(str(verified["customer_id"]))
                context.central_grant = verified["grant_token"]
                context.expires_at = _datetime(verified["expires_at"])
                context.challenge_state = "verified"
                context.candidate_reference = None
                context.auth_failures = 0
                result = _result(False, agent_message="identity_verified")
            elif unavailable:
                self._clear(session, context)
                result = _result(
                    True,
                    "La validación venció. Indica tipo y número de documento para comenzar de nuevo.",
                )
            elif temporary_failure:
                result = _result(
                    True,
                    "No se pudo validar el PIN en este momento. Intenta de nuevo en unos instantes.",
                )
            else:
                context.auth_failures = min(context.auth_failures + 1, 3)
                if context.auth_failures >= 3:
                    self._clear(session, context)
                    context.auth_failures = 3
                    result = _result(False, agent_message="auth_attempts_exhausted")
                else:
                    reason = (
                        "El mensaje no está en el formato esperado."
                        if has_attachments or not numeric_pin
                        else "El PIN no es válido."
                    )
                    if locked:
                        reason = "La validación está temporalmente bloqueada. Intenta de nuevo más tarde."
                    remaining = 3 - context.auth_failures
                    opportunities = (
                        "Te queda 1 oportunidad."
                        if remaining == 1
                        else f"Te quedan {remaining} oportunidades."
                    )
                    result = _result(True, f"{reason} {PIN_INSTRUCTIONS} {opportunities}")
            result = self._save_auth_result(session, context, event, result)
        await self._clear_auth_history(thread_id, result)
        return result

    async def intercept(self, thread_id, content, has_attachments=False, message_id=""):
        """Worker/direct-call gate. Outside awaiting_pin every string is agent data.

        Callers serialize the thread. Durable queue processing uses consume_auth so
        replaying a source message cannot consume another authentication attempt.
        """
        content = content if isinstance(content, str) else ""
        if self.snapshot(thread_id)["challenge_state"] != "awaiting_pin":
            return _result(False, agent_message=content)
        return await self._authenticate(thread_id, content, has_attachments, message_id)

    async def consume_auth(self, event):
        """Consume a signed ticket under the caller's thread lock, after HTTP ACK.

        Reload the durable result before decoding: a detached event may still carry
        a ticket from before a worker failure. Never return decrypted text to callers.
        """
        with self.sessions() as session:
            stored = session.get(InboxEvent, event.id)
            if stored is None:
                raise DomainError("auth_event_missing", "Mensaje de validación no disponible.", 409)
            content = stored.normalized_content
            event.normalized_content = content
            event.identity_revision = stored.identity_revision
            event.attachments = list(stored.attachments)
        protected = decode_protected(content, self.settings.session_secret)
        if protected is None:
            return None
        if "sealed_auth" not in protected:
            await self._clear_auth_history(event.thread_id, protected)
            return protected
        try:
            payload = unseal_auth(protected["sealed_auth"], self.settings.session_secret)
            if (
                not isinstance(payload, dict)
                or payload.get("thread_id") != event.thread_id
                or payload.get("message_id") != str(event.message_id)
                or payload.get("account_id") not in {None, str(event.account_id)}
                or type(payload.get("identity_revision")) is not int
                or not isinstance(payload.get("candidate_reference"), str)
                or not isinstance(payload.get("content"), str)
                or type(payload.get("has_attachments")) is not bool
            ):
                raise ValueError("invalid authentication binding")
        except (InvalidToken, ValueError, UnicodeError, TypeError):
            result = _result(
                True, "La validación cambió. Comienza de nuevo con el documento del registro."
            )
            with self.sessions.begin() as session:
                context = self._context(session, event.thread_id)
                self._save_auth_result(session, context, event, result)
            return result
        return await self._authenticate(
            event.thread_id,
            payload["content"],
            payload["has_attachments"],
            event.message_id,
            event=event,
            expected_revision=payload["identity_revision"],
            expected_candidate=payload["candidate_reference"],
        )

    async def select_debt(self, thread_id, debt_id):
        snapshot = self.snapshot(thread_id)
        if not snapshot["verified"]:
            raise DomainError(
                "identity_required", "Valida el registro antes de consultar su cartera.", status=403
            )
        debt = await self.central.request("GET", f"/debts/{debt_id}", grant=snapshot["grant_token"])
        with self.sessions.begin() as session:
            context = self._context(session, thread_id)
            self._expire(session, context)
            if (
                not context.central_grant
                or context.identity_revision != snapshot["identity_revision"]
            ):
                raise DomainError(
                    "identity_changed", "La validación cambió. Valida de nuevo.", status=409
                )
            context.selected_debt_id = UUID(str(debt_id))
        return debt

    async def contact_changed(self, customer_id):
        with self.sessions() as session:
            threads = list(
                session.scalars(
                    select(VerifiedContext.thread_id).where(
                        VerifiedContext.customer_id == UUID(str(customer_id))
                    )
                )
            )
        for thread_id in threads:
            with self.sessions() as lock_session, thread_lock(lock_session, thread_id):
                await self.invalidate(thread_id)
        with self.sessions.begin() as session:
            session.execute(
                update(ChannelBinding)
                .where(ChannelBinding.customer_id == UUID(str(customer_id)))
                .values(valid=False)
            )

    async def protect_incoming(
        self, source_id, content, has_attachments=False, message_id="", *, persist, account_id=None
    ):
        """Persist encrypted authentication input without central/provider requests.

        The callback durably inserts the signed envelope before returning. Only the
        worker may consume its encrypted payload, after ingress returns HTTP 200.
        """
        validate_source_id(source_id)
        query = select(InboxEvent).where(
            InboxEvent.thread_id == source_id, InboxEvent.message_id == str(message_id)
        )
        if account_id is not None:
            query = query.where(InboxEvent.account_id == str(account_id))
        with self.sessions() as session:
            existing = session.scalar(query.limit(1))
            if existing is not None:
                return {
                    "duplicate": True,
                    "event": existing,
                    "result": decode_protected(
                        existing.normalized_content, self.settings.session_secret
                    ),
                }
        # Sender text, including forged envelope prefixes, remains untrusted data
        # inside our signed envelope; only this outer signature is authoritative.
        content = content if isinstance(content, str) else ""
        snapshot = self.snapshot(source_id)
        if snapshot["challenge_state"] == "awaiting_pin":
            result = _result()
            result["sealed_auth"] = seal_auth(
                {
                    "thread_id": source_id,
                    "message_id": str(message_id),
                    "account_id": str(account_id) if account_id is not None else None,
                    "identity_revision": snapshot["identity_revision"],
                    "candidate_reference": snapshot["candidate_reference"],
                    "content": content,
                    "has_attachments": bool(has_attachments),
                },
                self.settings.session_secret,
            )
        else:
            result = _result(False, agent_message=content)
        safe_content = encode_protected(result, self.settings.session_secret)
        event = persist(safe_content)
        if inspect.isawaitable(event):
            event = await event
        return {
            "duplicate": False,
            "event": event,
            "result": result,
            "safe_content": safe_content,
        }
