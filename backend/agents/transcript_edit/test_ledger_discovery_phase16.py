"""Phase 16: discovery-first default, optional domain template policy, discovery lifecycle hygiene."""
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
from backend.agents.transcript_edit.organized_work_composition import compute_organized_work_composition
from backend.agents.transcript_edit.transcript_edit_discovery_lifecycle import (
    apply_discovery_lifecycle_hygiene,
    discovery_lifecycle_priority_penalty,
)
from backend.agents.transcript_edit.decision_ledger_state import reconcile_ledger_derived_fields
from backend.agents.transcript_edit.llm_startup_understanding import native_rows_from_llm_initial_ledger_items
from backend.agents.transcript_edit.transcript_edit_ledger_bootstrap_policy import (
    DEFAULT_ORGANIZED_WORK_MODE,
    TRANSCRIPT_EDIT_SEED_TEMPLATE_POLICY_ID,
    transcript_edit_bootstrap_policy_snapshot,
)
from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import DISCOVERY_KEY_PREFIX, merge_discovery_from_audit_findings
from backend.harness.decision_ledger import contracts as dl_contracts


def _long_contra() -> str:
    return (
        "contradiction between candidate bearings and recorded calls in the boundary description for audit"
    )


def _long_msg(suffix: str) -> str:
    return (
        f"contradiction between candidate bearings and recorded calls in the boundary description {suffix}"
    )


def test_startup_discovery_first_no_awake_seed() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    rows = native_rows_from_llm_initial_ledger_items(
        [{"title": "Discovery first startup", "summary": _long_contra(), "mapping_blocking": True}]
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
    assert comp.get("discovery_led_startup_surface") is True
    assert comp.get("bootstrap_policy", {}).get("default_organized_work_mode") == DEFAULT_ORGANIZED_WORK_MODE


def test_audit_does_not_activate_seed_rows_phase24() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
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


def test_dormant_template_does_not_pollute_seed_awake_in_composition() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    rows = native_rows_from_llm_initial_ledger_items(
        [{"title": "Template composition row", "summary": _long_contra(), "mapping_blocking": True}]
    )
    ledger["items"].extend(rows)
    reconcile_ledger_derived_fields(ledger)
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    comp = compute_organized_work_composition(native_decision_ledger=ledger, unified_work_board=unified)
    assert comp.get("domain_template_rows_awake") is False
    assert int(comp.get("unresolved_seed_scaffolding_awake_count") or 0) == 0


def test_explicit_awake_seed_still_wins_when_needed() -> None:
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


def test_discovery_cooling_deprioritized_in_focus() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    ledger["items"].extend(
        native_rows_from_llm_initial_ledger_items(
            [{"title": "Cooling row alpha", "summary": _long_msg("alpha"), "mapping_blocking": True}]
        )
    )
    ledger["items"].extend(
        native_rows_from_llm_initial_ledger_items(
            [{"title": "Cooling row bravo", "summary": _long_msg("bravo"), "mapping_blocking": True}]
        )
    )
    reconcile_ledger_derived_fields(ledger)
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "a", "message": _long_msg("alpha")}],
    )
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "b", "message": _long_msg("bravo")}],
    )
    keys = [
        str(i.get("key"))
        for i in ledger.get("items") or []
        if isinstance(i, dict) and str(i.get("key") or "").startswith(DISCOVERY_KEY_PREFIX)
    ]
    assert len(keys) >= 2
    old_key = keys[0]
    for it in ledger.get("items") or []:
        if not isinstance(it, dict):
            continue
        if str(it.get("key")) != old_key:
            continue
        dm = dict(it.get("discovery_meta") or {})
        dm["last_merged_epoch"] = 100
        dm["evidence_touch_count"] = 0
        it["discovery_meta"] = dm
        break
    apply_discovery_lifecycle_hygiene(ledger, now_epoch=200, cooling_age_seconds=50)
    dm_old = next(
        i.get("discovery_meta")
        for i in ledger.get("items") or []
        if isinstance(i, dict) and str(i.get("key")) == old_key
    )
    assert isinstance(dm_old, dict)
    assert str(dm_old.get("lifecycle_hint") or "").lower() == "cooling"
    assert discovery_lifecycle_priority_penalty(dm_old) == 12
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "") != old_key


def test_harness_contract_domain_agnostic() -> None:
    assert not hasattr(dl_contracts, "DEFAULT_ORGANIZED_WORK_MODE")
    assert not hasattr(dl_contracts, "transcript_edit_bootstrap_policy_snapshot")


def test_bootstrap_policy_is_optional_domain_framing_not_harness() -> None:
    snap = transcript_edit_bootstrap_policy_snapshot()
    assert snap.get("harness_ontology") is False
    assert snap.get("domain_template_policy_id") == TRANSCRIPT_EDIT_SEED_TEMPLATE_POLICY_ID
    assert snap.get("domain_template_capability") == "optional"


def test_composition_v4_includes_bootstrap_and_cooling_counts() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    ledger["items"].extend(
        native_rows_from_llm_initial_ledger_items(
            [{"title": "Bootstrap cooling counts", "summary": _long_contra(), "mapping_blocking": True}]
        )
    )
    reconcile_ledger_derived_fields(ledger)
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    comp = compute_organized_work_composition(native_decision_ledger=ledger, unified_work_board=unified)
    assert comp.get("schema_version") == "organized_work_composition.v5"
    assert "bootstrap_policy" in comp
    assert "unresolved_discovery_cooling_count" in comp
