"""Real queue/checkpoint integration, signed webhook fixtures and mocked providers."""

import asyncio
import hashlib
import hmac
import json
import os
import time
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from agil_shared.errors import DomainError
from backend.api.webhooks import router
from backend.persistence.checkpoints import checkpointer, thread_config
from backend.persistence.models import (
    Base,
    ConversationJob,
    InboxEvent,
    Outbox,
    utcnow,
)
from backend.persistence.outbox import OutboxStore
from backend.persistence.queue import Queue, thread_lock
from backend.services.events import EventService
from backend.services.handoff import HandoffService
from backend.services.identity import (
    PIN_INSTRUCTIONS,
    IdentityService,
    decode_protected,
    encode_protected,
)
from backend.worker import process_job, send_outputs
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def worker_store():
    url = os.getenv("TEST_MEMORY_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_MEMORY_DATABASE_URL for real PostgreSQL webhook/worker tests")
    schema = "webhook_worker_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(scoped)
    conninfo = (
        make_url(url)
        .set(drivername="postgresql")
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    yield sessionmaker(scoped, expire_on_commit=False), conninfo
    scoped.dispose()
    with engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


class Central:
    def __init__(self):
        self.customer = uuid4()
        self.candidate = uuid4()
        self.calls = []
        self.failure = None

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/identity/locate":
            return {
                "candidate_count": 1,
                "candidates": [
                    {"candidate_reference": str(self.candidate), "masked_hint": "F*** · CC ***001"}
                ],
            }
        if path == "/identity/verify":
            if self.failure:
                raise self.failure
            return {
                "customer_id": str(self.customer),
                "grant_token": "PRIVATE-RUNTIME-GRANT",
                "expires_at": (utcnow() + timedelta(minutes=20)).isoformat(),
            }
        if path == "/identity/revoke":
            return {"revoked": True}
        raise AssertionError(path)


class Channel:
    def __init__(self):
        self.status = "pending"
        self.sent = []
        self.reads = []
        self.failure = None

    async def conversation(self, conversation_id):
        self.reads.append(str(conversation_id))
        return {"id": int(conversation_id), "inbox_id": 7, "status": self.status, "can_reply": True}

    async def send_message(self, conversation_id, content, *, private=False):
        self.sent.append((str(conversation_id), content, private))
        if self.failure:
            raise self.failure
        return {"id": len(self.sent)}

    async def set_open(self, conversation_id):
        self.status = "open"
        return {"id": "status-open"}


class Output(SimpleNamespace):
    def model_dump(self, **_):
        return dict(vars(self))


class Inference:
    def __init__(self):
        self.settings = SimpleNamespace(
            ai_max_calls_per_turn=5, ai_max_input_tokens=12000, history_visible_messages=20
        )
        self.calls = []

    async def response(self, **kwargs):
        self.calls.append(kwargs)
        reply = "Respuesta ficticia " + str(len(self.calls))
        return SimpleNamespace(
            output=[
                Output(
                    type="message",
                    id="msg_" + uuid4().hex,
                    role="assistant",
                    status="completed",
                    content=[{"type": "output_text", "text": reply, "annotations": []}],
                )
            ],
            output_text=reply,
        )


class Observability:
    """Record backend span payloads without invoking an external exporter."""

    capture_content = True

    def __init__(self):
        self.calls = []

    @contextmanager
    def span(self, name, **kwargs):
        record = {"name": name, **kwargs, "updates": [], "failures": []}
        self.calls.append(record)
        yield SimpleNamespace(
            update=lambda **values: record["updates"].append(values),
            failed=lambda **values: record["failures"].append(values),
        )


@pytest.fixture
def runtime(worker_store):
    sessions, conninfo = worker_store
    settings = SimpleNamespace(
        session_secret=SecretStr("fictional-webhook-worker-session" * 2),
        chatwoot_webhook_secret=SecretStr("fictional-webhook-signature"),
        chatwoot_webhook_auth_mode="hmac",
        chatwoot_webhook_tolerance_seconds=300,
        chatwoot_account_id=9,
        chatwoot_inbox_id=7,
        memory_conninfo=conninfo,
        public_base_url="http://demo.example",
        app_env="test",
        enable_local_message_endpoint=True,
    )
    central = Central()
    instance = SimpleNamespace(
        settings=settings,
        sessions=sessions,
        central=central,
        channel=Channel(),
        inference=Inference(),
        queue=Queue(sessions),
        outbox=OutboxStore(sessions),
        maintenance=lambda: False,
        observability=Observability(),
    )
    instance.identity = IdentityService(settings, sessions, central)
    instance.handoff = HandoffService(settings, sessions)
    instance.events = EventService(None, sessions)
    return instance


@pytest.fixture
def webapp(runtime):
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router)

    @app.exception_handler(DomainError)
    async def errors(request, exc):
        return JSONResponse(exc.as_dict(), status_code=exc.status)

    return app


def payload(
    source=" whatsapp:CO.DEMO#opaque ", *, message=101, conversation=11, content="Hola ficticio"
):
    return {
        "event": "message_created",
        "id": message,
        "account": {"id": 9},
        "inbox": {"id": 7},
        "message_type": "incoming",
        "private": False,
        "content": content,
        "source_id": "TOP-LEVEL-EXTERNAL-MESSAGE-ID-NOT-THREAD",
        "conversation": {
            "id": conversation,
            "account_id": 9,
            "inbox_id": 7,
            "contact_inbox": {"source_id": source},
        },
    }


def signed(runtime, body):
    raw = json.dumps(body, ensure_ascii=False, indent=2).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        runtime.settings.chatwoot_webhook_secret.get_secret_value().encode(),
        timestamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return raw, {
        "Content-Type": "application/json",
        "X-Chatwoot-Timestamp": timestamp,
        "X-Chatwoot-Signature": "sha256=" + signature,
    }


async def post(client, runtime, body):
    raw, headers = signed(runtime, body)
    return await client.post("/webhooks/chatwoot", content=raw, headers=headers)


@pytest.mark.asyncio
async def test_webhook_literal_source_durable_ack_and_duplicate_without_llm(runtime, webapp):
    body = payload()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json() == {"accepted": True, "duplicate": False}
        assert (await post(client, runtime, body)).json() == {"accepted": True, "duplicate": True}
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 1
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 1
        event = session.scalar(select(InboxEvent))
        assert event.thread_id == body["conversation"]["contact_inbox"]["source_id"]
        assert event.thread_id != body["source_id"] and event.conversation_id == "11"
        assert (
            decode_protected(event.normalized_content, runtime.settings.session_secret)[
                "agent_message"
            ]
            == "Hola ficticio"
        )
    assert not runtime.inference.calls and not runtime.channel.reads


@pytest.mark.asyncio
async def test_wrong_inbox_private_outgoing_and_unsigned_never_enqueue(runtime, webapp):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        bad = payload()
        bad["inbox"]["id"] = 999
        assert (await post(client, runtime, bad)).status_code == 403
        for changes in (
            {"private": True},
            {"message_type": "outgoing"},
            {"event": "conversation_status_changed"},
        ):
            body = {**payload(), **changes}
            assert (await post(client, runtime, body)).json()["accepted"] is False
        assert (await client.post("/webhooks/chatwoot", json=payload())).status_code == 401
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0
    assert not runtime.channel.reads and not runtime.inference.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"conversation": "invalid"},
        {"conversation": {"id": 11, "contact_inbox": "invalid"}},
        {"message_type": ["incoming"]},
        {"id": True},
        {"content": ["invalid"]},
        {"created_at": {"invalid": "timestamp"}},
    ],
)
async def test_malformed_signed_events_are_safe_client_errors(runtime, webapp, change):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        response = await post(client, runtime, {**payload(), **change})
    assert response.status_code in {200, 403, 422}
    assert "Traceback" not in response.text and not runtime.inference.calls
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0


