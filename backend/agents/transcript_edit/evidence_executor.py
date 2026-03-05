from __future__ import annotations

from typing import Any, Callable

SUPPORTED_EVIDENCE_KINDS = {
    "open_spans",
    "image_verify",
    "retrieve_dependency_evidence",
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
    return (
        {
            "kind": kind,
            "decision_key": request_key,
            "reason": str(evidence_request.get("reason") or "").strip(),
            "target": {
                "span_ids": span_ids,
                "expected_fields": expected_fields,
            },
        },
        "ok",
    )


def execute_evidence_request(
    *,
    normalized_request: dict[str, Any],
    source_transcript_hash: str,
    repeat_guard: dict[str, dict[str, Any]],
    evidence_signal_counter: int,
    max_repeats_per_signature: int,
    open_spans_runner: Callable[[dict[str, Any]], list[dict[str, Any]]],
    image_verify_runner: Callable[[dict[str, Any]], dict[str, Any]],
    retrieve_dependency_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kind = str(normalized_request.get("kind") or "").strip().lower()
    decision_key = str(normalized_request.get("decision_key") or "").strip().lower()
    signature = _evidence_signature(
        decision_key=decision_key,
        source_transcript_hash=source_transcript_hash,
        kind=kind,
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
