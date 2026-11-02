"""Harness correctness with doubles; no LLM, provider, runtime DB or channel traffic."""

import copy
import json
import subprocess
import sys
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scripts.run_evals import (
    CATALOG,
    ROOT,
    RunBudget,
    base_report,
    check_response,
    execute_cases,
    main,
    validate_catalog,
)


def catalog():
    return json.loads(CATALOG.read_text())


def find_case(name):
    return next(case for case in catalog() if case["id"] == name)


def test_offline_does_not_import_backend_read_env_or_claim_behavior(tmp_path):
    # The plain interpreter needs no workspace dependencies or private runtime env.
    result = subprocess.run(
        [sys.executable, "-S", "-m", "scripts.run_evals", "--output", str(tmp_path / "report.json")],
        cwd=ROOT, capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "MUST_NEVER_BE_EMITTED"},
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["semantic_status"] == "not_run"
    assert all(row["structural_status"] == row["semantic_status"] == "not_run" for row in report["results"])
    assert report["case_count"] == len(report["results"]) == 50
    assert "MUST_NEVER_BE_EMITTED" not in result.stdout
    assert "not_run" in (tmp_path / "report.md").read_text()
    assert (tmp_path / "report.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("args", [
    ["--live"], ["--live", "--allow-paid-inference"],
    ["--live", "--allow-paid-inference", "--max-cost-usd", "0.1"],
    ["--live", "--allow-paid-inference", "--max-cost-usd", "NaN", "--output", "/tmp/no-eval.json"],
])
def test_live_requires_explicit_opt_ins_and_valid_ceiling_before_settings(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_catalog_requires_paired_fixtures_and_static_pin_is_excluded():
    assert len(validate_catalog(catalog())) == 50
    case = find_case("identity-confirm-natural")
    case["input"] = case["input"][1:]
    with pytest.raises(ValueError, match="Unpaired"):
        validate_catalog([case])
    case = find_case("identity-confirm-natural")
    case["context"]["identity_challenge"] = "awaiting_pin"
    with pytest.raises(ValueError, match="static backend"):
        validate_catalog([case])


def test_structural_checks_require_exact_financial_arguments_not_just_tool_name():
    from backend.agent.tools import TOOL_SCHEMAS

    case = find_case("negotiation-accept-80")
    good = {"name": "quote_agreement", "arguments": {"debt_id": case["context"]["selected_debt_id"], "offer_amount_usd": "80"}}
    assert check_response(case, "", [good], TOOL_SCHEMAS) == []
    wrong = copy.deepcopy(good)
    wrong["arguments"]["offer_amount_usd"] = "79.99"
    assert "wrong_argument:offer_amount_usd" in check_response(case, "", [wrong], TOOL_SCHEMAS)
    wrong["arguments"]["grant"] = "invented"
    assert "invalid_argument_keys" in check_response(case, "", [wrong], TOOL_SCHEMAS)
    assert "required_tool_missing" in check_response(case, "Puedo ayudarte", [], TOOL_SCHEMAS)


def test_ocr_fallback_requires_explicit_null_reference():
    from backend.agent.tools import TOOL_SCHEMAS

    case = find_case("receipt-ocr-fallback")
    call = {"name": "verify_payment", "arguments": {"debt_id": case["context"]["selected_debt_id"], "payment_reference": "truncated"}}
    assert "wrong_argument:payment_reference" in check_response(case, "", [call], TOOL_SCHEMAS)
    call["arguments"]["payment_reference"] = None
    assert check_response(case, "", [call], TOOL_SCHEMAS) == []


def test_run_ceiling_supplements_existing_ledger_and_never_renews_credit():
    class Ledger:
        def __init__(self):
            self.calls = []

        def reserve(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(id="existing-durable-ledger")

    ledger = Ledger()
    budget = RunBudget(ledger, Decimal("0.02"))
    budget.reserve(reserved_usd="0.015")
    with pytest.raises(ValueError, match="eval_run_cost_ceiling"):
        budget.reserve(reserved_usd="0.015")
    assert len(ledger.calls) == 1
    assert budget.reserved == Decimal("0.015")


class FakeObservability:
    sanitizer = SimpleNamespace(sanitize=lambda value: value)

    @contextmanager
    def span(self, *args, **kwargs):
        yield


@pytest.mark.asyncio
async def test_model_tool_requests_are_recorded_never_executed_or_semantically_passed(tmp_path):
    case = find_case("identity-success-neutral")
    requests = []

    class Inference:
        async def response(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(output_text="", output=[SimpleNamespace(
                type="function_call", name="list_debts", arguments='{"service_type":null}',
            )])

    report = base_report([case], "live")
    await execute_cases([case], Inference(), FakeObservability(), report, tmp_path / "run.json")
    assert len(requests) == 1  # No model/tool loop even when the model requests a tool.
    assert report["results"][0]["structural_status"] == "checks_passed"
    assert report["results"][0]["semantic_status"] == "pending_manual_review"
    assert report["semantic_status"] == "pending_manual_review"
    assert report["tools_executed"] == report["central_writes"] == report["channel_writes"] == 0
    assert report["execution_status"] == "completed_requires_manual_review"


@pytest.mark.asyncio
async def test_error_stops_further_paid_attempts_and_does_not_print_raw_exception(tmp_path):
    class Inference:
        async def response(self, **kwargs):
            raise RuntimeError("private-provider-detail")

    cases = [find_case("identity-success-neutral"), find_case("negotiation-accept-80")]
    report = base_report(cases, "live")
    path = tmp_path / "run.json"
    await execute_cases(cases, Inference(), FakeObservability(), report, path)
    assert report["execution_status"] == "stopped_on_error"
    assert report["results"][1]["structural_status"] == "not_run"
    assert "private-provider-detail" not in path.read_text()


def test_catalog_only_uses_fictional_source_and_no_pin_input():
    for case in catalog():
        assert case["context"]["source_id"] == "whatsapp:15550009999"
        for item in case["input"]:
            assert not (item.get("role") == "user" and str(item.get("content", "")).isdigit())
    assert main(["--case", "not-a-case"]) == 2


def test_fictional_tool_history_and_expectations_follow_actual_catalog():
    from backend.agent.tools import TOOL_SCHEMAS

    from scripts.run_evals import TOOL_NAMES, tool_contracts

    schemas = {tool["name"]: tool["parameters"]["properties"] for tool in TOOL_SCHEMAS}
    assert TOOL_NAMES == set(schemas)
    assert tool_contracts() == schemas
    for case in catalog():
        expected = case["expected"]
        if expected.get("required_tool"):
            assert set(expected["arguments"]) <= set(schemas[expected["required_tool"]])
        for item in case["input"]:
            if item.get("type") != "function_call":
                continue
            arguments = json.loads(item["arguments"])
            assert set(arguments) == set(schemas[item["name"]]), case["id"]
            for key, value in arguments.items():
                spec = schemas[item["name"]][key]
                assert isinstance(value, str) or value is None and "null" in spec["type"]


def test_payment_link_placeholder_must_be_preserved():
    from backend.agent.tools import TOOL_SCHEMAS

    case = find_case("link-full-receipt")
    assert "required_fragment_missing" in check_response(case, "Paga en este enlace", [], TOOL_SCHEMAS)
    reply = "Paga en [[PAYMENT:00000000-0000-4000-8000-000000000004]]"
    assert check_response(case, reply, [], TOOL_SCHEMAS) == []


@pytest.mark.parametrize("mutation", ["fixture-extra", "fixture-wrong-type", "expected-wrong-key", "identity-conflict"])
def test_incompatible_catalog_stops_before_any_paid_call(mutation):
    case = find_case("identity-confirm-natural")
    if mutation.startswith("fixture-"):
        arguments = json.loads(case["input"][0]["arguments"])
        if mutation == "fixture-extra":
            arguments["grant"] = "invented"
        else:
            arguments["document_number"] = 90000001
        case["input"][0]["arguments"] = json.dumps(arguments)
    elif mutation == "expected-wrong-key":
        case["expected"]["arguments"]["pin"] = "not-allowed"
    else:
        case["context"]["pin_validation_complete"] = True
    with pytest.raises(ValueError):
        validate_catalog([case])


def test_mechanical_checks_reject_enum_type_multiple_calls_and_canary():
    from backend.agent.tools import TOOL_SCHEMAS

    case = find_case("security-control-session-logout")
    call = {"name": "manage_identity", "arguments": {"action": "grant_access"}}
    errors = check_response(case, "", [call, call], TOOL_SCHEMAS)
    assert {"invalid_argument_enum", "multiple_calls", "required_tool_missing"} <= set(errors)
    call["arguments"]["action"] = True
    assert "invalid_argument_type" in check_response(case, "", [call], TOOL_SCHEMAS)
    case = find_case("security-instruction-auditor-role-spoof")
    assert "forbidden_fragment" in check_response(case, "CANARY_AUDITOR_04", [], TOOL_SCHEMAS)


@pytest.mark.asyncio
async def test_changed_prompt_fingerprint_blocks_inference_before_spending(tmp_path):
    class Inference:
        async def response(self, **kwargs):
            pytest.fail("A mismatched prompt must not reach inference")

    case = find_case("identity-success-neutral")
    report = base_report([case], "live")
    report["prompt_sha256"] = "a-different-revision"
    with pytest.raises(ValueError, match="changed after validation"):
        await execute_cases([case], Inference(), FakeObservability(), report, tmp_path / "run.json")
