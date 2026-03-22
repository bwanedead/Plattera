"""Phase 15: discovery-led startup, seed on-demand wake, composition/run-story hints."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import (
    initialize_decision_ledger_with_domain_template_seed,
    update_ledger_from_iteration,
)
from backend.agents.transcript_edit.decision_ledger_adapter import build_transcript_edit_unified_decision_ledger
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.decision_ledger_state import reconcile_ledger_derived_fields
from backend.agents.transcript_edit.llm_startup_understanding import native_rows_from_llm_initial_ledger_items
from backend.agents.transcript_edit.organized_work_composition import compute_organized_work_composition
from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import DISCOVERY_KEY_PREFIX, merge_discovery_from_audit_findings
from backend.harness.decision_ledger import contracts as dl_contracts


def _long_contra() -> str:
    return (
        "contradiction between candidate bearings and recorded calls in the boundary description for audit"
    )


def test_startup_remains_discovery_led_with_dormant_seed_present() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    rows = native_rows_from_llm_initial_ledger_items(
        [{"title": "Discovery-led startup row", "summary": _long_contra(), "mapping_blocking": True}]
    )
    ledger["items"].extend(rows)
    reconcile_ledger_derived_fields(ledger)
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    comp = compute_organized_work_composition(native_decision_ledger=ledger, unified_work_board=unified)
    assert comp.get("seed_materialization_mode") == "on_demand"
    assert comp.get("discovery_led_startup_surface") is True
    assert comp.get("startup_active_work_posture") == "discovery_first_surface"
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert focus.get("startup_discovery_led_surface") is True
    assert str(focus.get("decision_key") or "").startswith(DISCOVERY_KEY_PREFIX)


def test_audit_observations_do_not_wake_seed_rows_phase24() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    by_k = {str(i.get("key")): i for i in ledger.get("items") or [] if isinstance(i, dict)}
    assert by_k["range"].get("seed_scaffolding_dormant") is True
    out = update_ledger_from_iteration(
        ledger=ledger,
        findings=[
            {
                "finding_id": "f-td",
                "message": "Tie distance appears as 1320 feet in call language for the segment",
            },
        ],
    )
    by2 = {str(i.get("key")): i for i in out.get("items") or [] if isinstance(i, dict)}
    assert by2["tie_distance"].get("seed_scaffolding_dormant") is True
    assert by2["range"].get("seed_scaffolding_dormant") is True
    assert by2["township"].get("seed_scaffolding_dormant") is True


def test_dormant_seed_does_not_pollute_seed_awake_in_composition() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    rows = native_rows_from_llm_initial_ledger_items(
        [{"title": "Composition discovery row", "summary": _long_contra(), "mapping_blocking": True}]
    )
    ledger["items"].extend(rows)
    reconcile_ledger_derived_fields(ledger)
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    comp = compute_organized_work_composition(native_decision_ledger=ledger, unified_work_board=unified)
    assert int(comp.get("unresolved_seed_scaffolding_awake_count") or 0) == 0
    assert int(comp.get("unresolved_discovery_active_count") or 0) >= 1


def test_awake_seed_still_respected_when_closure_authority_requires() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for it in ledger.get("items") or []:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "")
        if k == "range":
            it["seed_scaffolding_dormant"] = False
            it["state"] = "disputed"
            it["blocking"] = True
            it["alternatives"] = ["A", "B"]
            it["evidence_refs"] = ["e1"]
            it["closure_requirement"] = {
                "mapping_blocking": True,
                "scope_status": "in_target",
                "block_reason": "contradiction",
            }
            continue
        if k.startswith(DISCOVERY_KEY_PREFIX):
            continue
        it["state"] = "verified"
        it["closure_requirement"] = None
        it["blocking"] = False
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "x", "message": _long_contra()}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "") == "range"


def test_harness_decision_ledger_contract_stays_domain_agnostic() -> None:
    assert not hasattr(dl_contracts, "SEED_WAKE_AT_INIT_KEYS")
    assert not hasattr(dl_contracts, "seed_materialization_mode")
