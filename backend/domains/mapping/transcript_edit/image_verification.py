from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_kernel.models import StepExecutionState

from .execution_action_ids import TX_VERIFY_TRANSCRIPT_WITH_IMAGE

from .disagreement_analysis import first_expected_token_from_message

_IMAGE_VERIFY_HEARTBEAT_THRESHOLDS_SECONDS: tuple[int, ...] = (15, 30, 60)
_IMAGE_VERIFY_HEARTBEAT_EVERY_SECONDS = 60
_IMAGE_VERIFY_STEP_TIMEOUT_SECONDS = 240
_IMAGE_VERIFY_MAX_ATTEMPTS_PER_CHECK = 2
_IMAGE_VERIFY_MAX_CHECKS = 4


def verify_mapping_critical_with_image(
    *,
    session_manager: Any,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
    disagreement_hints: dict[str, Any],
    source_image_refs: list[str],
    model: str,
    step_fn: Callable[..., Any],
    read_step_outputs_inline_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    read_str_fn: Callable[[object], str | None],
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    focus_decision_key: str | None = None,
    llm_call_seq_start: int = 0,
    max_checks: int = _IMAGE_VERIFY_MAX_CHECKS,
    step_timeout_seconds: int = _IMAGE_VERIFY_STEP_TIMEOUT_SECONDS,
    max_attempts_per_check: int = _IMAGE_VERIFY_MAX_ATTEMPTS_PER_CHECK,
    heartbeat_thresholds_seconds: tuple[int, ...] = _IMAGE_VERIFY_HEARTBEAT_THRESHOLDS_SECONDS,
    heartbeat_every_seconds: int = _IMAGE_VERIFY_HEARTBEAT_EVERY_SECONDS,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    focus_k = str(focus_decision_key or "").strip().lower() or None
    for finding in top_findings[:6]:
        if not isinstance(finding, dict):
            continue
        message = str(finding.get("message") or "").strip()
        if len(message) < 8:
            continue
        inferred_decision_key = _decision_key_for_finding(finding)
        check_decision_key = inferred_decision_key or focus_k
        if not check_decision_key:
            continue
        check_id = str(finding.get("observation_ref") or finding.get("finding_id") or f"check_{len(checks) + 1}")
        checks.append(
            {
                "check_id": check_id,
                "query": message[:320],
                "expected_text": first_expected_token_from_message(message),
                "decision_key": check_decision_key,
                "locator_context": {
                    "observation_ref": str(finding.get("observation_ref") or check_id)[:120],
                    "message_excerpt": message[:320],
                },
            }
        )
    del disagreement_hints
    if not checks:
        return {}

    inputs: dict[str, Any] = {
        "dossier_id": dossier_id,
        "source_transcript_ref": source_transcript_ref,
        "checks": checks[:4],
        "model": model,
        "zoom_factor": 3.2,
    }
    if isinstance(source_image_refs, list) and source_image_refs:
        first_image = read_str_fn(source_image_refs[0])
        if first_image:
            inputs["image_ref"] = first_image

    selected_checks = checks[: max(1, int(max_checks))]
    all_results: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    latest_refs: dict[str, Any] = {}
    image_path: str | None = None
    total_checks = len(selected_checks)
    llm_call_seq = int(llm_call_seq_start)

    for check_index, check in enumerate(selected_checks, start=1):
        check_id = str(check.get("check_id") or f"check_{check_index}")
        check_decision_key = str(check.get("decision_key") or "").strip().lower() or None
        succeeded = False
        for phase_attempt in range(1, max(1, int(max_attempts_per_check)) + 1):
            llm_call_seq += 1
            phase_started_at_epoch_seconds = int(time.time())
            if progress_cb is not None:
                progress_cb(
                    {
                        "check_index": check_index,
                        "check_total": total_checks,
                        "check_id": check_id,
                        "check_decision_key": check_decision_key,
                        "focus_decision_key": str(focus_decision_key or "").strip().lower() or None,
                        "stage": "running",
                        "llm_call_seq": llm_call_seq,
                        "phase_attempt": phase_attempt,
                        "phase_started_at_epoch_seconds": phase_started_at_epoch_seconds,
                        "timeout_seconds": int(step_timeout_seconds),
                        "max_attempts_per_check": int(max_attempts_per_check),
                        "wait_reason": "awaiting_image_verify_step_response",
                    }
                )
            step_inputs = dict(inputs)
            step_inputs["checks"] = [check]
            try:
                step = _run_step_with_heartbeat(
                    session_manager=session_manager,
                    session_id=session_id,
                    iteration=iteration,
                    check_index=check_index,
                    check_total=total_checks,
                    check_id=check_id,
                    step_fn=step_fn,
                    step_inputs=step_inputs,
                    progress_cb=progress_cb,
                    llm_call_seq=llm_call_seq,
                    phase_attempt=phase_attempt,
                    focus_decision_key=(str(focus_decision_key or "").strip().lower() or None),
                    check_decision_key=check_decision_key,
                    timeout_seconds=int(step_timeout_seconds),
                    heartbeat_thresholds_seconds=heartbeat_thresholds_seconds,
                    heartbeat_every_seconds=int(heartbeat_every_seconds),
                    phase_started_at_epoch_seconds=phase_started_at_epoch_seconds,
                    max_attempts_per_check=int(max_attempts_per_check),
                )
            except TimeoutError:
                diagnostic = {
                    "decision_key": str(focus_decision_key or "").strip().lower() or None,
                    "evidence_kind": "image_verify",
                    "check_id": check_id,
                    "check_decision_key": check_decision_key,
                    "llm_call_seq": llm_call_seq,
                    "phase_attempt": phase_attempt,
                    "error_class": "timeout",
                    "error_code": "image_verify_step_timeout",
                    "timeout_seconds": int(step_timeout_seconds),
                    "checks_in_request": 1,
                    "image_count": 1 if isinstance(inputs.get("image_ref"), str) else 0,
                }
                diagnostics.append(diagnostic)
                if progress_cb is not None:
                    progress_cb(
                        {
                            "check_index": check_index,
                            "check_total": total_checks,
                            "check_id": check_id,
                            "check_decision_key": check_decision_key,
                            "focus_decision_key": str(focus_decision_key or "").strip().lower() or None,
                            "stage": "timeout",
                            "llm_call_seq": llm_call_seq,
                            "phase_attempt": phase_attempt,
                            "phase_started_at_epoch_seconds": phase_started_at_epoch_seconds,
                            "timeout_seconds": int(step_timeout_seconds),
                            "max_attempts_per_check": int(max_attempts_per_check),
                            "wait_reason": "step_timeout",
                            "diagnostic": diagnostic,
                        }
                    )
                if phase_attempt < max(1, int(max_attempts_per_check)):
                    if progress_cb is not None:
                        progress_cb(
                            {
                                "check_index": check_index,
                                "check_total": total_checks,
                                "check_id": check_id,
                                "check_decision_key": check_decision_key,
                                "focus_decision_key": str(focus_decision_key or "").strip().lower() or None,
                                "stage": "retrying",
                                "llm_call_seq": llm_call_seq,
                                "phase_attempt": phase_attempt + 1,
                                "phase_started_at_epoch_seconds": int(time.time()),
                                "timeout_seconds": int(step_timeout_seconds),
                                "max_attempts_per_check": int(max_attempts_per_check),
                                "wait_reason": "retry_after_timeout",
                            }
                        )
                    continue
                break
            latest_refs = step.dashboard.latest_refs.model_dump(mode="json")
            if step.execution_state != StepExecutionState.EXECUTED:
                refusal = step.refusal.reason_code if step.refusal is not None else "tx_verify_refused"
                diagnostic = {
                    "decision_key": str(focus_decision_key or "").strip().lower() or None,
                    "evidence_kind": "image_verify",
                    "check_id": check_id,
                    "check_decision_key": check_decision_key,
                    "llm_call_seq": llm_call_seq,
                    "phase_attempt": phase_attempt,
                    "error_class": "step_refusal",
                    "error_code": refusal,
                    "checks_in_request": 1,
                    "image_count": 1 if isinstance(inputs.get("image_ref"), str) else 0,
                }
                diagnostics.append(diagnostic)
                if progress_cb is not None:
                    progress_cb(
                        {
                            "check_index": check_index,
                            "check_total": total_checks,
                            "check_id": check_id,
                            "check_decision_key": check_decision_key,
                            "focus_decision_key": str(focus_decision_key or "").strip().lower() or None,
                            "stage": "failed",
                            "llm_call_seq": llm_call_seq,
                            "phase_attempt": phase_attempt,
                            "phase_started_at_epoch_seconds": phase_started_at_epoch_seconds,
                            "timeout_seconds": int(step_timeout_seconds),
                            "max_attempts_per_check": int(max_attempts_per_check),
                            "wait_reason": "step_refused_or_failed",
                            "diagnostic": diagnostic,
                        }
                    )
                if phase_attempt < max(1, int(max_attempts_per_check)):
                    if progress_cb is not None:
                        progress_cb(
                            {
                                "check_index": check_index,
                                "check_total": total_checks,
                                "check_id": check_id,
                                "check_decision_key": check_decision_key,
                                "focus_decision_key": str(focus_decision_key or "").strip().lower() or None,
                                "stage": "retrying",
                                "llm_call_seq": llm_call_seq,
                                "phase_attempt": phase_attempt + 1,
                                "phase_started_at_epoch_seconds": int(time.time()),
                                "timeout_seconds": int(step_timeout_seconds),
                                "max_attempts_per_check": int(max_attempts_per_check),
                                "wait_reason": "retry_after_failure",
                            }
                        )
                    continue
                break

            inline = read_step_outputs_inline_fn(step.step_record)
            region_ref = _read_inline_ref(inline.get("tx_image_evidence_region_ref"))
            context_ref = _read_inline_ref(inline.get("tx_image_evidence_context_ref"))
            if region_ref is not None:
                latest_refs["tx_image_evidence_region_ref"] = region_ref
            if context_ref is not None:
                latest_refs["tx_image_evidence_context_ref"] = context_ref
            step_results = _read_full_image_verify_results(latest_refs=latest_refs)
            if not step_results:
                inline_results = inline.get("tx_image_verify_results")
                if isinstance(inline_results, list):
                    step_results = [item for item in inline_results if isinstance(item, dict)]
            if step_results:
                for row in step_results:
                    if not isinstance(row, dict):
                        continue
                    annotated = dict(row)
                    annotated.setdefault("decision_key", check_decision_key)
                    annotated.setdefault("focus_decision_key", str(focus_decision_key or "").strip().lower() or None)
                    annotated.setdefault("query", str(check.get("query") or "").strip() or None)
                    annotated.setdefault("llm_call_seq", llm_call_seq)
                    annotated.setdefault("phase_attempt", phase_attempt)
                    annotated.setdefault("tx_image_evidence_region_ref", region_ref)
                    annotated.setdefault("tx_image_evidence_context_ref", context_ref)
                    all_results.append(annotated)
            image_path = read_str_fn(inline.get("tx_image_path")) or image_path
            if progress_cb is not None:
                progress_cb(
                    {
                        "check_index": check_index,
                        "check_total": total_checks,
                        "check_id": check_id,
                        "check_decision_key": check_decision_key,
                        "focus_decision_key": str(focus_decision_key or "").strip().lower() or None,
                        "stage": "completed",
                        "llm_call_seq": llm_call_seq,
                        "phase_attempt": phase_attempt,
                        "phase_started_at_epoch_seconds": phase_started_at_epoch_seconds,
                        "timeout_seconds": int(step_timeout_seconds),
                        "max_attempts_per_check": int(max_attempts_per_check),
                        "wait_reason": "step_completed",
                    }
                )
            succeeded = True
            break
        if not succeeded:
            all_results.append(
                {
                    "check_id": check_id,
                    "status": "error",
                    "decision_key": check_decision_key,
                    "focus_decision_key": str(focus_decision_key or "").strip().lower() or None,
                    "confidence": "low",
                    "reason": "image_verify_check_failed_after_retries",
                    "llm_call_seq": llm_call_seq,
                    "phase_attempt": max(1, int(max_attempts_per_check)),
                }
            )

    match_count = sum(1 for item in all_results if str(item.get("status") or "").lower() in {"match", "confirmed"})
    mismatch_count = sum(1 for item in all_results if str(item.get("status") or "").lower() in {"mismatch", "rejected"})
    unclear_count = sum(1 for item in all_results if str(item.get("status") or "").lower() in {"unclear", "unknown"})
    failed_count = sum(1 for item in all_results if str(item.get("status") or "").lower() in {"error", "failed"})
    payload = {
        "summary": {
            "total_checks": total_checks,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "unclear_count": unclear_count,
            "failed_count": failed_count,
        },
        "results": all_results,
        "image_path": image_path,
        "diagnostics": diagnostics,
        "image_evidence_regions": _collect_image_evidence_regions(all_results),
    }
    return {"latest_refs": latest_refs, "payload": payload, "llm_call_seq_end": llm_call_seq}


def _run_step_with_heartbeat(
    *,
    session_manager: Any,
    session_id: str,
    iteration: int,
    check_index: int,
    check_total: int,
    check_id: str,
    step_fn: Callable[..., Any],
    step_inputs: dict[str, Any],
    progress_cb: Callable[[dict[str, Any]], None] | None,
    llm_call_seq: int,
    phase_attempt: int,
    focus_decision_key: str | None,
    check_decision_key: str | None,
    timeout_seconds: int,
    heartbeat_thresholds_seconds: tuple[int, ...] = _IMAGE_VERIFY_HEARTBEAT_THRESHOLDS_SECONDS,
    heartbeat_every_seconds: int = _IMAGE_VERIFY_HEARTBEAT_EVERY_SECONDS,
    phase_started_at_epoch_seconds: int | None = None,
    max_attempts_per_check: int = _IMAGE_VERIFY_MAX_ATTEMPTS_PER_CHECK,
) -> Any:
    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            result_box["step"] = step_fn(
                session_manager=session_manager,
                session_id=session_id,
                prefix=f"tx_verify_img_{check_index}",
                iteration=iteration,
                action_type=TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
                inputs=step_inputs,
            )
        except BaseException as exc:  # pragma: no cover - defensive thread handoff
            error_box["error"] = exc

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    started = time.monotonic()
    emitted_thresholds: set[int] = set()
    started_epoch = int(phase_started_at_epoch_seconds or time.time())
    while worker.is_alive():
        worker.join(timeout=0.4)
        now = time.monotonic()
        elapsed_seconds = int(now - started)
        if worker.is_alive() and elapsed_seconds >= int(timeout_seconds):
            raise TimeoutError("image_verify_step_timeout")
        if progress_cb is not None and worker.is_alive():
            threshold = _next_wait_heartbeat_threshold(
                elapsed_seconds=elapsed_seconds,
                emitted_thresholds=emitted_thresholds,
                thresholds=heartbeat_thresholds_seconds,
                heartbeat_every_seconds=heartbeat_every_seconds,
            )
            if threshold is not None:
                emitted_thresholds.add(threshold)
                stage = "waiting"
                if elapsed_seconds >= 120:
                    stage = "degraded"
                elif elapsed_seconds >= 60:
                    stage = "long_running"
                progress_cb(
                    {
                        "check_index": check_index,
                        "check_total": check_total,
                        "check_id": check_id,
                        "check_decision_key": check_decision_key,
                        "focus_decision_key": focus_decision_key,
                        "stage": stage,
                        "elapsed_seconds": elapsed_seconds,
                        "llm_call_seq": llm_call_seq,
                        "phase_attempt": phase_attempt,
                        "phase_started_at_epoch_seconds": started_epoch,
                        "timeout_seconds": int(timeout_seconds),
                        "max_attempts_per_check": int(max_attempts_per_check),
                        "wait_reason": "awaiting_image_verify_step_response",
                    }
                )
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("step")


def _next_wait_heartbeat_threshold(
    *,
    elapsed_seconds: int,
    emitted_thresholds: set[int],
    thresholds: tuple[int, ...] = _IMAGE_VERIFY_HEARTBEAT_THRESHOLDS_SECONDS,
    heartbeat_every_seconds: int = _IMAGE_VERIFY_HEARTBEAT_EVERY_SECONDS,
) -> int | None:
    for threshold in tuple(int(v) for v in thresholds if int(v) > 0):
        if elapsed_seconds >= threshold and threshold not in emitted_thresholds:
            return int(threshold)
    if elapsed_seconds < 60:
        return None
    cadence = max(1, int(heartbeat_every_seconds))
    coarse = (int(elapsed_seconds) // cadence) * cadence
    if coarse >= 60 and coarse not in emitted_thresholds:
        return int(coarse)
    return None


def _decision_key_for_finding(finding: dict[str, Any]) -> str | None:
    """Infer mapping check key from evidence text and optional explicit keys (no validator taxonomy)."""
    if not isinstance(finding, dict):
        return None
    for k in ("suggested_decision_key", "decision_key", "target_decision_key"):
        raw = str(finding.get(k) or "").strip().lower()
        if raw in {
            "range",
            "township",
            "section",
            "tie_distance",
            "tie_bearing",
            "acreage",
            "closure_or_pob",
        }:
            return raw
    message = str(finding.get("message") or "").strip().lower()
    if "bearing" in message:
        return "tie_bearing"
    if "distance" in message or "tie distance" in message:
        return "tie_distance"
    if "acre" in message:
        return "acreage"
    if "closure" in message or "pob" in message or "point of beginning" in message:
        return "closure_or_pob"
    if "township" in message:
        return "township"
    if "section" in message:
        return "section"
    if "range" in message:
        return "range"
    return None


def _read_full_image_verify_results(*, latest_refs: dict[str, Any]) -> list[dict[str, Any]]:
    artifact_ref = latest_refs.get("tx_image_verify_ref") if isinstance(latest_refs, dict) else None
    artifact_path: str | None = None
    if isinstance(artifact_ref, dict):
        raw_path = artifact_ref.get("artifact_path")
        if isinstance(raw_path, str) and raw_path.strip():
            artifact_path = raw_path
    elif isinstance(artifact_ref, str) and artifact_ref.strip():
        artifact_path = artifact_ref
    if not artifact_path:
        return []
    try:
        payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


def _read_inline_ref(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        artifact_path = raw.get("artifact_path")
        if isinstance(artifact_path, str) and artifact_path.strip():
            return {"artifact_path": artifact_path}
    if isinstance(raw, str) and raw.strip():
        return {"artifact_path": raw}
    return None


def _collect_image_evidence_regions(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        region_ref = _read_inline_ref(row.get("tx_image_evidence_region_ref"))
        context_ref = _read_inline_ref(row.get("tx_image_evidence_context_ref"))
        if region_ref is None and context_ref is None:
            continue
        out.append(
            {
                "check_id": str(row.get("check_id") or "").strip() or None,
                "decision_key": str(row.get("decision_key") or "").strip().lower() or None,
                "status": str(row.get("status") or "").strip().lower() or None,
                "tx_image_evidence_region_ref": region_ref,
                "tx_image_evidence_context_ref": context_ref,
            }
        )
        if len(out) >= 12:
            break
    return out


def final_image_sanity_pass_before_promote(
    *,
    session_manager: Any,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    source_image_refs: list[str],
    disagreement_hints: dict[str, Any],
    model: str,
    step_fn: Callable[..., Any],
    read_step_outputs_inline_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    read_str_fn: Callable[[object], str | None],
    read_int_fn: Callable[[object, int], int],
) -> dict[str, Any]:
    checks = [
        {
            "check_id": "final_sanity_plss",
            "query": (
                "Read the deed image and report the key PLSS location tokens exactly as written "
                "(township, range, section if present)."
            ),
            "expected_text": None,
        },
        {
            "check_id": "final_sanity_distance",
            "query": (
                "Report the principal tie distance in feet from the point-of-beginning tie language if present."
            ),
            "expected_text": None,
        },
        {
            "check_id": "final_sanity_bearing",
            "query": (
                "Report the first explicit bearing token exactly as written (including degree value/minutes if present)."
            ),
            "expected_text": None,
        },
        {
            "check_id": "final_sanity_acreage",
            "query": "Report acreage value(s) stated for parcel descriptions if present.",
            "expected_text": None,
        },
    ]
    del disagreement_hints
    inputs: dict[str, Any] = {
        "dossier_id": dossier_id,
        "source_transcript_ref": source_transcript_ref,
        "checks": checks[:4],
        "model": model,
        "zoom_factor": 3.2,
    }
    if isinstance(source_image_refs, list) and source_image_refs:
        first_image = read_str_fn(source_image_refs[0])
        if first_image:
            inputs["image_ref"] = first_image

    step = step_fn(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_final_verify",
        iteration=iteration,
        action_type=TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
        inputs=inputs,
    )
    latest_refs = step.dashboard.latest_refs.model_dump(mode="json")
    if step.execution_state != StepExecutionState.EXECUTED:
        refusal_code = step.refusal.reason_code if step.refusal is not None else "tx_agent_final_image_verify_refused"
        return {"passed": False, "reason": f"tx_agent_final_image_verify_failed:{refusal_code}", "latest_refs": latest_refs}

    inline = read_step_outputs_inline_fn(step.step_record)
    summary = inline.get("tx_image_verify_summary") if isinstance(inline.get("tx_image_verify_summary"), dict) else {}
    mismatch_count = read_int_fn(summary.get("mismatch_count"), 0) if isinstance(summary, dict) else 0
    unclear_count = read_int_fn(summary.get("unclear_count"), 0) if isinstance(summary, dict) else 0
    total_checks = read_int_fn(summary.get("total_checks"), 0) if isinstance(summary, dict) else 0
    if total_checks <= 0:
        return {"passed": False, "reason": "tx_agent_final_image_verify_failed:no_checks", "latest_refs": latest_refs}
    if mismatch_count > 0:
        return {"passed": False, "reason": "tx_agent_final_image_verify_failed:mismatch", "latest_refs": latest_refs}
    if unclear_count > 0:
        return {"passed": False, "reason": "tx_agent_final_image_verify_failed:unclear", "latest_refs": latest_refs}
    return {"passed": True, "reason": "ok", "latest_refs": latest_refs}
