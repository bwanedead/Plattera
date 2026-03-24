"""Phase 13: seed demotion, discovery posture, composition observability."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed
from backend.agents.transcript_edit.decision_ledger_adapter import build_transcript_edit_unified_decision_ledger
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.decision_ledger_state import reconcile_ledger_derived_fields
from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.llm_startup_understanding import native_rows_from_llm_initial_ledger_items
from backend.agents.transcript_edit.organized_work_composition import compute_organized_work_composition
from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import (
    DISCOVERY_KEY_PREFIX,
    merge_discovery_from_audit_findings,
    merge_discovered_native_items,
    refresh_discovery_posture_fields,
)


def _append_llm_discovery_row(ledger: dict, *, title: str, summary: str) -> None:
    rows = native_rows_from_llm_initial_ledger_items(
        [{"title": title, "summary": summary, "mapping_blocking": True}]
    )
    ledger["items"].extend(rows)
    reconcile_ledger_derived_fields(ledger)
from backend.harness.decision_ledger import contracts as dl_contracts


def _long_contra(msg: str = "") -> str:
    return (
        "contradiction between candidate bearings and recorded calls in the boundary description " + msg
    )


def test_stable_discovery_outranks_weak_seed_placeholder() -> None:
    """Weak deterministic seed (no evidence, not disputed) demoted vs mature discovery."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for it in ledger.get("items") or []:
        if isinstance(it, dict) and str(it.get("key") or "") == "range":
            it["state"] = "unknown"
            it["blocking"] = True
            it["evidence_refs"] = []
            it["alternatives"] = []
            it["provenance"] = "deterministic"
            it["closure_requirement"] = {
                "mapping_blocking": True,
                "scope_status": "in_target",
                "block_reason": "ambiguity",
            }
            break
    _append_llm_discovery_row(
        ledger,
        title="Stable mature discovery",
        summary=_long_contra(),
    )
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    for it in ledger.get("items") or []:
        if isinstance(it, dict) and str(it.get("key") or "").startswith(DISCOVERY_KEY_PREFIX):
            dm = it.get("discovery_meta") if isinstance(it.get("discovery_meta"), dict) else {}
            dm = dict(dm)
            dm["posture"] = "stable"
            dm["evidence_touch_count"] = 4
            it["discovery_meta"] = dm
            cr = dict(it.get("closure_requirement") or {})
            cr["mapping_blocking"] = True
            cr["scope_status"] = "in_target"
            cr["block_reason"] = "ambiguity"
            it["closure_requirement"] = cr
            it["state"] = "unknown"
            break
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "").startswith(DISCOVERY_KEY_PREFIX)
    assert str((focus.get("seed_candidate") or {}).get("decision_key") or "").startswith(DISCOVERY_KEY_PREFIX)
    assert str(focus.get("bootstrap_focus_source") or "") in {"ledger_discovery", "ledger_decision", "harness_emergent"}


def test_seed_wins_when_closure_authority_strong() -> None:
    """Non-weak seed (disputed + alternatives) still ahead of discovery when materially urgent."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for it in ledger.get("items") or []:
        if isinstance(it, dict) and str(it.get("key") or "") == "range":
            it["seed_scaffolding_dormant"] = False
            it["state"] = "disputed"
            it["blocking"] = True
            it["alternatives"] = ["A", "B"]
            it["evidence_refs"] = ["e1"]
            it["provenance"] = "deterministic"
            it["closure_requirement"] = {
                "mapping_blocking": True,
                "scope_status": "in_target",
                "block_reason": "contradiction",
            }
            break
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "x1", "message": _long_contra()}],
    )
    for it in ledger.get("items") or []:
        if isinstance(it, dict) and str(it.get("key") or "").startswith(DISCOVERY_KEY_PREFIX):
            dm = dict(it.get("discovery_meta") or {})
            dm["posture"] = "fresh"
            it["discovery_meta"] = dm
            it["state"] = "unknown"
            break
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "") == "range"


def test_packet_shows_composition_and_discovery_posture() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    _append_llm_discovery_row(
        ledger,
        title="Composition posture row",
        summary=_long_contra(),
    )
    merge_discovery_from_audit_findings(
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
        focus_reason_code="test",
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
    ec = packet.get("execution_context") or {}
    assert ec.get("organized_work_composition", {}).get("schema_version") == "organized_work_composition.v5"
    assert int(ec["organized_work_composition"].get("unresolved_discovery_active_count") or 0) >= 1
    dwc = ec.get("discovery_work_context") or {}
    assert dwc.get("posture") in (None, "fresh", "touched", "stable", "escalated")


def test_discovery_more_salient_after_repeated_evidence_merges() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    msg = _long_contra("repeat path")
    _append_llm_discovery_row(ledger, title="Repeat merge base", summary=msg)
    merge_discovery_from_audit_findings(ledger, [{"finding_id": "a", "message": msg}])
    row = next(
        i
        for i in ledger.get("items") or []
        if isinstance(i, dict) and str(i.get("key") or "").startswith(DISCOVERY_KEY_PREFIX)
    )
    key = str(row.get("key"))
    dup = dict(row)
    dup["key"] = f"{DISCOVERY_KEY_PREFIX}contradiction_cluster:feedbeefcafe"
    dup["evidence_refs"] = ["finding:extra"]
    ledger2 = merge_discovered_native_items(ledger, [dup])
    it = next(
        i
        for i in ledger2.get("items") or []
        if isinstance(i, dict) and str(i.get("key") or "") == key
    )
    refresh_discovery_posture_fields(it)
    dm = it.get("discovery_meta") or {}
    assert int(dm.get("evidence_touch_count") or 0) >= 1
    assert str(dm.get("posture") or "") in {"touched", "stable", "escalated", "fresh"}


def test_harness_decision_ledger_contract_has_no_transcript_edit_ontology() -> None:
    assert not hasattr(dl_contracts, "DISCOVERY_KEY_PREFIX")
    assert not hasattr(dl_contracts, "TRANSCRIPT_EDIT_SLOT_PRIORITY")

