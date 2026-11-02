"""Durable human takeover: case first, then ordered effects through the outbox.

This service never calls the channel directly and never treats queued work as an
external success. Return to the bot requires observed open after applied transfer,
then an explicitly observed pending state on a later source event.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from agil_shared.errors import DomainError
from agil_shared.money import format_usd, parse_usd
from backend.integrations.observability import current_trace_context
from backend.persistence.database import get_session_factory
from backend.persistence.models import HumanCase, InboxEvent, Outbox, VerifiedContext, utcnow
from backend.services.events import EventService
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

REASONS = {
    "requested": "Solicitud de atención humana",
    "dispute": "Disputa sobre la deuda",
    "below_minimum": "Oferta fuera de la política automática",
    "payment_unverified": "Pago sin verificación suficiente",
    "technical_failure": "Fallo técnico que impide continuar con seguridad",
}


def _safe_summary(summary, secrets=()):
    value = str(summary or "Sin resumen adicional.")[:1800]
    for secret in secrets:
        if secret:
            value = value.replace(str(secret), "[secreto omitido]")
    value = re.sub(r"https?://\S+", "[enlace omitido]", value)
    value = re.sub(
        r"(?i)\b(?:pin|token|password|contraseña|grant)\s*(?:es\s*)?[:=]?\s*\S+",
        "[secreto omitido]",
        value,
    )
    value = re.sub(
        r"(?<!\w)\+?[0-9][0-9\s-]{5,}[0-9](?!\w)", "[dato de contacto o documento omitido]", value
    )
    return " ".join(value.split())[:1200]


class HandoffService:
    def __init__(self, settings=None, session_factory=None, channel=None, observability=None):
        self.settings = settings
        self.sessions = session_factory or get_session_factory()
        self.channel = channel
        self.observability = observability

    def _event(self, session, event):
        identifier = event.id if hasattr(event, "id") else event
        try:
            identifier = UUID(str(identifier))
        except (ValueError, TypeError):
            raise DomainError(
                "event_not_found", "No se encontró el mensaje de origen.", status=404
            ) from None
        stored = session.get(InboxEvent, identifier)
        if stored is None:
            raise DomainError("event_not_found", "No se encontró el mensaje de origen.", status=404)
        local_event = stored.account_id == "local" and stored.inbox_id == "local"
        local_allowed = (
            self.settings is not None
            and getattr(self.settings, "app_env", None) in {"local", "development", "test"}
            and getattr(self.settings, "enable_local_message_endpoint", False)
        )
        if local_event and not local_allowed:
            raise DomainError(
                "channel_scope_denied", "La entrada local no está habilitada.", status=403
            )
        if self.settings is not None and not (local_event and local_allowed):
            for field, setting in (
                ("account_id", "chatwoot_account_id"),
                ("inbox_id", "chatwoot_inbox_id"),
            ):
                allowed = getattr(self.settings, setting, None)
                if allowed is not None and str(getattr(stored, field)) != str(allowed):
                    raise DomainError(
                        "channel_scope_denied", "El canal no está autorizado.", status=403
                    )
        return stored

    @staticmethod
    def _result(case):
        return {
            "case_id": str(case.id),
            "status": "action_pending" if case.status == "open" else case.status,
            "case_status": case.status,
            "reason": case.reason,
        }

    async def request(self, event, reason, summary, offer_amount_usd=None):
        if reason not in REASONS:
            raise DomainError(
                "invalid_handoff_reason", "Motivo de atención humana no permitido.", status=422
            )
        offer_cents = parse_usd(offer_amount_usd) if offer_amount_usd is not None else None
        with self.sessions.begin() as session:
            source = self._event(session, event)
            context = session.scalar(
                select(VerifiedContext)
                .where(VerifiedContext.thread_id == source.thread_id)
                .with_for_update()
            )
            revision = context.identity_revision if context else 0
            verified = bool(
                context
                and context.central_grant
                and context.expires_at
                and context.expires_at > utcnow()
                and context.challenge_state == "verified"
            )
            customer_id = context.customer_id if verified else None
            debt_id = context.selected_debt_id if verified else None
            safe_summary = _safe_summary(summary, (context.central_grant if context else None,))
            # Identity and destination always derive from the persisted server event/context.
            case_id = session.execute(
                insert(HumanCase)
                .values(
                    id=uuid4(),
                    thread_id=source.thread_id,
                    account_id=source.account_id,
                    inbox_id=source.inbox_id,
                    conversation_id=source.conversation_id,
                    source_event_id=source.id,
                    customer_id=customer_id,
                    debt_id=debt_id,
                    reason=reason,
                    origin="agent",
                    offer_cents=offer_cents,
                    verification_summary=safe_summary,
                    status="open",
                )
                .on_conflict_do_nothing(index_elements=["source_event_id", "origin"])
                .returning(HumanCase.id)
            ).scalar_one_or_none()
            if case_id is None:
                case = session.scalar(
                    select(HumanCase).where(
                        HumanCase.source_event_id == source.id, HumanCase.origin == "agent"
                    )
                )
                return self._result(case)
            case = session.get(HumanCase, case_id)
            EventService._save(
                session,
                source_key=f"human:{case_id}",
                event_type="human_requested" if reason == "requested" else "automatic_escalation",
                customer_id=customer_id,
                debt_id=debt_id,
                thread_id=source.thread_id,
                account_id=source.account_id,
                inbox_id=source.inbox_id,
                conversation_id=source.conversation_id,
                payload={"case_id": str(case_id), "reason": reason},
            )
            session.execute(
                update(Outbox)
                .where(
                    Outbox.thread_id == source.thread_id,
                    Outbox.state == "queued",
                    Outbox.kind.not_in(["private_note", "handoff_notice", "set_open"]),
                )
                .values(state="cancelled")
            )
            note_lines = [
                "DERIVACIÓN HUMANA · DEMO",
                f"Motivo: {REASONS[reason]}.",
                f"Registro validado: {'sí' if verified else 'no'}.",
            ]
            if customer_id:
                note_lines.append(f"Referencia interna de cliente: {customer_id}.")
            if debt_id:
                note_lines.append(f"Referencia interna de deuda: {debt_id}.")
            if offer_cents is not None:
                note_lines.append(
                    f"Oferta comunicada: USD {format_usd(offer_cents)}. Sin aprobación automática."
                )
            note_lines.append("Resumen conversacional (no verificado): " + safe_summary)
            previous = []
            effects = [
                ("private_note", {"content": "\n".join(note_lines), "private": True}),
                (
                    "handoff_notice",
                    {
                        "content": "Solicité apoyo de un asesor para continuar con tu caso. La atención automática queda en pausa.",
                        "private": False,
                    },
                ),
                ("set_open", {"status": "open"}),
            ]
            trace_context = current_trace_context()
            for kind, payload in effects:
                outbox_id = uuid4()
                session.add(
                    Outbox(
                        id=outbox_id,
                        operation_key=f"handoff:{case_id}:{kind}",
                        source_event_id=source.id,
                        thread_id=source.thread_id,
                        identity_revision=revision,
                        account_id=source.account_id,
                        inbox_id=source.inbox_id,
                        conversation_id=source.conversation_id,
                        kind=kind,
                        payload_private={
                            **payload,
                            "case_id": str(case_id),
                            "depends_on": list(previous),
                            **({"_trace_context": trace_context} if trace_context else {}),
                        },
                        state="queued",
                    )
                )
                previous.append(str(outbox_id))
            session.flush()
            return self._result(case)

    def blocked(self, thread_id):
        with self.sessions() as session:
            return (
                session.scalar(
                    select(HumanCase.id)
                    .where(
                        HumanCase.thread_id == thread_id,
                        HumanCase.status.in_(["open", "transferred"]),
                    )
                    .limit(1)
                )
                is not None
            )

    async def reconcile_control(self, event, status):
        """status must be a server-verified channel observation, never a model argument."""
        if status not in {"open", "pending", "resolved", "snoozed"}:
            raise DomainError(
                "invalid_control_status", "Estado de control no permitido.", status=422
            )
        with self.sessions.begin() as session:
            source = self._event(session, event)
            cases = list(
                session.scalars(
                    select(HumanCase)
                    .where(
                        HumanCase.thread_id == source.thread_id,
                        HumanCase.account_id == source.account_id,
                        HumanCase.inbox_id == source.inbox_id,
                        HumanCase.conversation_id == source.conversation_id,
                        HumanCase.status.in_(["open", "transferred"]),
                    )
                    .with_for_update()
                )
            )
            for case in cases:
                transfer = session.scalar(
                    select(Outbox).where(Outbox.operation_key == f"handoff:{case.id}:set_open")
                )
                if transfer is None or transfer.state != "sent":
                    continue
                if case.status == "open":
                    case.status = "transferred"
                if status == "open":
                    case.open_observed = True
                elif (
                    status == "pending" and case.open_observed and source.id != case.source_event_id
                ):
                    case.status = "returned"
                    # Commit the return and its originating event together. A worker
                    # retry can recover the same marker even before a checkpoint exists.
                    case.return_event_id = source.id
            # A takeover observed during inference cancels its not-yet-sent message.
            if status != "pending":
                session.execute(
                    update(Outbox)
                    .where(
                        Outbox.thread_id == source.thread_id,
                        Outbox.account_id == source.account_id,
                        Outbox.inbox_id == source.inbox_id,
                        Outbox.conversation_id == source.conversation_id,
                        Outbox.state == "queued",
                        Outbox.kind.not_in(["private_note", "set_open", "handoff_notice"]),
                    )
                    .values(state="cancelled")
                )
            session.flush()
            thread_blocked = (
                session.scalar(
                    select(HumanCase.id)
                    .where(
                        HumanCase.thread_id == source.thread_id,
                        HumanCase.status.in_(["open", "transferred"]),
                    )
                    .limit(1)
                )
                is not None
            )
            return {
                "thread_blocked": thread_blocked,
                "cases": [self._result(case) for case in cases],
            }
