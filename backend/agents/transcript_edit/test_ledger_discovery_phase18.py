"""Phase 18: single-ledger story, native write seam, compatibility vs canonical surfaces."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel import KernelSessionManager
from backend.agent_kernel.kernel import run_kernel
from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger, initialize_decision_ledger_with_domain_template_seed
from backend.agents.transcript_edit.decision_ledger_adapter import (
    build_transcript_edit_unified_decision_ledger,
    transcript_edit_closure_read_ledger,
    transcript_edit_unified_and_closure_read_for_native,
)
from backend.agents.transcript_edit.decision_ledger_state import reconcile_ledger_derived_fields
from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.llm_startup_understanding import native_rows_from_llm_initial_ledger_items
from backend.agents.transcript_edit.transcript_edit_ledger_discovery_prep import merge_discovery_from_audit_findings
from backend.harness.mission_state.resolution_projection import RESOLUTION_PROJECTION_VERSION


def _long_contra() -> str:
    return (
        "contradiction between candidate bearings and recorded calls in the boundary description for audit"
    )


def test_resolution_projection_version_is_native() -> None:
    """Single organized-work envelope uses the native resolution projection wire id."""
    assert RESOLUTION_PROJECTION_VERSION == "resolution_projection.v1"


def test_unified_and_closure_read_center_envelope_not_raw_native_items() -> None:
    """Authoritative read path: unified envelope + closure overlay; empty native still yields valid reads."""
    native = initialize_decision_ledger()
    assert native.get("items") == []
    unified, read_ledger = transcript_edit_unified_and_closure_read_for_native(native_decision_ledger=native)
    assert str(unified.get("schema_version") or "") == RESOLUTION_PROJECTION_VERSION
    assert isinstance(read_ledger.get("items"), list)


def test_closure_read_items_follow_unified_after_discovery_merge() -> None:
    native = initialize_decision_ledger()
    native["items"].extend(
        native_rows_from_llm_initial_ledger_items(
            [{"title": "Closure read discovery", "summary": _long_contra(), "mapping_blocking": True}]
        )
    )
    reconcile_ledger_derived_fields(native)
    merge_discovery_from_audit_findings(
        native,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=native)
    closure = transcript_edit_closure_read_ledger(
        unified_decision_ledger=unified,
        native_decision_ledger=native,
    )
    u_rows = [
        i
        for i in unified.get("items") or []
        if isinstance(i, dict) and str(i.get("item_id") or "").startswith("te:ledger:")
    ]
    c_rows = [i for i in closure.get("items") or [] if isinstance(i, dict)]
    assert len(u_rows) == len(c_rows) >= 1


def test_optional_template_seed_is_explicit_and_non_default() -> None:
    disc = initialize_decision_ledger()
    tmpl = initialize_decision_ledger_with_domain_template_seed()
    assert disc.get("ledger_establishment_mode") == "discovery_native"
    assert tmpl.get("ledger_establishment_mode") == "template_seed"
    assert len(disc.get("items") or []) == 0
    assert len(tmpl.get("items") or []) >= 1


def test_focus_packet_exposes_unified_envelope_on_work_board_key() -> None:
    """Historical field name `work_board` holds the same envelope as the decision ledger wire shape."""
    ledger = initialize_decision_ledger()
    ledger["items"].extend(
        native_rows_from_llm_initial_ledger_items(
            [{"title": "Focus packet discovery", "summary": _long_contra(), "mapping_blocking": True}]
        )
    )
    reconcile_ledger_derived_fields(ledger)
    merge_discovery_from_audit_findings(
        ledger,
        [{"finding_id": "d1", "message": _long_contra()}],
    )
    keys = [str(i.get("key")) for i in ledger.get("items") or [] if isinstance(i, dict)]
    focus_key = next(k for k in keys if k)
    packet = build_focus_packet(
        decision_ledger=ledger,
        decision_key=focus_key,
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    wb = packet.get("work_board")
    assert isinstance(wb, dict)
    assert str(wb.get("schema_version") or "") == RESOLUTION_PROJECTION_VERSION


def test_mission_state_exports_remain_domain_agnostic() -> None:
    from backend.harness import mission_state

    names = {n for n in dir(mission_state) if not n.startswith("_")}
    assert not any("transcript" in n.lower() or "plss" in n.lower() or "deed" in n.lower() for n in names)


def test_agent_kernel_canonical_and_compatibility_exports() -> None:
    assert callable(run_kernel)
    assert isinstance(KernelSessionManager, type)
