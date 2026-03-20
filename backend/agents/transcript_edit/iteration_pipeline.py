"""Stable public facade for transcript-edit per-iteration handlers (controller entrypoint).

``handle_clean_iteration`` / ``handle_repair_iteration`` delegate to ``iteration_repair_runtime`` (clean path
no longer hops through a separate clean-flow module — Phase 19).

``_sync_repair_runtime_seams`` exists so tests can monkeypatch symbols on **this** module while repair
implementation lives in ``iteration_repair_runtime`` / ``iteration_repair_moves`` — keep that seam.

**Canonical kernel:** import ``KernelSessionManager`` from the ``agent_kernel`` package (not ``run_kernel``).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_kernel import KernelSessionManager
from transcript_edit.persistence import TranscriptionEditPersistenceService

from .contracts import TranscriptEditAgentRunRequest
from .hitl_feedback import build_human_feedback_prompt, poll_feedback_response
from .iteration_repair_focus import _select_focus_decision_key, _select_focus_target
from .iteration_repair_moves import (
    _open_planner_context_spans,
    _run_image_evidence_mode,
    _verify_mapping_critical_with_image,
)
from .iteration_repair_runtime import handle_clean_iteration as _handle_clean_iteration_impl
from .iteration_repair_runtime import handle_repair_iteration as _handle_repair_iteration_impl
from .iteration_repair_runtime import (
    _accept_apply_edit_plan,
    _accept_mark_blocked,
    _accept_mark_resolved_no_edit,
    _accept_request_human_feedback,
    _findings_for_focus_key,
    _image_verify_runtime_config,
)
from .loop_state import TranscriptEditLoopState
from .planner import TranscriptEditPlanPlanner
from .result_policy import TranscriptEditDecision


def _sync_repair_runtime_seams() -> None:
    # Compatibility seam: tests monkeypatch symbols on iteration_pipeline.
    from . import iteration_repair_runtime as runtime
    from . import iteration_repair_moves as moves

    runtime.poll_feedback_response = poll_feedback_response
    runtime.build_human_feedback_prompt = build_human_feedback_prompt
    runtime._select_focus_target = _select_focus_target
    runtime._select_focus_decision_key = _select_focus_decision_key
    runtime._open_planner_context_spans = _open_planner_context_spans
    runtime._verify_mapping_critical_with_image = _verify_mapping_critical_with_image
    runtime._run_image_evidence_mode = _run_image_evidence_mode
    moves._open_planner_context_spans = _open_planner_context_spans
    moves._verify_mapping_critical_with_image = _verify_mapping_critical_with_image
    moves._run_image_evidence_mode = _run_image_evidence_mode


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


def handle_repair_iteration(
    *,
    state: TranscriptEditLoopState,
    session_manager: KernelSessionManager,
    session_id: str,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    iterations: int,
    planner_client: TranscriptEditPlanPlanner,
    tx_persistence: TranscriptionEditPersistenceService,
    planning_findings: list[dict[str, Any]],
    top_findings: list[dict[str, Any]],
    findings_summary: dict[str, Any],
    source_transcript_hash: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    model: str,
    validation_mode: str,
) -> TranscriptEditDecision | None:
    _sync_repair_runtime_seams()
    return _handle_repair_iteration_impl(
        state=state,
        session_manager=session_manager,
        session_id=session_id,
        request=request,
        request_id_prefix=request_id_prefix,
        iterations=iterations,
        planner_client=planner_client,
        tx_persistence=tx_persistence,
        planning_findings=planning_findings,
        top_findings=top_findings,
        findings_summary=findings_summary,
        source_transcript_hash=source_transcript_hash,
        progress_cb=progress_cb,
        model=model,
        validation_mode=validation_mode,
    )


__all__ = [
    "handle_clean_iteration",
    "handle_repair_iteration",
    "build_human_feedback_prompt",
    "poll_feedback_response",
    "_select_focus_target",
    "_select_focus_decision_key",
    "_accept_mark_resolved_no_edit",
    "_accept_mark_blocked",
    "_accept_request_human_feedback",
    "_accept_apply_edit_plan",
    "_image_verify_runtime_config",
    "_findings_for_focus_key",
    "_open_planner_context_spans",
    "_verify_mapping_critical_with_image",
    "_run_image_evidence_mode",
]
