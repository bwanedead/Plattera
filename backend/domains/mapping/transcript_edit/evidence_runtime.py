from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_kernel.models import StepExecutionState

from .execution_action_ids import TX_VERIFY_TRANSCRIPT_WITH_IMAGE
from agent_kernel.session import KernelSessionManager

from .context_spans import open_planner_context_spans
from .image_verification import verify_mapping_critical_with_image
from .loop_runtime import emit_progress
from .loop_state import TranscriptEditLoopState
from services.workflows.mapping.transcription_edit.run_reporting import image_verify_progress_payload


def open_planner_context_spans_adapter(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
    step_fn,
    read_step_outputs_inline_fn,
) -> list[dict[str, Any]]:
    return open_planner_context_spans(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        step_fn=step_fn,
        read_step_outputs_inline_fn=read_step_outputs_inline_fn,
    )


def verify_mapping_critical_with_image_adapter(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
    source_image_refs: list[str],
    model: str,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    focus_decision_key: str | None,
    llm_call_seq_start: int,
    validation_mode: str,
    step_fn,
    read_step_outputs_inline_fn,
    read_str_fn,
) -> dict[str, Any]:
    verify_runtime = image_verify_runtime_config(validation_mode)

    def _emit_check_progress(update: dict[str, Any]) -> None:
        check_index = int(update.get("check_index") or 0)
        check_total = int(update.get("check_total") or 0)
        check_id = str(update.get("check_id") or "").strip() or "unknown_check"
        stage = str(update.get("stage") or "running")
        elapsed_seconds = int(update.get("elapsed_seconds") or 0)
        llm_call_seq = int(update.get("llm_call_seq") or 0)
        phase_attempt = int(update.get("phase_attempt") or 1)
        wait_reason = str(update.get("wait_reason") or "").strip().lower() or None
        phase_started_at_epoch_seconds = int(update.get("phase_started_at_epoch_seconds") or 0) or None
        timeout_seconds = int(update.get("timeout_seconds") or 0) or None
        max_attempts_per_check = int(update.get("max_attempts_per_check") or 0) or None
        check_decision_key = str(update.get("check_decision_key") or "").strip().lower() or None
        focus_key = str(update.get("focus_decision_key") or focus_decision_key or "").strip().lower() or None
        emit_progress(
            progress_cb,
            image_verify_progress_payload(
                iteration=iteration,
                decision_key=focus_key,
                evidence_kind="image_verify",
                check_id=f"{check_index}/{check_total}:{check_id}",
                check_decision_key=check_decision_key,
                llm_call_seq=llm_call_seq,
                phase_attempt=phase_attempt,
                stage=stage,
                elapsed_seconds=elapsed_seconds,
                wait_reason=wait_reason,
                phase_started_at_epoch_seconds=phase_started_at_epoch_seconds,
                timeout_seconds=timeout_seconds,
                max_attempts_per_check=max_attempts_per_check,
                check_index=int(update.get("check_index") or 0),
                check_total=int(update.get("check_total") or 0),
                diagnostic=(update.get("diagnostic") if isinstance(update.get("diagnostic"), dict) else None),
                latest_refs={},
            ),
        )

    return verify_mapping_critical_with_image(
        session_manager=session_manager,
        session_id=session_id,
        iteration=iteration,
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        top_findings=top_findings,
        disagreement_hints={},
        source_image_refs=source_image_refs,
        model=model,
        step_fn=step_fn,
        read_step_outputs_inline_fn=read_step_outputs_inline_fn,
        read_str_fn=read_str_fn,
        progress_cb=_emit_check_progress,
        focus_decision_key=focus_decision_key,
        llm_call_seq_start=llm_call_seq_start,
        max_checks=int(verify_runtime.get("max_checks") or 4),
        step_timeout_seconds=int(verify_runtime.get("step_timeout_seconds") or 240),
        max_attempts_per_check=int(verify_runtime.get("max_attempts_per_check") or 2),
        heartbeat_thresholds_seconds=tuple(verify_runtime.get("heartbeat_thresholds_seconds") or (15, 30, 60)),
        heartbeat_every_seconds=int(verify_runtime.get("heartbeat_every_seconds") or 60),
    )


