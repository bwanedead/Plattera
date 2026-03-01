from __future__ import annotations

import hashlib
import json
from typing import Any

from agent_kernel.models import (
    ActionType,
    KernelBudgets,
    KernelGoal,
    KernelSessionStartRequest,
    KernelStepRequest,
    StepExecutionState,
)
from agent_kernel.session import KernelSessionManager
from transcript_edit.persistence import TranscriptionEditPersistenceService

from .contracts import TranscriptEditAgentRunRequest, TranscriptEditAgentRunResult
from .planner import TranscriptEditPlanPlanner
from .span_seeds import build_transcript_span_seeds_artifact, load_transcript_text_for_seeds

_MODE_OFF = "off"
_MODE_AUDIT_ONLY = "audit_only"
_MODE_AUDIT_REPAIR = "audit_then_repair"
_MODE_AUDIT_REPAIR_PROMOTE = "audit_then_repair_then_promote"


def run_transcript_edit_controller_loop(
    *,
    session_manager: KernelSessionManager,
    request: TranscriptEditAgentRunRequest,
    request_id_prefix: str,
    planner: TranscriptEditPlanPlanner | None = None,
) -> TranscriptEditAgentRunResult:
    if not request.source_transcript_ref and not request.source_text:
        raise ValueError("source_transcript_ref_or_source_text_required")
    mode = _normalized_mode(request.mode)
    if mode == _MODE_OFF:
        return TranscriptEditAgentRunResult(
            run_artifact_ref=None,
            session_id="",
            iterations=0,
            status="completed",
            reason_code="tx_agent_mode_off",
            latest_refs={},
            review_required=False,
        )
    start = session_manager.start_session(
        KernelSessionStartRequest(
            request_id=f"{request_id_prefix}-kernel",
            goal=KernelGoal(
                requires_global_placement=False,
                render_required=False,
                objective="transcript_edit_agent",
            ),
            budgets=KernelBudgets(
                max_steps=max(8, request.max_iterations * 4),
                max_wall_time_seconds=600,
                max_retrieval_calls=100,
                max_semantic_calls=100,
                max_patch_calls=100,
            ),
            dossier_id=request.dossier_id,
            source_entry_ref=(f"final:{request.dossier_id}" if request.dossier_id else None),
            initial_graph_json={
                "graph_id": f"tx_agent_{request_id_prefix}",
                "nodes": [],
                "edges": [],
                "metadata": {
                    "source": "transcript_edit_agent",
                    "dossier_id": request.dossier_id,
                },
            },
        )
    )
    if start.refusal is not None or start.session_id is None:
        raise RuntimeError(f"kernel_start_refused:{start.refusal.reason_code if start.refusal else 'missing_session'}")

    session_id = start.session_id
    latest_refs = start.dashboard.latest_refs.model_dump(mode="json") if start.dashboard else {}
    current_transcript_ref = request.source_transcript_ref
    planner_client = planner or TranscriptEditPlanPlanner()
    tx_persistence = TranscriptionEditPersistenceService()
    iterations = 0
    invalid_plan_strikes = 0
    no_progress_streak = 0
    previous_finding_signature: str | None = None
    applied_non_normalization = False
    applied_requires_review = False
    span_seeds_ref: str | None = None
    last_reason = "tx_agent_not_started"

    for iterations in range(1, request.max_iterations + 1):
        audit_inputs: dict[str, Any] = {"dossier_id": request.dossier_id}
        if current_transcript_ref:
            audit_inputs["source_transcript_ref"] = current_transcript_ref
        elif request.source_text:
            audit_inputs["source_text"] = request.source_text
        audit = _step(
            session_manager=session_manager,
            session_id=session_id,
            prefix="tx_audit",
            iteration=iterations,
            action_type=ActionType.TX_AUDIT_TRANSCRIPT,
            inputs=audit_inputs,
        )
        latest_refs = audit.dashboard.latest_refs.model_dump(mode="json")
        if audit.execution_state != StepExecutionState.EXECUTED:
            reason = audit.refusal.reason_code if audit.refusal is not None else "tx_audit_refused"
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="failed",
                reason=reason,
                latest_refs=latest_refs,
                review_required=True,
            )
        inline = _read_step_outputs_inline(audit.step_record)
        source_ref_candidate = _read_str(inline.get("tx_source_transcript_ref"))
        if source_ref_candidate:
            current_transcript_ref = source_ref_candidate
        finding_count = _read_int(inline.get("tx_findings_count"), 0)
        error_count = _read_int(inline.get("tx_error_findings_count"), 0)
        findings_summary = inline.get("tx_validator_summary") if isinstance(inline.get("tx_validator_summary"), dict) else {}
        top_findings = inline.get("tx_top_findings") if isinstance(inline.get("tx_top_findings"), list) else []
        source_transcript_hash = _read_str(inline.get("tx_source_transcript_hash")) or ""
        if not source_transcript_hash:
            source_transcript_hash = _read_str_from_latest_refs(latest_refs, "tx_source_transcript_ref") or ""

        finding_signature = _finding_signature(summary=findings_summary, findings=top_findings)
        if previous_finding_signature is not None and finding_signature == previous_finding_signature:
            no_progress_streak += 1
        else:
            no_progress_streak = 0
        previous_finding_signature = finding_signature

        if finding_count <= 0:
            if (
                request.dossier_id
                and current_transcript_ref
                and source_transcript_hash
                and error_count <= 0
            ):
                span_seeds_ref = _emit_transcript_span_seeds(
                    persistence=tx_persistence,
                    dossier_id=request.dossier_id,
                    source_transcript_ref=current_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                )
                if span_seeds_ref:
                    latest_refs["tx_span_seeds_ref"] = {"artifact_path": span_seeds_ref}
            should_promote = (
                mode == _MODE_AUDIT_REPAIR_PROMOTE
                and request.auto_promote
                and not applied_non_normalization
                and not applied_requires_review
                and error_count <= 0
            )
            if should_promote and current_transcript_ref:
                promote = _step(
                    session_manager=session_manager,
                    session_id=session_id,
                    prefix="tx_promote",
                    iteration=iterations,
                    action_type=ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
                    inputs={
                        "dossier_id": request.dossier_id,
                        "transcript_ref": current_transcript_ref,
                        "run_id": request_id_prefix,
                    },
                )
                latest_refs = promote.dashboard.latest_refs.model_dump(mode="json")
                if span_seeds_ref:
                    latest_refs["tx_span_seeds_ref"] = {"artifact_path": span_seeds_ref}
                if promote.execution_state != StepExecutionState.EXECUTED:
                    reason = promote.refusal.reason_code if promote.refusal is not None else "tx_promote_refused"
                    return _result(
                        start=start,
                        session_id=session_id,
                        iterations=iterations,
                        status="failed",
                        reason=reason,
                        latest_refs=latest_refs,
                        review_required=True,
                    )
                return _result(
                    start=start,
                    session_id=session_id,
                    iterations=iterations,
                    status="completed",
                    reason="tx_agent_clean_promoted",
                    latest_refs=latest_refs,
                    review_required=False,
                )
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="completed" if error_count <= 0 and not applied_requires_review else "needs_review",
                reason="tx_agent_clean_no_promote" if error_count <= 0 else "tx_agent_blocked_error_findings",
                latest_refs=latest_refs,
                review_required=(error_count > 0 or applied_requires_review or applied_non_normalization),
            )

        if mode == _MODE_AUDIT_ONLY:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_audit_only_findings_present",
                latest_refs=latest_refs,
                review_required=True,
            )

        if no_progress_streak >= request.max_no_progress_iterations:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_no_progress",
                latest_refs=latest_refs,
                review_required=True,
            )

        if not current_transcript_ref:
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason="tx_agent_missing_source_ref_for_planning",
                latest_refs=latest_refs,
                review_required=True,
            )

        span_context = _open_planner_context_spans(
            session_manager=session_manager,
            session_id=session_id,
            iteration=iterations,
            dossier_id=request.dossier_id,
            source_transcript_ref=current_transcript_ref,
            top_findings=top_findings,
        )
        manual_plan = request.edit_plan if isinstance(request.edit_plan, dict) else None
        if manual_plan is not None:
            plan_payload = manual_plan
            plan_reason = "manual_plan"
            raw_plan_text = json.dumps(manual_plan, ensure_ascii=False)
        else:
            plan, plan_reason, raw_plan_text = planner_client.propose_plan(
                model=request.model,
                source_transcript_ref=current_transcript_ref,
                source_transcript_hash=source_transcript_hash,
                findings_summary=findings_summary,
                top_findings=_coerce_findings(top_findings),
                span_context=span_context,
                max_attempts=request.max_invalid_plan_attempts,
            )
            plan_payload = plan.model_dump(mode="json") if plan is not None else None
            if plan_payload is None:
                invalid_plan_strikes += 1
                if invalid_plan_strikes >= request.max_invalid_plan_attempts:
                    return _result(
                        start=start,
                        session_id=session_id,
                        iterations=iterations,
                        status="needs_review",
                        reason=f"tx_agent_plan_invalid:{plan_reason}",
                        latest_refs=latest_refs,
                        review_required=True,
                    )
                continue
        apply = _step(
            session_manager=session_manager,
            session_id=session_id,
            prefix="tx_apply",
            iteration=iterations,
            action_type=ActionType.TX_APPLY_EDIT_PLAN,
            inputs={"dossier_id": request.dossier_id, "edit_plan": plan_payload},
        )
        latest_refs = apply.dashboard.latest_refs.model_dump(mode="json")
        if apply.execution_state != StepExecutionState.EXECUTED:
            reason = apply.refusal.reason_code if apply.refusal is not None else "tx_apply_refused"
            return _result(
                start=start,
                session_id=session_id,
                iterations=iterations,
                status="needs_review",
                reason=reason,
                latest_refs=latest_refs,
                review_required=True,
            )
        apply_inline = _read_step_outputs_inline(apply.step_record)
        edited_ref = _read_str(apply_inline.get("tx_edited_transcript_ref"))
        if edited_ref:
            current_transcript_ref = edited_ref
        plan_cc = _max_change_class_from_plan(plan_payload or {})
        if plan_cc in {"semantic", "structural"}:
            applied_non_normalization = True
        if _plan_has_review_required(plan_payload or {}):
            applied_requires_review = True
        if manual_plan is None:
            invalid_plan_strikes = 0
        last_reason = plan_reason if plan_reason else "tx_apply_completed"
        if raw_plan_text:
            _ = raw_plan_text  # retain variable for debugging parity without expanding artifacts

    return _result(
        start=start,
        session_id=session_id,
        iterations=iterations,
        status="needs_review",
        reason=last_reason if last_reason != "tx_agent_not_started" else "tx_agent_max_iterations_reached",
        latest_refs=latest_refs,
        review_required=True,
    )


