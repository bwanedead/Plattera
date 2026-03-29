from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.contracts import TranscriptEditAgentRunRequest
from backend.domains.mapping.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed
from backend.domains.mapping.transcript_edit.iteration_repair_runtime import handle_repair_iteration
from backend.domains.mapping.transcript_edit.loop_state import TranscriptEditLoopState


def _ledger_item_by_key(ledger: dict, key: str) -> dict:
    for item in ledger.get("items") or []:
        if isinstance(item, dict) and str(item.get("key") or "") == key:
            return item
    raise AssertionError(f"missing ledger key {key}")


class _PlannerCapture:
    def __init__(self) -> None:
        self.propose_plan_kwargs: list[dict] = []

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        self.propose_plan_kwargs.append(dict(kwargs))
        return None, "planner_stub", ""

    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        dk = str((kwargs.get("focus_packet") or {}).get("decision_key") or "range")
        return {"decision_key": dk, "move": "gather_more_evidence", "reason": "stub"}, "ok", ""


def _range_disputed_ledger() -> dict:
    """Phase 24: disputed range is LLM/orient-authored on the ledger, not from audit findings."""
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for item in ledger.get("items") or []:
        if isinstance(item, dict) and str(item.get("key") or "") == "range":
            item["state"] = "disputed"
            item["blocking"] = True
            item["alternatives"] = ["Range 75 West", "Range 74 West"]
            item["closure_requirement"] = {
                "block_reason": "contradiction",
                "mapping_blocking": True,
                "operational_impact": "mapping_blocking",
                "resolution_options": ["Range 75 West", "Range 74 West"],
                "evidence_refs": ["plss_range_conflict_001"],
            }
            break
    return ledger


def test_handle_repair_iteration_invokes_standalone_planner_with_execution_context_when_flag_on() -> None:
    ledger = _range_disputed_ledger()
    range_row = _ledger_item_by_key(ledger, "range")
    assert str(range_row.get("state") or "") == "disputed"

    state = TranscriptEditLoopState(
        current_transcript_ref="artifact://src",
        decision_ledger=ledger,
        blocker_registry={},
        continuity_log=[],
        llm_startup_understanding={
            "initial_focus_candidates": [
                {"decision_key": "range", "title": "Range startup-authored focus"}
            ]
        },
    )
    planner = _PlannerCapture()
    request = TranscriptEditAgentRunRequest(
        run_standalone_edit_planner=True,
        max_no_progress_iterations=5,
        mission_objective="test mission",
    )
    with (
        patch(
            "backend.domains.mapping.transcript_edit.iteration_repair_runtime.drain_pending_feedback",
            return_value=None,
        ),
        patch(
            "backend.domains.mapping.transcript_edit.iteration_repair_runtime.handle_repair_move_outcome",
            return_value=None,
        ),
    ):
        handle_repair_iteration(
            state=state,
            session_manager=MagicMock(),
            session_id="sid",
            request=request,
            request_id_prefix="run-test",
            iterations=1,
            planner_client=planner,  # type: ignore[arg-type]
            tx_persistence=MagicMock(),
            planning_findings=[],
            top_findings=[],
            findings_summary={},
            source_transcript_hash="hash9",
            progress_cb=None,
            model="gpt-test",
            validation_mode="off",
        )

    assert len(planner.propose_plan_kwargs) == 1
    ec = planner.propose_plan_kwargs[0].get("execution_context")
    assert isinstance(ec, dict)
    assert ec.get("schema_version") == "execution_context.v1"
    assert str(planner.propose_plan_kwargs[0].get("source_transcript_ref") or "") == "artifact://src"

