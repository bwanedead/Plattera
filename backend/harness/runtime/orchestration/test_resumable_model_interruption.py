"""Integration tests for resumable model interruption terminal posture."""

from __future__ import annotations

from harness.runtime.orchestration.test_orchestrator import FakeSessionManager
from harness.runtime.orchestration.lifecycle import OrchestrationLifecycle
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.resumable_model_interruption import ResumableModelInterruption
from harness.runtime.model_failure_classifier import classify_model_failure


class _InterruptingAdapter:
    def initialize(self, context) -> None:
        pass

    def sync(self, context, projection=None):
        return None

    def evaluate_terminal(self, context, projection=None):
        return None

    def choose_action(self, context, projection=None):
        classification = classify_model_failure(
            raw_response={"success": False, "error": "insufficient_quota"},
        )
        raise ResumableModelInterruption(
            classification=classification,
            iteration=int(context.loop_memory.iterations),
            prompt_mode="choose_action",
        )


def test_orchestrator_returns_paused_resumable_on_quota_interruption() -> None:
    sm = FakeSessionManager()
    session_id = "s-quota"
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_InterruptingAdapter(),
        session_manager=sm,
        session_id=session_id,
        run_artifact_ref=None,
        request_id_prefix="r-quota",
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(),
    )
    assert result.terminal_class == "paused"
    assert result.reason_code == "api_quota_exhausted"
    assert result.kernel_resume_snapshot is not None
    assert bool(result.runtime_state.get("resumable")) is True