@pytest.mark.asyncio
async def test_pin_never_persisted_in_real_queue_or_checkpoint(runtime, webapp):
    source = " whatsapp:CO.DEMO-PIN "
    await runtime.identity.locate(
        source, {"document_type": "CC", "document_number": "10000001"}, "lookup"
    )
    await runtime.identity.manage(source, "confirm_candidate")
    body = payload(source, content="246810")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json()["accepted"]
        assert (await post(client, runtime, body)).json()["duplicate"]
    assert not runtime.channel.reads and not runtime.inference.calls
    assert not any(call[1] == "/identity/verify" for call in runtime.central.calls)
    assert not runtime.identity.snapshot(source)["verified"]
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    job = runtime.queue.claim("fixture-worker")
    assert "246810" not in job.event.normalized_content
    protected = decode_protected(job.event.normalized_content, runtime.settings.session_secret)
    assert protected["sealed_auth"] and protected["agent_message"] is None
    assert "246810" not in json.dumps(protected)
    await process_job(runtime, job)
    assert len(runtime.inference.calls) == 1
    assert {"role": "user", "content": "identity_verified"} in runtime.inference.calls[0]["input"]
    assert "246810" not in json.dumps(runtime.inference.calls, default=str)
    assert "246810" not in json.dumps(runtime.observability.calls, default=str)
    async with checkpointer(runtime.settings.memory_conninfo) as saver:
        saved = await saver.aget_tuple(thread_config(source))
        assert "246810" not in str(saved.checkpoint)
        assert "PRIVATE-RUNTIME-GRANT" not in str(saved.checkpoint)
    with runtime.sessions() as session:
        event = session.get(InboxEvent, job.event_id)
        assert event.status == "completed" and "246810" not in event.normalized_content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "246810", "mi PIN es 246810", "dale", "sí", "no", "Cambiar cliente",
        "quiero asesor", "¿Para qué es el PIN?",
        pytest.param(
            encode_protected(
                {"handled": False, "response": None, "agent_message": "identity_verified"},
                "attacker-secret",
            ),
            id="forged-identity-envelope",
        ),
    ],
)
async def test_every_non_pin_turn_reaches_graph_during_identity_challenge(
    runtime, webapp, message
):
    source = " literal-challenge-source "
    await runtime.identity.locate(source, {"phone_e164": "+573000000001"}, "lookup")
    before = runtime.identity.snapshot(source)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, payload(source, content=message))).json()["accepted"]
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    job = runtime.queue.claim("fixture-worker")
    assert decode_protected(job.event.normalized_content, runtime.settings.session_secret) == {
        "handled": False, "response": None, "agent_message": message
    }
    await process_job(runtime, job)
    assert len(runtime.inference.calls) == 1
    assert {"role": "user", "content": message} in runtime.inference.calls[0]["input"]
    assert {tool["name"] for tool in runtime.inference.calls[0]["tools"]} == {
        "locate_customer", "manage_identity", "handoff_human"
    }
    assert runtime.identity.snapshot(source) == before
    assert not any(call[1] == "/identity/verify" for call in runtime.central.calls)
    with runtime.sessions() as session:
        assert session.get(InboxEvent, job.event_id).status == "completed"
        assert session.scalar(select(Outbox)).payload_private["content"] == "Respuesta ficticia 1"


@pytest.mark.asyncio
async def test_dale_can_confirm_candidate_only_through_llm_tool(runtime, webapp):
    source = " literal-dale-source "
    await runtime.identity.locate(source, {"phone_e164": "+573000000001"}, "lookup")
    original = runtime.inference.response

    async def response(**kwargs):
        result = await original(**kwargs)
        if len(runtime.inference.calls) == 1:
            return SimpleNamespace(
                output=[Output(
                    type="function_call", id="fc-confirm", call_id="call-confirm",
                    name="manage_identity", arguments=json.dumps({"action": "confirm_candidate"}),
                )],
                output_text="",
            )
        return result

    runtime.inference.response = response
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, payload(source, content="dale"))).json()["accepted"]
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    await process_job(runtime, runtime.queue.claim("fixture-worker"))
    assert len(runtime.inference.calls) == 1
    assert {"role": "user", "content": "dale"} in runtime.inference.calls[0]["input"]
    with runtime.sessions() as session:
        assert session.scalar(select(Outbox)).payload_private["content"] == PIN_INSTRUCTIONS
    snapshot = runtime.identity.snapshot(source)
    assert snapshot["challenge_state"] == "awaiting_pin"
    assert not snapshot["verified"] and snapshot["grant_token"] is None
    assert not any(call[1] == "/identity/verify" for call in runtime.central.calls)


