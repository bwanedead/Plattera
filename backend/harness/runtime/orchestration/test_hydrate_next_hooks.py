"""Tests for the orchestrator hooks that drive agent-authored ``hydrate_next``."""

from __future__ import annotations

from typing import Any

from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionRefusal,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.execution.session import ExecutionSessionManager
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import ActionPlan
from harness.runtime.orchestration.hydrate_next_hooks import (
    capture_hydrate_next_after_step,
    clear_surfaced_hydration,
    surface_pending_hydration_before_choose_action,
)


def _dashboard() -> ExecutionDashboard:
    return ExecutionDashboard(
        latest_refs=ExecutionLatestRefs(refs={}),
        budgets_remaining={},
        last_refusal=None,
    )


def _step_result_with_outputs(
    *,
    action_id: str,
    session_id: str = "s",
    outputs: dict[str, Any] | None = None,
    artifact_refs: tuple[str, ...] = (),
) -> ExecutionStepResult:
    request = ExecutionStepRequest(session_id=session_id, action_id=action_id)
    result = ActionDispatchResult(
        action_id=action_id,
        executed=True,
        outputs=dict(outputs or {}),
        artifact_refs=artifact_refs,
    )
    record = SessionExecutionRecord(
        session_id=session_id, run_id="r", request=request, result=result,
    )
    return ExecutionStepResult(
        session_id=session_id,
        idempotency_key="",
        execution_state=ExecutionState.EXECUTED,
        dashboard=_dashboard(),
        record=record,
    )


def _refused_step_result(*, action_id: str = "x", reason_code: str = "ref_ids_required") -> ExecutionStepResult:
    request = ExecutionStepRequest(session_id="s", action_id=action_id)
    refusal = ExecutionRefusal(reason_code=reason_code, retryable=False, blocked_by_invariant=True)
    result = ActionDispatchResult(action_id=action_id, executed=False, refusal=refusal)
    record = SessionExecutionRecord(session_id="s", run_id="r", request=request, result=result)
    return ExecutionStepResult(
        session_id="s",
        idempotency_key="",
        execution_state=ExecutionState.REFUSED,
        dashboard=_dashboard(),
        refusal=refusal,
        record=record,
    )


class _RecordingSessionManager(ExecutionSessionManager):
    """Records each step request and returns a configurable result."""

    def __init__(self, *, result: ExecutionStepResult | None = None) -> None:
        super().__init__()
        self.requests: list[ExecutionStepRequest] = []
        self._result = result

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.requests.append(request)
        if self._result is not None:
            return self._result
        # Default: an EXECUTED hydration result mimicking ``hydrate_artifact_refs``.
        return _step_result_with_outputs(
            action_id=request.action_id,
            session_id=request.session_id,
            outputs={
                "results": [{"ref_id": rid, "kind": "stub", "payload": {}} for rid in (request.inputs.get("ref_ids") or [])],
                "errors": [],
            },
        )


# ---------------------------------------------------------------------------
# capture_hydrate_next_after_step
# ---------------------------------------------------------------------------

def test_capture_does_nothing_when_plan_has_no_hydrate_next() -> None:
    lm = LoopMemoryState()
    plan = ActionPlan(action_type="noop", rationale="t")
    capture_hydrate_next_after_step(
        loop_memory=lm, action_plan=plan, step_result=None, iteration=3,
    )
    assert lm.continuity.pending_agent_hydration is None


def test_capture_resolves_literal_refs_with_no_step_result() -> None:
    lm = LoopMemoryState()
    plan = ActionPlan(
        action_type=None, skip_execution=True, rationale="t",
        hydrate_next=("artifact://x", "artifact://y"),
        hydrate_next_reason="inspect both",
    )
    capture_hydrate_next_after_step(
        loop_memory=lm, action_plan=plan, step_result=None, iteration=5,
    )
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["resolved_refs"] == ["artifact://x", "artifact://y"]
    assert rec["status"] == "pending"
    assert rec["reason"] == "inspect both"
    assert rec["source_turn_index"] == 5


