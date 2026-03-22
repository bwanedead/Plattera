"""Phase 14–15: lazy/on-demand seed dormancy, discovery-led focus, composition v2→v3."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import (
    initialize_decision_ledger_with_domain_template_seed,
    update_ledger_from_iteration,
)
from backend.agents.transcript_edit.decision_ledger_state import reconcile_ledger_derived_fields
from backend.agents.transcript_edit.llm_startup_understanding import native_rows_from_llm_initial_ledger_items
from backend.agents.transcript_edit.decision_ledger_adapter import (
    build_transcript_edit_unified_decision_ledger,
    transcript_edit_unified_and_closure_read_for_native,
)
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.organized_work_composition import compute_organized_work_composition
from backend.agents.transcript_edit.transcript_edit_default_checklist_seed import SEED_WAKE_AT_INIT_KEYS
from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import DISCOVERY_KEY_PREFIX, merge_discovery_from_audit_findings
from backend.harness.decision_ledger import contracts as dl_contracts


def _long_contra() -> str:
    return (
        "contradiction between candidate bearings and recorded calls in the boundary description for audit"
    )


def test_seed_wake_at_init_keys_empty_phase15() -> None:
    assert len(SEED_WAKE_AT_INIT_KEYS) == 0


def test_lazy_dormant_flags_on_init() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    by_k = {str(i.get("key")): i for i in ledger.get("items") or [] if isinstance(i, dict)}
    assert by_k["tie_distance"].get("seed_scaffolding_dormant") is True
    assert by_k["range"].get("seed_scaffolding_dormant") is True
    assert by_k["township"].get("seed_scaffolding_dormant") is True


def test_audit_finding_does_not_wake_dormant_seed_row_phase24() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    out = update_ledger_from_iteration(
        ledger=ledger,
        findings=[
            {"finding_id": "f-td", "message": "Tie distance appears as 1320 feet in call language for the segment"},
        ],
    )
    by_k = {str(i.get("key")): i for i in out.get("items") or [] if isinstance(i, dict)}
    assert by_k["tie_distance"].get("seed_scaffolding_dormant") is True


def test_discovery_led_focus_skips_dormant_unresolved_seed() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for it in ledger.get("items") or []:
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "")
        if k == "tie_distance":
            continue
        if k.startswith(DISCOVERY_KEY_PREFIX):
            continue
        it["state"] = "verified"
        it["blocking"] = False
        it["closure_requirement"] = None
    td = next(i for i in ledger["items"] if isinstance(i, dict) and str(i.get("key")) == "tie_distance")
    td["state"] = "unknown"
    td["blocking"] = True
    td["closure_requirement"] = {
        "mapping_blocking": True,
        "scope_status": "in_target",
        "block_reason": "ambiguity",
    }
    disc_rows = native_rows_from_llm_initial_ledger_items(
        [
            {
                "title": "Contradiction cluster from interpretation",
                "summary": _long_contra(),
                "mapping_blocking": True,
            }
        ]
    )
    ledger["items"].extend(disc_rows)
    ledger = reconcile_ledger_derived_fields(ledger)
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "").startswith(DISCOVERY_KEY_PREFIX)


def test_awake_seed_still_wins_when_closure_strong_vs_fresh_discovery() -> None:
    """Explicit material seed dispute outranks fresh discovery (Phase 13/14 authority preserved)."""
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


def test_packet_composition_v2_and_formation_hint() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    disc_rows = native_rows_from_llm_initial_ledger_items(
        [
            {
                "title": "Contradiction cluster for packet test",
                "summary": _long_contra(),
                "mapping_blocking": True,
            }
        ]
    )
    ledger["items"].extend(disc_rows)
    ledger = reconcile_ledger_derived_fields(ledger)
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "p1", "message": _long_contra()}],
    )
    disc_key = next(
        str(i.get("key"))
        for i in ledger.get("items") or []
        if isinstance(i, dict) and str(i.get("key") or "").startswith(DISCOVERY_KEY_PREFIX)
    )
    packet = build_focus_packet(
        decision_ledger=ledger,
        decision_key=disc_key,
        focus_source="resolver",
        focus_reason_code="t",
        loop_iteration=1,
        active_emergent_blocker=None,
        blocker_registry=None,
        source_transcript_ref="ref:t",
        source_transcript_hash="h",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    ow = (packet.get("execution_context") or {}).get("organized_work_composition") or {}
    assert ow.get("schema_version") == "organized_work_composition.v5"
    assert "work_formation_hint" in ow
    assert int(ow.get("unresolved_seed_scaffolding_dormant_count") or 0) >= 1


def test_closure_read_overlays_seed_dormant() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    _, read = transcript_edit_unified_and_closure_read_for_native(native_decision_ledger=ledger)
    td = next(i for i in read.get("items") or [] if isinstance(i, dict) and str(i.get("key")) == "tie_distance")
    assert td.get("seed_scaffolding_dormant") is True


def test_harness_contract_stays_domain_agnostic() -> None:
    assert not hasattr(dl_contracts, "SEED_WAKE_AT_INIT_KEYS")
