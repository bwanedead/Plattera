"""Discovery-first ledger merge: native store + unified/read surfaces + focus eligibility."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed
from backend.agents.transcript_edit.decision_ledger_adapter import (
    build_transcript_edit_unified_decision_ledger,
    transcript_edit_unified_and_closure_read_for_native,
)
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import (
    DISCOVERY_ITEM_PROVENANCE,
    DISCOVERY_KEY_PREFIX,
    _MAX_DISCOVERY_ROWS_TOTAL,
    infer_discovery_items_from_audit_findings,
    merge_discovered_native_items,
    merge_discovery_from_audit_findings,
)


def test_closure_read_overlays_discovery_meta_from_native() -> None:
    """Unified envelope does not carry discovery_meta; closure read must overlay from native."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    out = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "f-meta", "message": "contradiction between range lines in candidates"}],
    )
    _, read = transcript_edit_unified_and_closure_read_for_native(native_decision_ledger=out)
    disc = next(
        i
        for i in (read.get("items") or [])
        if isinstance(i, dict) and str(i.get("key") or "").startswith(DISCOVERY_KEY_PREFIX)
    )
    dm = disc.get("discovery_meta")
    assert isinstance(dm, dict) and str(dm.get("kind") or "")


def test_merge_from_audit_findings_adds_non_seed_discovery_item() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    findings = [
        {"finding_id": "f-contra-1", "message": "contradiction between range lines in candidates"},
    ]
    out = merge_discovery_from_audit_findings(ledger, findings)
    keys = [str(i.get("key") or "") for i in (out.get("items") or []) if isinstance(i, dict)]
    assert any(k.startswith(DISCOVERY_KEY_PREFIX) for k in keys)
    disc = next(i for i in out["items"] if isinstance(i, dict) and str(i.get("key", "")).startswith(DISCOVERY_KEY_PREFIX))
    assert disc.get("provenance") == DISCOVERY_ITEM_PROVENANCE
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=out)
    item_ids = [str(r.get("item_id") or "") for r in unified.get("items") or [] if isinstance(r, dict)]
    assert any("te:ledger:discovery:" in iid for iid in item_ids)
    _, read = transcript_edit_unified_and_closure_read_for_native(native_decision_ledger=out)
    read_keys = [str(i.get("key") or "") for i in (read.get("items") or []) if isinstance(i, dict)]
    assert any(k.startswith(DISCOVERY_KEY_PREFIX) for k in read_keys)


def test_mixed_seed_and_discovery_unified_surface() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "dep1", "message": "dependency on prior deed not attached"}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    titles = [str(r.get("title") or "") for r in unified.get("items") or [] if isinstance(r, dict)]
    assert any("Township" in t or "Range" in t for t in titles)
    assert any("Discovered" in t for t in titles)


def test_discovery_item_can_win_focus_when_only_mapping_critical_unresolved() -> None:
    """Anti-hard-scripting: discovery rows are not excluded from focus selection."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for it in ledger.get("items") or []:
        if isinstance(it, dict):
            it["state"] = "verified"
            it["blocking"] = False
            it["closure_requirement"] = None
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "c1", "message": "contradiction in boundary calls"}],
    )
    for it in ledger.get("items") or []:
        if isinstance(it, dict) and str(it.get("key") or "").startswith(DISCOVERY_KEY_PREFIX):
            it["state"] = "disputed"
            it["alternatives"] = ["a", "b"]
            cr = dict(it.get("closure_requirement") or {})
            cr["mapping_blocking"] = True
            cr["scope_status"] = "in_target"
            it["closure_requirement"] = cr
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "").startswith(DISCOVERY_KEY_PREFIX)
    assert str(focus.get("focus_target_kind") or "") == "ledger_discovery"


def test_duplicate_audit_merge_does_not_sprawl_rows() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    findings = [{"finding_id": "same", "message": "conflict in section text of the legal description body"}]
    m1 = merge_discovery_from_audit_findings(ledger, findings)
    n1 = sum(1 for i in m1.get("items") or [] if isinstance(i, dict) and str(i.get("key")).startswith(DISCOVERY_KEY_PREFIX))
    m2 = merge_discovery_from_audit_findings(m1, findings)
    n2 = sum(1 for i in m2.get("items") or [] if isinstance(i, dict) and str(i.get("key")).startswith(DISCOVERY_KEY_PREFIX))
    assert n2 == n1


def test_infer_respects_per_audit_cap() -> None:
    findings = [
        {"finding_id": f"f{i}", "message": "contradiction issue in the candidate boundary calls and curves"}
        for i in range(20)
    ]
    inf = infer_discovery_items_from_audit_findings(findings, max_items=2)
    assert len(inf) <= 2


def test_merge_respects_total_discovery_cap() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    contribs = []
    for i in range(_MAX_DISCOVERY_ROWS_TOTAL + 5):
        contribs.append(
            {
                "key": f"{DISCOVERY_KEY_PREFIX}contradiction_cluster:{i:012x}",
                "label": f"D{i}",
                "state": "unknown",
                "selected_value": None,
                "alternatives": [],
                "confidence": None,
                "blocking": True,
                "evidence_refs": [],
                "user_override_state": "none",
                "layer_tag": "layer1_canonical_recovery",
                "operational_impact": "mapping_blocking",
                "provenance": DISCOVERY_ITEM_PROVENANCE,
                "verification_required": False,
                "scope_id": "target_scope",
                "scope_label": "Target scope",
                "scope_priority": 45,
                "in_target_scope": True,
                "scope_proof": [],
                "closure_requirement": {
                    "mapping_blocking": True,
                    "scope_status": "in_target",
                    "block_reason": "contradiction",
                },
                "discovery_meta": {
                    "kind": "contradiction_cluster",
                    "finding_id": str(i),
                    "version": 1,
                    "signal_fp": f"{i:012x}",
                },
            }
        )
    out = merge_discovered_native_items(ledger, contribs, max_additions=50)
    n = sum(1 for i in out.get("items") or [] if isinstance(i, dict) and str(i.get("key")).startswith(DISCOVERY_KEY_PREFIX))
    assert n <= _MAX_DISCOVERY_ROWS_TOTAL