def test_capture_resolves_placeholders_against_executed_tool_result() -> None:
    lm = LoopMemoryState()
    plan = ActionPlan(
        action_type="save_workspace_artifact", rationale="t",
        hydrate_next=("@result.revision_ref",),
    )
    step_result = _step_result_with_outputs(
        action_id="save_workspace_artifact",
        outputs={"revision_ref": "transcript_edit:working:rev:0001"},
    )
    capture_hydrate_next_after_step(
        loop_memory=lm, action_plan=plan, step_result=step_result, iteration=7,
    )
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["resolved_refs"] == ["transcript_edit:working:rev:0001"]
    assert rec["errors"] == []


def test_capture_records_compact_error_when_placeholder_cannot_resolve() -> None:
    lm = LoopMemoryState()
    plan = ActionPlan(
        action_type="transform_artifact", rationale="t",
        hydrate_next=("@result.derived_ref_id",),
    )
    step_result = _step_result_with_outputs(action_id="transform_artifact", outputs={})
    capture_hydrate_next_after_step(
        loop_memory=lm, action_plan=plan, step_result=step_result, iteration=9,
    )
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["resolved_refs"] == []
    assert rec["errors"][0]["reason_code"] == "placeholder_not_found"


def test_capture_resolves_artifact_refs_list_placeholder() -> None:
    lm = LoopMemoryState()
    plan = ActionPlan(
        action_type="transform_artifact", rationale="t",
        hydrate_next=("@result.artifact_refs[]",),
    )
    step_result = _step_result_with_outputs(
        action_id="transform_artifact",
        artifact_refs=("a", "b", "c"),
    )
    capture_hydrate_next_after_step(
        loop_memory=lm, action_plan=plan, step_result=step_result, iteration=2,
    )
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["resolved_refs"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# surface_pending_hydration_before_choose_action
# ---------------------------------------------------------------------------

def test_surface_is_noop_when_no_pending_record() -> None:
    lm = LoopMemoryState()
    sm = _RecordingSessionManager()
    surface_pending_hydration_before_choose_action(
        loop_memory=lm, session_manager=sm, session_id="s",
        request_id_prefix="rid", run_id="r", iteration=1,
    )
    assert sm.requests == []
    assert lm.continuity.pending_agent_hydration is None


def test_surface_dispatches_hydrate_artifact_refs_and_attaches_results() -> None:
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 4,
        "requested_refs": ["@result.revision_ref"],
        "resolved_refs": ["r-1"],
        "reason": None,
        "errors": [],
        "hydrated_results": None,
        "hydration_errors": None,
        "status": "pending",
        "surfaced_iteration": None,
    }
    sm = _RecordingSessionManager()
    surface_pending_hydration_before_choose_action(
        loop_memory=lm, session_manager=sm, session_id="s",
        request_id_prefix="rid", run_id="r", iteration=5,
    )
    assert len(sm.requests) == 1
    assert sm.requests[0].action_id == "hydrate_artifact_refs"
    assert sm.requests[0].inputs == {"ref_ids": ["r-1"]}
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["status"] == "surfaced"
    assert rec["surfaced_iteration"] == 5
    assert rec["hydrated_results"] == [{"ref_id": "r-1", "kind": "stub", "payload": {}}]


def test_surface_flips_status_even_without_resolved_refs() -> None:
    """No refs to hydrate (all placeholders failed); still surface so agent sees errors."""
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 4,
        "requested_refs": ["@result.revision_ref"],
        "resolved_refs": [],
        "reason": None,
        "errors": [{"requested_ref": "@result.revision_ref", "reason_code": "placeholder_not_found"}],
        "hydrated_results": None,
        "hydration_errors": None,
        "status": "pending",
        "surfaced_iteration": None,
    }
    sm = _RecordingSessionManager()
    surface_pending_hydration_before_choose_action(
        loop_memory=lm, session_manager=sm, session_id="s",
        request_id_prefix="rid", run_id="r", iteration=6,
    )
    assert sm.requests == []
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["status"] == "surfaced"
    assert rec["surfaced_iteration"] == 6


def test_surface_is_noop_when_already_surfaced() -> None:
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 4,
        "requested_refs": ["r-1"],
        "resolved_refs": ["r-1"],
        "reason": None,
        "errors": [],
        "hydrated_results": [{"ref_id": "r-1"}],
        "hydration_errors": None,
        "status": "surfaced",
        "surfaced_iteration": 5,
    }
    sm = _RecordingSessionManager()
    surface_pending_hydration_before_choose_action(
        loop_memory=lm, session_manager=sm, session_id="s",
        request_id_prefix="rid", run_id="r", iteration=6,
    )
    assert sm.requests == []
    # No re-hydration, no resurface.
    assert lm.continuity.pending_agent_hydration["surfaced_iteration"] == 5


