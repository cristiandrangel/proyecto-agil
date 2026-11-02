"""Restartable real PostgreSQL checkpoints with deterministic SDK-shaped inference.

These tests do not spend tokens or send messages to Chatwoot. The provider/channel
live journeys remain a separate opt-in acceptance step.
"""

import copy
import json
import os
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from agil_shared.errors import DomainError
from backend.agent.graph import build_graph
from backend.agent.tools import ToolRuntime
from backend.persistence.checkpoints import checkpointer, thread_config
from backend.persistence.models import Base, InboxEvent, VerifiedContext, utcnow
from backend.services.handoff import HandoffService
from backend.services.identity import IdentityService
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def journey_store():
    url = os.getenv("TEST_MEMORY_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_MEMORY_DATABASE_URL for real PostgreSQL checkpoint tests")
    schema = "journey_" + uuid4().hex
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


class Item(SimpleNamespace):
    def model_dump(self, **_):
        return dict(vars(self))


def call(name, args, call_id=None):
    return Item(
        type="function_call",
        id="fc_" + uuid4().hex,
        call_id=call_id or uuid4().hex,
        name=name,
        arguments=json.dumps(args),
    )


def final(message):
    return SimpleNamespace(
        output=[
            Item(
                type="message",
                id="msg_" + uuid4().hex,
                role="assistant",
                status="completed",
                content=[{"type": "output_text", "text": message, "annotations": []}],
            )
        ],
        output_text=message,
    )


def response(*items):
    return SimpleNamespace(output=list(items), output_text="")


