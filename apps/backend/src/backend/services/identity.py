"""Deterministic identity/PIN boundary outside persistence of conversational content.

Workers call locate/intercept while holding the literal source_id thread lock.
Ingress uses protect_incoming with a persist callback so redaction, identity state and
queue insertion remain under that same lock. Raw PIN exists only on this call stack.
"""

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
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

PREFIX = "agil.identity.v1."
PIN = re.compile(r"[0-9]{4,8}\Z")
PIN_MENTION = re.compile(
    r"\bpin\b\s*(?:(?:es|es el|de acceso es)\s*)?[:=]?\s*[0-9]{4,8}\b", re.IGNORECASE
)
YES = {
    "si",
    "sí",
    "yes",
    "confirmo",
    "confirmar",
    "correcto",
    "es correcto",
    "sí confirmo",
    "si confirmo",
    "es ese",
    "ese registro",
}
NO = {"no", "no soy", "no es", "otro", "otra persona", "no es ese", "no corresponde"}
CHANGE = {
    "cambiar cliente",
    "cambiar de cliente",
    "cambiar titular",
    "otro cliente",
    "otra persona",
    "cambiar registro",
}


def _secret(value):
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


def encode_protected(result, session_secret):
    """Only a backend-signed envelope can request deterministic identity handling."""
    payload = json.dumps(
        {
            "handled": bool(result["handled"]),
            "response": result.get("response"),
            "agent_message": result.get("agent_message"),
        },
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
            or set(data) != {"handled", "response", "agent_message"}
            or type(data["handled"]) is not bool
        ):
            return None
        if any(
            data[key] is not None and not isinstance(data[key], str)
            for key in ("response", "agent_message")
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

    async def intercept(self, thread_id, content, has_attachments=False, message_id=""):
        """Must run before logging, queue insertion, checkpointing or model input."""
        content = content if isinstance(content, str) else ""
        normalized = content.strip().casefold().rstrip(".!? ")
        snapshot = self.snapshot(thread_id)
        if normalized in CHANGE:
            await self.invalidate(thread_id)
            return _result(
                True,
                "Gestionaremos otro registro. Indica tipo y número de documento para localizarlo.",
            )
        if snapshot["challenge_state"] == "awaiting_confirmation":
            if has_attachments:
                return _result(
                    True, "Confirma por escrito: ¿quieres gestionar ese registro? Responde sí o no."
                )
            if normalized in YES:
                with self.sessions.begin() as session:
                    context = self._context(session, thread_id)
                    context.challenge_state = "awaiting_pin"
                return _result(
                    True,
                    "Registro confirmado. Escribe el PIN de acceso de ese registro; no envíes imágenes ni audio.",
                )
            if normalized in NO:
                await self.invalidate(thread_id)
                return _result(
                    True, "Indica tipo y número de documento del registro que quieres gestionar."
                )
            return _result(
                True,
                "Antes de continuar, confirma si quieres gestionar ese registro. Responde sí o no.",
            )
        if snapshot["challenge_state"] == "awaiting_pin":
            if has_attachments or not PIN.fullmatch(content.strip()):
                return _result(
                    True, "Escribe únicamente el PIN de acceso. No se valida por audio o imagen."
                )
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
                if exc.status == 423:
                    return _result(
                        True,
                        "La validación está temporalmente bloqueada. Intenta de nuevo más tarde.",
                    )
                if exc.status in {404, 409, 410}:
                    await self.invalidate(thread_id)
                    return _result(
                        True,
                        "La validación venció. Indica tipo y número de documento para comenzar de nuevo.",
                    )
                if exc.status in {401, 403, 422}:
                    return _result(
                        True, "El PIN no es válido. Revisa el código e intenta de nuevo."
                    )
                return _result(
                    True,
                    "No se pudo validar el PIN en este momento. Intenta de nuevo en unos instantes.",
                )
            with self.sessions.begin() as session:
                context = self._context(session, thread_id)
                if (
                    context.identity_revision != snapshot["identity_revision"]
                    or context.challenge_state != "awaiting_pin"
                ):
                    return _result(
                        True,
                        "La validación cambió. Comienza de nuevo con el documento del registro.",
                    )
                context.customer_id = UUID(str(verified["customer_id"]))
                context.central_grant = verified["grant_token"]
                context.expires_at = _datetime(verified["expires_at"])
                context.challenge_state = "verified"
                context.candidate_reference = None
            return _result(False, agent_message="identity_verified")
        if PIN.fullmatch(content.strip()) or PIN_MENTION.search(content):
            return _result(
                True,
                "Por seguridad, primero localicemos y confirmemos el registro. Indica tipo y número de documento.",
            )
        return _result(False, agent_message=content)

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
        """persist(safe_content) must enqueue before this method releases the thread lock.

        It may be sync or async. Worker decodes signed content using
        decode_protected(event.normalized_content, settings.session_secret), handles
        response deterministically or passes ONLY agent_message to the graph.
        Attachment content must also be discarded when handled=True.
        """
        validate_source_id(source_id)
        with self.sessions() as lock_session, thread_lock(lock_session, source_id):
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
            # Never trust an envelope supplied by a browser or channel sender.
            if isinstance(content, str) and content.startswith(PREFIX):
                result = _result(True, "Ese mensaje no es válido. Envía tu consulta por escrito.")
            else:
                result = await self.intercept(source_id, content, has_attachments, message_id)
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