def run_image_evidence_mode(
    *,
    normalized_request: dict[str, Any],
    session_manager: KernelSessionManager,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    source_image_refs: list[str],
    model: str,
    focus_decision_key: str | None,
    top_findings: list[dict[str, Any]],
    llm_call_seq_start: int,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    latest_visual_evidence: dict[str, Any] | None,
    step_fn,
    read_step_outputs_inline_fn,
) -> dict[str, Any]:
    mode = str(normalized_request.get("mode") or "").strip().lower()
    if mode == "verify":
        mode = "verify_region"
    target = normalized_request.get("target") if isinstance(normalized_request.get("target"), dict) else {}
    requested_selector_type = selector_type_from_target(target)
    decision_key = str(normalized_request.get("decision_key") or focus_decision_key or "").strip().lower()
    source_image_ref = str(target.get("source_image_ref") or "").strip()
    if not source_image_ref and isinstance(source_image_refs, list) and source_image_refs:
        source_image_ref = str(source_image_refs[0] or "").strip()
    if not source_transcript_ref or not source_image_ref:
        return {"mode": mode, "status": "invalid", "reason": "image_evidence_missing_source_inputs"}

    expected_fields = [
        str(v).strip().lower()
        for v in list(target.get("expected_fields") or [])
        if str(v).strip()
    ][:6]
    query = str(target.get("query") or "").strip()
    if not query:
        query = str(target.get("anchor_hint") or "").strip()
    if not query:
        query = str(((top_findings or [{}])[0] or {}).get("message") or "").strip()
    if not query:
        query = f"Inspect evidence for {decision_key or 'focused decision'}."
    expected_text = str(target.get("expected_text") or "").strip()
    if not expected_text and expected_fields:
        expected_text = ", ".join(expected_fields[:2])

    region_ref = coerce_artifact_ref_for_state(target.get("region_ref"))
    if mode in {"verify_region", "refine_region"} and region_ref is None and isinstance(latest_visual_evidence, dict):
        region_ref = coerce_artifact_ref_for_state(latest_visual_evidence.get("tx_image_evidence_region_ref"))

    check_id = f"{decision_key or 'focus'}:{mode or 'mode'}"
    check = {
        "check_id": check_id,
        "type": "mapping_critical",
        "query": query[:320],
        "expected_text": expected_text[:180] or None,
        "decision_key": decision_key or None,
    }
    emit_progress(
        progress_cb,
        image_verify_progress_payload(
            iteration=iteration,
            decision_key=decision_key or None,
            evidence_kind=f"image_evidence:{mode}",
            check_id=check_id,
            check_decision_key=decision_key or None,
            llm_call_seq=int(llm_call_seq_start) + 1,
            phase_attempt=1,
            stage="running",
            elapsed_seconds=0,
            wait_reason="awaiting_image_evidence_step_response",
            latest_refs={},
        ),
    )
    step = step_fn(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_image_evidence",
        iteration=iteration,
        action_type=TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
        inputs={
            "dossier_id": dossier_id,
            "source_transcript_ref": source_transcript_ref,
            "image_ref": source_image_ref,
            "model": model,
            "mode": mode,
            "target": {
                "region_ref": region_ref,
                "query": query[:320],
                "expected_text": expected_text[:180] or None,
                "expected_fields": expected_fields,
                "anchor_hint": str(target.get("anchor_hint") or "").strip()[:220] or None,
                "crop_box_pixels": (
                    dict(target.get("crop_box_pixels"))
                    if isinstance(target.get("crop_box_pixels"), dict)
                    else None
                ),
                "crop_box_normalized": (
                    dict(target.get("crop_box_normalized"))
                    if isinstance(target.get("crop_box_normalized"), dict)
                    else None
                ),
                "grid_selection": (
                    dict(target.get("grid_selection"))
                    if isinstance(target.get("grid_selection"), dict)
                    else None
                ),
                "grid_spec": (
                    dict(target.get("grid_spec"))
                    if isinstance(target.get("grid_spec"), dict)
                    else None
                ),
                "zoom_factor": target.get("zoom_factor"),
                "transform": str(target.get("transform") or "").strip().lower() or None,
                "amount": target.get("amount"),
                "decision_key": decision_key or None,
                "check_id": check_id,
            },
            "checks": [check] if mode == "locate" else None,
            "decision_key": decision_key or None,
        },
    )
    latest_refs = step.dashboard.latest_refs.model_dump(mode="json")
    if step.execution_state != StepExecutionState.EXECUTED:
        refusal = step.refusal.reason_code if step.refusal is not None else "tx_image_evidence_refused"
        return {"mode": mode, "status": "failed", "reason": refusal, "latest_refs": latest_refs}
    inline = read_step_outputs_inline_fn(step.step_record)
    summary = inline.get("tx_image_verify_summary") if isinstance(inline.get("tx_image_verify_summary"), dict) else {}
    results = inline.get("tx_image_verify_results") if isinstance(inline.get("tx_image_verify_results"), list) else []
    results = [dict(row) for row in results if isinstance(row, dict)]
    first = dict(results[0]) if results else {}
    selected_crop = inline.get("crop_box") if isinstance(inline.get("crop_box"), dict) else None
    selected_zoom = inline.get("zoom_factor")
    lineage = inline.get("tx_image_region_lineage") if isinstance(inline.get("tx_image_region_lineage"), dict) else {}
    inspection_ref = inline.get("tx_image_inspection_ref") if isinstance(inline.get("tx_image_inspection_ref"), dict) else None
    region = coerce_artifact_ref_for_state(
        first.get("tx_image_evidence_region_ref") or inline.get("tx_image_evidence_region_ref")
    )
    context = coerce_artifact_ref_for_state(
        first.get("tx_image_evidence_context_ref") or inline.get("tx_image_evidence_context_ref")
    )
    locator = first.get("locator") if isinstance(first.get("locator"), dict) else {}
    visual_evidence = {
        "mode": mode,
        "status": str(first.get("status") or "executed").strip().lower() or "executed",
        "check_id": str(first.get("check_id") or check.get("check_id") or "").strip() or None,
        "decision_key": decision_key or None,
        "query": str(first.get("query") or check.get("query") or "").strip()[:320] or None,
        "expected_text": str(check.get("expected_text") or "").strip()[:180] or None,
        "observed_text": str(first.get("observed_text") or "").strip()[:220] or None,
        "locator": {
            "status": str(locator.get("status") or "").strip().lower() or None,
            "confidence": str(locator.get("confidence") or "").strip().lower() or None,
            "reason": str(locator.get("reason") or "").strip()[:220] or None,
        },
        "tx_image_evidence_region_ref": region,
        "tx_image_evidence_context_ref": context,
        "verify_summary": dict(summary),
        "crop_box": selected_crop,
        "zoom_factor": selected_zoom,
        "inspection_ref": inspection_ref,
        "region_lineage": lineage,
        "tx_image_region_lineage_ref": coerce_artifact_ref_for_state(inline.get("tx_image_region_lineage_ref")),
        "image_width": inline.get("image_width"),
        "image_height": inline.get("image_height"),
        "grid_spec": (dict(inline.get("grid_spec")) if isinstance(inline.get("grid_spec"), dict) else None),
        "grid_overlay_ref": coerce_artifact_ref_for_state(inline.get("grid_overlay_ref")),
        "selector_type": (
            str(inline.get("selector_type") or "").strip().lower()
            or str(lineage.get("selector_type") or "").strip().lower()
            or (requested_selector_type if mode == "select_region" else None)
        ),
        "source_image_path": str(lineage.get("source_image_path") or "").strip() or None,
        "latest_refs": latest_refs,
        "llm_call_seq_end": int(llm_call_seq_start) + 1,
    }
    image_verification = {}
    if mode == "verify_region":
        image_verification = {
            "latest_refs": latest_refs,
            "llm_call_seq_end": int(llm_call_seq_start) + 1,
            "payload": {
                "summary": dict(summary),
                "results": results,
                "diagnostics": [],
            },
        }
    return {
        "mode": mode,
        "status": "executed",
        "reason": f"image_evidence_{mode}_executed",
        "latest_refs": latest_refs,
        "llm_call_seq_end": int(llm_call_seq_start) + 1,
        "image_evidence": visual_evidence,
        "image_verification": image_verification,
    }


