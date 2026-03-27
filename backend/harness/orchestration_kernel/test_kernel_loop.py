from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.harness.orchestration_kernel.contracts import (
    ClosureEvaluation,
    FocusPacket,
    KernelLoopResult,
    MoveDecision,
    MoveExecutionPlan,
    OrchestratorContext,
    ProgressMetrics,
    RefreshResult,
    SharedStateProjection,
)
from backend.harness.mission_state import new_mission_state, new_resolution_state
from backend.harness.orchestration_kernel.kernel import run_orchestration_kernel_loop


class _NoStepSessionManager:
    def step(self, request: object) -> object:  # pragma: no cover - should never run here
        raise AssertionError("kernel should not dispatch a step in this test")


@dataclass
class _FakePack:
    focus_key: str
    complete_after_iterations: int
    seen_focus_keys: list[str]

    def orient(self, context: OrchestratorContext) -> None:
        return None

    def refresh(self, context: OrchestratorContext) -> RefreshResult:
        return RefreshResult(latest_refs={}, execution_succeeded=True)

    def project(self, context: OrchestratorContext) -> SharedStateProjection:
        advisory = [
            {"item_id": "ranked-candidate", "status": "open", "priority": 0},
            {"item_id": self.focus_key, "status": "open", "priority": 1},
        ]
        resolution_state = new_resolution_state(
            active_item_id=self.focus_key,
            items=[
                {
                    "item_id": self.focus_key,
                    "title": self.focus_key,
                    "kind": "test_item",
                    "status": "open",
                }
            ],
            updated_at_epoch_seconds=float(context.loop_memory.iterations),
        )
        return SharedStateProjection(
            mission_state=new_mission_state(
                mission_id="mission-1",
                session_id=context.session_id,
                request_id=context.request_id_prefix,
                loop_family="test_loop",
                resolution_state=resolution_state,
            ),
            resolution_state=resolution_state,
            advisory_active_items=advisory,
        )

    def build_focus_packet(self, context: OrchestratorContext, focus_key: str) -> FocusPacket:
        self.seen_focus_keys.append(focus_key)
        return FocusPacket(focus_key=focus_key, domain_packet={"focus_key": focus_key})

    def resolve_move(self, context: OrchestratorContext, focus_packet: FocusPacket) -> MoveDecision:
        assert focus_packet.focus_key == self.focus_key
        return MoveDecision(
            move_type="skip_no_action",
            focus_key=focus_packet.focus_key,
            rationale="domain-authored focus selected",
            domain_move_payload={},
        )

    def compile_move(self, context: OrchestratorContext, move_decision: MoveDecision) -> MoveExecutionPlan:
        return MoveExecutionPlan(
            action_type="skip_no_action",
            action_inputs={},
            idempotency_key=f"move-{context.loop_memory.iterations}",
            skip_execution=True,
        )

    def supply_progress_metrics(self, context: OrchestratorContext) -> ProgressMetrics:
        return ProgressMetrics(
            previous_finding_signature="same",
            current_finding_signature="same",
            previous_blocking_signature="same",
            current_blocking_signature="same",
            previous_blocking_count=1,
            current_blocking_count=1,
            new_evidence_signal=False,
            pending_feedback_prompt_id=None,
            pending_refresh=False,
            refresh_baseline_blocking_count=None,
            refresh_baseline_blocking_signature=None,
        )

    def supply_closure_rules(self, context: OrchestratorContext) -> ClosureEvaluation:
        complete = context.loop_memory.iterations >= self.complete_after_iterations
        return ClosureEvaluation(
            domain_complete=complete,
            domain_terminal_class="completed" if complete else "blocked",
            closure_reason_code="done" if complete else "not_done_yet",
            open_items_summary="",
        )

    def integrate_feedback(self, context: OrchestratorContext, feedback_response: dict[str, object]):
        raise AssertionError("feedback integration is not part of this kernel test")


