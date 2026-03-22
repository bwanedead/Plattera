"""Phase 17: discovery-native default ledger + optional template seed + vestigial audit notes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import (
    initialize_decision_ledger,
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


def test_default_startup_empty_then_discovery_establishes_work() -> None:
    ledger = initialize_decision_ledger()
    assert ledger.get("items") == []
    assert ledger.get("ledger_establishment_mode") == "discovery_native"
    rows = native_rows_from_llm_initial_ledger_items(
        [{"title": "Establish discovery work", "summary": _long_contra(), "mapping_blocking": True}]
    )
    ledger["items"].extend(rows)
    reconcile_ledger_derived_fields(ledger)
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    keys = [str(i.get("key")) for i in ledger.get("items") or [] if isinstance(i, dict)]
    assert any(k.startswith(DISCOVERY_KEY_PREFIX) for k in keys)
    assert not any(k in {"range", "township", "section"} for k in keys)
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "").startswith(DISCOVERY_KEY_PREFIX)


def test_optional_template_seed_injects_full_checklist() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    assert ledger.get("ledger_establishment_mode") == "template_seed"
    assert len(ledger.get("items") or []) == 7


def test_focus_and_composition_with_discovery_native_after_merge() -> None:
    ledger = initialize_decision_ledger()
    ledger["items"].extend(
        native_rows_from_llm_initial_ledger_items(
            [{"title": "Native merge composition", "summary": _long_contra(), "mapping_blocking": True}]
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
    assert comp.get("ledger_establishment_mode") == "discovery_native"
    assert int(comp.get("unresolved_discovery_active_count") or 0) >= 1


def test_update_ledger_from_iteration_does_not_materialize_seed_rows_from_audit_phase24() -> None:
    ledger = initialize_decision_ledger()
    out = update_ledger_from_iteration(
        ledger=ledger,
        findings=[
            {
                "finding_id": "f-td",
                "message": "Tie distance appears as 1320 feet in call language for the segment",
            },
        ],
    )
    assert out.get("items") == []


def test_placeholder_hook_removed_is_unreferenced() -> None:
    import backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep as prep

    assert not hasattr(prep, "discovery_ledger_merge_hook_placeholder")


def test_harness_still_domain_agnostic() -> None:
    assert not hasattr(dl_contracts, "ledger_establishment_mode")