def image_verify_runtime_config(validation_mode: str | None) -> dict[str, Any]:
    mode = str(validation_mode or "").strip().lower()
    if mode == "live_hitl":
        return {
            "max_checks": 1,
            "step_timeout_seconds": 90,
            "max_attempts_per_check": 1,
            "heartbeat_thresholds_seconds": (10, 20, 30, 60),
            "heartbeat_every_seconds": 30,
        }
    return {
        "max_checks": 4,
        "step_timeout_seconds": 240,
        "max_attempts_per_check": 2,
        "heartbeat_thresholds_seconds": (15, 30, 60),
        "heartbeat_every_seconds": 60,
    }


def selector_type_from_target(target: dict[str, Any]) -> str | None:
    if isinstance(target.get("crop_box_normalized"), dict):
        return "normalized_box"
    if isinstance(target.get("crop_box_pixels"), dict):
        return "pixel_box"
    if isinstance(target.get("grid_selection"), dict):
        return "grid_selection"
    return None


def evidence_request_mode_hint(evidence_request: dict[str, Any] | None) -> str | None:
    if not isinstance(evidence_request, dict):
        return None
    top_level_mode = str(evidence_request.get("mode") or "").strip().lower()
    if top_level_mode:
        return top_level_mode
    target = evidence_request.get("target") if isinstance(evidence_request.get("target"), dict) else {}
    target_mode = str(target.get("mode") or "").strip().lower()
    if target_mode:
        return target_mode
    operation_modes = [
        mode
        for mode in ("select_region", "refine_region", "verify_region", "locate")
        if isinstance(target.get(mode), dict)
    ]
    if len(operation_modes) == 1:
        return operation_modes[0]
    return None


