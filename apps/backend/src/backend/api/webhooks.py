import json
from datetime import datetime, timezone
from types import SimpleNamespace

from agil_shared.errors import DomainError
from backend.integrations.chatwoot import verify_signature
from backend.persistence.models import InboxEvent, ResetMetadata, utcnow
from backend.services.delivery import DeliveryService
from backend.services.events import EventService
from backend.services.human_memory import HumanMemory
from backend.services.identity import decode_protected
from fastapi import APIRouter, Request
from sqlalchemy import select

router = APIRouter()


async def enqueue_message(
    runtime, *, source_id, content, attachments, message_id, account_id, inbox_id, conversation_id
):
    def persist(safe_content):
        protected = decode_protected(safe_content, runtime.settings.session_secret)
        event, _ = runtime.queue.enqueue(
            account_id=account_id,
            inbox_id=inbox_id,
            conversation_id=conversation_id,
            message_id=message_id,
            source_id=source_id,
            content=safe_content,
            attachments=[]
            if protected and (protected["handled"] or "sealed_auth" in protected)
            else attachments,
            identity_revision=runtime.identity.snapshot(source_id)["identity_revision"],
        )
        return event

    return await runtime.identity.protect_incoming(
        source_id,
        content,
        bool(attachments),
        message_id,
        persist=persist,
        account_id=account_id,
    )


@router.post("/webhooks/chatwoot")
async def webhook(request: Request):
    runtime = request.app.state.runtime
    cfg = runtime.settings
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 524288:
            raise DomainError("payload_too_large", "Evento demasiado grande.", 413)
    verify_signature(cfg, request.headers, bytes(raw))
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError
    except (ValueError, UnicodeError):
        raise DomainError("invalid_json", "Evento JSON inválido.", 422) from None
    conversation = body.get("conversation") or {}
    account_data, inbox_data = body.get("account") or {}, body.get("inbox") or {}
    if not all(isinstance(value, dict) for value in (conversation, account_data, inbox_data)):
        raise DomainError("invalid_channel_event", "Estructura del evento inválida.", 422)
    account = account_data.get("id", conversation.get("account_id"))
    inbox = inbox_data.get("id", conversation.get("inbox_id"))
    if str(account) != str(cfg.chatwoot_account_id) or str(inbox) != str(cfg.chatwoot_inbox_id):
        raise DomainError("wrong_channel", "Evento fuera de la bandeja de prueba.", 403)
    if body.get("event") == "message_updated":
        if body.get("message_type") not in ("outgoing", 1) or body.get("private") not in (
            None,
            False,
        ):
            return {"accepted": False, "reason": "ignored_delivery_event"}
        if runtime.maintenance():
            raise DomainError("maintenance", "Demo en restauración. Reintenta después.", 429, True)
        return DeliveryService(runtime.sessions).record(
            {**body, "account": {"id": account}, "inbox": {"id": inbox}}
        )
    sender = body.get("sender") or {}
    human_outgoing = (
        body.get("message_type") in ("outgoing", 1)
        and isinstance(sender, dict) and sender.get("type") == "user"
    )
    if (
        body.get("event") != "message_created"
        or (body.get("message_type") not in ("incoming", 0) and not human_outgoing)
        or body.get("private") not in (None, False)
    ):
        return {"accepted": False, "reason": "ignored_event"}
    if runtime.maintenance():
        raise DomainError("maintenance", "Demo en restauración. Reintenta después.", 429, True)
    contact_inbox = conversation.get("contact_inbox") or {}
    if not isinstance(contact_inbox, dict):
        raise DomainError("invalid_channel_event", "Identidad de canal inválida.", 422)
    source = contact_inbox.get("source_id")
    message_id, conversation_id = body.get("id"), conversation.get("id")
    if (
        not isinstance(source, str)
        or not source
        or type(message_id) is not int
        or type(conversation_id) is not int
        or message_id <= 0
        or conversation_id <= 0
    ):
        raise DomainError("invalid_channel_event", "Falta identidad o destino del mensaje.", 422)
    created_at = body.get("created_at")
    event_time = utcnow()
    if created_at is not None:
        try:
            if type(created_at) not in {int, float, str}:
                raise ValueError
            event_time = (
                datetime.fromtimestamp(created_at, timezone.utc)
                if isinstance(created_at, (int, float))
                else datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            )
            if event_time.tzinfo is None:
                raise ValueError
            with runtime.sessions() as session:
                metadata = session.get(ResetMetadata, "demo")
                if metadata and event_time < metadata.reset_at:
                    return {"accepted": False, "reason": "before_reset"}
        except (ValueError, TypeError, OverflowError):
            raise DomainError("invalid_event_time", "Fecha del mensaje inválida.", 422) from None
    content = body.get("content") if body.get("content") is not None else ""
    attachments = body.get("attachments") if body.get("attachments") is not None else []
    if (
        not isinstance(content, str)
        or len(content) > 20000
        or not isinstance(attachments, list)
        or len(attachments) > 5
    ):
        raise DomainError("invalid_message", "Mensaje fuera de los límites de la demo.", 422)
    passive_event = SimpleNamespace(
        account_id=str(account), inbox_id=str(inbox), conversation_id=str(conversation_id),
        message_id=str(message_id), thread_id=source, received_at=event_time,
    )
    if human_outgoing:
        return HumanMemory(runtime.sessions).record(
            passive_event, speaker="advisor", content=content, attachments=attachments
        )
    # Contactability is independent of bot control. Persist only authenticated
    # channel metadata; human-owned conversations never enter the content queue.
    await EventService(session_factory=runtime.sessions).record_incoming(
        SimpleNamespace(
            account_id=str(account),
            inbox_id=str(inbox),
            conversation_id=str(conversation_id),
            message_id=str(message_id),
            thread_id=source,
            received_at=event_time,
        )
    )
    # Signed event metadata is enough to acknowledge promptly. The worker rechecks
    # authoritative channel control before any authentication, media or inference.
    if conversation.get("status") is not None and conversation.get("status") != "pending":
        if conversation.get("status") == "open":
            HumanMemory(runtime.sessions).record(
                passive_event, speaker="customer", content=content, attachments=attachments
            )
        return {"accepted": False, "reason": "human_control"}
    try:
        result = await enqueue_message(
            runtime,
            source_id=source,
            content=content,
            attachments=attachments,
            message_id=str(message_id),
            account_id=str(account),
            inbox_id=str(inbox),
            conversation_id=str(conversation_id),
        )
    except DomainError as exc:
        if exc.code == "thread_busy":
            raise DomainError(
                "thread_busy", "La conversación está ocupada; reintenta la entrega.", 429, True
            ) from None
        raise
    return {"accepted": True, "duplicate": result["duplicate"]}


def event_by_id(runtime, event_id):
    with runtime.sessions() as session:
        return session.scalar(select(InboxEvent).where(InboxEvent.id == event_id))
