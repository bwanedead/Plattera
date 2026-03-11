from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_kernel.session import KernelSessionManager

from .contracts import TranscriptEditAgentRunRequest
from .iteration_repair_runtime import handle_clean_iteration as _handle_clean_iteration_impl
from .loop_state import TranscriptEditLoopState
from .result_policy import TranscriptEditDecision


def handle_clean_iteration(
    *,
    state: TranscriptEditLoopState,
    session_manager: KernelSessionManager,
    session_id: str,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    mode: str,
    promote_mode: str,
    min_iterations_before_complete: int,
    iterations: int,
    error_count: int,
    has_disagreements: bool,
    source_transcript_hash: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    model: str,
) -> TranscriptEditDecision | None:
    return _handle_clean_iteration_impl(
        state=state,
        session_manager=session_manager,
        session_id=session_id,
        request=request,
        request_id_prefix=request_id_prefix,
        mode=mode,
        promote_mode=promote_mode,
        min_iterations_before_complete=min_iterations_before_complete,
        iterations=iterations,
        error_count=error_count,
        has_disagreements=has_disagreements,
        source_transcript_hash=source_transcript_hash,
        progress_cb=progress_cb,
        model=model,
    )
