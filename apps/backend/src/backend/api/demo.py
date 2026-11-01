from uuid import UUID, uuid4

from agil_shared.errors import DomainError
from backend.api.operator import object_body, require_operator
from backend.api.webhooks import enqueue_message
from backend.persistence.models import InboxEvent, Outbox
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

router = APIRouter(dependencies=[Depends(require_operator)])


def allowed(runtime):
    if runtime.settings.app_env not in {"local", "development", "test"} or not runtime.settings.enable_local_message_endpoint:
        raise DomainError("local_endpoint_disabled", "Entrada local deshabilitada.", 403)


@router.post("/api/demo/messages")
async def message(request: Request):
    runtime = request.app.state.runtime
    allowed(runtime)
    body = await object_body(request)
    if body.get("live_inference") is not True:
        raise DomainError("inference_opt_in", "Activa live_inference para usar el LLM real en la prueba local.", 422)
    source = body.get("source_id")
    content = body.get("content", "")
    if not isinstance(content, str) or len(content) > 20000:
        raise DomainError("invalid_message", "Mensaje inválido.", 422)
    result = await enqueue_message(runtime, source_id=source, content=content, attachments=body.get("attachments", []),
        message_id=str(body.get("message_id") or uuid4()), account_id="local", inbox_id="local",
        conversation_id=str(body.get("conversation_id") or "local-demo"))
    return {"event_id": str(result["event"].id), "duplicate": result["duplicate"], "status": "queued"}


@router.get("/api/demo/messages/{event_id}")
async def result(request: Request, event_id: UUID):
    runtime = request.app.state.runtime
    allowed(runtime)
    with runtime.sessions() as session:
        event = session.get(InboxEvent, event_id)
        if not event or event.account_id != "local":
            raise DomainError("event_not_found", "Mensaje no encontrado.", 404)
        rows = list(session.scalars(select(Outbox).where(Outbox.source_event_id == event_id)))
        return {"status": event.status, "responses": [
            {"content": row.payload_private.get("rendered_content", row.payload_private.get("content", "")), "state": row.state}
            for row in rows if row.kind in {"message", "handoff_notice"}
        ]}