@pytest.mark.asyncio
async def test_auth_questions_return_to_llm_only_after_three_failures(runtime, webapp):
    source = "literal-exhausted-source"
    await runtime.identity.locate(source, {"phone_e164": "+573000000001"}, "lookup")
    await runtime.identity.manage(source, "confirm_candidate")
    revision = runtime.identity.snapshot(source)["identity_revision"]
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    messages = ["¿Por qué necesitas validar mi identidad?", "quiero asesor", "no quiero compartir el código"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for index, message in enumerate(messages, 1):
            body = payload(source, message=600 + index, content=message)
            assert (await post(client, runtime, body)).json()["accepted"]
            assert (await post(client, runtime, body)).json()["duplicate"]
            assert runtime.identity.snapshot(source)["auth_failures"] == index - 1
            job = runtime.queue.claim("fixture-worker")
            assert message not in job.event.normalized_content
            await process_job(runtime, job)
            assert runtime.identity.snapshot(source)["auth_failures"] == index
            assert len(runtime.inference.calls) == (index == 3)
    snapshot = runtime.identity.snapshot(source)
    assert snapshot["challenge_state"] == "none" and snapshot["identity_revision"] > revision
    assert not snapshot["verified"] and snapshot["grant_token"] is None
    assert runtime.inference.calls[0]["input"] == [
        {"role": "user", "content": "auth_attempts_exhausted"}
    ]
    for message in messages:
        assert message not in json.dumps(runtime.inference.calls, default=str)
        assert message not in json.dumps(runtime.observability.calls, default=str)
    async with checkpointer(runtime.settings.memory_conninfo) as saver:
        saved = await saver.aget_tuple(thread_config(source))
        assert "auth_attempts_exhausted" in str(saved.checkpoint)
        for message in messages:
            assert message not in str(saved.checkpoint)
    assert not any(call[1] == "/identity/verify" for call in runtime.central.calls)


@pytest.mark.asyncio
async def test_same_thread_two_conversations_keep_distinct_outbox_destinations(runtime, webapp):
    source = " raw-source:two-conversations "
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for number, conversation in [(101, 11), (102, 22)]:
            assert (
                await post(
                    client, runtime, payload(source, message=number, conversation=conversation)
                )
            ).status_code == 200
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    for _ in range(2):
        await process_job(runtime, runtime.queue.claim("fixture-worker"))
    with runtime.sessions() as session:
        outputs = list(session.scalars(select(Outbox).order_by(Outbox.created_at)))
        assert len(outputs) == 2 and outputs[0].source_event_id != outputs[1].source_event_id
        assert [row.conversation_id for row in outputs] == ["11", "22"]
        assert all(
            row.thread_id == source and row.account_id == "9" and row.inbox_id == "7"
            for row in outputs
        )
    await send_outputs(runtime)
    assert [(conversation, content) for conversation, content, _ in runtime.channel.sent] == [
        ("11", "Respuesta ficticia 1"),
        ("22", "Respuesta ficticia 2"),
    ]
    assert "Respuesta ficticia 1" in json.dumps(runtime.inference.calls[1]["input"])


@pytest.mark.asyncio
async def test_revision_fence_discards_queued_old_identity_before_inference(runtime, webapp):
    body = payload()
    source = body["conversation"]["contact_inbox"]["source_id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).status_code == 200
    await runtime.identity.invalidate(source)
    job = runtime.queue.claim("fixture-worker")
    await process_job(runtime, job)
    assert not runtime.inference.calls
    with runtime.sessions() as session:
        assert session.get(InboxEvent, job.event_id).status == "completed"
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0


@pytest.mark.asyncio
async def test_ingress_acks_while_worker_thread_lock_is_busy(runtime, webapp):
    body = payload(content="246810")
    source = body["conversation"]["contact_inbox"]["source_id"]
    with runtime.sessions() as session, thread_lock(session, source):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(webapp), base_url="http://testserver"
        ) as client:
            response = await post(client, runtime, body)
    assert response.status_code == 200 and response.json()["accepted"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 1
    assert not runtime.channel.reads and not runtime.inference.calls


@pytest.mark.asyncio
async def test_sender_rechecks_pending_cancels_and_never_repeats_uncertain(runtime):
    source = "literal-send-source"
    snapshot = runtime.identity.snapshot(source)
    rows = []
    for message, conversation in [(101, 11), (102, 22)]:
        event, _ = runtime.queue.enqueue(
            account_id="9",
            inbox_id="7",
            conversation_id=str(conversation),
            message_id=str(message),
            source_id=source,
        )
        rows.append(
            runtime.outbox.enqueue(
                event_id=event.id,
                identity_revision=snapshot["identity_revision"],
                kind="message",
                payload={"content": "Demo response"},
                operation_key="send-" + str(message),
            )
        )
    runtime.channel.status = "open"
    await send_outputs(runtime)
    assert not runtime.channel.sent
    with runtime.sessions() as session:
        assert all(session.get(Outbox, row.id).state == "cancelled" for row in rows)
    event, _ = runtime.queue.enqueue(
        account_id="9", inbox_id="7", conversation_id="33", message_id="103", source_id=source
    )
    row = runtime.outbox.enqueue(
        event_id=event.id,
        identity_revision=0,
        kind="message",
        payload={"content": "Uncertain response"},
        operation_key="uncertain-send",
    )
    runtime.channel.status = "pending"
    runtime.channel.failure = DomainError("channel_uncertain", "Provider result uncertain", 503)
    await send_outputs(runtime)
    await send_outputs(runtime)
    assert len(runtime.channel.sent) == 1 and runtime.channel.sent[0][0] == "33"
    with runtime.sessions() as session:
        assert session.get(Outbox, row.id).state == "uncertain"


@pytest.mark.asyncio
async def test_local_handoff_scope_explicitly_allowed_but_denied_in_production(runtime):
    event, _ = runtime.queue.enqueue(
        account_id="local",
        inbox_id="local",
        conversation_id="local-demo",
        message_id="local-scope",
        source_id="literal-local-source",
    )
    assert not (await runtime.handoff.reconcile_control(event, "pending"))["thread_blocked"]
    await runtime.handoff.request(event, "requested", "Local simulated request")
    assert runtime.handoff.blocked(event.thread_id)
    runtime.settings.app_env = "production"
    with pytest.raises(DomainError) as caught:
        await runtime.handoff.reconcile_control(event, "pending")
    assert caught.value.status == 403
    runtime.settings.app_env = "test"
    runtime.settings.enable_local_message_endpoint = False
    with pytest.raises(DomainError):
        await runtime.handoff.reconcile_control(event, "pending")


@pytest.mark.asyncio
async def test_job_heartbeat_renews_lease_and_stops_after_completion(runtime, monkeypatch):
    import backend.worker as worker

    event, _ = runtime.queue.enqueue(
        account_id="local",
        inbox_id="local",
        conversation_id="demo",
        message_id="heartbeat",
        source_id="heartbeat-source",
    )
    job = runtime.queue.claim("fixture-worker")
    calls = []
    original = runtime.queue.heartbeat

    def heartbeat(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    async def processing(runtime, job):
        await asyncio.sleep(0.035)
        runtime.queue.complete(job.id, job.claim_token)

    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "_process_job", processing)
    monkeypatch.setattr(runtime.queue, "heartbeat", heartbeat)
    await worker.process_job(runtime, job)
    assert len(calls) >= 2 and all(call["lease_seconds"] == 600 for call in calls)
    count = len(calls)
    await asyncio.sleep(0.025)
    assert len(calls) == count


@pytest.mark.asyncio
async def test_lost_heartbeat_claim_cancels_processing_before_effects(runtime, monkeypatch):
    import backend.worker as worker

    event, _ = runtime.queue.enqueue(
        account_id="local",
        inbox_id="local",
        conversation_id="demo",
        message_id="lost-heartbeat",
        source_id="heartbeat-source",
    )
    job = runtime.queue.claim("fixture-worker")
    cancelled = asyncio.Event()

    def heartbeat(*args, **kwargs):
        raise DomainError("stale_claim", "Claim lost", 409)

    async def processing(runtime, job):
        try:
            await asyncio.sleep(1)
            pytest.fail("Lost worker cannot continue effects")
        finally:
            cancelled.set()

    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "_process_job", processing)
    monkeypatch.setattr(runtime.queue, "heartbeat", heartbeat)
    with pytest.raises(DomainError) as caught:
        await worker.process_job(runtime, job)
    assert caught.value.code == "stale_claim" and cancelled.is_set()


def accepted_template(runtime, *, message_id="555", state="sent", mode="live"):
    from backend.persistence.models import Campaign, CampaignRecipient

    with runtime.sessions.begin() as session:
        campaign = Campaign(
            status="completed",
            filter_snapshot={},
            template_snapshot={"name": "delivery fixture"},
            launched_at=utcnow() - timedelta(minutes=1),
            followup_until=utcnow() + timedelta(hours=1),
        )
        session.add(campaign)
        session.flush()
        customer, debt, recipient_id = uuid4(), uuid4(), uuid4()
        recipient = CampaignRecipient(
            id=recipient_id,
            campaign_id=campaign.id,
            customer_id=customer,
            selected_debt_ids=[str(debt)],
            contact_version=1,
            position=0,
            delivery_mode=mode,
            destination_binding={"debt_balances": {str(debt): 10000}},
            account_id="9",
            inbox_id="7",
            conversation_id="11",
            thread_id="literal-delivery-scope",
            send_status="sent" if state == "sent" else "uncertain",
            sent_at=utcnow() - timedelta(seconds=20),
        )
        output = Outbox(
            operation_key=f"campaign:{campaign.id}:recipient:{recipient_id}",
            thread_id=recipient.thread_id,
            identity_revision=0,
            account_id="9",
            inbox_id="7",
            conversation_id="11",
            kind="template",
            payload_private={},
            state=state,
            channel_message_id=message_id if state == "sent" else None,
            lease_until=utcnow() + timedelta(seconds=60),
        )
        session.add_all([recipient, output])
        session.flush()
        return campaign.id, recipient.id, output.id


def delivery_payload(status=None, *, message=555, conversation=11):
    body = payload(
        message=message,
        conversation=conversation,
        content="PIN 246810 https://demo.example/p/x?token=PRIVATE-CAPABILITY",
    )
    body.update(event="message_updated", message_type="outgoing", updated_at=utcnow().isoformat())
    body["conversation"].pop("contact_inbox")
    if status is not None:
        body["status"] = status
    return body


@pytest.mark.asyncio
async def test_delivery_exact_message_dedup_metrics_without_new_turn_or_raw_payload(
    runtime, webapp
):
    from backend.persistence.models import BusinessEvent, ChannelDeliveryEvent, VerifiedContext
    from backend.services.metrics import MetricsService

    campaign_id, _, _ = accepted_template(runtime)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for status in ("delivered", "read", "read", "failed", "failed"):
            response = await post(client, runtime, delivery_payload(status))
            assert response.status_code == 200 and response.json()["processed"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ChannelDeliveryEvent)) == 3
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 3
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
        assert session.scalar(select(func.count()).select_from(VerifiedContext)) == 0
        for receipt in session.scalars(select(ChannelDeliveryEvent)):
            assert "246810" not in str(vars(receipt)) and "PRIVATE-CAPABILITY" not in str(
                vars(receipt)
            )
    metrics = await MetricsService(runtime.sessions).get(campaign_id)
    assert (
        metrics["messages_sent"],
        metrics["unique_sent"],
        metrics["delivered_known"],
        metrics["failed"],
        metrics["unique_replied"],
    ) == (1, 1, 1, 1, 0)
    assert not runtime.inference.calls and not runtime.channel.sent and not runtime.channel.reads