def test_surface_records_refusal_when_hydrate_step_refused() -> None:
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 4,
        "requested_refs": ["r-1"],
        "resolved_refs": ["r-1"],
        "reason": None,
        "errors": [],
        "hydrated_results": None,
        "hydration_errors": None,
        "status": "pending",
        "surfaced_iteration": None,
    }
    sm = _RecordingSessionManager(result=_refused_step_result(reason_code="unknown_ref_kind"))
    surface_pending_hydration_before_choose_action(
        loop_memory=lm, session_manager=sm, session_id="s",
        request_id_prefix="rid", run_id="r", iteration=7,
    )
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["status"] == "surfaced"
    assert rec["hydration_errors"] == [{"reason_code": "unknown_ref_kind"}]
    assert rec["hydrated_results"] is None


def test_surface_funnels_image_evidence_into_pending_buffer() -> None:
    """Regression: a hidden hydrate step that returns ``image_evidence`` must
    accumulate it onto ``loop_memory.pending_image_evidence`` so the next
    model turn actually receives the image pixels — not just JSON metadata."""
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 4,
        "requested_refs": ["image:derived:abc"],
        "resolved_refs": ["image:derived:abc"],
        "reason": None,
        "errors": [],
        "hydrated_results": None,
        "hydration_errors": None,
        "status": "pending",
        "surfaced_iteration": None,
    }
    img_evidence = (
        {"ref_id": "image:derived:abc", "b64": "ZmFrZQ==", "media_type": "image/png"},
    )
    request = ExecutionStepRequest(session_id="s", action_id="hydrate_artifact_refs")
    result = ActionDispatchResult(
        action_id="hydrate_artifact_refs",
        executed=True,
        outputs={
            "results": [{"ref_id": "image:derived:abc", "kind": "derived_image", "absolute_path": "/tmp/x.png"}],
            "errors": [],
        },
        image_evidence=img_evidence,
    )
    record_inner = SessionExecutionRecord(session_id="s", run_id="r", request=request, result=result)
    canned = ExecutionStepResult(
        session_id="s",
        idempotency_key="ik",
        execution_state=ExecutionState.EXECUTED,
        dashboard=_dashboard(),
        record=record_inner,
    )
    sm = _RecordingSessionManager(result=canned)
    surface_pending_hydration_before_choose_action(
        loop_memory=lm, session_manager=sm, session_id="s",
        request_id_prefix="rid", run_id="r", iteration=5,
    )
    assert lm.pending_image_evidence == list(img_evidence)
    # The agent-visible lane also still gets the JSON result row.
    rec = lm.continuity.pending_agent_hydration
    assert rec is not None
    assert rec["hydrated_results"][0]["ref_id"] == "image:derived:abc"


def test_surface_uses_iteration_in_idempotency_key() -> None:
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {
        "source_turn_index": 4,
        "requested_refs": ["r-1"],
        "resolved_refs": ["r-1"],
        "reason": None,
        "errors": [],
        "hydrated_results": None,
        "hydration_errors": None,
        "status": "pending",
        "surfaced_iteration": None,
    }
    sm = _RecordingSessionManager()
    surface_pending_hydration_before_choose_action(
        loop_memory=lm, session_manager=sm, session_id="s",
        request_id_prefix="my-run", run_id="r", iteration=12,
    )
    assert sm.requests[0].idempotency_key == "my-run:iter:12:agent_hydrate_next"


# ---------------------------------------------------------------------------
# clear_surfaced_hydration
# ---------------------------------------------------------------------------

def test_clear_drops_surfaced_record() -> None:
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {"status": "surfaced"}
    clear_surfaced_hydration(loop_memory=lm)
    assert lm.continuity.pending_agent_hydration is None


def test_clear_keeps_pending_record() -> None:
    lm = LoopMemoryState()
    lm.continuity.pending_agent_hydration = {"status": "pending"}
    clear_surfaced_hydration(loop_memory=lm)
    assert lm.continuity.pending_agent_hydration == {"status": "pending"}


def test_clear_is_noop_when_no_record() -> None:
    lm = LoopMemoryState()
    clear_surfaced_hydration(loop_memory=lm)
    assert lm.continuity.pending_agent_hydration is None