@dataclass
class _ContinuityPack:
    seen_focus_keys: list[str]
    project_calls: int = 0

    def orient(self, context: OrchestratorContext) -> None:
        return None

    def refresh(self, context: OrchestratorContext) -> RefreshResult:
        return RefreshResult(latest_refs={}, execution_succeeded=True)

    def project(self, context: OrchestratorContext) -> SharedStateProjection:
        self.project_calls += 1
        active_item_id = "carry-me" if self.project_calls == 1 else None
        resolution_state = new_resolution_state(
            active_item_id=active_item_id,
            items=[
                {
                    "item_id": "carry-me",
                    "title": "carry-me",
                    "kind": "test_item",
                    "status": "open",
                }
            ],
            updated_at_epoch_seconds=float(context.loop_memory.iterations),
        )
        return SharedStateProjection(
            mission_state=new_mission_state(
                mission_id="mission-1",
                session_id=context.session_id,
                request_id=context.request_id_prefix,
                loop_family="test_loop",
                resolution_state=resolution_state,
            ),
            resolution_state=resolution_state,
            advisory_active_items=[{"item_id": "other-candidate", "status": "open", "priority": 0}],
        )

    def build_focus_packet(self, context: OrchestratorContext, focus_key: str) -> FocusPacket:
        self.seen_focus_keys.append(focus_key)
        return FocusPacket(focus_key=focus_key, domain_packet={"focus_key": focus_key})

    def resolve_move(self, context: OrchestratorContext, focus_packet: FocusPacket) -> MoveDecision:
        return MoveDecision(
            move_type="skip_no_action",
            focus_key=focus_packet.focus_key,
            rationale="continuity",
            domain_move_payload={},
        )

    def compile_move(self, context: OrchestratorContext, move_decision: MoveDecision) -> MoveExecutionPlan:
        return MoveExecutionPlan(
            action_type="skip_no_action",
            action_inputs={},
            idempotency_key=f"move-{context.loop_memory.iterations}",
            skip_execution=True,
        )

    def supply_progress_metrics(self, context: OrchestratorContext) -> ProgressMetrics:
        return ProgressMetrics(
            previous_finding_signature="same",
            current_finding_signature="same",
            previous_blocking_signature="same",
            current_blocking_signature="same",
            previous_blocking_count=1,
            current_blocking_count=1,
            new_evidence_signal=False,
            pending_feedback_prompt_id=None,
            pending_refresh=False,
            refresh_baseline_blocking_count=None,
            refresh_baseline_blocking_signature=None,
        )

    def supply_closure_rules(self, context: OrchestratorContext) -> ClosureEvaluation:
        complete = context.loop_memory.iterations >= 2
        return ClosureEvaluation(
            domain_complete=complete,
            domain_terminal_class="completed" if complete else "blocked",
            closure_reason_code="done" if complete else "not_done_yet",
            open_items_summary="",
        )

    def integrate_feedback(self, context: OrchestratorContext, feedback_response: dict[str, object]):
        raise AssertionError("feedback integration is not part of this kernel test")


def _run_kernel(pack: _FakePack, *, max_iterations: int, max_no_progress: int) -> KernelLoopResult:
    return run_orchestration_kernel_loop(
        domain_pack=pack,
        session_manager=_NoStepSessionManager(),
        session_id="session-1",
        run_artifact_ref="artifact://run/1",
        request_id_prefix="req-1",
        dossier_id="D-1",
        max_iterations=max_iterations,
        max_no_progress_iterations=max_no_progress,
        max_invalid_plan_attempts=3,
    )


def test_kernel_uses_pack_authored_active_item_instead_of_advisory_candidates() -> None:
    pack = _FakePack(focus_key="authored-focus", complete_after_iterations=1, seen_focus_keys=[])

    result = _run_kernel(pack, max_iterations=2, max_no_progress=10)

    assert result.terminal_class == "completed"
    assert result.reason_code == "done"
    assert pack.seen_focus_keys == ["authored-focus"]


def test_no_progress_only_warns_and_does_not_stop_before_hard_ceiling() -> None:
    pack = _FakePack(focus_key="authored-focus", complete_after_iterations=99, seen_focus_keys=[])

    result = _run_kernel(pack, max_iterations=2, max_no_progress=1)

    assert result.terminal_class == "exhausted"
    assert result.reason_code == "max_iterations_reached"
    assert result.iterations == 2
    assert pack.seen_focus_keys == ["authored-focus", "authored-focus"]


def test_kernel_carries_active_item_continuity_when_projection_leaves_it_empty() -> None:
    pack = _ContinuityPack(seen_focus_keys=[])

    result = _run_kernel(pack, max_iterations=3, max_no_progress=10)

    assert result.terminal_class == "completed"
    assert pack.seen_focus_keys == ["carry-me", "carry-me"]