@pytest.mark.asyncio
async def test_delivery_early_receipt_survives_restart_until_message_id_mapping(runtime, webapp):
    from backend.persistence.models import BusinessEvent, CampaignRecipient, ChannelDeliveryEvent
    from backend.services.delivery import DeliveryService

    _, recipient_id, outbox_id = accepted_template(runtime, state="sending")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        response = await post(client, runtime, delivery_payload("delivered"))
    assert response.json()["pending"] and not response.json()["processed"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(ChannelDeliveryEvent)).outbox_id is None
    runtime.outbox.mark_sent(outbox_id, "555")
    with runtime.sessions.begin() as session:
        session.get(CampaignRecipient, recipient_id).send_status = "sent"
    resumed = DeliveryService(runtime.sessions)
    assert resumed.reconcile_pending() == 1 and resumed.reconcile_pending() == 0
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 1
        assert session.scalar(select(ChannelDeliveryEvent)).processed_at is not None


@pytest.mark.asyncio
async def test_installed_payload_nested_status_requires_exact_updated_message_id(runtime, webapp):
    from backend.persistence.models import BusinessEvent, ChannelDeliveryEvent

    accepted_template(runtime)
    nested = delivery_payload()
    nested["conversation"]["messages"] = [
        {"id": 555, "account_id": 9, "inbox_id": 7, "conversation_id": 11, "status": "read"}
    ]
    other = delivery_payload(message=556)
    other["conversation"]["messages"] = [
        {"id": 555, "account_id": 9, "inbox_id": 7, "conversation_id": 11, "status": "delivered"}
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, nested)).json()["processed"]
        assert (await post(client, runtime, other)).json()["pending"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 1
        unknown = session.scalar(
            select(ChannelDeliveryEvent).where(ChannelDeliveryEvent.message_id == "556")
        )
        assert (
            unknown.delivery_status == "unknown"
            and unknown.pending_reason == "status_missing"
            and unknown.processed_at is None
        )


@pytest.mark.asyncio
async def test_delivery_scope_private_incoming_simulated_and_wrong_mapping_cannot_attribute(
    runtime, webapp
):
    from backend.persistence.models import BusinessEvent

    accepted_template(runtime, mode="simulated")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for changes in ({"private": True}, {"message_type": "incoming"}):
            response = await post(client, runtime, {**delivery_payload("read"), **changes})
            assert not response.json()["accepted"]
        wrong = delivery_payload("read")
        wrong["inbox"]["id"] = 999
        assert (await post(client, runtime, wrong)).status_code == 403
        assert (await post(client, runtime, delivery_payload("read"))).json()["pending"]
        assert (await post(client, runtime, delivery_payload("read", message=999))).json()[
            "pending"
        ]
        mismatch = delivery_payload()
        mismatch["conversation"]["messages"] = [{"id": 555, "status": "read", "inbox_id": 999}]
        assert (await post(client, runtime, mismatch)).status_code == 403
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
    assert not runtime.inference.calls and not runtime.channel.sent


@pytest.mark.asyncio
async def test_delivery_receipts_clear_on_reset_and_migration_roundtrip_matches_metadata(runtime):
    import runpy
    from pathlib import Path

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from backend.persistence.models import ChannelDeliveryEvent
    from backend.persistence.reset import reset_operational
    from backend.services.delivery import DeliveryService

    accepted_template(runtime)
    assert DeliveryService(runtime.sessions).record(delivery_payload("read"))["processed"]
    reset_operational(event_cutoff=0, session_factory=runtime.sessions)
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ChannelDeliveryEvent)) == 0
    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "migrations/backend/versions/0003_channel_delivery_receipts.py"
        )
    )
    with runtime.sessions().get_bind().begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration["downgrade"]()
            migration["upgrade"]()
        assert compare_metadata(context, Base.metadata) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reply_source", ["literal-delivery-scope", "opaque-BSUID-source"])
async def test_human_control_reply_counts_once_without_queue_content_or_identity(
    runtime, webapp, reply_source
):
    from backend.persistence.models import BusinessEvent, VerifiedContext
    from backend.services.metrics import MetricsService

    campaign_id, _, _ = accepted_template(runtime)
    runtime.channel.status = "open"
    body = payload(source=reply_source, message=900, content="Mi PIN 246810")
    body["conversation"]["status"] = "open"
    body["created_at"] = utcnow().isoformat()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for _ in range(2):
            response = await post(client, runtime, body)
            assert response.status_code == 200 and response.json()["reason"] == "human_control"
    with runtime.sessions() as session:
        rows = session.scalars(select(BusinessEvent)).all()
        assert len(rows) == 1 and rows[0].event_type == "first_response"
        assert rows[0].source_key == "reply:9:900"
        assert rows[0].thread_id == reply_source
        assert "246810" not in str(vars(rows[0])) and "Mi PIN" not in str(vars(rows[0]))
        for model in (InboxEvent, ConversationJob, VerifiedContext):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert (await MetricsService(runtime.sessions).get(campaign_id))["unique_replied"] == 1
    # The worker sees the same public message metadata later; it cannot add a milestone.
    assert not await runtime.events.record_incoming(
        SimpleNamespace(
            id=uuid4(),
            account_id="9",
            inbox_id="7",
            conversation_id="11",
            message_id="900",
            thread_id=reply_source,
            received_at=utcnow(),
        )
    )
    assert not runtime.inference.calls and not runtime.channel.sent


