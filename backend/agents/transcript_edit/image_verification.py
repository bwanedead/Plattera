from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_kernel.models import ActionType, StepExecutionState

from .disagreement_analysis import (
    first_expected_token_from_message,
    image_checks_from_disagreement_hints,
)


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
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for finding in top_findings[:6]:
        if not isinstance(finding, dict):
            continue
        finding_type = str(finding.get("finding_type") or "").strip().lower()
        if finding_type not in {"plss_consistency", "bearing_parse", "numeric_unit_sanity", "call_chain_structure"}:
            continue
        check_id = str(finding.get("finding_id") or f"finding_{len(checks) + 1}")
        checks.append(
            {
                "check_id": check_id,
                "query": str(finding.get("message") or "")[:320],
                "expected_text": first_expected_token_from_message(str(finding.get("message") or "")),
            }
        )
    checks.extend(image_checks_from_disagreement_hints(disagreement_hints))
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

    selected_checks = checks[:4]
    all_results: list[dict[str, Any]] = []
    latest_refs: dict[str, Any] = {}
    image_path: str | None = None
    total_checks = len(selected_checks)

    for check_index, check in enumerate(selected_checks, start=1):
        if progress_cb is not None:
            progress_cb(
                {
                    "check_index": check_index,
                    "check_total": total_checks,
                    "check_id": str(check.get("check_id") or f"check_{check_index}"),
                    "stage": "running",
                }
            )
        step_inputs = dict(inputs)
        step_inputs["checks"] = [check]
        step = step_fn(
            session_manager=session_manager,
            session_id=session_id,
            prefix=f"tx_verify_img_{check_index}",
            iteration=iteration,
            action_type=ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
            inputs=step_inputs,
        )
        latest_refs = step.dashboard.latest_refs.model_dump(mode="json")
        if step.execution_state != StepExecutionState.EXECUTED:
            return {"latest_refs": latest_refs, "payload": {}}
        inline = read_step_outputs_inline_fn(step.step_record)
        step_results = _read_full_image_verify_results(latest_refs=latest_refs)
        if not step_results:
            inline_results = inline.get("tx_image_verify_results")
            if isinstance(inline_results, list):
                step_results = [item for item in inline_results if isinstance(item, dict)]
        if step_results:
            all_results.extend(step_results)
        image_path = read_str_fn(inline.get("tx_image_path")) or image_path
        if progress_cb is not None:
            progress_cb(
                {
                    "check_index": check_index,
                    "check_total": total_checks,
                    "check_id": str(check.get("check_id") or f"check_{check_index}"),
                    "stage": "completed",
                }
            )

    match_count = sum(1 for item in all_results if str(item.get("status") or "").lower() in {"match", "confirmed"})
    mismatch_count = sum(1 for item in all_results if str(item.get("status") or "").lower() in {"mismatch", "rejected"})
    unclear_count = sum(1 for item in all_results if str(item.get("status") or "").lower() in {"unclear", "unknown"})
    payload = {
        "summary": {
            "total_checks": total_checks,
            "match_count": match_count,
            "mismatch_count": mismatch_count,
            "unclear_count": unclear_count,
        },
        "results": all_results,
        "image_path": image_path,
    }
    return {"latest_refs": latest_refs, "payload": payload}


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
    existing_ids = {str(item.get("check_id") or "") for item in checks if isinstance(item, dict)}
    for extra in image_checks_from_disagreement_hints(disagreement_hints):
        if not isinstance(extra, dict):
            continue
        cid = str(extra.get("check_id") or "")
        if cid and cid not in existing_ids:
            checks.append(extra)
            existing_ids.add(cid)
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
        action_type=ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
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