def _step(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    prefix: str,
    iteration: int,
    action_type: ActionType,
    inputs: dict[str, Any],
):
    return session_manager.step(
        KernelStepRequest(
            session_id=session_id,
            idempotency_key=_idempotency_key(prefix, iteration, inputs),
            action_type=action_type,
            inputs=inputs,
        )
    )


def _open_planner_context_spans(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for finding in top_findings[:5]:
        if not isinstance(finding, dict):
            continue
        span = finding.get("span")
        if isinstance(span, dict):
            start = span.get("start_char")
            end = span.get("end_char")
            if isinstance(start, int) and isinstance(end, int) and end > start:
                spans.append({"start_char": max(0, start - 100), "end_char": end + 100, "span_id": finding.get("finding_id")})
    step = _step(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_open_spans",
        iteration=iteration,
        action_type=ActionType.TX_OPEN_TRANSCRIPT_SPANS,
        inputs={
            "dossier_id": dossier_id,
            "source_transcript_ref": source_transcript_ref,
            "spans": spans,
            "max_chars_per_span": 1400,
            "max_total_chars": 5000,
        },
    )
    if step.execution_state != StepExecutionState.EXECUTED:
        return []
    inline = _read_step_outputs_inline(step.step_record)
    raw_spans = inline.get("spans")
    if isinstance(raw_spans, list):
        return [s for s in raw_spans[:8] if isinstance(s, dict)]
    return []


def _result(
    *,
    start,
    session_id: str,
    iterations: int,
    status: str,
    reason: str,
    latest_refs: dict[str, Any],
    review_required: bool,
) -> TranscriptEditAgentRunResult:
    return TranscriptEditAgentRunResult(
        run_artifact_ref=start.run_artifact_ref,
        session_id=session_id,
        iterations=iterations,
        status=status,
        reason_code=reason,
        latest_refs=latest_refs,
        review_required=review_required,
    )


def _normalized_mode(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {_MODE_OFF, _MODE_AUDIT_ONLY, _MODE_AUDIT_REPAIR, _MODE_AUDIT_REPAIR_PROMOTE}:
        return value
    return _MODE_AUDIT_REPAIR_PROMOTE


def _idempotency_key(prefix: str, iteration: int, inputs: dict[str, Any]) -> str:
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{iteration:02d}-{digest}"


def _read_step_outputs_inline(step_record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(step_record, dict):
        return {}
    outputs_inline = step_record.get("outputs_inline")
    if isinstance(outputs_inline, dict):
        return outputs_inline
    return {}


def _read_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_findings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in values[:12]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "finding_id": item.get("finding_id"),
                "finding_type": item.get("finding_type"),
                "severity": item.get("severity"),
                "message": item.get("message"),
                "section_id": item.get("section_id"),
                "span": item.get("span"),
            }
        )
    return out


def _finding_signature(*, summary: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    payload = {
        "summary": summary,
        "findings": [
            {
                "finding_id": f.get("finding_id"),
                "severity": f.get("severity"),
                "finding_type": f.get("finding_type"),
            }
            for f in findings[:8]
            if isinstance(f, dict)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _max_change_class_from_plan(plan: dict[str, Any]) -> str:
    ops = plan.get("ops")
    if not isinstance(ops, list):
        return "normalization"
    rank = {"normalization": 0, "semantic": 1, "structural": 2}
    highest = 0
    for op in ops:
        if not isinstance(op, dict):
            continue
        cc = str(op.get("change_class") or "").strip().lower()
        highest = max(highest, rank.get(cc, 0))
    for key, value in rank.items():
        if value == highest:
            return key
    return "normalization"


def _plan_has_review_required(plan: dict[str, Any]) -> bool:
    flags = plan.get("global_flags")
    if isinstance(flags, dict) and bool(flags.get("review_required")):
        return True
    ops = plan.get("ops")
    if isinstance(ops, list):
        for op in ops:
            if isinstance(op, dict) and bool(op.get("review_required")):
                return True
    return False


def _read_str_from_latest_refs(latest_refs: dict[str, Any], key: str) -> str | None:
    value = latest_refs.get(key)
    if isinstance(value, dict):
        path = value.get("artifact_path")
        return _read_str(path)
    return _read_str(value)


def _emit_transcript_span_seeds(
    *,
    persistence: TranscriptionEditPersistenceService,
    dossier_id: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
) -> str | None:
    transcript_text = load_transcript_text_for_seeds(source_transcript_ref)
    if not transcript_text:
        return None
    artifact = build_transcript_span_seeds_artifact(
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        transcript_text=transcript_text,
    )
    if not artifact.seeds:
        return None
    try:
        return persistence.save_transcript_span_seeds(dossier_id=dossier_id, artifact=artifact)
    except Exception:
        # Seeds are advisory only; failure here must not fail the controller loop.
        return None