@pytest.mark.asyncio
async def test_human_reply_must_follow_real_send_and_valid_scope(runtime, webapp):
    from backend.persistence.models import BusinessEvent, CampaignRecipient, ResetMetadata

    _, recipient_id, _ = accepted_template(runtime)
    runtime.channel.status = "open"
    with runtime.sessions.begin() as session:
        sent_at = session.get(CampaignRecipient, recipient_id).sent_at
        session.add(ResetMetadata(key="demo", reset_at=sent_at - timedelta(minutes=1)))
    before_send = payload(source="opaque-BSUID-source", message=901, content="246810")
    before_send["conversation"]["status"] = "open"
    before_send["created_at"] = (sent_at - timedelta(seconds=1)).isoformat()
    before_reset = {
        **before_send,
        "id": 902,
        "created_at": (sent_at - timedelta(minutes=2)).isoformat(),
    }
    wrong_source = payload(source="unrelated-contact", conversation=99, message=903)
    wrong_source["conversation"]["status"] = "open"
    invalid_content = {**payload(source="literal-delivery-scope", message=904), "content": []}
    private = {**payload(source="literal-delivery-scope", message=905), "private": True}
    wrong_inbox = {**payload(source="literal-delivery-scope", message=906), "inbox": {"id": 999}}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, before_send)).json()["reason"] == "human_control"
        assert (await post(client, runtime, before_reset)).json()["reason"] == "before_reset"
        assert (await post(client, runtime, wrong_source)).json()["reason"] == "human_control"
        assert (await post(client, runtime, invalid_content)).status_code == 422
        assert (await post(client, runtime, private)).json()["accepted"] is False
        assert (await post(client, runtime, wrong_inbox)).status_code == 403
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,send_status", [("simulated", "simulated"), ("live", "queued")])
async def test_human_reply_does_not_count_prepared_or_simulated_campaign(
    runtime, webapp, mode, send_status
):
    from backend.persistence.models import BusinessEvent, CampaignRecipient

    _, recipient_id, _ = accepted_template(runtime)
    with runtime.sessions.begin() as session:
        recipient = session.get(CampaignRecipient, recipient_id)
        recipient.delivery_mode, recipient.send_status = mode, send_status
    runtime.channel.status = "open"
    body = payload(source="opaque-BSUID-source", content="Mi PIN 246810")
    body["conversation"]["status"] = "open"
    body["created_at"] = utcnow().isoformat()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json()["reason"] == "human_control"
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
    assert not runtime.inference.calls and not runtime.channel.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("cutoff_field", ["closed_at", "followup_until"])
async def test_alternate_source_reply_still_respects_campaign_cutoff(runtime, webapp, cutoff_field):
    from backend.persistence.models import BusinessEvent, Campaign

    campaign_id, _, _ = accepted_template(runtime)
    with runtime.sessions.begin() as session:
        setattr(session.get(Campaign, campaign_id), cutoff_field, utcnow() - timedelta(seconds=1))
    runtime.channel.status = "open"
    body = payload(source="opaque-BSUID-source", message=907, content="Mi PIN 246810")
    body["conversation"]["status"] = "open"
    body["created_at"] = utcnow().isoformat()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, body)).json()["reason"] == "human_control"
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0


@pytest.fixture
def traced_runtime(runtime):
    """Real SDK/OTEL tree, isolated exporter, and the existing real PostgreSQL fixture."""
    from backend.integrations.observability import Observability, mask_payload
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    sdk = Langfuse(
        public_key="pk-lf-worker-test-" + uuid4().hex,
        secret_key="sk-lf-fictional-worker-fixture",
        base_url="http://127.0.0.1:1",
        tracer_provider=provider,
        span_exporter=exporter,
        mask=mask_payload,
    )
    observation = Observability(SimpleNamespace(langfuse_enabled=False))
    observation.client = sdk
    runtime.observability = observation
    try:
        yield runtime, exporter
    finally:
        sdk.flush()
        provider.shutdown()


def exported_status(span):
    # SDK v5 serializes each metadata value as JSON in its own OTEL attribute.
    return json.loads(span.attributes["langfuse.observation.metadata.status"])


def exported_span_data(spans):
    return json.dumps(
        [
            {
                "name": span.name,
                "attributes": dict(span.attributes),
                "events": [str(event) for event in span.events],
                "status": span.status.description,
            }
            for span in spans
        ],
        default=str,
        ensure_ascii=False,
    )


def test_all_agent_tools_keep_their_names_and_auth_phase_in_real_traces(traced_runtime):
    from backend.agent.tools import TOOL_SCHEMAS

    runtime, exporter = traced_runtime
    expected = {"tool." + tool["name"] for tool in TOOL_SCHEMAS}
    with runtime.observability.span("conversation", thread_id="literal-tool-catalog"):
        for tool in TOOL_SCHEMAS:
            with runtime.observability.span("tool", tool=tool["name"]) as span:
                span.update(phase="awaiting_pin")
    runtime.observability.flush()
    tools = [span for span in exporter.get_finished_spans() if span.name != "conversation"]
    assert {span.name for span in tools} == expected
    for span in tools:
        assert json.loads(span.attributes["langfuse.observation.metadata.phase"]) == "awaiting_pin"


@pytest.mark.asyncio
async def test_handoff_deliveries_keep_original_tool_parent_after_root_and_retry(traced_runtime):
    runtime, exporter = traced_runtime
    source = "literal-handoff-trace-source"
    await runtime.identity.locate(source, {"phone_e164": "+573000000001"}, "lookup")
    await runtime.identity.manage(source, "confirm_candidate")
    await runtime.identity.intercept(source, "246810", False, "pin")
    event, _ = runtime.queue.enqueue(
        account_id="9", inbox_id="7", conversation_id="11", message_id="handoff-trace",
        source_id=source, content="Quiero un asesor",
    )
    with runtime.observability.span("conversation", event_id=event.id, thread_id=source):
        with runtime.observability.span("tool", event_id=event.id, tool="handoff_human") as tool:
            original_context = tool.export_context()
            first = await runtime.handoff.request(event, "requested", "Revisar una alternativa")
    with runtime.observability.span("operation", thread_id="unrelated-retry"):
        assert await runtime.handoff.request(event, "requested", "Solicitud repetida") == first
    with runtime.sessions() as session:
        effects = session.scalars(select(Outbox).where(Outbox.source_event_id == event.id)).all()
        assert len(effects) == 3
        for row in effects:
            assert row.payload_private["_trace_context"] == original_context
    await send_outputs(runtime)
    runtime.observability.flush()
    deliveries = [span for span in exporter.get_finished_spans() if span.name == "delivery"]
    assert len(deliveries) == 3
    for delivery in deliveries:
        assert f"{delivery.context.trace_id:032x}" == original_context["trace_id"]
        assert f"{delivery.parent.span_id:016x}" == original_context["parent_span_id"]
        assert exported_status(delivery) == "sent"
    with runtime.sessions() as session:
        assert all(row.state == "sent" for row in session.scalars(select(Outbox)))
    assert runtime.channel.status == "open"
    assert not runtime.inference.calls


