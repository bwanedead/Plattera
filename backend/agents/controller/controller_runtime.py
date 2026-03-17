"""Public controller runtime surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_kernel.models import KernelSessionStartRequest, TerminalOutcome
from agent_kernel.session import KernelSessionManager

from .controller_runtime_loop import _run_controller_loop_impl
from .tool_specs import ToolSpec


class NextStepLLMClient(Protocol):
    """LLM interface for proposing one controller step."""

    def propose_next_step(
        self,
        *,
        model: str,
        tools: list[ToolSpec],
        tool_choice_name: str | None,
        developer_message: str,
        user_message: str,
    ) -> dict[str, object]: ...


class IterationDigestClient(Protocol):
    """Cheap summarizer interface for compact per-iteration digest memory."""

    def summarize_iteration_digest(
        self,
        *,
        payload: dict[str, object],
        model: str = "gpt-5-mini",
    ) -> dict[str, object]: ...


class ControllerLoopError(RuntimeError):
    """Raised when controller runtime invariants are violated."""


@dataclass(frozen=True)
class ControllerRunResult:
    terminal: TerminalOutcome
    last_dashboard: dict[str, object]
    transcript_artifact_ref: str
    session_id: str | None
    run_artifact_ref: str | None
    iterations: int


def run_controller_loop(
    *,
    session_manager: KernelSessionManager,
    llm_client: NextStepLLMClient,
    start_request: KernelSessionStartRequest,
    model: str = "gpt-5-mini",
    max_iterations: int = 20,
    digest_client: IterationDigestClient | None = None,
) -> ControllerRunResult:
    import os as _os
    if not _os.environ.get("PLATTERA_ENABLE_LEGACY_CONTROLLERS"):
        raise RuntimeError(
            "run_controller_loop is a retired legacy entrypoint. "
            "Use run_orchestration_kernel_deed_loop instead. "
            "Set PLATTERA_ENABLE_LEGACY_CONTROLLERS=1 to temporarily re-enable for testing."
        )
    return _run_controller_loop_impl(
        session_manager=session_manager,
        llm_client=llm_client,
        start_request=start_request,
        model=model,
        max_iterations=max_iterations,
        digest_client=digest_client,
        controller_run_result_cls=ControllerRunResult,
        controller_loop_error_cls=ControllerLoopError,
    )
