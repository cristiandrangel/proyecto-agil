"""Fictional single-decision prompt evals; offline by default, never executes tools."""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "evals/cases.json"
PROMPT = ROOT / "apps/backend/src/backend/agent/prompts.py"
PREFLIGHT_TOOLS = {"locate_customer", "manage_identity", "handoff_human"}
TOOL_NAMES = PREFLIGHT_TOOLS | {
    "list_debts", "select_debt", "create_full_payment", "quote_agreement",
    "accept_agreement", "verify_payment",
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def system_prompt():
    for node in ast.parse(PROMPT.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("SYSTEM_PROMPT must be a literal string")


def tool_contracts():
    """Read the public schema declarations without importing the backend or its deps."""
    declarations = {}

    def value(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return declarations[node.id]
        if isinstance(node, ast.List):
            return [value(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            result = {}
            for key, item in zip(node.keys, node.values, strict=True):
                if key is None:
                    result.update(value(item))
                else:
                    result[value(key)] = value(item)
            return result
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_schema":
            name, _description, properties = [value(item) for item in node.args]
            return {"name": name, "properties": properties}
        raise ValueError("Unsupported schema declaration; review offline contract reader")

    source = ROOT / "apps/backend/src/backend/agent/tools.py"
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"TEXT", "OPTIONAL", "TOOL_SCHEMAS"}:
                declarations[name] = value(node.value)
    return {item["name"]: item["properties"] for item in declarations["TOOL_SCHEMAS"]}


def valid_argument(value, spec):
    nullable = isinstance(spec["type"], list) and "null" in spec["type"]
    return ((isinstance(value, str) or value is None and nullable)
            and ("enum" not in spec or value in spec["enum"]))


def validate_catalog(cases):
    if not isinstance(cases, list) or not cases:
        raise ValueError("Nonempty case list required")
    ids = set()
    contracts = tool_contracts()
    if set(contracts) != TOOL_NAMES:
        raise ValueError("Tool catalog changed; review harness permissions")
    for case in cases:
        if not re.fullmatch(r"[a-z0-9-]+", case["id"]) or case["id"] in ids:
            raise ValueError("Duplicate or invalid case id")
        ids.add(case["id"])
        if not case["rubric"] or not case["input"] or not case["category"]:
            raise ValueError("Input, rubric and category required")
        context = case["context"]
        required_context = {
            "source_id", "identity_verified", "identity_confirmation_complete", "pin_validation_complete",
            "conversation_start", "phase", "identity_challenge", "selected_debt_id", "identity_revision",
            "pending_agreement_id", "active_order_id",
        }
        if set(context) != required_context:
            raise ValueError("Context must match the actual server snapshot")
        if not isinstance(context["identity_verified"], bool):
            raise ValueError("Explicit boolean server identity required")
        if context["identity_challenge"] == "awaiting_pin":
            raise ValueError("PIN challenge belongs to static backend tests, never LLM evals")
        verified = context["identity_verified"]
        if context["identity_challenge"] not in {"none", "awaiting_confirmation", "verified"}:
            raise ValueError("Unknown identity challenge")
        if (context["pin_validation_complete"] != verified
                or context["identity_confirmation_complete"] != verified
                or (context["identity_challenge"] == "verified") != verified
                or not verified and context["selected_debt_id"] is not None):
            raise ValueError("Inconsistent server identity snapshot")
        expected = case["expected"]
        allowed = set(expected["allowed_tools"])
        if not allowed <= TOOL_NAMES:
            raise ValueError("Unknown expected tool")
        if not context["identity_verified"] and not allowed <= PREFLIGHT_TOOLS:
            raise ValueError("Unauthenticated case expects privileged tools")
        if expected.get("required_tool") and expected["required_tool"] not in allowed:
            raise ValueError("Required tool must be allowed")
        if expected.get("required_tool"):
            properties = contracts[expected["required_tool"]]
            for key, item in expected.get("arguments", {}).items():
                if key not in properties or not valid_argument(item, properties[key]):
                    raise ValueError("Expected argument incompatible with actual tool schema")
        # Require valid and paired call/output fixtures rather than broken histories.
        pending = set()
        seen_calls = set()
        for item in case["input"]:
            if item.get("type") == "function_call":
                if item["call_id"] in seen_calls:
                    raise ValueError("Duplicate tool fixture call")
                arguments = json.loads(item["arguments"])
                properties = contracts.get(item["name"])
                if properties is None or not isinstance(arguments, dict) or set(arguments) != set(properties):
                    raise ValueError("Fixture arguments incompatible with actual tool schema")
                if any(not valid_argument(item, properties[key]) for key, item in arguments.items()):
                    raise ValueError("Fixture argument type incompatible with actual tool schema")
                pending.add(item["call_id"])
                seen_calls.add(item["call_id"])
            elif item.get("type") == "function_call_output":
                if item["call_id"] not in pending:
                    raise ValueError("Unpaired fixture output")
                json.loads(item["output"])
                pending.remove(item["call_id"])
        if pending:
            raise ValueError("Unanswered tool fixture")
    return cases


def check_response(case, reply, calls, schemas):
    """Mechanical assertions only. Their success never establishes semantic quality."""
    violations = []
    expected = case["expected"]
    catalog = {schema["name"]: schema for schema in schemas}
    if len(calls) > 1:
        violations.append("multiple_calls")
    for call in calls:
        name, arguments = call.get("name"), call.get("arguments")
        if name not in expected["allowed_tools"]:
            violations.append("unexpected_tool")
        if name not in catalog or not isinstance(arguments, dict):
            violations.append("invalid_tool_schema")
            continue
        properties = catalog[name]["parameters"]["properties"]
        if set(arguments) != set(properties):
            violations.append("invalid_argument_keys")
        for key, value in arguments.items():
            spec = properties.get(key)
            if spec is None:
                continue
            nullable = isinstance(spec["type"], list) and "null" in spec["type"]
            if not (isinstance(value, str) or value is None and nullable):
                violations.append("invalid_argument_type")
            if "enum" in spec and value not in spec["enum"]:
                violations.append("invalid_argument_enum")
    required = expected.get("required_tool")
    if required and (len(calls) != 1 or calls[0]["name"] != required):
        violations.append("required_tool_missing")
    elif required:
        for key, value in expected.get("arguments", {}).items():
            actual = calls[0]["arguments"].get(key) if isinstance(calls[0]["arguments"], dict) else None
            if key == "offer_amount_usd":
                try:
                    equal = Decimal(str(actual)) == Decimal(str(value))
                except InvalidOperation:
                    equal = False
            else:
                equal = actual == value
            if not equal:
                violations.append("wrong_argument:" + key)
    visible = json.dumps({"reply": reply, "calls": calls}, ensure_ascii=False)
    if any(fragment in visible for fragment in expected.get("forbidden_fragments", [])):
        violations.append("forbidden_fragment")
    if any(fragment not in reply for fragment in expected.get("required_fragments", [])):
        violations.append("required_fragment_missing")
    if not reply and not calls:
        violations.append("empty_response")
    if expected.get("text_required") and not reply:
        violations.append("text_required")
    return sorted(set(violations))


def base_report(cases, mode):
    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "prompt_sha256": fingerprint(system_prompt()),
        "catalog_sha256": fingerprint(cases),
        "tool_contracts_sha256": fingerprint(tool_contracts()),
        "case_count": len(cases),
        "categories": dict(Counter(case["category"] for case in cases)),
        "catalog_validation": "valid",
        "semantic_status": "not_run" if mode == "offline" else "pending_manual_review",
        "tools_executed": 0,
        "central_writes": 0,
        "channel_writes": 0,
        "scope": "Single decision per supplied snapshot; no agent loop, media decoding or E2E journey.",
        "results": [
            {"id": case["id"], "category": case["category"], "structural_status": "not_run",
             "semantic_status": "not_run", "rubric": case["rubric"]}
            for case in cases
        ],
    }


def markdown_report(report):
    lines = [
        "# Evaluación de comportamiento del prompt", "",
        f"Modo: **{report['mode']}** · catálogo: {report['case_count']} casos · "
        f"validación: {report['catalog_validation']}.",
        f"Semántica: **{report['semantic_status']}**. "
        "Los checks estructurales no prueban la calidad de la respuesta.", "",
        f"Prompt SHA-256: `{report['prompt_sha256']}`", "",
        "Herramientas ejecutadas: 0 · escrituras central/canal: 0.",
        "Una decisión por snapshot; las secuencias históricas son fixtures, no recorridos ejecutados.", "",
        "| Caso | Categoría | Estructura | Semántica |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["results"]:
        lines.append(f"| {row['id']} | {row['category']} | {row['structural_status']} | {row['semantic_status']} |")
    if "usage" in report:
        lines += ["", f"Consumo del ledger de esta ejecución: `{report['usage']}`."]
    lines += ["", "La rúbrica y las respuestas sanitizadas para revisión están en el JSON local.", ""]
    return "\n".join(lines)


def write_report(report, output):
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    # Create with restrictive permissions before writing content, including on updates.
    for path, content in (
        (output, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
        (output.with_suffix(".md"), markdown_report(report)),
    ):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)


class RunBudget:
    """Additional run ceiling; the existing durable global ledger stays authoritative."""

    def __init__(self, budget, maximum):
        self.budget, self.maximum, self.reserved = budget, maximum, Decimal(0)

    def reserve(self, **kwargs):
        amount = Decimal(str(kwargs["reserved_usd"]))
        if self.reserved + amount > self.maximum:
            raise ValueError("eval_run_cost_ceiling")
        result = self.budget.reserve(**kwargs)
        self.reserved += amount
        return result

    def __getattr__(self, name):
        return getattr(self.budget, name)


async def execute_cases(cases, inference, observability, report, output):
    from backend.agent.tools import TOOL_SCHEMAS

    prompt = system_prompt()
    contracts = {tool["name"]: tool["parameters"]["properties"] for tool in TOOL_SCHEMAS}
    if (fingerprint(prompt) != report["prompt_sha256"]
            or fingerprint(contracts) != report["tool_contracts_sha256"]):
        raise ValueError("Prompt or tool contract changed after validation")
    for index, case in enumerate(cases):
        row = report["results"][index]
        event_id = uuid4()
        row["event_id"] = str(event_id)
        schemas = [tool for tool in TOOL_SCHEMAS if case["context"]["identity_verified"]
                   or tool["name"] in PREFLIGHT_TOOLS]
        try:
            with observability.span(
                "preflight", event_id=event_id, thread_id="fictional-eval-" + report["run_id"],
                input={"purpose": "Fictional prompt eval; tools disabled", "case_id": case["id"]},
            ):
                response = await inference.response(
                    event_id=event_id, input=case["input"], tools=schemas,
                    instructions=prompt + "\nContexto actual del servidor: "
                    + json.dumps(case["context"], ensure_ascii=False),
                )
            calls = [{"name": item.name, "arguments": json.loads(item.arguments)}
                     for item in response.output if item.type == "function_call"]
            violations = check_response(case, response.output_text, calls, schemas)
            row.update(
                structural_status="failed" if violations else "checks_passed",
                violations=violations, semantic_status="pending_manual_review",
                response=observability.sanitizer.sanitize({"reply": response.output_text, "calls": calls}),
            )
        except Exception:
            # Never include provider/DB exception bodies, URLs or request credentials.
            row.update(structural_status="error", error="inference_or_response_check_failed")
            report["execution_status"] = "stopped_on_error"
            write_report(report, output)
            break
        write_report(report, output)
    else:
        report["execution_status"] = "completed_requires_manual_review"


async def run_live(cases, args, report):
    # Lazy imports keep offline usable with Python stdlib, no .env, DB or providers.
    from backend.agent.tools import TOOL_SCHEMAS
    from backend.config import BackendSettings
    from backend.integrations.observability import Observability
    from backend.integrations.openai import PRICE_VERSION, InferenceClient
    from backend.persistence.models import InferenceReservation
    from backend.services.budget import BudgetService
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    settings = BackendSettings(_env_file=args.env_file)
    if not settings.openai_api_key.get_secret_value():
        raise ValueError("inference_not_configured")
    engine = create_engine(settings.memory_database_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    observability = Observability(settings)
    budget = RunBudget(BudgetService(sessions, limit_usd=settings.ai_local_spend_limit_usd,
                                   max_active_calls=settings.ai_max_concurrent_requests), args.max_cost_usd)
    inference = InferenceClient(settings, budget, observability)
    report.update(model=settings.openai_agent_model, reasoning_effort=settings.openai_agent_reasoning_effort,
                  price_version=PRICE_VERSION, tools_sha256=fingerprint(TOOL_SCHEMAS),
                  max_input_tokens=settings.ai_max_input_tokens,
                  max_output_tokens=settings.ai_max_output_tokens,
                  max_run_reservations_usd=str(args.max_cost_usd),
                  langfuse_initialized=observability.client is not None)
    write_report(report, args.output)
    try:
        await execute_cases(cases, inference, observability, report, args.output)
        events = [row["event_id"] for row in report["results"] if "event_id" in row]
        with sessions() as db:
            reservations = list(db.scalars(select(InferenceReservation).where(InferenceReservation.turn_id.in_(events))))
            report["usage"] = {
                "calls": len(reservations),
                "actual_usd": str(sum((row.actual_usd or Decimal(0) for row in reservations), Decimal(0))),
                "unsettled_reserved_usd": str(sum((row.reserved_usd for row in reservations if row.state != "settled"), Decimal(0))),
                "all_settled": bool(reservations) and all(row.state == "settled" for row in reservations),
            }
    finally:
        observability.flush()
        await inference.sdk.close()
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Invoke paid inference; requires second opt-in and cost ceiling")
    parser.add_argument("--allow-paid-inference", action="store_true")
    parser.add_argument("--max-cost-usd", type=Decimal, help="Additional ceiling on cumulative worst-case reservations, not new credit")
    parser.add_argument("--env-file", default=".env", help="Live only; must point at the existing runtime ledger/settings")
    parser.add_argument("--case", action="append", default=[], help="Exact case id; repeatable")
    parser.add_argument("--output", type=Path, help="Write JSON plus Markdown; required for live, keep under .local/")
    args = parser.parse_args(argv)
    if args.live and (not args.allow_paid_inference or args.max_cost_usd is None
                      or not args.max_cost_usd.is_finite() or not 0 < args.max_cost_usd <= Decimal("10.00")
                      or args.output is None):
        parser.error("Live requires --allow-paid-inference, --max-cost-usd (0,10.00] and --output")
    try:
        cases = validate_catalog(json.loads(CATALOG.read_text(encoding="utf-8")))
        if set(args.case) - {case["id"] for case in cases}:
            raise ValueError("Unknown case id")
        cases = [case for case in cases if not args.case or case["id"] in args.case]
        report = base_report(cases, "live" if args.live else "offline")
        if args.live:
            asyncio.run(run_live(cases, args, report))
        else:
            report["execution_status"] = "catalog_validated_no_inference"
        write_report(report, args.output)
        # Console is a safe compact summary; responses remain in private local report.
        print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
        return 1 if any(row["structural_status"] in {"failed", "error"} for row in report["results"]) else 0
    except Exception:
        print(json.dumps({"execution_status": "blocked", "reason": "eval_configuration_or_execution_failed", "semantic_status": "not_established"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