@pytest.mark.asyncio
async def test_pin_only_turn_exports_complete_tree_and_delivery_without_inference(
    traced_runtime, webapp
):
    from backend.integrations.observability import opaque_id

    runtime, exporter = traced_runtime
    pin = "732918"
    source = " whatsapp:PRIVATE-TRACE-FIXTURE#opaque "
    await runtime.identity.locate(source, {"phone_e164": "+573000000001"}, "lookup")
    await runtime.identity.manage(source, "confirm_candidate")
    runtime.central.failure = DomainError("pin_invalid", "Incorrect PIN", status=401)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        response = await post(client, runtime, payload(source, content=pin))
    assert response.status_code == 200 and response.json()["accepted"]
    job = runtime.queue.claim("trace-pin-worker")
    protected = decode_protected(job.event.normalized_content, runtime.settings.session_secret)
    assert protected["sealed_auth"] and protected["agent_message"] is None
    assert pin not in job.event.normalized_content

    await process_job(runtime, job)
    runtime.observability.flush()
    before_send = exporter.get_finished_spans()
    assert {span.name for span in before_send} == {
        "conversation",
        "identity_gate",
        "response_enqueue",
    }
    by_name = {span.name: span for span in before_send}
    root = by_name["conversation"]
    gate, enqueue_span = by_name["identity_gate"], by_name["response_enqueue"]
    assert root.parent is None and root.end_time is not None
    assert gate.parent.span_id == root.context.span_id
    assert enqueue_span.parent.span_id == root.context.span_id
    assert exported_status(gate) == "handled"
    assert exported_status(root) == "completed"
    assert not runtime.inference.calls
    assert [call[1] for call in runtime.central.calls] == ["/identity/locate", "/identity/verify"]

    with runtime.sessions() as session:
        row = session.scalar(select(Outbox))
        assert row.state == "queued"
        context = row.payload_private["_trace_context"]
        assert context == {
            "trace_id": f"{root.context.trace_id:032x}",
            "parent_span_id": f"{enqueue_span.context.span_id:016x}",
        }
    # process_job has returned and its root is already closed before this task sends.
    await send_outputs(runtime)
    runtime.observability.flush()
    spans = exporter.get_finished_spans()
    (delivery,) = [span for span in spans if span.name == "delivery"]
    assert delivery.context.trace_id == root.context.trace_id
    assert delivery.parent.span_id == enqueue_span.context.span_id
    assert delivery.start_time >= root.end_time
    assert exported_status(delivery) == "sent"
    assert all(span.attributes.get("session.id") == opaque_id(source) for span in spans)
    assert len(runtime.channel.sent) == 1 and not runtime.inference.calls
    with runtime.sessions() as session:
        assert session.get(Outbox, row.id).state == "sent"
        assert session.get(InboxEvent, job.event_id).status == "completed"
    serialized = exported_span_data(spans)
    for private in (
        pin,
        source,
        runtime.settings.session_secret.get_secret_value(),
        runtime.settings.chatwoot_webhook_secret.get_secret_value(),
        "PRIVATE-RUNTIME-GRANT",
        "sk-lf-fictional-worker-fixture",
    ):
        assert private not in serialized
    assert all(not span.events for span in spans)


def test_outbox_retry_keeps_original_trace_parent_and_business_conflicts(traced_runtime):
    runtime, exporter = traced_runtime
    source = "literal-private-idempotency-source"
    event, _ = runtime.queue.enqueue(
        account_id="9",
        inbox_id="7",
        conversation_id="11",
        message_id="trace-idempotency",
        source_id=source,
    )
    runtime.identity.snapshot(source)
    options = {
        "event_id": event.id,
        "identity_revision": 0,
        "kind": "message",
        "operation_key": "same-business-output",
        "payload": {"content": "Respuesta ficticia"},
    }
    with runtime.observability.span(
        "response_enqueue", event_id=event.id, thread_id=source
    ) as first:
        first_context = first.export_context()
        # Callers cannot inject a trace parent through the private payload field.
        row = runtime.outbox.enqueue(
            **{
                **options,
                "payload": {
                    **options["payload"],
                    "_trace_context": {"trace_id": "a" * 32, "parent_span_id": "b" * 16},
                },
            }
        )
    with runtime.observability.span(
        "response_enqueue", event_id=event.id, thread_id=source
    ) as retry:
        retry_context = retry.export_context()
        repeated = runtime.outbox.enqueue(**options)
    assert first_context != retry_context
    assert first_context["trace_id"] != retry_context["trace_id"]
    assert repeated.id == row.id
    assert runtime.outbox.enqueue(**options).id == row.id
    with runtime.sessions() as session:
        stored = session.get(Outbox, row.id)
        assert stored.payload_private == {**options["payload"], "_trace_context": first_context}
        assert session.scalar(select(func.count()).select_from(Outbox)) == 1
    with pytest.raises(DomainError) as caught:
        runtime.outbox.enqueue(**{**options, "payload": {"content": "Otro contenido de negocio"}})
    assert caught.value.code == "outbox_conflict"
    with runtime.sessions() as session:
        assert session.get(Outbox, row.id).payload_private["_trace_context"] == first_context
    assert not runtime.channel.sent


@pytest.mark.asyncio
async def test_delivery_restores_persisted_parent_after_root_closed_despite_unrelated_ambient_trace(
    traced_runtime,
):
    runtime, exporter = traced_runtime
    source = "literal-delivery-trace-source"
    event, _ = runtime.queue.enqueue(
        account_id="9",
        inbox_id="7",
        conversation_id="11",
        message_id="detached-delivery",
        source_id=source,
    )
    runtime.identity.snapshot(source)
    with runtime.observability.span("conversation", event_id=event.id, thread_id=source):
        with runtime.observability.span("response_enqueue", event_id=event.id) as enqueue_span:
            context = enqueue_span.export_context()
            row = runtime.outbox.enqueue(
                event_id=event.id,
                identity_revision=0,
                kind="message",
                payload={"content": "Respuesta ficticia diferida"},
                operation_key="detached-delivery",
            )
    runtime.observability.flush()
    (original,) = [span for span in exporter.get_finished_spans() if span.name == "conversation"]
    assert original.end_time is not None
    with runtime.observability.span("operation", thread_id="unrelated-private-source") as unrelated:
        unrelated_context = unrelated.export_context()
        assert unrelated_context["trace_id"] != context["trace_id"]
        await send_outputs(runtime)
    runtime.observability.flush()
    (delivery,) = [span for span in exporter.get_finished_spans() if span.name == "delivery"]
    assert f"{delivery.context.trace_id:032x}" == context["trace_id"]
    assert f"{delivery.parent.span_id:016x}" == context["parent_span_id"]
    assert f"{delivery.context.trace_id:032x}" != unrelated_context["trace_id"]
    assert delivery.start_time >= original.end_time
    assert exported_status(delivery) == "sent"
    assert len(runtime.channel.sent) == 1
    with runtime.sessions() as session:
        assert session.get(Outbox, row.id).state == "sent"
        assert session.get(Outbox, row.id).payload_private["_trace_context"] == context


