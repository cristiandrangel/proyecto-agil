import asyncio
import logging
import re
import signal
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from agil_shared.errors import DomainError
from sqlalchemy import select

from backend.agent.graph import build_graph
from backend.agent.media import MediaProcessor
from backend.agent.tools import ToolRuntime
from backend.integrations.observability import configure_logging, opaque_id
from backend.persistence.checkpoints import checkpointer, thread_config
from backend.persistence.models import InboxEvent, Outbox
from backend.persistence.queue import thread_lock
from backend.runtime import Runtime
from backend.services.delivery import DeliveryService
from backend.services.identity import decode_protected

logger = logging.getLogger("agil.worker")
HEARTBEAT_INTERVAL_SECONDS = 20
JOB_LEASE_SECONDS = 600
PAYMENT = re.compile(r"\[\[PAYMENT:([0-9a-fA-F-]{36})\]\]")


async def process_job(runtime, job):
    """Renew a fenced lease while media/inference awaits external services."""

    async def renew():
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            runtime.queue.heartbeat(job.id, job.claim_token, lease_seconds=JOB_LEASE_SECONDS)

    processing = asyncio.create_task(_process_job(runtime, job))
    heartbeat = asyncio.create_task(renew())
    try:
        done, _ = await asyncio.wait({processing, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
        if processing in done:
            # Completion fences its own claim. A concurrent final heartbeat may see
            # the just-completed state and correctly report stale; completion wins.
            return await processing
        if heartbeat in done:
            # A lost claim must stop the old worker before it can create further effects.
            await heartbeat
            raise DomainError("stale_claim", "Se perdió la reserva del trabajo.", 409)
        return await processing
    finally:
        processing.cancel()
        heartbeat.cancel()
        await asyncio.gather(processing, heartbeat, return_exceptions=True)


async def _process_job(runtime, job):
    event = job.event
    with runtime.observability.span(
        "conversation", event_id=event.id, thread_id=event.thread_id,
        input={"event_id": str(event.id), "source_id": event.thread_id,
               "account_id": event.account_id, "inbox_id": event.inbox_id,
               "conversation_id": event.conversation_id, "message_id": event.message_id},
    ) as trace:
        status = await _process_turn(runtime, job, trace=trace)
        if trace is not None:
            trace.update(status=status)


async def _process_turn(runtime, job, *, trace=None):
    event = job.event
    with runtime.sessions() as lock_session, thread_lock(lock_session, event.thread_id):
        local = event.account_id == "local"
        current = (
            {"status": "pending"}
            if local
            else await runtime.channel.conversation(event.conversation_id)
        )
        await runtime.handoff.reconcile_control(event, current["status"])
        if current["status"] != "pending" or runtime.handoff.blocked(event.thread_id):
            if trace is not None:
                trace.update(output={"status": "cancelled", "reason": "human_control"})
            runtime.queue.complete(job.id, job.claim_token)
            return "cancelled"
        snapshot = runtime.identity.snapshot(event.thread_id)
        if event.identity_revision != snapshot["identity_revision"]:
            if trace is not None:
                trace.update(output={"status": "cancelled", "reason": "identity_revision_changed"})
            runtime.queue.complete(job.id, job.claim_token)
            return "cancelled"
        with runtime.sessions() as session:
            existing = session.scalar(
                select(Outbox).where(Outbox.operation_key == f"response:{event.id}")
            )
            if existing:
                runtime.queue.complete(job.id, job.claim_token)
                return "completed"
        await runtime.events.record_incoming(event)
        with runtime.observability.span("identity_gate", event_id=event.id) as gate:
            protected = decode_protected(event.normalized_content, runtime.settings.session_secret)
            if protected is None:
                raise DomainError("unsafe_message", "Mensaje interno sin protección válida.", 422)
            if gate is not None:
                gate.update(
                    input={"identity": snapshot, "message": protected["agent_message"]},
                    output=protected,
                    status="handled" if protected["handled"] else "passed",
                )
            if trace is not None:
                trace.update(input={
                    "event_id": str(event.id), "source_id": event.thread_id,
                    "account_id": event.account_id, "inbox_id": event.inbox_id,
                    "conversation_id": event.conversation_id, "message_id": event.message_id,
                    "message": protected["agent_message"],
                    "identity_handled": protected["handled"], "attachments": event.attachments,
                })
        if protected["handled"]:
            reply = protected["response"] or "Envía tu consulta por escrito."
        else:
            text = protected["agent_message"] or ""
            if event.attachments:
                processor = MediaProcessor(
                    runtime.settings, runtime.inference, runtime.observability
                )
                media_context = await processor.process(event.attachments, event_id=event.id)
                text += "\n" + media_context
            tools = ToolRuntime(
                event, runtime.identity, runtime.central, runtime.handoff, runtime.observability
            )
            async with checkpointer(runtime.settings.memory_conninfo) as saver:
                graph = build_graph(saver, runtime=tools, inference=runtime.inference, text=text)
                with runtime.observability.span(
                    "agent", event_id=event.id, thread_id=event.thread_id,
                    input={"message": text, "identity": snapshot},
                ) as agent_trace:
                    if agent_trace is not None and getattr(runtime.observability, "capture_content", False):
                        previous = await graph.aget_state(thread_config(event.thread_id))
                        agent_trace.update(input={
                            "message": text, "identity": snapshot, "state_before": previous.values,
                        })
                    state = await graph.ainvoke({}, thread_config(event.thread_id))
                    if agent_trace is not None:
                        agent_trace.update(output={"state_after": state})
                group = next(
                    (g for g in state.get("messages", []) if g["id"] == str(event.id)), None
                )
                reply = group.get("reply") if group else None
                if not reply:
                    raise DomainError(
                        "response_missing", "No se generó una respuesta verificable.", 503
                    )
        snapshot = runtime.identity.snapshot(event.thread_id)
        if not runtime.handoff.blocked(event.thread_id):
            with runtime.observability.span(
                "response_enqueue", event_id=event.id, status="queued",
                input={"content": reply, "identity_revision": snapshot["identity_revision"]},
            ) as queued:
                saved_output = runtime.outbox.enqueue(
                    event_id=event.id,
                    identity_revision=snapshot["identity_revision"],
                    kind="message",
                    payload={"content": reply},
                    operation_key=f"response:{event.id}",
                )
                if queued is not None:
                    queued.update(output={"outbox_id": str(saved_output.id), "state": saved_output.state})
        if trace is not None:
            trace.update(output={
                "reply": reply,
                "identity": runtime.identity.snapshot(event.thread_id),
                "handoff_blocked": runtime.handoff.blocked(event.thread_id),
            })
        runtime.queue.complete(job.id, job.claim_token)

        return "completed"


async def render_payment_links(runtime, row, snapshot):
    content = row.payload_private.get("content", "")
    for order_id in set(PAYMENT.findall(content)):
        if not snapshot["verified"]:
            raise DomainError("identity_required", "Valida nuevamente el registro.", 403)
        order = await runtime.central.request(
            "GET", f"/orders/{order_id}", grant=snapshot["grant_token"]
        )
        capability = order.get("capability")
        if not capability:
            raise DomainError(
                "payment_link_unavailable", "No se pudo generar el enlace autorizado.", 503
            )
        link = f"{runtime.settings.public_base_url}/p/{order_id}?token={quote(capability, safe='')}"
        content = content.replace(f"[[PAYMENT:{order_id}]]", link)
    return content


async def send_outputs(runtime):
    if runtime.maintenance():
        return
    for row in runtime.outbox.queued(limit=20):
        if row.kind == "template":
            continue
        with runtime.observability.span(
            "delivery", event_id=row.source_event_id, thread_id=row.thread_id,
            trace_context=(row.payload_private or {}).get("_trace_context"),
            input={"outbox_id": str(row.id), "kind": row.kind,
                   "conversation_id": row.conversation_id, "payload": row.payload_private},
        ) as delivery:
            try:
                with runtime.sessions() as lock_session, thread_lock(lock_session, row.thread_id):
                    local = row.account_id == "local"
                    current = (
                        {"status": "pending"}
                        if local
                        else await runtime.channel.conversation(row.conversation_id)
                    )
                    snapshot = runtime.identity.snapshot(row.thread_id)
                    prepared = runtime.outbox.prepare(
                        row.id,
                        pending=current.get("status") == "pending",
                        identity_revision=snapshot["identity_revision"],
                    )
                    if prepared is None:
                        with runtime.sessions() as session:
                            saved = session.get(Outbox, row.id)
                            state = saved.state if saved else "deferred"
                        if delivery is not None:
                            delivery.update(status="cancelled" if state == "cancelled" else "deferred")
                        continue
                    try:
                        if row.kind == "set_open":
                            result = (
                                {"id": "local-open"}
                                if local
                                else await runtime.channel.set_open(row.conversation_id)
                            )
                        else:
                            content = await render_payment_links(runtime, row, snapshot)
                            if delivery is not None:
                                delivery.update(input={
                                    "outbox_id": str(row.id), "kind": row.kind,
                                    "conversation_id": row.conversation_id, "content": content,
                                })
                            result = (
                                {"id": "local-" + str(row.id)}
                                if local
                                else await runtime.channel.send_message(
                                    row.conversation_id,
                                    content,
                                    private=row.kind in {"private_note", "handoff_note"},
                                )
                            )
                        runtime.outbox.mark_sent(
                            row.id,
                            str(result.get("id", "status-open")),
                            claim_token=prepared.claim_token,
                        )
                        if delivery is not None:
                            delivery.update(output={"channel_response": result, "status": "sent"}, status="sent")
                        if local and row.kind == "message":
                            with runtime.sessions.begin() as session:
                                saved = session.get(Outbox, row.id)
                                saved.payload_private = {
                                    **saved.payload_private,
                                    "rendered_content": content,
                                }
                        if row.kind == "set_open" and row.source_event_id:
                            with runtime.sessions() as session:
                                event = session.get(InboxEvent, row.source_event_id)
                            await runtime.handoff.reconcile_control(event, "open")
                    except DomainError as exc:
                        if exc.code in {"channel_uncertain", "channel_unavailable"}:
                            runtime.outbox.mark_uncertain(row.id, claim_token=prepared.claim_token)
                        else:
                            runtime.outbox.mark_failed(row.id, claim_token=prepared.claim_token)
                        if delivery is not None:
                            delivery.update(status="uncertain" if exc.code in {
                                "channel_uncertain", "channel_unavailable"
                            } else "failed")
                            delivery.failed(error=exc)
                        logger.warning("send_failed code=%s output=%s", exc.code, row.id)
            except DomainError as exc:
                if delivery is not None:
                    delivery.update(status="deferred" if exc.code == "thread_busy" else "failed")
                    if exc.code != "thread_busy":
                        delivery.failed(error=exc)
                if exc.code != "thread_busy":
                    logger.warning("send_deferred code=%s output=%s", exc.code, row.id)


async def slot(runtime, stop, number):
    worker_id = f"worker-{uuid4()}-{number}"
    while not stop.is_set():
        job = None
        try:
            if runtime.maintenance():
                await asyncio.sleep(1)
                continue
            job = runtime.queue.claim(worker_id, lease_seconds=JOB_LEASE_SECONDS)
            if job:
                await process_job(runtime, job)
            elif number == 0:
                await send_outputs(runtime)
                await runtime.campaigns.dispatch_one()
                DeliveryService(runtime.sessions).reconcile_pending()
                await runtime.events.consume_once()
            await asyncio.sleep(0.2 if job else 1)
        except DomainError as exc:
            logger.warning("job_failed code=%s event=%s", exc.code, job.event_id if job else "none")
            if job:
                try:
                    retryable = exc.retryable and exc.code not in {
                        "inference_failed",
                        "inference_incomplete",
                    }
                    if not retryable or job.attempts >= 3:
                        if job.event.account_id != "local":
                            await runtime.handoff.request(
                                job.event,
                                reason="technical_failure",
                                summary=f"Fallo técnico: {exc.code}",
                            )
                        else:
                            snap = runtime.identity.snapshot(job.thread_id)
                            runtime.outbox.enqueue(
                                event_id=job.event_id,
                                identity_revision=snap["identity_revision"],
                                kind="message",
                                payload={"content": exc.message},
                                operation_key=f"response:{job.event_id}",
                            )
                    runtime.queue.fail(job.id, job.claim_token, exc.code, retryable=retryable)
                except DomainError:
                    pass
            await asyncio.sleep(1)
        except Exception as exc:
            # Nunca volcar la excepción o argumentos (pueden contener contactos o tokens).
            logger.error("worker_error type=%s ref=%s", type(exc).__name__, opaque_id(worker_id))
            if job:
                try:
                    runtime.queue.fail(job.id, job.claim_token, "internal_failure", retryable=False)
                except DomainError:
                    pass
            await asyncio.sleep(1)


async def main():
    configure_logging()
    runtime = Runtime()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async def heartbeat():
        while not stop.is_set():
            Path("/tmp/agil-worker-heartbeat").touch()
            await asyncio.sleep(5)

    tasks = [
        asyncio.create_task(slot(runtime, stop, i))
        for i in range(runtime.settings.worker_concurrency)
    ]
    tasks.append(asyncio.create_task(heartbeat()))
    await stop.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
