"""START -> agent -> END; a bounded tool loop lives inside this one node."""

from __future__ import annotations

import json
from typing import TypedDict

from agil_shared.errors import DomainError
from backend.agent.prompts import SYSTEM_PROMPT
from backend.integrations.openai import token_count
from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict, total=False):
    messages: list[dict]
    phase: str
    selected_debt_id: str | None
    pending_agreement_id: str | None
    active_order_id: str | None
    identity_revision: int


def merge_messages(old, new):
    merged = {item["id"]: item for item in old}
    for message in new:
        merged[message["id"]] = message
    return list(merged.values())


def context_window(groups, *, visible_limit=20):
    """Keep complete tool groups; never split a call from its output."""
    selected, visible = [], 0
    for group in reversed(groups):
        items = group["items"]
        count = sum(item.get("role") in {"user", "assistant"} for item in items)
        if selected and visible + count > visible_limit:
            break
        selected.insert(0, items)
        visible += count
    return [item for group in selected for item in group]


def _neutral_group(event_id):
    return {
        "id": event_id,
        "items": [
            {
                "role": "user",
                "content": "El registro o su autorización cambió. Continúa la validación sin utilizar información financiera anterior.",
            }
        ],
    }


def _clear_runtime(runtime):
    runtime.pending_agreement_id = None
    runtime.active_order_id = None
    runtime.phase = "identify"


def _challenge_group(group):
    financial = {
        "list_debts",
        "select_debt",
        "create_full_payment",
        "quote_agreement",
        "accept_agreement",
        "verify_payment",
    }
    calls = {item.get("name") for item in group["items"] if item.get("type") == "function_call"}
    return "locate_customer" in calls or (
        not calls.intersection(financial)
        and any(
            item.get("role") == "user" and item.get("content") == "identity_verified"
            for item in group["items"]
        )
    )