@pytest.mark.asyncio
async def test_full_content_turn_exports_messages_checkpoint_and_delivery_in_private_trace(
    runtime, webapp
):
    from backend.integrations.observability import Observability
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    observation = Observability(SimpleNamespace(
        langfuse_enabled=False, langfuse_capture_content=True,
        session_secret=runtime.settings.session_secret,
        chatwoot_webhook_secret=runtime.settings.chatwoot_webhook_secret,
    ))
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    sdk = Langfuse(
        public_key='pk-lf-private-content-' + uuid4().hex,
        secret_key='sk-lf-fictional-private-content', base_url='http://127.0.0.1:1',
        tracer_provider=provider, span_exporter=exporter, mask=observation.sanitizer.mask,
    )
    observation.client = sdk
    runtime.observability = observation
    source = 'whatsapp:+15550004567'
    messages = ['Soy Ana Martínez, CC 10000001; consulto mi deuda de USD 100.',
                '¿Qué opciones tengo para pagar?']
    try:
        async with checkpointer(runtime.settings.memory_conninfo, setup=True):
            pass
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(webapp), base_url='http://testserver'
        ) as client:
            for index, message in enumerate(messages, 1):
                response = await post(client, runtime, payload(
                    source, message=1200 + index, content=message,
                ))
                assert response.status_code == 200
                await process_job(runtime, runtime.queue.claim('private-content-worker'))
                await send_outputs(runtime)
        observation.flush()
        spans = exporter.get_finished_spans()
        serialized = json.dumps([
            json.loads(value)
            for span in spans for key, value in span.attributes.items()
            if key in {"langfuse.observation.input", "langfuse.observation.output"}
        ], ensure_ascii=False)
        for value in messages + [source, '10000001', 'Ana Martínez', 'Respuesta ficticia 1',
                                 'Respuesta ficticia 2', 'state_before', 'state_after']:
            assert value in serialized
        for value in [runtime.settings.session_secret.get_secret_value(),
                      runtime.settings.chatwoot_webhook_secret.get_secret_value(),
                      'PRIVATE-RUNTIME-GRANT', 'sk-lf-fictional-private-content']:
            assert value not in serialized
        assert len([span for span in spans if span.name == 'conversation']) == 2
        agents = [span for span in spans if span.name == 'agent']
        assert len(agents) == 2
        second_agent = max(agents, key=lambda span: span.start_time)
        assert 'Respuesta ficticia 1' in second_agent.attributes['langfuse.observation.input']
        assert len([span for span in spans if span.name == 'delivery']) == 2
        assert len(runtime.channel.sent) == 2
    finally:
        observation.flush()
        provider.shutdown()


def human_event(source="literal-human-memory", message="102", **changes):
    return SimpleNamespace(
        **{
            "account_id": "9", "inbox_id": "7", "conversation_id": "11",
            "message_id": message, "thread_id": source, "received_at": utcnow(),
            **changes,
        }
    )


def seed_human_context(runtime, source="literal-human-memory", revision=3):
    from backend.persistence.models import VerifiedContext

    with runtime.sessions.begin() as session:
        session.add(VerifiedContext(thread_id=source, identity_revision=revision))
        session.add(InboxEvent(
            account_id="9", inbox_id="7", conversation_id="11", message_id="100",
            thread_id=source, identity_revision=revision, status="completed",
        ))


def test_human_memory_is_durable_idempotent_and_never_creates_work(runtime):
    from backend.services.human_memory import HumanMemory

    seed_human_context(runtime)
    memory = HumanMemory(runtime.sessions)
    event = human_event()
    assert memory.record(event, speaker="advisor", content="Acordamos revisar mañana")["accepted"]
    assert memory.record(event, speaker="advisor", content="Contenido repetido")["duplicate"]
    with runtime.sessions() as session:
        rows = session.scalars(select(InboxEvent).where(InboxEvent.status == "human_context")).all()
        assert len(rows) == 1 and rows[0].identity_revision == 3
        assert "Acordamos revisar mañana" in rows[0].normalized_content
        assert "Contenido repetido" not in rows[0].normalized_content
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0
    groups = memory.groups(human_event(message="103"), 3)
    assert len(groups) == 1
    assert groups[0]["id"] == "human:" + str(rows[0].id)
    assert groups[0]["items"] == [
        {"role": "user", "content": "asesorhumano: Acordamos revisar mañana"}
    ]
    assert groups[0]["complete"] is True
    assert not runtime.inference.calls and not runtime.channel.sent


def test_human_memory_requires_existing_bot_context_and_exact_channel_scope(runtime):
    from backend.persistence.models import VerifiedContext
    from backend.services.human_memory import HumanMemory

    memory = HumanMemory(runtime.sessions)
    assert not memory.record(human_event(), speaker="advisor", content="Sin contexto")["accepted"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(VerifiedContext)) == 0
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 0
    seed_human_context(runtime)
    for index, change in enumerate((
        {"account_id": "99"}, {"inbox_id": "99"}, {"conversation_id": "99"},
        {"thread_id": "unrelated-human-contact"},
    ), 200):
        assert not memory.record(
            human_event(message=str(index), **change), speaker="advisor", content="Ajeno"
        )["accepted"]
    with runtime.sessions() as session:
        assert session.scalar(select(func.count()).select_from(InboxEvent)) == 1


def test_human_memory_groups_filter_revision_scope_and_future_numeric_ids(runtime):
    from backend.persistence.models import VerifiedContext
    from backend.services.human_memory import HumanMemory

    seed_human_context(runtime)
    memory = HumanMemory(runtime.sessions)
    earlier = human_event(message="102", received_at=utcnow() - timedelta(minutes=2))
    later = human_event(message="103", received_at=utcnow() - timedelta(minutes=1))
    # Insert in reverse order to prove retrieval follows message chronology.
    memory.record(later, speaker="customer", content="Gracias por la ayuda")
    memory.record(earlier, speaker="advisor", content="Revisaremos el caso")
    memory.record(human_event(message="110"), speaker="advisor", content="Mensaje futuro")
    groups = memory.groups(human_event(message="104"), 3)
    assert [group["items"][0]["content"] for group in groups] == [
        "asesorhumano: Revisaremos el caso",
        "cliente (durante atención humana): Gracias por la ayuda",
    ]
    for change in ({"account_id": "99"}, {"inbox_id": "99"},
                   {"conversation_id": "99"}, {"thread_id": "another-contact"}):
        assert memory.groups(human_event(message="104", **change), 3) == []
    assert memory.groups(human_event(message="104"), 4) == []
    with runtime.sessions.begin() as session:
        session.get(VerifiedContext, "literal-human-memory").identity_revision = 4
    memory.record(human_event(message="120"), speaker="advisor", content="Nuevo cliente")
    assert [group["items"][0]["content"] for group in memory.groups(human_event(message="121"), 4)] == [
        "asesorhumano: Nuevo cliente"
    ]


def test_human_memory_reset_cutoff_prevents_old_revision_zero_history(runtime):
    from backend.persistence.models import ResetMetadata
    from backend.services.human_memory import HumanMemory

    seed_human_context(runtime, revision=0)
    memory = HumanMemory(runtime.sessions)
    memory.record(human_event(message="102"), speaker="advisor", content="Contexto anterior al reset")
    with runtime.sessions.begin() as session:
        session.add(ResetMetadata(key="demo", epoch=1, reset_at=utcnow()))
    assert memory.groups(human_event(message="200"), 0) == []
    assert not memory.record(
        human_event(message="201"), speaker="advisor", content="Sin conversación nueva"
    )["accepted"]
    with runtime.sessions.begin() as session:
        session.add(InboxEvent(
            account_id="9", inbox_id="7", conversation_id="11", message_id="202",
            thread_id="literal-human-memory", identity_revision=0, status="completed",
        ))
    memory.record(human_event(message="203"), speaker="customer", content="10000002")
    assert [group["items"][0]["content"] for group in memory.groups(human_event(message="204"), 0)] == [
        "cliente (durante atención humana): 10000002"
    ]


