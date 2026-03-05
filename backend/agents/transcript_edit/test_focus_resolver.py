from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from transcript_edit.contracts import EditPlanV0

from backend.agents.transcript_edit.focus_resolver import resolve_focus_move


class _PlannerNoPlan:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "resolver_unavailable", ""

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "planner_unavailable", ""


class _PlannerNoOps:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        decision_key = str((kwargs.get("focus_packet") or {}).get("decision_key") or "section")
        return {
            "decision_key": decision_key,
            "move": "gather_more_evidence",
            "reason": "needs_more_evidence",
            "edit_plan": None,
            "feedback_prompt": None,
            "evidence_request": {"kind": "image_verify"},
            "closure_update_hint": None,
            "iteration_summary": "Need more evidence.",
        }, "ok", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = kwargs["source_transcript_ref"]
        source_hash = kwargs["source_transcript_hash"]
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "noop",
                "summary": "no safe edits",
                "ops": [],
                "global_flags": {"review_required": True},
            }
        )
        return plan, "ok", json.dumps(plan.model_dump(mode="json"))


class _PlannerWithOps:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = (kwargs.get("focus_packet") or {}).get("source_transcript_ref") or "in-memory://source.json"
        source_hash = (kwargs.get("focus_packet") or {}).get("source_transcript_hash") or "sha256:test"
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "ops",
                "summary": "safe edit",
                "ops": [
                    {
                        "op_id": "op-1",
                        "op_type": "replace_span",
                        "change_class": "semantic",
                        "confidence": "high",
                        "review_required": True,
                        "reason": "test",
                        "evidence_refs": [source_ref],
                        "target": {"locator_type": "offsets", "start_char": 0, "end_char": 5},
                        "expected_old": {"old_excerpt": "abc"},
                        "new_text": "xyz",
                    }
                ],
                "global_flags": {"review_required": True},
            }
        )
        return {
            "decision_key": str((kwargs.get("focus_packet") or {}).get("decision_key") or "section"),
            "move": "apply_edit_plan",
            "reason": "have_safe_plan",
            "edit_plan": plan.model_dump(mode="json"),
            "feedback_prompt": None,
            "evidence_request": None,
            "closure_update_hint": None,
            "iteration_summary": "Apply plan.",
        }, "ok", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = kwargs["source_transcript_ref"]
        source_hash = kwargs["source_transcript_hash"]
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "ops",
                "summary": "safe edit",
                "ops": [
                    {
                        "op_id": "op-1",
                        "op_type": "replace_span",
                        "change_class": "semantic",
                        "confidence": "high",
                        "review_required": True,
                        "reason": "test",
                        "evidence_refs": [source_ref],
                        "target": {"locator_type": "offsets", "start_char": 0, "end_char": 5},
                        "expected_old": {"old_excerpt": "abc"},
                        "new_text": "xyz",
                    }
                ],
                "global_flags": {"review_required": True},
            }
        )
        return plan, "ok", json.dumps(plan.model_dump(mode="json"))


def _focus_packet(*, state: str = "disputed", feedback: dict | None = None) -> dict:
    return {
        "decision_key": "section",
        "ledger_item": {
            "key": "section",
            "state": state,
            "blocking": True,
            "closure_requirement": {"mapping_blocking": True},
        },
        "closure_requirement": {"mapping_blocking": True},
        "source_transcript_ref": "in-memory://source.json",
        "source_transcript_hash": "sha256:test",
        "span_context": [],
        "image_verification": {},
        "feedback": feedback,
    }


def test_focus_resolver_returns_request_human_feedback_when_no_plan_and_no_feedback() -> None:
    out = resolve_focus_move(
        focus_packet=_focus_packet(state="disputed", feedback=None),
        planner_client=_PlannerNoPlan(),
        model="gpt-5.2",
        findings_summary={},
        planning_findings=[],
        max_invalid_plan_attempts=2,
    )
    assert out["move"] in {"request_human_feedback", "mark_blocked"}


def test_focus_resolver_returns_mark_blocked_when_feedback_but_no_plan() -> None:
    out = resolve_focus_move(
        focus_packet=_focus_packet(state="disputed", feedback={"decision_key": "section", "selected_value": "Section 12"}),
        planner_client=_PlannerNoPlan(),
        model="gpt-5.2",
        findings_summary={},
        planning_findings=[],
        max_invalid_plan_attempts=2,
    )
    assert out["move"] == "mark_blocked"


def test_focus_resolver_returns_gather_more_evidence_for_noop_plan() -> None:
    out = resolve_focus_move(
        focus_packet=_focus_packet(state="unknown", feedback=None),
        planner_client=_PlannerNoOps(),
        model="gpt-5.2",
        findings_summary={},
        planning_findings=[],
        max_invalid_plan_attempts=2,
    )
    assert out["move"] == "gather_more_evidence"


def test_focus_resolver_returns_apply_edit_plan_for_valid_ops() -> None:
    out = resolve_focus_move(
        focus_packet=_focus_packet(state="candidate_found", feedback={"decision_key": "section", "selected_value": "Section 12"}),
        planner_client=_PlannerWithOps(),
        model="gpt-5.2",
        findings_summary={},
        planning_findings=[],
        max_invalid_plan_attempts=2,
    )
    assert out["move"] == "apply_edit_plan"
    assert isinstance(out.get("edit_plan"), dict)


def test_focus_resolver_returns_mark_resolved_no_edit_when_not_unresolved_blocker() -> None:
    out = resolve_focus_move(
        focus_packet=_focus_packet(state="verified", feedback=None),
        planner_client=_PlannerWithOps(),
        model="gpt-5.2",
        findings_summary={},
        planning_findings=[],
        max_invalid_plan_attempts=2,
    )
    assert out["move"] == "mark_resolved_no_edit"