def build_graph(checkpointer, *, runtime, inference, text):
    async def agent(state: AgentState):
        event = runtime.event
        snapshot = runtime.identity.snapshot(event.thread_id)
        same_identity = state.get("identity_revision", -1) == snapshot["identity_revision"]
        groups = list(state.get("messages", [])) if same_identity else []
        # References are hydrated once and subsequently assigned explicitly, including None.
        runtime.pending_agreement_id = state.get("pending_agreement_id") if same_identity else None
        runtime.active_order_id = state.get("active_order_id") if same_identity else None
        runtime.phase = state.get("phase", "identify") if same_identity else "identify"
        bootstrap_identity = bool(
            snapshot["verified"]
            and (
                text == "identity_verified"
                or (not snapshot["selected_debt_id"] and runtime.phase == "identify")
            )
        )
        if snapshot["verified"] and not snapshot["selected_debt_id"]:
            runtime.phase = "select_debt"
        group_id = str(event.id)
        prior = next(
            (group for group in groups if group["id"] == group_id and group.get("complete")), None
        )
        if prior:
            return dict(state)
        current = {"id": group_id, "items": [{"role": "user", "content": text}]}
        groups = merge_messages(groups, [current])
        completed = False
        for call_index in range(inference.settings.ai_max_calls_per_turn):
            fresh = runtime.identity.snapshot(event.thread_id)
            if fresh["identity_revision"] != snapshot["identity_revision"]:
                snapshot = fresh
                current = _neutral_group(group_id)
                groups = [current]
                _clear_runtime(runtime)
            context = {
                "source_id": event.thread_id,
                "identity_verified": snapshot["verified"],
                "identity_confirmation_complete": snapshot["verified"],
                "pin_validation_complete": snapshot["verified"],
                "phase": runtime.phase,
                "identity_challenge": snapshot.get("challenge_state", "none"),
                "selected_debt_id": snapshot["selected_debt_id"],
                "identity_revision": snapshot["identity_revision"],
                "pending_agreement_id": runtime.pending_agreement_id,
                "active_order_id": runtime.active_order_id,
            }
            instructions = (
                SYSTEM_PROMPT
                + "\nContexto actual del servidor: "
                + json.dumps(context, ensure_ascii=False)
            )
            catalog = runtime.catalog()
            candidates = [
                group
                for group in groups
                if group is current
                or not snapshot["verified"]
                or (not bootstrap_identity and not _challenge_group(group))
            ]
            while True:
                inputs = context_window(
                    candidates, visible_limit=inference.settings.history_visible_messages
                )
                if (
                    token_count({"instructions": instructions, "input": inputs, "tools": catalog})
                    <= inference.settings.ai_max_input_tokens
                ):
                    break
                if len(candidates) <= 1:
                    raise DomainError(
                        "context_limit", "El mensaje es demasiado largo; envíalo más breve.", 422
                    )
                candidates.pop(0)
            response_options = {}
            if (
                call_index == 0
                and bootstrap_identity
                and snapshot["verified"]
                and any(tool["name"] == "list_debts" for tool in catalog)
            ):
                response_options["tool_choice"] = {"type": "function", "name": "list_debts"}
            response = await inference.response(
                event_id=event.id,
                input=inputs,
                instructions=instructions,
                tools=catalog,
                **response_options,
            )
            # An authorization may expire while inference runs. Discard that response,
            # including its reasoning and proposed effects, before using the new identity.
            fresh = runtime.identity.snapshot(event.thread_id)
            if fresh["identity_revision"] != snapshot["identity_revision"]:
                snapshot = fresh
                current = _neutral_group(group_id)
                groups = [current]
                _clear_runtime(runtime)
                continue
            calls = [item for item in response.output if item.type == "function_call"]
            if len(calls) > 1:
                raise DomainError(
                    "parallel_tools_denied", "No se admiten herramientas simultáneas.", 503
                )
            output = [item.model_dump(mode="json", exclude_none=True) for item in response.output]
            current["items"].extend(output)
            if not calls:
                current["complete"] = True
                current["reply"] = (
                    response.output_text or "No pude completar la respuesta. Intenta de nuevo."
                )
                completed = True
                break
            call = calls[0]
            try:
                result = await runtime.execute(call.name, json.loads(call.arguments))
            except (ValueError, TypeError, DomainError) as exc:
                result = {
                    "code": exc.code if isinstance(exc, DomainError) else "invalid_tool_arguments",
                    "message": exc.message
                    if isinstance(exc, DomainError)
                    else "Argumentos inválidos.",
                }
            tool_output = {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(result, ensure_ascii=False, default=str),
            }
            current["items"].append(tool_output)
            fresh = runtime.identity.snapshot(event.thread_id)
            if fresh["identity_revision"] != snapshot["identity_revision"]:
                snapshot = fresh
                # Only a fresh masked lookup survives the identity boundary. Neither
                # original text, reasoning, old balances nor previous tool groups survive.
                current = _neutral_group(group_id)
                if call.name == "locate_customer" and "code" not in result:
                    current["items"].extend(
                        [call.model_dump(mode="json", exclude_none=True), tool_output]
                    )
                groups = [current]
                _clear_runtime(runtime)
            if runtime.phase == "handoff_requested" or runtime.handoff.blocked(event.thread_id):
                current["complete"] = True
                current["reply"] = (
                    "La solicitud de atención humana quedó registrada; la transferencia está pendiente de confirmación."
                )
                runtime.phase = "handoff_requested"
                completed = True
                break
        if not completed:
            await runtime.handoff.request(
                event,
                reason="technical_failure",
                summary="Se alcanzó el límite de llamadas del turno sin una respuesta final.",
            )
            current["complete"] = True
            current["reply"] = (
                "No pude completar la gestión dentro del límite. Registré una solicitud de atención humana; la transferencia está pendiente de confirmación."
            )
            runtime.phase = "handoff_requested"
        fresh = runtime.identity.snapshot(event.thread_id)
        if fresh["identity_revision"] != snapshot["identity_revision"]:
            current = _neutral_group(group_id)
            current.update(
                complete=True,
                reply="La validación cambió. Debemos validar el registro de nuevo antes de continuar.",
            )
            groups = [current]
            _clear_runtime(runtime)
        return {
            "messages": groups,
            "phase": runtime.phase,
            "identity_revision": fresh["identity_revision"],
            "selected_debt_id": fresh["selected_debt_id"],
            "pending_agreement_id": runtime.pending_agreement_id,
            "active_order_id": runtime.active_order_id,
        }

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph.compile(checkpointer=checkpointer)
