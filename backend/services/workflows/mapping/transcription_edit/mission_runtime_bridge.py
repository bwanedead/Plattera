from __future__ import annotations

import logging
from typing import Any, Callable

from agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest
from agent_kernel.session import KernelSessionManager
from harness.mission_runtime.contracts import MissionLedgerView, MissionRuntimeRequest
from harness.orchestration_kernel import KernelLoopResult, run_orchestration_kernel_loop
from harness.tracing.kernel_trace_persistence import persist_kernel_trace, persist_rationale_strip

from domains.mapping.transcript_edit.contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from domains.mapping.transcript_edit.domain_pack import (
    TranscriptEditDomainPack,
    build_transcript_edit_domain_pack_bundle,
)
from domains.mapping.transcript_edit.mission_mode_adapter import TranscriptEditModeAdapter
from .run_feed_persistence import write_transcript_edit_run_snapshot
from domains.mapping.transcript_edit.terminalization import terminal_message, terminal_summary

_LOG = logging.getLogger(__name__)


def build_transcript_edit_mode_adapter_from_controller_inputs(
    *,
    session_manager: KernelSessionManager,
    transcript_request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: Any | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> TranscriptEditModeAdapter:
    def _runner(
        _request: MissionRuntimeRequest,
        _ledger: MissionLedgerView,
    ) -> TranscriptEditAgentRunResult:
        return run_orchestration_kernel_transcript_loop(
            session_manager=session_manager,
            request=transcript_request,
            request_id_prefix=request_id_prefix,
            planner=planner,
            progress_cb=progress_cb,
        )

    return TranscriptEditModeAdapter(runner=_runner)


def run_orchestration_kernel_transcript_loop(
    *,
    session_manager: KernelSessionManager,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: Any | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    resume_feedback_response: dict[str, Any] | None = None,
) -> TranscriptEditAgentRunResult:
    max_steps = max(8, int(request.max_iterations) * 4)
    start_request = KernelSessionStartRequest(
        request_id=f"{request_id_prefix}-ok",
        goal=KernelGoal(
            requires_global_placement=False,
            render_required=False,
            objective="orchestration_kernel_transcript_edit",
        ),
        budgets=KernelBudgets(
            max_steps=max_steps,
            max_wall_time_seconds=600,
            max_retrieval_calls=100,
            max_semantic_calls=100,
            max_patch_calls=100,
        ),
        dossier_id=request.dossier_id,
        source_entry_ref=(f"final:{request.dossier_id}" if request.dossier_id else None),
        initial_graph_json={
            "graph_id": f"ok_tx_{request_id_prefix}",
            "nodes": [],
            "edges": [],
            "metadata": {
                "source": "orchestration_kernel_transcript_edit",
                "dossier_id": request.dossier_id,
            },
        },
    )
    start_result = session_manager.start_session(start_request)
    if start_result.refusal is not None or start_result.session_id is None:
        reason = start_result.refusal.reason_code if start_result.refusal else "missing_session"
        return TranscriptEditAgentRunResult(
            run_artifact_ref=None,
            session_id="",
            iterations=0,
            status="failed",
            reason_code=f"kernel_start_refused:{reason}",
            latest_refs={},
            review_required=True,
        )
    session_id = start_result.session_id
    run_artifact_ref = start_result.run_artifact_ref

    progress_events: list[dict[str, Any]] = []

    def _wrapped_progress_cb(event: dict[str, Any]) -> None:
        progress_events.append(dict(event))
        if progress_cb is not None:
            progress_cb(event)

    domain_pack = TranscriptEditDomainPack(
        request=request,
        session_id=session_id,
        request_id_prefix=request_id_prefix,
        planner=planner,
        progress_cb=_wrapped_progress_cb,
    )
    build_transcript_edit_domain_pack_bundle(domain_pack)
    kernel_result = run_orchestration_kernel_loop(
        domain_pack=domain_pack,
        session_manager=session_manager,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        request_id_prefix=request_id_prefix,
        dossier_id=request.dossier_id,
        max_iterations=int(request.max_iterations),
        max_no_progress_iterations=int(getattr(request, "max_no_progress_iterations", 3)),
        max_invalid_plan_attempts=int(request.max_invalid_plan_attempts),
        progress_cb=_wrapped_progress_cb,
        resume_hitl_response=resume_feedback_response,
    )

    trace_artifact_ref = persist_kernel_trace(
        kernel_result=kernel_result,
        request_id_prefix=request_id_prefix,
    )
    rationale_strip_artifact_ref = persist_rationale_strip(
        kernel_result=kernel_result,
        request_id_prefix=request_id_prefix,
        source_trace_artifact_ref=trace_artifact_ref,
    )
    enriched_latest_refs = dict(kernel_result.latest_refs)
    if trace_artifact_ref:
        enriched_latest_refs["trace_artifact_ref"] = trace_artifact_ref
    if rationale_strip_artifact_ref:
        enriched_latest_refs["rationale_strip_artifact_ref"] = rationale_strip_artifact_ref

    domain_state = domain_pack.build_domain_runtime_state()
    kernel_state = kernel_result.domain_runtime_state if isinstance(kernel_result.domain_runtime_state, dict) else {}
    merged_runtime_state = {**kernel_state, **domain_state}
    merged_runtime_state.setdefault(
        "apply_refusal_same_focus_streak",
        kernel_state.get("apply_refusal_same_focus_streak", 0),
    )
    merged_runtime_state.setdefault(
        "last_apply_refusal_focus_key",
        kernel_state.get("last_apply_refusal_focus_key"),
    )

    adapted = _adapt_kernel_loop_result(
        kernel_result,
        runtime_hitl_state=merged_runtime_state,
        latest_refs_override=enriched_latest_refs,
    )

    logical_run_id = (
        request_id_prefix if str(request_id_prefix).startswith("tx-agent-") else f"tx-agent-{request_id_prefix}"
    )
    request_id_for_feed = (
        str(request_id_prefix).removeprefix("tx-agent-")
        if str(request_id_prefix).startswith("tx-agent-")
        else str(request_id_prefix)
    )
    trace_ref: str | None = None
    latest_refs = adapted.latest_refs if isinstance(adapted.latest_refs, dict) else {}
    trace_payload = latest_refs.get("trace_artifact_ref")
    if isinstance(trace_payload, str) and trace_payload.strip():
        trace_ref = trace_payload.strip()
    elif isinstance(trace_payload, dict):
        artifact_path = str(trace_payload.get("artifact_path") or "").strip()
        trace_ref = artifact_path or None

    run_terminal_message = terminal_message(adapted)
    run_terminal_summary = terminal_summary(
        progress_events,
        adapted,
        critical_events=[],
        runtime_hitl_state=merged_runtime_state if isinstance(merged_runtime_state, dict) else None,
    )
    waiting_feedback = adapted.status == "waiting_feedback"
    final_status = "waiting_feedback" if waiting_feedback else adapted.status
    try:
        write_transcript_edit_run_snapshot(
            request_id=request_id_for_feed,
            run_id=logical_run_id,
            session_id=adapted.session_id,
            dossier_id=request.dossier_id,
            final_status=final_status,
            reason_code=adapted.reason_code,
            iterations=adapted.iterations,
            terminal_message=run_terminal_message,
            terminal_summary=run_terminal_summary,
            final_freshness_posture=run_terminal_summary.get("final_freshness_posture")
            if isinstance(run_terminal_summary.get("final_freshness_posture"), dict)
            else None,
            final_freshness_summary=str(run_terminal_summary.get("final_freshness_summary") or "").strip() or None,
            run_artifact_ref=adapted.run_artifact_ref,
            progress_log=list(progress_events),
            critical_events=[],
            trace_artifact_ref=trace_ref,
        )
    except Exception as exc:
        _LOG.warning(
            "TX_RUN_FEED_WRITE_FAILED ► logical_run_id=%s error_type=%s error=%s",
            logical_run_id,
            type(exc).__name__,
            str(exc)[:220],
        )

    return adapted


def _adapt_kernel_loop_result(
    result: KernelLoopResult,
    *,
    runtime_hitl_state: dict[str, Any] | None = None,
    latest_refs_override: dict[str, Any] | None = None,
) -> TranscriptEditAgentRunResult:
    terminal_class = result.terminal_class
    if terminal_class == "completed":
        status = "completed"
    elif terminal_class == "waiting_human":
        status = "waiting_feedback"
    elif terminal_class == "failed":
        status = "failed"
    else:
        status = "needs_review"

    review_required = not (status == "completed" and "auto_promote" in (result.reason_code or ""))
    if runtime_hitl_state is None:
        runtime_hitl_state = result.domain_runtime_state if isinstance(result.domain_runtime_state, dict) else {}
    latest_refs = latest_refs_override if latest_refs_override is not None else dict(result.latest_refs)

    return TranscriptEditAgentRunResult(
        run_artifact_ref=result.run_artifact_ref,
        session_id=result.session_id,
        iterations=result.iterations,
        status=status,
        reason_code=result.reason_code,
        latest_refs=latest_refs,
        review_required=review_required,
        runtime_hitl_state=runtime_hitl_state if runtime_hitl_state else None,
    )
