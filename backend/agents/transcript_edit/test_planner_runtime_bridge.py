from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.iteration_repair_runtime import run_standalone_edit_planner_for_focus_packet
from backend.agents.transcript_edit.prompting import build_planner_user_message, slim_execution_context_for_planner


class _CapturingPlanner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(dict(kwargs))
        return None, "ok", ""

    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "unused", ""


def test_bridge_passes_execution_context_into_propose_plan() -> None:
    planner = _CapturingPlanner()
    ledger = {"items": [], "scope_summaries": {}, "source_completeness": "unknown"}
    packet = build_focus_packet(
        decision_ledger=ledger,
        decision_key=None,
        focus_source="test",
        focus_reason_code="t",
        loop_iteration=1,
        active_emergent_blocker=None,
        blocker_registry={},
        source_transcript_ref="ref:x",
        source_transcript_hash="hash:x",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    run_standalone_edit_planner_for_focus_packet(
        planner_client=planner,  # type: ignore[arg-type]
        model="gpt-test",
        focus_packet=packet,
        findings_summary={},
        top_findings=[],
        span_context=[],
        image_verification={},
        mapping_priority_focus={},
        max_attempts=1,
        run_link_id="rid",
        mission_objective="m",
    )
    assert len(planner.calls) == 1
    ec = planner.calls[0].get("execution_context")
    assert isinstance(ec, dict)
    assert ec.get("schema_version") == "execution_context.v1"


def test_slim_execution_context_stays_bounded_for_planner_payload() -> None:
    ledger = {"items": [], "scope_summaries": {}, "source_completeness": "unknown"}
    packet = build_focus_packet(
        decision_ledger=ledger,
        decision_key=None,
        source_transcript_ref="ref:x",
        source_transcript_hash="h",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[{"iteration": i, "move": "gather_more_evidence"} for i in range(30)],
    )
    ec = packet.get("execution_context")
    slim = slim_execution_context_for_planner(ec if isinstance(ec, dict) else None)
    assert slim is not None
    dumped = json.dumps(slim)
    assert slim.get("support_state", {}).get("item_context", {}).get("role") == "sticky_note"
    assert len(dumped) < 12000
    msg = build_planner_user_message(
        source_transcript_ref="r",
        source_transcript_hash="h",
        findings_summary={},
        top_findings=[],
        span_context=[],
        image_verification={},
        candidate_disagreement_hints={},
        mapping_priority_focus={},
        investigation_brief={"role": "sticky_note", "purpose": "current_case_understanding"},
        item_context={"role": "sticky_note", "purpose": "current_case_understanding"},
        continuity_context={"active_item_id": "range"},
        evidence_context={"source_completeness": "unknown"},
        item_history=[],
        unresolved_questions=[],
        execution_context=slim,
    )
    assert isinstance(msg, str)
    assert len(msg) < 50000
    payload = json.loads(msg)
    assert "policy_signals" not in payload