def visual_evidence_from_verify_payload(
    *,
    verify_payload: dict[str, Any],
    existing_visual_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(verify_payload, dict):
        return coerce_visual_evidence_state(existing_visual_evidence)
    results = verify_payload.get("results") if isinstance(verify_payload.get("results"), list) else []
    latest = dict(results[-1]) if results and isinstance(results[-1], dict) else {}
    merged = coerce_visual_evidence_state(existing_visual_evidence if isinstance(existing_visual_evidence, dict) else {})
    merged.update(
        {
            "mode": merged.get("mode") or "verify",
            "status": str(latest.get("status") or merged.get("status") or "").strip().lower() or None,
            "check_id": str(latest.get("check_id") or merged.get("check_id") or "").strip() or None,
            "query": str(latest.get("query") or merged.get("query") or "").strip()[:320] or merged.get("query"),
            "observed_text": str(latest.get("observed_text") or merged.get("observed_text") or "").strip()[:220] or merged.get("observed_text"),
            "verify_summary": dict(verify_payload.get("summary")) if isinstance(verify_payload.get("summary"), dict) else {},
            "tx_image_evidence_region_ref": coerce_artifact_ref_for_state(
                latest.get("tx_image_evidence_region_ref") or merged.get("tx_image_evidence_region_ref")
            ),
            "tx_image_evidence_context_ref": coerce_artifact_ref_for_state(
                latest.get("tx_image_evidence_context_ref") or merged.get("tx_image_evidence_context_ref")
            ),
        }
    )
    return merged


def coerce_artifact_ref_for_state(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        artifact_path = str(raw.get("artifact_path") or "").strip()
        if artifact_path:
            return {"artifact_path": artifact_path}
    if isinstance(raw, str):
        value = raw.strip()
        if value:
            return {"artifact_path": value}
    return None


def cache_entry_matches_transcript(
    *,
    entry: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> bool:
    requested_ref = str(source_transcript_ref or "").strip()
    requested_hash = str(source_transcript_hash or "").strip()
    entry_ref = str(entry.get("source_transcript_ref") or "").strip()
    entry_hash = str(entry.get("source_transcript_hash") or "").strip()
    if requested_ref and entry_ref and requested_ref != entry_ref:
        return False
    if requested_hash and entry_hash and requested_hash != entry_hash:
        return False
    return True


def clear_cached_focus_evidence(*, state: TranscriptEditLoopState) -> None:
    state.span_context_by_decision_key = {}
    state.image_verification_payload_by_decision_key = {}
    state.visual_evidence_by_decision_key = {}


def cached_span_context_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> list[dict[str, Any]]:
    key = str(decision_key or "").strip().lower()
    if not key:
        return []
    entry = state.span_context_by_decision_key.get(key)
    if not isinstance(entry, dict):
        return []
    if not cache_entry_matches_transcript(
        entry=entry,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    ):
        return []
    rows = entry.get("span_context")
    if not isinstance(rows, list):
        return []
    return [dict(item) for item in rows if isinstance(item, dict)][:12]


def cache_span_context_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    span_context: list[dict[str, Any]],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    key = str(decision_key or "").strip().lower()
    if not key:
        return
    bounded = [dict(item) for item in span_context if isinstance(item, dict)][:12]
    state.span_context_by_decision_key[key] = {
        "source_transcript_ref": str(source_transcript_ref or "").strip() or None,
        "source_transcript_hash": str(source_transcript_hash or "").strip() or None,
        "span_context": bounded,
    }


def cached_image_verification_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> dict[str, Any]:
    key = str(decision_key or "").strip().lower()
    if not key:
        return {}
    entry = state.image_verification_payload_by_decision_key.get(key)
    if not isinstance(entry, dict):
        return {}
    if not cache_entry_matches_transcript(
        entry=entry,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    ):
        return {}
    payload = entry.get("image_verification_payload")
    if not isinstance(payload, dict):
        return {}
    return dict(payload)


def cached_visual_evidence_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> dict[str, Any]:
    key = str(decision_key or "").strip().lower()
    if not key:
        return {}
    entry = state.visual_evidence_by_decision_key.get(key)
    if not isinstance(entry, dict):
        return {}
    if not cache_entry_matches_transcript(
        entry=entry,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
    ):
        return {}
    payload = entry.get("visual_evidence")
    if not isinstance(payload, dict):
        return {}
    return coerce_visual_evidence_state(payload)


def cache_image_verification_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    image_verification: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    key = str(decision_key or "").strip().lower()
    if not key:
        return
    payload = image_verification.get("payload") if isinstance(image_verification, dict) else None
    if isinstance(payload, dict):
        state.image_verification_payload_by_decision_key[key] = {
            "source_transcript_ref": str(source_transcript_ref or "").strip() or None,
            "source_transcript_hash": str(source_transcript_hash or "").strip() or None,
            "image_verification_payload": dict(payload),
        }


def cache_visual_evidence_for_key(
    *,
    state: TranscriptEditLoopState,
    decision_key: str | None,
    visual_evidence: dict[str, Any],
    source_transcript_ref: str | None,
    source_transcript_hash: str | None,
) -> None:
    key = str(decision_key or "").strip().lower()
    if not key:
        return
    bounded = coerce_visual_evidence_state(visual_evidence)
    if not bounded:
        return
    state.visual_evidence_by_decision_key[key] = {
        "source_transcript_ref": str(source_transcript_ref or "").strip() or None,
        "source_transcript_hash": str(source_transcript_hash or "").strip() or None,
        "visual_evidence": bounded,
    }


def coerce_visual_evidence_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    locator = data.get("locator") if isinstance(data.get("locator"), dict) else {}
    return {
        "mode": str(data.get("mode") or "").strip().lower() or None,
        "status": str(data.get("status") or "").strip().lower() or None,
        "check_id": str(data.get("check_id") or "").strip() or None,
        "decision_key": str(data.get("decision_key") or "").strip().lower() or None,
        "query": str(data.get("query") or "").strip()[:320] or None,
        "expected_text": str(data.get("expected_text") or "").strip()[:180] or None,
        "observed_text": str(data.get("observed_text") or "").strip()[:220] or None,
        "locator": {
            "status": str(locator.get("status") or "").strip().lower() or None,
            "confidence": str(locator.get("confidence") or "").strip().lower() or None,
            "reason": str(locator.get("reason") or "").strip()[:220] or None,
        },
        "verify_summary": dict(data.get("verify_summary")) if isinstance(data.get("verify_summary"), dict) else {},
        "crop_box": dict(data.get("crop_box")) if isinstance(data.get("crop_box"), dict) else None,
        "zoom_factor": data.get("zoom_factor"),
        "inspection_ref": coerce_artifact_ref_for_state(data.get("inspection_ref")),
        "tx_image_region_lineage_ref": coerce_artifact_ref_for_state(data.get("tx_image_region_lineage_ref")),
        "region_lineage": dict(data.get("region_lineage")) if isinstance(data.get("region_lineage"), dict) else {},
        "image_width": data.get("image_width"),
        "image_height": data.get("image_height"),
        "grid_spec": dict(data.get("grid_spec")) if isinstance(data.get("grid_spec"), dict) else None,
        "grid_overlay_ref": coerce_artifact_ref_for_state(data.get("grid_overlay_ref")),
        "selector_type": str(data.get("selector_type") or "").strip().lower() or None,
        "source_image_path": str(data.get("source_image_path") or "").strip() or None,
        "tx_image_evidence_region_ref": coerce_artifact_ref_for_state(data.get("tx_image_evidence_region_ref")),
        "tx_image_evidence_context_ref": coerce_artifact_ref_for_state(data.get("tx_image_evidence_context_ref")),
    }

