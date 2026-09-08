"""MAPDEP-BR-025: same-turn apply_transcript_edits + resolve transition orchestration."""

from __future__ import annotations

import copy
import json
from typing import Any

from harness.execution.contracts import (
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionRefusal,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import (
    ResolutionCoveredUnit,
    ResolutionItem,
    new_mission_state,
    new_resolution_state,
)
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.orchestration.action_sequence import ActionPlanAction
from harness.runtime.orchestration.contracts import (
    ActionPlan,
    OrchestratorContext,
    SharedStateProjection,
    TerminalEvaluation,
)
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop

_PACK_CJ = {"pack_continuity_stub": True}


def _dashboard() -> ExecutionDashboard:
    return ExecutionDashboard(
        latest_refs=ExecutionLatestRefs(refs={}),
        budgets_remaining={},
        last_refusal=None,
    )


class ApplyTranscriptEditsSessionManager(ExecutionSessionManager):
    """Records apply_transcript_edits; configurable success vs refusal."""

    def __init__(self, *, refuse: bool = False) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []
        self.write_side_effects = 0
        self.refuse = refuse

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        if request.action_id == "apply_transcript_edits":
            if self.refuse:
                return ExecutionStepResult(
                    session_id=request.session_id,
                    idempotency_key=request.idempotency_key,
                    execution_state=ExecutionState.REFUSED,
                    dashboard=_dashboard(),
                    refusal=ExecutionRefusal(
                        reason_code="apply_transcript_edits_refused",
                        retryable=False,
                    ),
                )
            self.write_side_effects += 1
            return ExecutionStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=ExecutionState.EXECUTED,
                dashboard=_dashboard(),
            )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(),
        )


class _InheritSyncMixin:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state
        return SharedStateProjection(
            mission_state=prior_ms,
            resolution_state=prior_rs,
            latest_refs=dict(context.loop_memory.continuity.latest_refs),
            active_item_id=prior_rs.active_item_id,
        )


def _seed_item() -> ResolutionItem:
    return ResolutionItem(
        item_id="bearing-group",
        title="Bearing group",
        kind="group",
        status="open",
        next_needed_step="apply transcription",
        blocking=True,
        requires_hitl=False,
        no_further_progress=False,
        covered_units=[
            ResolutionCoveredUnit(
                unit_id="call-2-bearing",
                title="Call 2 bearing",
                status="open",
                next_needed_step="apply transcription",
            )
        ],
    )


def _seed_memory() -> LoopMemoryState:
    mem = LoopMemoryState()
    items = [_seed_item()]
    rs = new_resolution_state(items=items, active_item_id=items[0].item_id)
    ms = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        objective="t",
        resolution_state=rs,
    )
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs
    return mem


def _resolve_unit_patch() -> dict[str, Any]:
    return {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "covered_units": [
                        {
                            "unit_id": "call-2-bearing",
                            "transition": {"kind": "resolve"},
                            "determination": "earned",
                            "determined_value": "N 42° E",
                            "verification_basis": "Confirmed from source evidence.",
                            "evidence_refs": ["image:derived:abc"],
                        }
                    ],
                }
            ]
        }
    }


def _production_apply_transcript_edits_inputs() -> dict[str, Any]:
    """Production-shaped BR-024 request body (no tooling imports)."""
    return {
        "base_revision_ref": "transcript_edit:working:rev:0001",
        "decisions": [
            {
                "decision_id": "decide-call-2-bearing",
                "determination": "earned",
                "verification_basis": "Confirmed from focused source observation.",
                "evidence_refs": ["image:derived:abc"],
                "edits": [
                    {
                        "lane": "source_transcript_verbatim",
                        "expected_text": "N 40 E",
                        "replacement_text": "N 42° E",
                    }
                ],
            }
        ],
    }


class ApplyThenResolvePack(_InheritSyncMixin):
    def evaluate_terminal(
        self, context: OrchestratorContext, projection: SharedStateProjection | None
    ) -> TerminalEvaluation | None:
        if context.loop_memory.iterations >= 2:
            return TerminalEvaluation(terminal_class="completed", reason_code="done")
        return None

    def choose_action(
        self, context: OrchestratorContext, projection: SharedStateProjection | None
    ) -> ActionPlan:
        if context.loop_memory.iterations == 1:
            return ActionPlan(
                actions=(
                    ActionPlanAction(
                        action_type="apply_transcript_edits",
                        action_inputs=_production_apply_transcript_edits_inputs(),
                        alias="apply",
                    ),
                ),
                state_patch=_resolve_unit_patch(),
                continuity_journal_entry=_PACK_CJ,
            )
        return ActionPlan(skip_execution=True, continuity_journal_entry=_PACK_CJ)


