from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from backend.agents.transcript_edit.domain_pack import TranscriptEditDomainPack
from backend.agents.transcript_edit.domain_pack_focus_wiring import (
    choose_investigation_fallback_focus_from_state,
    composite_work_board_from_loop_state,
)
from backend.agents.transcript_edit.loop_state import TranscriptEditLoopState
from backend.agents.transcript_edit.work_board_composite import transcript_edit_composite_work_board
from backend.harness.orchestration_kernel.contracts import OrchestratorContext
from backend.harness.orchestration_kernel.loop_memory import LoopMemoryState


def test_composite_and_fallback_match_inline_assembly() -> None:
    from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed

    ledger = initialize_decision_ledger_with_domain_template_seed()
    st = TranscriptEditLoopState(
        decision_ledger=ledger,
        harness_emergent_board_items=[],
        harness_board_context_notes={},
        last_focus_key="range",
    )
    inline = transcript_edit_composite_work_board(
        decision_ledger=ledger,
        harness_emergent_board_items=[],
        harness_board_context_notes={},
    )
    assert composite_work_board_from_loop_state(st) == inline
    b = choose_investigation_fallback_focus_from_state(st)
    assert b["decision_key"] == "range"
    assert b["focus_source"] == "continuity"


def test_domain_pack_project_keeps_last_focus_continuity_over_advisory_ranking() -> None:
    request = TranscriptEditAgentRunRequest(mission_objective="continuity test")
    state = TranscriptEditLoopState(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True, "scope_status": "outside_target"},
                },
                {
                    "key": "section",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True, "scope_status": "in_target"},
                },
            ]
        },
        blocker_registry={
            "rows": [
                {
                    "blocker_id": "blocker:section",
                    "decision_key": "section",
                    "state": "answered_unintegrated",
                    "mapping_blocking": True,
                    "scope_status": "in_target",
                }
            ]
        },
        last_focus_key="range",
    )
    pack = TranscriptEditDomainPack(
        request=request,
        session_id="session:test",
        request_id_prefix="req:test",
        initial_state=state,
    )
    context = OrchestratorContext(
        session_manager=SimpleNamespace(),
        session_id="session:test",
        loop_memory=LoopMemoryState(active_item_id="range"),
        request_id_prefix="req:test",
        dossier_id=None,
    )

    projection = pack.project(context)

    assert projection.resolution_state.active_item_id == "range"
    assert projection.advisory_active_items
    assert projection.advisory_active_items[0]["item_id"] == "range"


def test_domain_pack_project_leaves_selected_focus_empty_without_continuity_or_startup_authorship() -> None:
    request = TranscriptEditAgentRunRequest(mission_objective="startup test")
    state = TranscriptEditLoopState(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True, "scope_status": "outside_target"},
                },
                {
                    "key": "section",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True, "scope_status": "in_target"},
                },
            ]
        },
        blocker_registry={},
        last_focus_key=None,
        llm_startup_understanding=None,
    )
    pack = TranscriptEditDomainPack(
        request=request,
        session_id="session:test",
        request_id_prefix="req:test",
        initial_state=state,
    )
    context = OrchestratorContext(
        session_manager=SimpleNamespace(),
        session_id="session:test",
        loop_memory=LoopMemoryState(active_item_id=None),
        request_id_prefix="req:test",
        dossier_id=None,
    )

    projection = pack.project(context)

    assert projection.resolution_state.active_item_id is None
    assert projection.advisory_active_items


def test_domain_pack_project_uses_startup_understanding_for_first_focus_when_continuity_absent() -> None:
    request = TranscriptEditAgentRunRequest(mission_objective="startup auth test")
    state = TranscriptEditLoopState(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True, "scope_status": "outside_target"},
                }
            ]
        },
        blocker_registry={},
        last_focus_key=None,
        llm_startup_understanding={
            "initial_focus_candidates": [
                {"decision_key": "startup_choice", "title": "Startup-authored focus"}
            ]
        },
    )
    pack = TranscriptEditDomainPack(
        request=request,
        session_id="session:test",
        request_id_prefix="req:test",
        initial_state=state,
    )
    context = OrchestratorContext(
        session_manager=SimpleNamespace(),
        session_id="session:test",
        loop_memory=LoopMemoryState(active_item_id=None),
        request_id_prefix="req:test",
        dossier_id=None,
    )

    projection = pack.project(context)

    assert projection.resolution_state.active_item_id == "startup_choice"
    assert projection.advisory_active_items


def test_domain_pack_project_keeps_continuity_over_startup_understanding() -> None:
    request = TranscriptEditAgentRunRequest(mission_objective="continuity startup precedence test")
    state = TranscriptEditLoopState(
        decision_ledger={"items": []},
        blocker_registry={},
        last_focus_key="range",
        llm_startup_understanding={
            "initial_focus_candidates": [
                {"decision_key": "startup_choice", "title": "Startup-authored focus"}
            ]
        },
    )
    pack = TranscriptEditDomainPack(
        request=request,
        session_id="session:test",
        request_id_prefix="req:test",
        initial_state=state,
    )
    context = OrchestratorContext(
        session_manager=SimpleNamespace(),
        session_id="session:test",
        loop_memory=LoopMemoryState(active_item_id="range"),
        request_id_prefix="req:test",
        dossier_id=None,
    )

    projection = pack.project(context)

    assert projection.resolution_state.active_item_id == "range"
