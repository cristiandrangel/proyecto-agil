"""Agent context/tools: valid groups, strict arguments and server-owned authority."""

from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agil_shared.errors import DomainError
from backend.agent.graph import context_window, merge_messages
from backend.agent.tools import ToolRuntime


class Identity:
    def __init__(self, verified=True):
        self.data = {
            "verified": verified,
            "grant_token": "server-private-grant",
            "selected_debt_id": str(uuid4()),
        }
        self.selections = []

    def snapshot(self, _):
        return self.data.copy()

    async def select_debt(self, thread, debt):
        self.selections.append((thread, debt))
        self.data["selected_debt_id"] = debt
        return {"id": debt}


class Central:
    def __init__(self):
        self.calls = []
        self.result = None

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        if path.startswith("/debts/"):
            return {"version": 3, "balance_cents": 10000}
        return self.result or {"items": []}


class Human:
    def __init__(self):
        self.active = False
        self.requests = []

    def blocked(self, _):
        return self.active

    async def request(self, event, **kwargs):
        self.active = True
        self.requests.append(kwargs)
        return {"case_id": "demo-case", "status": "action_pending"}


def runtime(verified=True):
    event = SimpleNamespace(
        id=uuid4(), thread_id="literal:+source with spaces", message_id="current-message"
    )
    return ToolRuntime(
        event,
        Identity(verified),
        Central(),
        Human(),
        SimpleNamespace(span=lambda *a, **k: nullcontext()),
    )


def test_window_preserves_complete_call_output_groups_and_latest_message():
    groups = [
        {
            "id": str(i),
            "items": [
                {"role": "user", "content": f"User {i}"},
                {"type": "function_call", "call_id": f"call-{i}"},
                {"type": "function_call_output", "call_id": f"call-{i}"},
                {"role": "assistant", "content": f"Assistant {i}"},
            ],
        }
        for i in range(25)
    ]
    selected = context_window(groups, visible_limit=20)
    assert len(selected) == 40
    assert selected[0]["content"] == "User 15" and selected[-1]["content"] == "Assistant 24"
    for item in selected:
        if item.get("type") == "function_call":
            assert any(
                output.get("type") == "function_call_output"
                and output["call_id"] == item["call_id"]
                for output in selected
            )
    assert len(groups) == 25


def test_merge_dedupes_event_group_preserving_history():
    old = [{"id": "first", "items": []}, {"id": "second", "items": []}]
    assert merge_messages(
        old, [{"id": "second", "items": [{"role": "user", "content": "retry"}]}]
    ) == [old[0], {"id": "second", "items": [{"role": "user", "content": "retry"}]}]


@pytest.mark.asyncio
async def test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant():
    tool = runtime(False)
    assert {item["name"] for item in tool.catalog()} == {"locate_customer", "handoff_human"}
    with pytest.raises(DomainError) as caught:
        await tool.execute("list_debts", {"service_type": None})
    assert caught.value.code == "tool_forbidden" and not tool.central.calls
    tool = runtime()
    for arguments in [{"service_type": None, "grant_token": "forged"}, {}, {"service_type": 123}]:
        with pytest.raises(DomainError) as caught:
            await tool.execute("list_debts", arguments)
        assert caught.value.code == "invalid_tool_arguments"
    await tool.execute("list_debts", {"service_type": None})
    assert tool.central.calls[-1][2]["grant"] == "server-private-grant"


@pytest.mark.asyncio
async def test_debt_selection_required_and_select_clears_old_refs():
    tool = runtime()
    tool.pending_agreement_id, tool.active_order_id = str(uuid4()), str(uuid4())
    foreign_debt = str(uuid4())
    with pytest.raises(DomainError) as caught:
        await tool.execute("create_full_payment", {"debt_id": foreign_debt})
    assert caught.value.code == "debt_selection_required" and not tool.central.calls
    await tool.execute("select_debt", {"debt_id": foreign_debt})
    assert tool.pending_agreement_id is None and tool.active_order_id is None
    assert tool.identity.selections[-1] == (tool.event.thread_id, foreign_debt)


@pytest.mark.asyncio
async def test_accept_cannot_use_agreement_from_another_selection():
    tool = runtime()
    tool.pending_agreement_id = str(uuid4())
    with pytest.raises(DomainError) as caught:
        await tool.execute("accept_agreement", {"agreement_id": str(uuid4())})
    assert caught.value.code == "agreement_selection_required"
    assert all(method == "GET" for method, _, _ in tool.central.calls)


@pytest.mark.asyncio
async def test_payment_capability_never_crosses_model_checkpoint_boundary():
    tool = runtime()
    order = str(uuid4())
    tool.central.result = {
        "order_id": order,
        "capability": "private-payment-capability",
        "payable_cents": 10000,
    }
    result = await tool.execute(
        "create_full_payment", {"debt_id": tool.identity.data["selected_debt_id"]}
    )
    assert result["payment_link"] == f"[[PAYMENT:{order}]]"
    assert "capability" not in result and "private-payment-capability" not in str(result)
    assert tool.active_order_id == order


@pytest.mark.asyncio
async def test_handoff_blocks_further_financial_tools_in_same_turn():
    tool = runtime()
    tool.central.result = {"requires_human": True}
    result = await tool.execute(
        "quote_agreement",
        {"debt_id": tool.identity.data["selected_debt_id"], "offer_amount_usd": "79.99"},
    )
    assert result["status"] == "action_pending" and tool.phase == "handoff_requested"
    assert tool.catalog() == []
    with pytest.raises(DomainError):
        await tool.execute("list_debts", {"service_type": None})