def test_successful_apply_transcript_edits_plus_transition_commits_artifact_and_state() -> None:
    sm = ApplyTranscriptEditsSessionManager(refuse=False)
    mem = _seed_memory()
    before = copy.deepcopy(mem.continuity.resolution_state.model_dump(mode="json"))
    result = run_orchestration_kernel_loop(
        orchestration_adapter=ApplyThenResolvePack(),
        session_manager=sm,
        session_id="sess-br025-ok",
        run_artifact_ref=None,
        request_id_prefix="req-br025-ok",
        opaque_run_context={},
        max_iterations=4,
        initial_loop_memory=mem,
    )
    assert result.terminal_class == "completed"
    assert sm.write_side_effects == 1
    assert len(sm.steps) == 1
    assert sm.steps[0].action_id == "apply_transcript_edits"
    submitted = sm.steps[0].inputs
    assert submitted["base_revision_ref"] == "transcript_edit:working:rev:0001"
    assert "working_revision_ref" not in submitted
    assert "edits" not in submitted
    decisions = submitted["decisions"]
    assert isinstance(decisions, list) and len(decisions) == 1
    decision = decisions[0]
    assert decision["decision_id"] == "decide-call-2-bearing"
    assert decision["determination"] == "earned"
    assert decision["verification_basis"]
    assert decision["evidence_refs"] == ["image:derived:abc"]
    assert isinstance(decision["edits"], list) and decision["edits"]
    assert decision["edits"][0]["lane"] == "source_transcript_verbatim"
    rs = result.runtime_state["resolution_state"]
    unit = rs.items[0].covered_units[0]
    assert unit.status == "closed"
    assert unit.next_needed_step is None
    assert unit.requires_hitl is False
    assert unit.no_further_progress is False
    assert unit.determination == "earned"
    assert before["items"][0]["covered_units"][0]["status"] == "open"
    dumped = str(rs.model_dump(mode="json"))
    assert "transition" not in dumped
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "applied"


def test_refused_apply_transcript_edits_leaves_resolution_state_unchanged() -> None:
    sm = ApplyTranscriptEditsSessionManager(refuse=True)
    mem = _seed_memory()
    before = copy.deepcopy(mem.continuity.resolution_state.model_dump(mode="json"))
    result = run_orchestration_kernel_loop(
        orchestration_adapter=ApplyThenResolvePack(),
        session_manager=sm,
        session_id="sess-br025-refuse",
        run_artifact_ref=None,
        request_id_prefix="req-br025-refuse",
        opaque_run_context={},
        max_iterations=4,
        initial_loop_memory=mem,
    )
    assert sm.write_side_effects == 0
    assert len(sm.steps) == 1
    rs = result.runtime_state["resolution_state"]
    assert rs.model_dump(mode="json") == before
    fb = result.runtime_state["state_patch_feedback"]
    assert fb.get("outcome") == "not_applied"


def test_resolve_transition_checkpoint_resume_is_deterministic() -> None:
    from harness.runtime.orchestration.lifecycle import OrchestrationLifecycle

    sm = ApplyTranscriptEditsSessionManager(refuse=False)
    mem = _seed_memory()
    snapshots: list[dict[str, Any]] = []

    def _writer(snap: dict[str, Any]) -> None:
        snapshots.append(dict(snap))

    result = run_orchestration_kernel_loop(
        orchestration_adapter=ApplyThenResolvePack(),
        session_manager=sm,
        session_id="sess-br025-resume",
        run_artifact_ref=None,
        request_id_prefix="req-br025-resume",
        opaque_run_context={},
        max_iterations=4,
        initial_loop_memory=mem,
        lifecycle=OrchestrationLifecycle(resume_checkpoint_writer=_writer),
    )
    assert result.terminal_class == "completed"
    assert snapshots
    restored, _next_it, err = parse_kernel_resume_snapshot(snapshots[-1])
    assert err is None
    live = result.runtime_state["resolution_state"].model_dump(mode="json")
    assert restored.continuity.resolution_state.model_dump(mode="json") == live
    unit = restored.continuity.resolution_state.items[0].covered_units[0]
    assert unit.status == "closed"
    assert unit.next_needed_step is None
    restored_dump = json.dumps(
        restored.continuity.resolution_state.model_dump(mode="json"),
        ensure_ascii=False,
    )
    assert "transition" not in restored_dump
