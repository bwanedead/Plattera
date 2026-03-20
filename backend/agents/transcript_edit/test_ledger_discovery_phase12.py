"""Phase 12: discovery governance, focus fairness vs seed, packet + continuity signals."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.focus_authority_policy import authority_rank_for_candidate
from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import (
    DISCOVERY_ITEM_PROVENANCE,
    DISCOVERY_KEY_PREFIX,
    append_discovery_merge_continuity,
    merge_discovery_from_audit_findings,
    signal_fingerprint,
)


def _long_contradiction(msg_suffix: str = "") -> str:
    return (
        "contradiction between candidate bearings and recorded calls in the boundary description "
        + msg_suffix
    )


def test_authority_rank_discovery_matches_decision_when_mapping_blocking() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "a1", "message": _long_contradiction()}],
    )
    disc_key = next(
        str(i.get("key"))
        for i in ledger.get("items") or []
        if isinstance(i, dict) and str(i.get("key") or "").startswith(DISCOVERY_KEY_PREFIX)
    )
    from backend.agents.transcript_edit.decision_ledger_closure import (
        unresolved_mapping_blocking_requirements,
    )

    mb = {
        str(x.get("key") or ""): x
        for x in unresolved_mapping_blocking_requirements(ledger)
        if isinstance(x, dict)
    }
    d_rank = authority_rank_for_candidate(
        {"_candidate_source": "ledger_discovery", "key": disc_key},
        mapping_blocking_by_key=mb,
    )
    assert d_rank == 0


def test_discovery_can_outrank_seed_when_contradiction_signal_stronger() -> None:
    """Material discovery contradiction should not lose to seed slot priority alone."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for it in ledger.get("items") or []:
        if not isinstance(it, dict):
            continue
        if str(it.get("key") or "") == "range":
            it["state"] = "unknown"
            it["blocking"] = True
            cr = dict(it.get("closure_requirement") or {})
            cr["mapping_blocking"] = True
            cr["scope_status"] = "in_target"
            cr["block_reason"] = "ambiguity"
            it["closure_requirement"] = cr
            break
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "cx", "message": _long_contradiction()}],
    )
    for it in ledger.get("items") or []:
        if isinstance(it, dict) and str(it.get("key") or "").startswith(DISCOVERY_KEY_PREFIX):
            it["state"] = "disputed"
            it["alternatives"] = ["x", "y"]
            cr = dict(it.get("closure_requirement") or {})
            cr["mapping_blocking"] = True
            cr["scope_status"] = "in_target"
            cr["block_reason"] = "contradiction"
            it["closure_requirement"] = cr
    from backend.agents.transcript_edit.decision_ledger_adapter import build_transcript_edit_unified_decision_ledger

    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    focus = choose_investigation_focus(ledger, work_board=unified) or {}
    assert str(focus.get("decision_key") or "").startswith(DISCOVERY_KEY_PREFIX)


def test_near_duplicate_signal_merges_evidence_without_new_row() -> None:
    """Second contribution with same signal_fp merges into the first row (merge-layer dedupe)."""
    from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import merge_discovered_native_items

    ledger = initialize_decision_ledger_with_domain_template_seed()
    msg = _long_contradiction("segment one")
    m1 = merge_discovery_from_audit_findings(ledger, [{"finding_id": "id-a", "message": msg}])
    row1 = next(
        i for i in m1.get("items") or [] if isinstance(i, dict) and str(i.get("key") or "").startswith(DISCOVERY_KEY_PREFIX)
    )
    dm = dict(row1.get("discovery_meta") or {})
    sig = str(dm.get("signal_fp") or "")
    assert sig
    row2 = dict(row1)
    row2["key"] = f"{DISCOVERY_KEY_PREFIX}contradiction_cluster:deadbeefcafe"
    row2["evidence_refs"] = ["finding:extra-evidence"]
    stats: dict = {}
    m2 = merge_discovered_native_items(m1, [row2], merge_stats=stats)
    n2 = sum(1 for i in m2.get("items") or [] if isinstance(i, dict) and str(i.get("key")).startswith(DISCOVERY_KEY_PREFIX))
    assert n2 == 1
    assert int(stats.get("rejected_near_duplicate_signal") or 0) >= 1


def test_focus_packet_includes_discovery_work_context() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "p1", "message": _long_contradiction()}],
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
        loop_iteration=3,
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
    dwc = ec.get("discovery_work_context")
    assert isinstance(dwc, dict)
    assert dwc.get("origin") == "transcript_edit_discovery"
    assert dwc.get("kind") == "contradiction_cluster"
    assert dwc.get("why_matters")


def test_continuity_logs_discovery_merge() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    log: list = []
    ledger = merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "c1", "message": _long_contradiction()}],
        merge_stats={},
    )
    append_discovery_merge_continuity(log, iteration=4, merge_stats={"added_keys": ["x"], "signal_merged_into_keys": [], "evidence_only_keys": []})
    assert any(r.get("move") == "discovery_ledger_merge" for r in log if isinstance(r, dict))


def test_low_signal_finding_not_promoted() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    st: dict = {}
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "tiny", "message": "short text"}],  # < _MIN_MESSAGE_CHARS
        merge_stats=st,
    )
    infer = st.get("infer") or {}
    assert int(infer.get("rejected_low_signal") or 0) >= 1


def test_signal_fingerprint_stable() -> None:
    a = signal_fingerprint(kind="dependency", message="  Depends  on  prior  deed  attachment  issues  ")
    b = signal_fingerprint(kind="dependency", message="depends on prior deed attachment issues")
    assert a == b
