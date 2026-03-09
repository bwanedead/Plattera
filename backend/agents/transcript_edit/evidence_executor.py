from __future__ import annotations

from typing import Any, Callable

SUPPORTED_EVIDENCE_KINDS = {
    "open_spans",
    "image_verify",
    "image_evidence",
    "retrieve_dependency_evidence",
}

SUPPORTED_IMAGE_EVIDENCE_MODES = {
    "select_region",
    "refine_region",
    "verify_region",
    "locate",
}

SUPPORTED_REFINE_TRANSFORMS = {
    "expand",
    "shrink",
    "shift_up",
    "shift_down",
    "shift_left",
    "shift_right",
    "set_zoom",
}


def normalize_evidence_request(
    *,
    evidence_request: dict[str, Any] | None,
    decision_key: str,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(evidence_request, dict):
        return None, "evidence_request_missing"
    kind = str(evidence_request.get("kind") or "").strip().lower()
    if kind not in SUPPORTED_EVIDENCE_KINDS:
        return None, "evidence_request_kind_unsupported"
    request_key = str(evidence_request.get("decision_key") or decision_key).strip().lower()
    if not request_key or request_key != decision_key:
        return None, "evidence_request_decision_key_mismatch"
    target = evidence_request.get("target") if isinstance(evidence_request.get("target"), dict) else {}
    span_ids = [
        str(v).strip()
        for v in list(target.get("span_ids") or [])
        if str(v).strip()
    ][:8]
    expected_fields = [
        str(v).strip().lower()
        for v in list(target.get("expected_fields") or [])
        if str(v).strip()
    ][:6]
    mode = str(evidence_request.get("mode") or "").strip().lower()
    if kind == "image_evidence":
        if mode not in SUPPORTED_IMAGE_EVIDENCE_MODES:
            return None, "image_evidence_mode_invalid"
    else:
        mode = ""
    target_region_ref = target.get("region_ref")
    target_context_ref = target.get("context_ref")
    normalized_target_region_ref = target_region_ref if isinstance(target_region_ref, dict) else None
    normalized_target_context_ref = target_context_ref if isinstance(target_context_ref, dict) else None
    normalized_target = {
        "span_ids": span_ids,
        "expected_fields": expected_fields,
        "region_ref": normalized_target_region_ref,
        "context_ref": normalized_target_context_ref,
        "query": str(target.get("query") or "").strip()[:320] or None,
        "expected_text": str(target.get("expected_text") or "").strip()[:180] or None,
        "anchor_hint": str(target.get("anchor_hint") or "").strip()[:220] or None,
        "source_image_ref": str(target.get("source_image_ref") or "").strip() or None,
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
    }
    if kind == "image_evidence":
        image_reason = _validate_image_evidence_mode_target(mode=mode, target=normalized_target)
        if image_reason is not None:
            return None, image_reason
    return (
        {
            "kind": kind,
            "mode": mode or None,
            "decision_key": request_key,
            "reason": str(evidence_request.get("reason") or "").strip(),
            "target": normalized_target,
        },
        "ok",
    )


def _validate_image_evidence_mode_target(*, mode: str, target: dict[str, Any]) -> str | None:
    if mode == "select_region":
        selectors = (
            1 if isinstance(target.get("crop_box_pixels"), dict) else 0,
            1 if isinstance(target.get("crop_box_normalized"), dict) else 0,
            1 if isinstance(target.get("grid_selection"), dict) else 0,
        )
        selector_count = sum(selectors)
        if selector_count == 0:
            return "image_evidence_select_region_target_missing"
        if selector_count > 1:
            return "image_evidence_select_region_target_ambiguous"
        return None
    if mode == "refine_region":
        if not isinstance(target.get("region_ref"), dict):
            return "image_evidence_refine_region_region_ref_missing"
        transform = str(target.get("transform") or "").strip().lower()
        if transform not in SUPPORTED_REFINE_TRANSFORMS:
            return "image_evidence_refine_region_transform_invalid"
        amount_value = target.get("amount")
        try:
            amount = float(amount_value)
        except (TypeError, ValueError):
            return "image_evidence_refine_region_amount_invalid"
        if amount <= 0:
            return "image_evidence_refine_region_amount_invalid"
        return None
    if mode == "verify_region":
        if not isinstance(target.get("region_ref"), dict):
            return "image_evidence_verify_region_region_ref_missing"
        query = str(target.get("query") or "").strip()
        if not query:
            return "image_evidence_verify_region_query_missing"
        return None
    return None


def execute_evidence_request(
    *,
    normalized_request: dict[str, Any],
    source_transcript_hash: str,
    repeat_guard: dict[str, dict[str, Any]],
    evidence_signal_counter: int,
    max_repeats_per_signature: int,
    open_spans_runner: Callable[[dict[str, Any]], list[dict[str, Any]]],
    image_verify_runner: Callable[[dict[str, Any]], dict[str, Any]],
    image_evidence_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    retrieve_dependency_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kind = str(normalized_request.get("kind") or "").strip().lower()
    mode = str(normalized_request.get("mode") or "").strip().lower()
    decision_key = str(normalized_request.get("decision_key") or "").strip().lower()
    signature = _evidence_signature(
        decision_key=decision_key,
        source_transcript_hash=source_transcript_hash,
        kind=f"{kind}:{mode}" if kind == "image_evidence" and mode else kind,
    )
    repeat_entry = repeat_guard.get(signature)
    if not isinstance(repeat_entry, dict):
        repeat_entry = {"count": 0, "last_signal_counter": evidence_signal_counter}
        repeat_guard[signature] = repeat_entry
    last_signal_counter = int(repeat_entry.get("last_signal_counter") or 0)
    if last_signal_counter != evidence_signal_counter:
        repeat_entry["count"] = 0
        repeat_entry["last_signal_counter"] = evidence_signal_counter
    if int(repeat_entry.get("count") or 0) >= max(1, int(max_repeats_per_signature)):
        return {
            "status": "repeat_blocked",
            "reason": "evidence_repeat_budget_exhausted",
            "decision_key": decision_key,
            "kind": kind,
            "signature": signature,
        }
    repeat_entry["count"] = int(repeat_entry.get("count") or 0) + 1

    if kind == "open_spans":
        spans = open_spans_runner(normalized_request)
        return {
            "status": "executed",
            "reason": "evidence_open_spans_executed",
            "decision_key": decision_key,
            "kind": kind,
            "signature": signature,
            "span_context": [s for s in spans if isinstance(s, dict)],
            "image_verification": {},
        }
    if kind == "image_verify":
        image_verification = image_verify_runner(normalized_request)
        return {
            "status": "executed",
            "reason": "evidence_image_verify_executed",
            "decision_key": decision_key,
            "kind": kind,
            "signature": signature,
            "span_context": [],
            "image_verification": image_verification if isinstance(image_verification, dict) else {},
        }
    if kind == "image_evidence":
        if image_evidence_runner is None:
            return {
                "status": "unsupported",
                "reason": "image_evidence_runner_not_wired",
                "decision_key": decision_key,
                "kind": kind,
                "mode": mode or None,
                "signature": signature,
            }
        image_evidence = image_evidence_runner(normalized_request)
        image_evidence_payload = image_evidence if isinstance(image_evidence, dict) else {}
        if isinstance(image_evidence_payload.get("image_evidence"), dict):
            image_evidence_payload = image_evidence_payload.get("image_evidence")  # type: ignore[assignment]
        image_verification = (
            image_evidence.get("image_verification")  # type: ignore[union-attr]
            if isinstance(image_evidence, dict) and isinstance(image_evidence.get("image_verification"), dict)
            else {}
        )
        return {
            "status": "executed",
            "reason": f"evidence_image_evidence_{mode or 'unknown'}_executed",
            "decision_key": decision_key,
            "kind": kind,
            "mode": mode or None,
            "signature": signature,
            "span_context": [],
            "image_evidence": image_evidence_payload,
            "image_verification": image_verification,
        }
    if kind == "retrieve_dependency_evidence":
        if retrieve_dependency_runner is None:
            return {
                "status": "unsupported",
                "reason": "dependency_retrieval_not_wired",
                "decision_key": decision_key,
                "kind": kind,
                "signature": signature,
            }
        retrieval = retrieve_dependency_runner(normalized_request)
        return {
            "status": "executed",
            "reason": "evidence_dependency_retrieval_executed",
            "decision_key": decision_key,
            "kind": kind,
            "signature": signature,
            "retrieval": retrieval if isinstance(retrieval, dict) else {},
        }
    return {
        "status": "invalid",
        "reason": "evidence_request_kind_invalid",
        "decision_key": decision_key,
        "kind": kind,
        "signature": signature,
    }


def _evidence_signature(*, decision_key: str, source_transcript_hash: str, kind: str) -> str:
    return f"{decision_key}|{source_transcript_hash}|{kind}"
