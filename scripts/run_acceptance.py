"""Deterministic acceptance evidence; never invokes live inference or messaging."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

# Evidence identifiers are executable pytest node IDs. A passing automated check
# does not prove delivery by Chatwoot, LLM reasoning, provider usage, or deployment.
AC_EVIDENCE = {
    "AC-01": [
        "tests/integration/test_central_finance.py::test_frozen_alembic_upgrade_downgrade_matches_models",
        "tests/contracts/test_web_frontends.py::test_private_console_login_and_csrf_rotation",
    ],
    "AC-02": [
        "tests/integration/test_central_finance.py::test_customer_grants_isolate_debts_and_switch_revokes_prior",
        "tests/unit/test_agent_context.py::test_debt_selection_required_and_select_clears_old_refs",
    ],
    "AC-03": [
        "tests/integration/test_central_finance.py::test_masked_identity_pin_lock_and_retry_deduplication",
        "tests/integration/test_backend_identity.py::test_invalid_pin_media_and_temporary_failure_do_not_reach_agent",
    ],
    "AC-04": [
        "tests/integration/test_backend_identity.py::test_confirm_pin_is_neutral_and_grant_only_in_runtime",
        "tests/integration/test_text_journey.py::test_locate_preserves_only_fresh_masked_tool_after_identity_switch",
    ],
    "AC-05": [
        "tests/integration/test_central_finance.py::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated"
    ],
    "AC-06": [
        "tests/integration/test_central_finance.py::test_discount_boundaries_and_accept_only_subsequent_message"
    ],
    "AC-07": [
        "tests/integration/test_central_finance.py::test_discount_boundaries_and_accept_only_subsequent_message",
        "tests/unit/test_money_policy.py::test_exact_discount_boundary_and_roundtrip",
    ],
    "AC-08": [
        "tests/integration/test_central_finance.py::test_discount_boundaries_and_accept_only_subsequent_message",
        "tests/unit/test_agent_context.py::test_handoff_blocks_further_financial_tools_in_same_turn",
    ],
    "AC-09": [
        "tests/integration/test_central_finance.py::test_invalid_discount_amounts_do_not_create_orders",
        "tests/unit/test_money_policy.py::test_rejects_ambiguous_or_invalid_money",
    ],
    "AC-10": [
        "tests/integration/test_central_finance.py::test_unpaid_order_expiry_blocks_capability_and_projects_expired_to_owner",
        "tests/integration/test_central_finance.py::test_paid_receipt_survives_charge_expiry_but_no_new_attempt",
    ],
    "AC-11": [
        "tests/integration/test_media.py::test_download_pins_resolved_ip_preserves_tls_sni_and_sends_no_credentials",
        "tests/integration/test_central_finance.py::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated",
    ],
    "AC-12": [
        "tests/integration/test_central_finance.py::test_full_payment_rejected_then_applied_idempotently_and_reference_isolated",
        "tests/integration/test_handoff.py::test_case_persists_before_ordered_effects_and_duplicate_is_idempotent",
    ],
    "AC-13": [
        "tests/integration/test_central_finance.py::test_customer_grants_isolate_debts_and_switch_revokes_prior",
        "tests/integration/test_central_finance.py::test_order_capability_can_be_regenerated_only_under_owner_grant",
    ],
    "AC-14": [
        "tests/integration/test_central_finance.py::test_concurrent_orders_settle_exactly_once",
        "tests/integration/test_queue.py::test_durable_duplicate_delivery_has_one_job_and_original_destination",
    ],
    "AC-15": [
        "tests/integration/test_media.py::test_real_audio_duration_enforced_before_transcription"
    ],
    "AC-16": [
        "tests/integration/test_media.py::test_magic_rejects_unsafe_or_misleading_image_content",
        "tests/integration/test_media.py::test_real_audio_duration_enforced_before_transcription",
    ],
    "AC-17": [
        "tests/integration/test_handoff.py::test_case_persists_before_ordered_effects_and_duplicate_is_idempotent",
        "tests/integration/test_handoff.py::test_private_note_redacts_secrets_and_only_uses_trusted_identity",
    ],
    "AC-18": [
        "tests/integration/test_handoff.py::test_human_takeover_during_inference_cancels_queued_output",
        "tests/integration/test_handoff.py::test_return_requires_applied_transfer_open_observation_then_new_pending_event",
    ],
    "AC-19": [
        "tests/integration/test_text_journey.py::test_checkpoint_restart_literal_source_history_and_event_dedupe",
        "tests/integration/test_central_finance.py::test_recoverable_two_database_reset_clears_real_checkpoints_preserves_spend",
    ],
    "AC-20": [
        "tests/integration/test_campaigns.py::test_person_dedup_stable_snapshot_and_simulations_never_touch_channel"
    ],
    "AC-21": [
        "tests/integration/test_campaigns.py::test_active_person_excluded_and_close_stops_pending_dispatch",
        "tests/integration/test_campaigns.py::test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination",
    ],
    "AC-22": [
        "tests/integration/test_text_journey.py::test_five_tool_responses_stop_and_register_honest_handoff",
        "tests/integration/test_backend_identity.py::test_invalid_pin_media_and_temporary_failure_do_not_reach_agent",
    ],
    "AC-23": [
        "tests/unit/test_agent_context.py::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant",
        "tests/integration/test_handoff.py::test_reason_amount_and_tenant_are_validated",
    ],
    "AC-24": [
        "tests/integration/test_budget.py::test_concurrent_budget_cutoff_is_atomic",
        "tests/integration/test_budget.py::test_timeout_preserves_amount_and_expired_lease_only_releases_slot",
        "tests/unit/test_agent_context.py::test_payment_capability_never_crosses_model_checkpoint_boundary",
    ],
    "AC-25": [
        "tests/integration/test_central_finance.py::test_operator_contact_shared_version_mora_and_seed_never_overwrites",
        "tests/contracts/test_web_frontends.py::test_exact_mora_bucket_and_service_filters",
    ],
    "AC-26": [
        "tests/integration/test_campaigns.py::test_mora_buckets_boundaries_and_multiple_services"
    ],
    "AC-27": [
        "tests/integration/test_metrics.py::test_metrics_real_cohort_dedup_money_agreement_and_human_milestones",
        "tests/integration/test_metrics.py::test_active_human_and_expired_agreement_are_current_results_not_milestones",
    ],
    "AC-28": [
        "tests/integration/test_central_finance.py::test_operator_contact_shared_version_mora_and_seed_never_overwrites",
        "tests/integration/test_campaigns.py::test_changed_contact_is_skipped_and_unknown_delivery_is_not_resent",
    ],
    "AC-29": [
        "tests/unit/test_money_policy.py::test_rejects_ambiguous_or_invalid_money",
        "tests/unit/test_agent_context.py::test_pre_pin_catalog_and_strict_tool_schema_never_accept_identity_or_grant",
    ],
    "AC-30": [
        "tests/integration/test_central_finance.py::test_concurrent_orders_settle_exactly_once",
        "tests/integration/test_central_finance.py::test_stale_balance_invalidates_order_and_quote",
    ],
    "AC-31": [
        "tests/integration/test_campaigns.py::test_live_sequential_dispatch_launch_idempotency_and_immutable_outbox_destination",
        "tests/integration/test_campaigns.py::test_person_dedup_stable_snapshot_and_simulations_never_touch_channel",
    ],
}


def validate_test_database(value):
    if not value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"postgresql", "postgresql+psycopg"} and "test" in parsed.path.lower()


def report_from_junit(path, exit_code):
    tree = ET.parse(path)
    cases = []
    for element in tree.iter("testcase"):
        classname = element.attrib.get("classname", "").replace(".", "/")
        name = element.attrib.get("name", "").split("[", 1)[0]
        node = f"{classname}.py::{name}"
        status = (
            "failed"
            if element.find("failure") is not None or element.find("error") is not None
            else "skipped"
            if element.find("skipped") is not None
            else "passed"
        )
        cases.append({"node": node, "status": status})
    mapping = []
    for ac, refs in AC_EVIDENCE.items():
        matched = [case for case in cases if case["node"] in refs]
        missing = [ref for ref in refs if not any(case["node"] == ref for case in matched)]
        state = (
            "failed"
            if any(case["status"] == "failed" for case in matched)
            else "incomplete"
            if missing or any(case["status"] == "skipped" for case in matched)
            else "passed"
        )
        mapping.append(
            {
                "id": ac,
                "automated_evidence": state,
                "full_acceptance": "pending_live_or_manual_evidence",
                "tests": refs,
                "missing": missing,
            }
        )
    counts = {
        state: sum(case["status"] == state for case in cases)
        for state in ("passed", "failed", "skipped")
    }
    complete = (
        exit_code == 0
        and counts["skipped"] == 0
        and counts["passed"] > 0
        and all(item["automated_evidence"] == "passed" for item in mapping)
    )
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "automated": {
            "status": "passed" if complete else "failed_or_incomplete",
            **counts,
            "pytest_exit_code": exit_code,
        },
        "live": {
            "status": "not_run",
            "reason": "No live provider, Chatwoot, WhatsApp or AWS integration was invoked.",
        },
        "acceptance": mapping,
    }, complete


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Reserved; explicitly blocked until a reviewed live integration runner exists",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional local JSON evidence artifact; stdout also receives the report",
    )
    args = parser.parse_args(argv)
    if args.live:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": "live_acceptance_not_implemented",
                    "message": "This runner only executes deterministic tests. Live messaging/inference requires a separate reviewed opt-in workflow and real evidence.",
                },
                ensure_ascii=False,
            )
        )
        return 2
    for name in ("TEST_MEMORY_DATABASE_URL", "CENTRAL_TEST_DATABASE_URL"):
        if not validate_test_database(os.environ.get(name)):
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "code": "test_database_required",
                        "message": f"Set {name} to a disposable PostgreSQL test database; use infra/compose.test.yaml.",
                    },
                    ensure_ascii=False,
                )
            )
            return 2
    with tempfile.TemporaryDirectory(prefix="agil-acceptance-") as directory:
        junit = Path(directory) / "pytest.xml"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/unit",
                "tests/contracts",
                "tests/integration",
                "-m",
                "not live",
                "-q",
                f"--junitxml={junit}",
            ],
            cwd=ROOT,
            check=False,
        )
        if not junit.exists():
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "code": "pytest_report_missing",
                        "pytest_exit_code": result.returncode,
                    }
                )
            )
            return result.returncode or 1
        report, complete = report_from_junit(junit, result.returncode)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0 if complete else result.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
