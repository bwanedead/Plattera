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
from backend.agents.transcript_edit.transcript_edit_bootstrap_hints import TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS
from backend.agents.transcript_edit.loop_state import TranscriptEditLoopState
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.decision_ledger_state import (
    initialize_decision_ledger,
    initialize_decision_ledger_with_domain_template_seed,
)
from backend.harness.decision_ledger import contracts as dl_contracts
from backend.harness.work_board.contracts import WORK_BOARD_VERSION, new_work_board, work_board_item_dict
from backend.harness.work_board.lifecycle import EMERGENT_ITEM_ID_PREFIX


def test_choose_investigation_focus_unified_only_matches_legacy_plus_envelope() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
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
    ledger = initialize_decision_ledger_with_domain_template_seed()
    unified = build_transcript_edit_unified_decision_ledger(decision_ledger=ledger)
    legacy_shape = legacy_decision_ledger_shape_from_unified(unified)
    assert "schema_version" not in legacy_shape
    assert isinstance(legacy_shape.get("items"), list)
    assert len(legacy_shape["items"]) >= 1


def test_transcript_edit_slot_priority_not_on_harness_decision_ledger_contracts() -> None:
    assert not hasattr(dl_contracts, "TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY")
    assert "range" in TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY


def test_closure_read_ledger_pulls_top_level_fields_from_native() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
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
    ledger = initialize_decision_ledger_with_domain_template_seed()
    assert str(ledger.get("schema_version") or "") != WORK_BOARD_VERSION
    unified = new_work_board(domain_projection="t", items=[])
    assert str(unified.get("schema_version") or "") == WORK_BOARD_VERSION


def test_unified_closure_read_from_loop_state_matches_for_native() -> None:
    """Loop-state helper must not drift from the native+emergent+notes read build."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
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


def test_domain_slot_priority_matches_bootstrap_hints() -> None:
    assert TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY == dict(TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS)


def test_bootstrap_hints_file_does_not_import_checklist_seed() -> None:
    hints_path = Path(__file__).resolve().parents[0] / "transcript_edit_bootstrap_hints.py"
    text = hints_path.read_text(encoding="utf-8", errors="replace")
    assert "from .transcript_edit_default_checklist_seed import" not in text
    assert "import transcript_edit_default_checklist_seed" not in text


def test_discovery_prep_file_does_not_import_checklist_seed() -> None:
    prep_path = Path(__file__).resolve().parents[0] / "transcript_edit_ledger_discovery_prep.py"
    text = prep_path.read_text(encoding="utf-8", errors="replace")
    assert "from .transcript_edit_default_checklist_seed import" not in text
    assert "import transcript_edit_default_checklist_seed" not in text


def test_minimal_native_ledger_closure_read_without_full_bootstrap_rows() -> None:
    """Closure read must work when native items are not the default checklist (discovery-prep)."""
    native: dict[str, object] = {
        "items": [
            {
                "key": "custom_discovery_key",
                "label": "Custom",
                "state": "unknown",
                "selected_value": None,
                "alternatives": [],
                "confidence": None,
                "blocking": True,
                "evidence_refs": [],
                "user_override_state": "none",
                "layer_tag": "layer1_canonical_recovery",
                "operational_impact": "mapping_blocking",
                "provenance": "test",
                "verification_required": False,
                "scope_id": "unknown_scope",
                "scope_label": "Unknown",
                "scope_priority": 50,
                "in_target_scope": None,
                "scope_proof": [],
                "closure_requirement": {
                    "mapping_blocking": True,
                    "scope_status": "in_target",
                },
            }
        ],
        "external_context_injections": [],
        "source_completeness": "unknown",
        "source_completeness_reason": None,
        "source_limitations": [],
        "scope_summaries": {},
        "summary": {"unknown_count": 1},
        "blocker_feedback_state": {},
    }
    _, read = transcript_edit_unified_and_closure_read_for_native(native_decision_ledger=native)
    keys = [str(i.get("key") or "") for i in (read.get("items") or []) if isinstance(i, dict)]
    assert "custom_discovery_key" in keys


def test_harness_decision_ledger_contracts_do_not_import_default_checklist_seed() -> None:
    """Bootstrap seed must stay out of generic harness contract modules."""
    contracts_path = (
        Path(__file__).resolve().parents[2] / "harness" / "decision_ledger" / "contracts.py"
    )
    text = contracts_path.read_text(encoding="utf-8", errors="replace")
    assert "transcript_edit_default_checklist_seed" not in text