@pytest.mark.asyncio
async def test_public_human_webhook_stores_context_without_llm_jobs_or_reply(runtime, webapp):
    seed_human_context(runtime)
    runtime.channel.status = "open"
    body = payload("literal-human-memory", message=102, content="Le contactaré mañana")
    body.update(message_type="outgoing", sender={"id": 5, "type": "user"})
    body["conversation"]["status"] = "open"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        first = await post(client, runtime, body)
        assert first.status_code == 200 and first.json()["accepted"]
        assert (await post(client, runtime, body)).json()["duplicate"]
        for index, change in enumerate((
            {"private": True}, {"sender": {"id": 5, "type": "agent_bot"}},
        ), 103):
            ignored = await post(client, runtime, {**body, "id": index, **change})
            assert ignored.status_code == 200 and not ignored.json()["accepted"]
    with runtime.sessions() as session:
        rows = session.scalars(select(InboxEvent).where(InboxEvent.status == "human_context")).all()
        assert len(rows) == 1
        assert "Le contactaré mañana" in rows[0].normalized_content
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0
    assert not runtime.inference.calls and not runtime.channel.sent and not runtime.central.calls


@pytest.mark.asyncio
async def test_customer_human_turn_stored_but_active_pin_challenge_is_omitted(runtime, webapp):
    seed_human_context(runtime)
    runtime.channel.status = "open"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        for index, content in enumerate(("Gracias, esperaré la llamada", "246810"), 102):
            if index == 103:
                from backend.persistence.models import VerifiedContext

                with runtime.sessions.begin() as session:
                    session.get(VerifiedContext, "literal-human-memory").challenge_state = "awaiting_pin"
            body = payload("literal-human-memory", message=index, content=content)
            body["conversation"]["status"] = "open"
            assert (await post(client, runtime, body)).status_code == 200
    with runtime.sessions() as session:
        rows = session.scalars(select(InboxEvent).where(InboxEvent.status == "human_context")).all()
        assert any("Gracias, esperaré la llamada" in row.normalized_content for row in rows)
        assert "246810" not in json.dumps([row.normalized_content for row in rows])
        assert session.scalar(select(func.count()).select_from(ConversationJob)) == 0
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0
    assert not runtime.inference.calls and not runtime.channel.sent and not runtime.central.calls


@pytest.mark.asyncio
async def test_return_to_bot_loads_human_exchange_into_state_and_inference(runtime, webapp):
    from backend.persistence.models import VerifiedContext

    source = "literal-human-return"
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(webapp), base_url="http://testserver"
    ) as client:
        assert (await post(client, runtime, payload(source, message=100))).json()["accepted"]
        await process_job(runtime, runtime.queue.claim("human-return-worker"))
        calls_before = len(runtime.inference.calls)
        # Human ownership starts after an existing bot turn; no worker processes
        # either side of the exchange while the conversation is open.
        advisor = payload(source, message=101, content="El asesor revisará el caso mañana")
        advisor.update(message_type="outgoing", sender={"id": 5, "type": "user"})
        advisor["conversation"]["status"] = "open"
        customer = payload(source, message=102, content="Prefiero que me llamen en la tarde")
        customer["conversation"]["status"] = "open"
        assert (await post(client, runtime, advisor)).status_code == 200
        assert (await post(client, runtime, customer)).status_code == 200
        assert runtime.queue.claim("human-return-worker") is None
        assert len(runtime.inference.calls) == calls_before
        resumed = payload(source, message=103, content="¿Puedes retomar lo que hablamos?")
        resumed["conversation"]["status"] = "pending"
        assert (await post(client, runtime, resumed)).json()["accepted"]
        await process_job(runtime, runtime.queue.claim("human-return-worker"))
    expected = [
        {"role": "user", "content": "asesorhumano: El asesor revisará el caso mañana"},
        {"role": "user", "content": "cliente (durante atención humana): Prefiero que me llamen en la tarde"},
    ]
    assert len(runtime.inference.calls) == calls_before + 1
    request_messages = runtime.inference.calls[-1]["input"]
    for message in expected:
        assert request_messages.count(message) == 1
    assert request_messages.index(expected[0]) < request_messages.index(expected[1])
    with runtime.sessions() as session:
        assert session.get(VerifiedContext, source) is not None
    async with checkpointer(runtime.settings.memory_conninfo) as saver:
        saved = await saver.aget_tuple(thread_config(source))
        for message in expected:
            assert message["content"] in str(saved.checkpoint)


@pytest.mark.asyncio
@pytest.mark.parametrize('selected', [False, True])
async def test_applied_handoff_return_supplies_current_bot_control_not_historical_case(runtime, webapp, selected):
    from backend.agent.graph import build_graph
    from backend.agent.tools import ToolRuntime
    from backend.persistence.models import HumanCase, VerifiedContext

    source = 'literal-confirmed-bot-return'
    async with checkpointer(runtime.settings.memory_conninfo, setup=True):
        pass
    async with httpx.AsyncClient(transport=httpx.ASGITransport(webapp), base_url='http://testserver') as client:
        await post(client, runtime, payload(source, message=100))
        job = runtime.queue.claim('return-control-worker')
        await process_job(runtime, job)
        with runtime.sessions.begin() as db:
            identity = db.get(VerifiedContext, source)
            identity.challenge_state = 'verified'
            identity.central_grant = 'fictional-return-grant'
            identity.customer_id = runtime.central.customer
            identity.expires_at = utcnow() + timedelta(minutes=10)
            identity.selected_debt_id = uuid4() if selected else None
        async with checkpointer(runtime.settings.memory_conninfo) as saver:
            tools = ToolRuntime(job.event, runtime.identity, runtime.central, runtime.handoff, runtime.observability)
            graph = build_graph(saver, runtime=tools, inference=runtime.inference, text='')
            await graph.aupdate_state(thread_config(source), {'phase': 'handoff_requested'})
        await runtime.handoff.request(job.event, 'dispute', 'El saldo requiere aclaración')
        # Each poll can release the next dependency in the durable handoff outbox.
        for _ in range(3):
            await send_outputs(runtime)
        assert runtime.channel.status == 'open'
        calls_before = len(runtime.inference.calls)
        advisor = payload(source, message=101, content='La llamada era incorrecta; la deuda pendiente es hogar. Te devuelvo al asistente.')
        advisor.update(message_type='outgoing', sender={'id': 5, 'type': 'user'})
        advisor['conversation']['status'] = 'open'
        await post(client, runtime, advisor)
        assert len(runtime.inference.calls) == calls_before
        # Text claiming a return does not return control or schedule an agent turn.
        assert runtime.handoff.blocked(source)
        assert runtime.queue.claim('return-control-worker') is None
        runtime.channel.status = 'pending'
        resumed = payload(source, message=102, content='Entonces, ¿cuánto debo?')
        resumed['conversation']['status'] = 'pending'
        await post(client, runtime, resumed)
        await process_job(runtime, runtime.queue.claim('return-control-worker'))
    request = runtime.inference.calls[-1]
    context = json.loads(request['instructions'].rsplit('Contexto actual del servidor: ', 1)[1])
    assert context['channel_control'] == 'bot'
    assert context['identity_verified'] is True
    assert context['phase'] == ('discuss_payment' if selected else 'select_debt')
    assert any('asesorhumano: La llamada era incorrecta' in item.get('content', '') for item in request['input'])
    assert not runtime.handoff.blocked(source)
    with runtime.sessions() as db:
        case = db.scalar(select(HumanCase).where(HumanCase.thread_id == source))
        assert case.status == 'returned' and case.open_observed
