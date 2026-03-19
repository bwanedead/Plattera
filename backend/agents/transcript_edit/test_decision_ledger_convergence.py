"""Decision ledger convergence: one canonical unified envelope + adapter boundaries."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger_adapter import (
    TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY,
    build_transcript_edit_unified_decision_ledger,
    legacy_decision_ledger_shape_from_unified,
    transcript_edit_closure_read_ledger,
    transcript_edit_unified_and_closure_read_for_native,
    transcript_edit_unified_and_closure_read_from_loop_state,
)
from backend.agents.transcript_edit.loop_state import TranscriptEditLoopState
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.decision_ledger_state import initialize_decision_ledger
from backend.harness.decision_ledger import contracts as dl_contracts
from backend.harness.work_board.contracts import WORK_BOARD_VERSION, new_work_board, work_board_item_dict
from backend.harness.work_board.lifecycle import EMERGENT_ITEM_ID_PREFIX


def test_choose_investigation_focus_unified_only_matches_legacy_plus_envelope() -> None:
    ledger = initialize_decision_ledger()
    items = list(ledger.get("items") or [])
    for it in items:
        if isinstance(it, dict) and str(it.get("key") or "") == "range":
            it["state"] = "disputed"
            it["blocking"] = True
            it["alternatives"] = ["A", "B"]
            cr = it.get("closure_requirement")
            if not isinstance(cr, dict):
                cr = {}
            cr = dict(cr)
            cr["scope_status"] = "in_target"
            cr["mapping_blocking"] = True
            it["closure_requirement"] = cr
            break
    ledger["items"] = items

    em = work_board_item_dict(
        item_id=f"{EMERGENT_ITEM_ID_PREFIX}convtest",
        title="Emergent probe",
        kind="harness.emergent",
        state="open",
        priority=10,
        materiality="high",
        blocking_impact="mapping_blocking",
        provenance="harness.emergent.v1",
    )
    unified = build_transcript_edit_unified_decision_ledger(
        decision_ledger=ledger,
        harness_emergent_board_items=[em],
        harness_board_context_notes={},
    )
    dual = choose_investigation_focus(ledger, work_board=unified) or {}
    single = choose_investigation_focus(unified) or {}
    assert dual.get("decision_key") == single.get("decision_key")
    assert dual.get("focus_target_kind") == single.get("focus_target_kind")


def test_legacy_shape_from_unified_has_no_schema_version_pollution() -> None:
    """Reconstructed closure slice must look like native checklist dicts, not a ledger envelope."""
    ledger = initialize_decision_ledger()
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    legacy_shape = legacy_decision_ledger_shape_from_unified(unified)
    assert "schema_version" not in legacy_shape
    assert isinstance(legacy_shape.get("items"), list)
    assert len(legacy_shape["items"]) >= 1


def test_transcript_edit_slot_priority_not_on_harness_decision_ledger_contracts() -> None:
    assert not hasattr(dl_contracts, "TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY")
    assert "range" in TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY


def test_closure_read_ledger_pulls_top_level_fields_from_native() -> None:
    ledger = initialize_decision_ledger()
    ledger["source_completeness"] = "partial_truncated"
    ledger["external_context_injections"] = [
        {
            "type": "human_resolution_ticket",
            "ticket_id": "t1",
            "decision_key": "range",
            "lifecycle_state": "answered_unintegrated",
            "payload": {},
            "created_at": 1,
            "updated_at": 1,
        }
    ]
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    read = transcript_edit_closure_read_ledger(
        unified_decision_ledger=unified,
        native_decision_ledger=ledger,
    )
    assert read.get("source_completeness") == "partial_truncated"
    assert len(read.get("external_context_injections") or []) >= 1


def test_envelope_detection_distinguishes_native_ledger_from_unified() -> None:
    ledger = initialize_decision_ledger()
    assert str(ledger.get("schema_version") or "") != WORK_BOARD_VERSION
    unified = new_work_board(domain_projection="t", items=[])
    assert str(unified.get("schema_version") or "") == WORK_BOARD_VERSION


def test_unified_closure_read_from_loop_state_matches_for_native() -> None:
    """Loop-state helper must not drift from the native+emergent+notes read build."""
    ledger = initialize_decision_ledger()
    state = TranscriptEditLoopState(
        decision_ledger=ledger,
        harness_emergent_board_items=[],
        harness_board_context_notes={},
    )
    u_loop, r_loop = transcript_edit_unified_and_closure_read_from_loop_state(state)
    u_direct, r_direct = transcript_edit_unified_and_closure_read_for_native(
        native_decision_ledger=ledger,
        harness_emergent_board_items=[],
        harness_board_context_notes={},
    )
    assert u_loop == u_direct
    assert r_loop == r_direct


def test_harness_decision_ledger_contracts_do_not_import_default_checklist_seed() -> None:
    """Bootstrap seed must stay out of generic harness contract modules."""
    contracts_path = (
        Path(__file__).resolve().parents[2] / "harness" / "decision_ledger" / "contracts.py"
    )
    text = contracts_path.read_text(encoding="utf-8", errors="replace")
    assert "transcript_edit_default_checklist_seed" not in text