class Inference:
    def __init__(self, *responses, max_calls=5, max_tokens=12000):
        self.settings = SimpleNamespace(
            ai_max_calls_per_turn=max_calls,
            ai_max_input_tokens=max_tokens,
            history_visible_messages=20,
        )
        self.responses = list(responses)
        self.calls = []

    async def response(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if not self.responses:
            pytest.fail("Unexpected extra inference call")
        result = self.responses.pop(0)
        if callable(result):
            result = result(kwargs)
        return result


class Central:
    def __init__(self):
        self.owner, self.other = uuid4(), uuid4()
        self.debts = [uuid4(), uuid4()]
        self.foreign_debt = uuid4()
        self.candidate = uuid4()
        self.calls = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/identity/locate":
            return {
                "candidate_count": 1,
                "candidates": [
                    {"candidate_reference": str(self.candidate), "masked_hint": "N*** · CC ***999"}
                ],
            }
        if path == "/identity/revoke":
            return {"revoked": True}
        if path == "/identity/verify":
            return {
                "customer_id": str(self.other),
                "grant_token": "NEW-PRIVATE-GRANT",
                "expires_at": (utcnow() + timedelta(minutes=20)).isoformat(),
            }
        if path == "/debts":
            ids = self.debts if kwargs["grant"] == "OLD-PRIVATE-GRANT" else [self.foreign_debt]
            return {
                "items": [
                    {
                        "id": str(debt),
                        "service_type": "Ficticio",
                        "balance_cents": 34567,
                        "version": 1,
                    }
                    for debt in ids
                ],
                "total": len(ids),
            }
        if path.startswith("/debts/"):
            debt = UUID(path.rsplit("/", 1)[-1])
            allowed = self.debts if kwargs["grant"] == "OLD-PRIVATE-GRANT" else [self.foreign_debt]
            if debt not in allowed:
                raise DomainError("not_found", "Debt unavailable", 404)
            return {"id": str(debt), "balance_cents": 34567, "version": 1}
        raise AssertionError(path)


def setup_services(store, thread=" whatsapp:+573000000001 #literal "):
    central = Central()
    settings = SimpleNamespace(
        session_secret=SecretStr("fictional-checkpoint-test" * 2),
        chatwoot_account_id=None,
        chatwoot_inbox_id=None,
    )
    identity = IdentityService(settings, store, central)
    handoff = HandoffService(settings, store)
    with store.begin() as session:
        session.add(
            VerifiedContext(
                thread_id=thread,
                identity_revision=1,
                challenge_state="verified",
                customer_id=central.owner,
                central_grant="OLD-PRIVATE-GRANT",
                expires_at=utcnow() + timedelta(minutes=20),
                selected_debt_id=central.debts[0],
            )
        )
    return identity, handoff, central, thread


def event(store, thread, number, conversation="conversation-one"):
    with store.begin() as session:
        row = InboxEvent(
            account_id="demo",
            inbox_id="demo",
            message_id=str(number),
            conversation_id=conversation,
            thread_id=thread,
            normalized_content="sanitized envelope",
        )
        session.add(row)
        session.flush()
        return row


def runtime(row, identity, handoff, central):
    return ToolRuntime(
        row, identity, central, handoff, SimpleNamespace(span=lambda *a, **k: nullcontext())
    )


@pytest.mark.asyncio
async def test_checkpoint_restart_literal_source_history_and_event_dedupe(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    first = event(store, thread, 1)
    async with checkpointer(conninfo, setup=True) as saver:
        inference = Inference(final("Primera respuesta"))
        graph = build_graph(
            saver,
            runtime=runtime(first, identity, handoff, central),
            inference=inference,
            text="Hola",
        )
        state = await graph.ainvoke({}, thread_config(thread))
        assert state["messages"][-1]["reply"] == "Primera respuesta"
        context = json.loads(
            inference.calls[0]["instructions"].split("Contexto actual del servidor: ", 1)[1]
        )
        assert context["source_id"] == thread and "grant" not in context
        assert context["conversation_start"] is True
    # A fresh saver/graph resumes the latest state, not a manually reconstructed history.
    second = event(store, thread, 2, conversation="conversation-two")
    async with checkpointer(conninfo) as saver:
        inference = Inference(final("Segunda respuesta"))
        graph = build_graph(
            saver,
            runtime=runtime(second, identity, handoff, central),
            inference=inference,
            text="Continuar",
        )
        state = await graph.ainvoke({}, thread_config(thread))
        assert len(state["messages"]) == 2
        assert "Primera respuesta" in json.dumps(inference.calls[0]["input"])
        assert len(inference.calls) == 1
        second_context = json.loads(inference.calls[0]["instructions"].split("Contexto actual del servidor: ", 1)[1])
        assert second_context["conversation_start"] is False
        duplicate = await graph.ainvoke({}, thread_config(thread))
        assert duplicate == state and len(inference.calls) == 1
        assert (
            first.conversation_id != second.conversation_id and first.thread_id == second.thread_id
        )
        assert "PRIVATE-GRANT" not in json.dumps(state)


@pytest.mark.asyncio
async def test_locate_preserves_only_fresh_masked_tool_after_identity_switch(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    original = event(store, thread, 1)
    async with checkpointer(conninfo, setup=True) as saver:
        old = build_graph(
            saver,
            runtime=runtime(original, identity, handoff, central),
            inference=Inference(final("SALDO-ANTERIOR-CONFIDENCIAL 345.67")),
            text="Deuda anterior",
        )
        await old.ainvoke({}, thread_config(thread))
        row = event(store, thread, 2)
        locate = call(
            "locate_customer",
            {"phone_e164": None, "document_type": "CC", "document_number": "10000999"},
        )
        reasoning = Item(
            type="reasoning",
            id="reasoning-old",
            summary=[],
            encrypted_content="OLD-FINANCIAL-REASONING",
        )
        inference = Inference(
            response(reasoning, locate),
            final("Encontré N*** · CC ***999. ¿Quieres gestionar ese registro?"),
        )
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text="Cambiar a DEMO-999, antes saldo SALDO-ANTERIOR-CONFIDENCIAL",
        )
        state = await graph.ainvoke({}, thread_config(thread))
        second_input = json.dumps(inference.calls[1]["input"], ensure_ascii=False)
        assert "N***" in second_input and "function_call_output" in second_input
        assert (
            "SALDO-ANTERIOR-CONFIDENCIAL" not in second_input
            and "OLD-FINANCIAL-REASONING" not in second_input
        )
        serialized = json.dumps(state, ensure_ascii=False)
        assert "SALDO-ANTERIOR-CONFIDENCIAL" not in serialized and "PRIVATE-GRANT" not in serialized
        assert len(state["messages"]) == 1 and state["selected_debt_id"] is None
        assert not identity.snapshot(thread)["verified"]
        assert len(inference.calls) == 2


@pytest.mark.asyncio
async def test_pin_to_new_customer_neutral_message_and_ownership_after_recovery(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    await identity.locate(thread, {"phone_e164": "+573000000002"}, "locate")
    await identity.manage(thread, "confirm_candidate")
    protected = await identity.intercept(thread, "246810", False, "pin")
    assert protected["agent_message"] == "identity_verified"
    row = event(store, thread, 1)
    async with checkpointer(conninfo, setup=True) as saver:
        inference = Inference(
            response(call("list_debts", {"service_type": None})),
            final("Servicio ficticio disponible"),
        )
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text=protected["agent_message"],
        )
        state = await graph.ainvoke({}, thread_config(thread))
        assert "246810" not in json.dumps(state) and "PRIVATE-GRANT" not in json.dumps(state)
        assert central.calls[-1][2]["grant"] == "NEW-PRIVATE-GRANT"
        with pytest.raises(DomainError) as caught:
            await identity.select_debt(thread, central.debts[0])
        assert caught.value.status == 404 and identity.snapshot(thread)["selected_debt_id"] is None


@pytest.mark.asyncio
async def test_selecting_other_debt_explicitly_clears_saved_agreement_and_order(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    row = event(store, thread, 1)
    old_agreement, old_order = str(uuid4()), str(uuid4())
    async with checkpointer(conninfo, setup=True) as saver:
        inference = Inference(
            response(call("select_debt", {"debt_id": str(central.debts[1])})),
            final("Servicio seleccionado"),
        )
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text="Otro servicio",
        )
        state = await graph.ainvoke(
            {
                "identity_revision": 1,
                "messages": [],
                "pending_agreement_id": old_agreement,
                "active_order_id": old_order,
            },
            thread_config(thread),
        )
        assert state["selected_debt_id"] == str(central.debts[1])
        assert state["pending_agreement_id"] is None and state["active_order_id"] is None
        latest = json.loads(
            inference.calls[1]["instructions"].split("Contexto actual del servidor: ", 1)[1]
        )
        assert latest["pending_agreement_id"] is None and latest["active_order_id"] is None


@pytest.mark.asyncio
async def test_five_tool_responses_stop_and_register_honest_handoff(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    row = event(store, thread, 1)
    inference = Inference(*[response(call("list_debts", {"service_type": None})) for _ in range(5)])
    async with checkpointer(conninfo, setup=True) as saver:
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text="Consulta",
        )
        state = await graph.ainvoke({}, thread_config(thread))
        assert len(inference.calls) == 5 and state["phase"] == "handoff_requested"
        assert handoff.blocked(thread)
        assert "pendiente de confirmación" in state["messages"][-1]["reply"]
        assert state["messages"][-1]["complete"]


@pytest.mark.asyncio
async def test_oversized_current_input_fails_before_inference(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    row = event(store, thread, 1)
    inference = Inference(max_tokens=1)
    async with checkpointer(conninfo, setup=True) as saver:
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text="Mensaje que no cabe",
        )
        with pytest.raises(DomainError) as caught:
            await graph.ainvoke({}, thread_config(thread))
        assert caught.value.code == "context_limit" and not inference.calls


@pytest.mark.asyncio
async def test_token_window_trims_complete_old_groups_without_deleting_history(journey_store):
    from backend.integrations.openai import token_count

    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    row = event(store, thread, 1)
    history = [
        {
            "id": f"old-{number}",
            "items": [
                {"role": "user", "content": f"History-{number} " + "anterior " * 500},
                {
                    "type": "function_call",
                    "call_id": f"old-call-{number}",
                    "name": "list_debts",
                    "arguments": "{}",
                },
                {"type": "function_call_output", "call_id": f"old-call-{number}", "output": "{}"},
                {"role": "assistant", "content": "Respuesta anterior " * 200},
            ],
            "complete": True,
            "reply": "Respuesta anterior",
        }
        for number in range(30)
    ]
    inference = Inference(final("Respuesta nueva"), max_tokens=4500)
    async with checkpointer(conninfo, setup=True) as saver:
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text="Mensaje más reciente",
        )
        state = await graph.ainvoke(
            {"identity_revision": 1, "messages": history}, thread_config(thread)
        )
        sent = inference.calls[0]
        assert (
            token_count(
                {
                    "instructions": sent["instructions"],
                    "input": sent["input"],
                    "tools": sent["tools"],
                }
            )
            <= 4500
        )
        serialized = json.dumps(sent["input"], ensure_ascii=False)
        assert "Mensaje más reciente" in serialized and "History-0 " not in serialized
        assert sum(item.get("role") in {"user", "assistant"} for item in sent["input"]) <= 20
        assert len(state["messages"]) == 31
        assert state["messages"][0]["id"] == "old-0"
        latest = await graph.aget_state(thread_config(thread))
        assert len(latest.values["messages"]) == 31


@pytest.mark.asyncio
async def test_expiry_during_inference_discards_financial_reply_before_checkpoint(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    row = event(store, thread, 1)

    def expires_while_waiting(_):
        with store.begin() as session:
            session.get(VerifiedContext, thread).expires_at = utcnow() - timedelta(seconds=1)
        return final("STALE-PRIVATE-BALANCE 345.67")

    inference = Inference(expires_while_waiting, final("Debemos validar el registro de nuevo."))
    async with checkpointer(conninfo, setup=True) as saver:
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text="Consulta deuda",
        )
        state = await graph.ainvoke({}, thread_config(thread))
        assert len(inference.calls) == 2 and not identity.snapshot(thread)["verified"]
        assert "STALE-PRIVATE-BALANCE" not in json.dumps(state)
        assert "STALE-PRIVATE-BALANCE" not in json.dumps(inference.calls[1]["input"])
        assert state["selected_debt_id"] is None


@pytest.mark.asyncio
async def test_verified_pin_forces_real_list_debts_loop_and_retires_old_challenges(journey_store):
    store, conninfo = journey_store
    identity, handoff, central, thread = setup_services(store)
    with store.begin() as session:
        session.get(VerifiedContext, thread).selected_debt_id = None
    row = event(store, thread, 1)
    stale = [
        {
            "id": "old-lookup",
            "items": [
                {"role": "user", "content": "Busca mi registro"},
                {
                    "type": "function_call",
                    "name": "locate_customer",
                    "call_id": "old-call",
                    "arguments": "{}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "old-call",
                    "output": '{"requires_confirmation":true,"masked_hint":"F***"}',
                },
                {"role": "assistant", "content": "¿Confirmas el registro?"},
            ],
            "complete": True,
        }
    ]
    inference = Inference(
        response(call("list_debts", {"service_type": None})),
        final("Hay dos servicios. ¿Cuál quieres gestionar?"),
    )
    async with checkpointer(conninfo, setup=True) as saver:
        graph = build_graph(
            saver,
            runtime=runtime(row, identity, handoff, central),
            inference=inference,
            text="identity_verified",
        )
        state = await graph.ainvoke(
            {"identity_revision": 1, "messages": stale, "phase": "identify"}, thread_config(thread)
        )
        assert inference.calls[0]["tool_choice"] == {"type": "function", "name": "list_debts"}
        assert "tool_choice" not in inference.calls[1]
        assert (
            central.calls[-1][1] == "/debts"
            and central.calls[-1][2]["grant"] == "OLD-PRIVATE-GRANT"
        )
        assert "requires_confirmation" not in json.dumps(
            [request["input"] for request in inference.calls]
        )
        context = json.loads(
            inference.calls[0]["instructions"].split("Contexto actual del servidor: ", 1)[1]
        )
        assert context["identity_confirmation_complete"] and context["pin_validation_complete"]
        assert state["phase"] == "select_debt" and len(state["messages"]) == 2
        # A subsequent authenticated turn keeps the challenge out of the model input.
        newer = event(store, thread, 2)
        subsequent = Inference(final("Selecciona uno de tus servicios."))
        graph = build_graph(
            saver,
            runtime=runtime(newer, identity, handoff, central),
            inference=subsequent,
            text="Quiero pagar",
        )
        await graph.ainvoke({}, thread_config(thread))
        assert "requires_confirmation" not in json.dumps(
            [request["input"] for request in subsequent.calls]
        )
        assert "tool_choice" not in subsequent.calls[0]
