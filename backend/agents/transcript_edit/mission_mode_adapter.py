from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contracts import TranscriptEditAgentRunResult
from .terminal_taxonomy import classify_transcript_edit_terminal
from harness.mission_runtime.contracts import (
    MissionBlockerPostureSummary,
    MissionLedgerView,
    MissionModeAdapter,
    MissionModeRunEnvelope,
    MissionResumabilitySummary,
    MissionRuntimeRequest,
    MissionVerificationPostureSummary,
    ModeCycleContext,
    ModeInterpretation,
    ModeRecommendation,
    TerminalRecommendation,
)
from harness.mission_runtime.mapping_family import build_mapping_family_coordination

TRANSCRIPT_EDIT_MODE_NAME = "transcript_edit"


@dataclass(frozen=True)
class _TranscriptAuthoritySnapshot:
    waiting_feedback: bool
    pending_feedback_prompt_id: str | None
    open_blocker_count: int | None
    unresolved_closure_count: int
    closure_blocking: bool
    verification_status: str
    verification_kind: str
    terminal_classification: str | None


class TranscriptEditModeAdapter(MissionModeAdapter):
    mode_name = TRANSCRIPT_EDIT_MODE_NAME

    def __init__(
        self,
        *,
        runner: Callable[[MissionRuntimeRequest, MissionLedgerView], TranscriptEditAgentRunResult],
    ) -> None:
        self._runner = runner

    def build_context(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
    ) -> ModeCycleContext:
        return ModeCycleContext(
            payload={},
            execution_adapter=lambda: self._runner(request, ledger),
        )

    def build_run_envelope(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> MissionModeRunEnvelope:
        result = _require_transcript_result(context)
        interpretation, recommendation = adapt_transcript_edit_run_result(result)
        coordination = build_mapping_family_coordination(
            current_mode=TRANSCRIPT_EDIT_MODE_NAME,
            handoff_posture=result.handoff_posture,
            terminal=recommendation.terminal,
            transition_allowed=_metadata_flag(request.metadata, "phase_e_enable_linear_transitions")
            and _metadata_flag(request.metadata, "transcript_edit_transition_to_deed_to_ir"),
            handed_forward_artifact_refs=_curate_tx_to_deed_handoff_refs(result, recommendation),
            resume_note_for_prior_mode="return to transcript_edit only if new closure blockers emerge",
        )
        domain_payload: dict[str, Any] = {
            "mode": TRANSCRIPT_EDIT_MODE_NAME,
            "status": result.status,
            "reason_code": result.reason_code,
            "iterations": result.iterations,
            "session_id": result.session_id,
            "run_artifact_ref": result.run_artifact_ref,
            "latest_refs": dict(result.latest_refs),
        }
        if isinstance(result.handoff_posture, dict):
            domain_payload["handoff_posture"] = dict(result.handoff_posture)
        return MissionModeRunEnvelope(
            summary=interpretation.summary,
            high_signal_artifact_refs=tuple(recommendation.high_signal_artifact_refs),
            blocker_posture=recommendation.blocker_posture,
            verification_posture=recommendation.verification_posture,
            resumability=recommendation.resumability,
            terminal=recommendation.terminal,
            transition=coordination.transition_recommendation,
            family_coordination=coordination,
            domain_payload=domain_payload,
        )

    def interpret(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> ModeInterpretation:
        del request
        del ledger
        envelope = _require_transcript_run_envelope(context)
        return ModeInterpretation(summary=envelope.summary, details=dict(envelope.domain_payload))

    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation:
        del request
        del ledger
        del interpretation
        envelope = _require_transcript_run_envelope(context)
        recommendation = ModeRecommendation(
            terminal=envelope.terminal,
            high_signal_artifact_refs=list(envelope.high_signal_artifact_refs),
            blocker_posture=envelope.blocker_posture,
            verification_posture=envelope.verification_posture,
            resumability=envelope.resumability,
        )
        if envelope.transition is None:
            return recommendation
        return ModeRecommendation(
            transition=envelope.transition,
            terminal=recommendation.terminal,
            high_signal_artifact_refs=list(recommendation.high_signal_artifact_refs),
            blocker_posture=recommendation.blocker_posture,
            verification_posture=recommendation.verification_posture,
            resumability=recommendation.resumability,
        )


def adapt_transcript_edit_run_result(
    result: TranscriptEditAgentRunResult,
) -> tuple[ModeInterpretation, ModeRecommendation]:
    return (
        interpret_transcript_edit_run_result(result),
        recommend_transcript_edit_run_result(result),
    )


def interpret_transcript_edit_run_result(result: TranscriptEditAgentRunResult) -> ModeInterpretation:
    authority = _authority_snapshot(result)
    terminal_result = classify_transcript_edit_terminal(
        status=result.status,
        reason_code=result.reason_code,
        terminal_classification=authority.terminal_classification,
        human_feedback_pending=authority.waiting_feedback,
    )
    return ModeInterpretation(
        summary=f"transcript_edit_cycle:{terminal_result.terminal_class}",
        details={
            "mode": TRANSCRIPT_EDIT_MODE_NAME,
            "status": result.status,
            "terminal_class": terminal_result.terminal_class,
            "reason_code": result.reason_code,
            "iterations": result.iterations,
            "session_id": result.session_id,
            "run_artifact_ref": result.run_artifact_ref,
            "waiting_feedback": authority.waiting_feedback,
            "closure_blocking": authority.closure_blocking,
            "unresolved_closure_count": authority.unresolved_closure_count,
        },
    )


def recommend_transcript_edit_run_result(result: TranscriptEditAgentRunResult) -> ModeRecommendation:
    authority = _authority_snapshot(result)
    terminal_result = classify_transcript_edit_terminal(
        status=result.status,
        reason_code=result.reason_code,
        terminal_classification=authority.terminal_classification,
        human_feedback_pending=authority.waiting_feedback,
    )
    return ModeRecommendation(
        terminal=TerminalRecommendation(
            terminal=True,
            terminal_class=terminal_result.terminal_class,
            reason_code=result.reason_code,
        ),
        high_signal_artifact_refs=_collect_high_signal_refs(result),
        blocker_posture=MissionBlockerPostureSummary(
            waiting_human=authority.waiting_feedback,
            open_blocker_count=authority.open_blocker_count,
        ),
        verification_posture=MissionVerificationPostureSummary(
            status=authority.verification_status,
            last_verification_kind=authority.verification_kind,
        ),
        resumability=MissionResumabilitySummary(
            resumable=authority.waiting_feedback,
            resume_reason="waiting_human_feedback" if authority.waiting_feedback else None,
            resume_requirements=(
                [authority.pending_feedback_prompt_id] if authority.pending_feedback_prompt_id else []
            ),
        ),
    )


def _authority_snapshot(result: TranscriptEditAgentRunResult) -> _TranscriptAuthoritySnapshot:
    runtime_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
    summary = (
        dict(runtime_state.get("mission_runtime_summary"))
        if isinstance(runtime_state.get("mission_runtime_summary"), dict)
        else {}
    )
    waiting_feedback = bool(summary.get("waiting_feedback"))
    pending_feedback_prompt_id = str(summary.get("pending_feedback_prompt_id") or "").strip() or None
    open_blocker_count = summary.get("open_blocker_count")
    unresolved_closure_count = int(summary.get("unresolved_closure_count") or 0)
    closure_blocking = bool(summary.get("closure_blocking"))
    verification_status = _normalize_verification_status(
        summary.get("verification_status"), closure_blocking, unresolved_closure_count
    )
    verification_kind = str(summary.get("verification_kind") or "").strip() or "transcript_edit_closure_ledger"
    terminal_classification = str(summary.get("terminal_classification") or "").strip() or None

    if not summary:
        waiting_feedback = bool(runtime_state.get("waiting_feedback"))
        pending_feedback_prompt_id = str(runtime_state.get("pending_feedback_prompt_id") or "").strip() or None

    return _TranscriptAuthoritySnapshot(
        waiting_feedback=waiting_feedback,
        pending_feedback_prompt_id=pending_feedback_prompt_id,
        open_blocker_count=int(open_blocker_count) if isinstance(open_blocker_count, int) else None,
        unresolved_closure_count=unresolved_closure_count,
        closure_blocking=closure_blocking,
        verification_status=verification_status,
        verification_kind=verification_kind,
        terminal_classification=terminal_classification,
    )


def _collect_high_signal_refs(result: TranscriptEditAgentRunResult) -> list[str]:
    refs: list[str] = []
    if isinstance(result.run_artifact_ref, str) and result.run_artifact_ref.strip():
        refs.append(result.run_artifact_ref.strip())
    latest_refs = result.latest_refs if isinstance(result.latest_refs, dict) else {}
    for payload in latest_refs.values():
        if isinstance(payload, dict):
            for key in ("artifact_ref", "artifact_path", "ref", "path"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    refs.append(value.strip())
        elif isinstance(payload, str) and payload.strip():
            refs.append(payload.strip())
    deduped: list[str] = []
    for value in refs:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _normalize_verification_status(
    value: Any,
    closure_blocking: bool,
    unresolved_closure_count: int,
) -> str:
    text = str(value or "").strip().lower()
    if text in {"closure_blocking", "closure_partial", "closure_clear"}:
        return text
    if closure_blocking:
        return "closure_blocking"
    if unresolved_closure_count > 0:
        return "closure_partial"
    return "closure_clear"


def _curate_tx_to_deed_handoff_refs(
    result: TranscriptEditAgentRunResult,
    recommendation: ModeRecommendation,
) -> list[str]:
    refs: list[str] = []
    latest_refs = result.latest_refs if isinstance(result.latest_refs, dict) else {}
    trace_ref = latest_refs.get("trace_artifact_ref")
    if isinstance(trace_ref, str) and trace_ref.strip():
        refs.append(trace_ref.strip())
    if isinstance(result.run_artifact_ref, str) and result.run_artifact_ref.strip():
        refs.append(result.run_artifact_ref.strip())
    for payload in latest_refs.values():
        if isinstance(payload, dict):
            for key in ("artifact_ref", "artifact_path", "ref", "path"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip() and "transcript" in value.lower():
                    if value.strip() not in refs:
                        refs.append(value.strip())
        elif isinstance(payload, str) and payload.strip() and "transcript" in payload.lower():
            if payload.strip() not in refs:
                refs.append(payload.strip())
    if refs:
        return refs
    return list(recommendation.high_signal_artifact_refs)


def _metadata_flag(metadata: Any, key: str) -> bool:
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get(key))


def _require_transcript_result(context: ModeCycleContext) -> TranscriptEditAgentRunResult:
    result = context.execution_result
    if isinstance(result, TranscriptEditAgentRunResult):
        return result
    raise ValueError("transcript_edit_mode_context_missing_execution_result")


def _require_transcript_run_envelope(context: ModeCycleContext) -> MissionModeRunEnvelope:
    envelope = context.run_envelope
    if isinstance(envelope, MissionModeRunEnvelope):
        return envelope
    raise ValueError("transcript_edit_mode_context_missing_run_envelope")
