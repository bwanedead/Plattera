from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .span_seeds import load_transcript_text_for_seeds

_SUPPORTED_DECISION_KEYS = {
    "township",
    "range",
    "section",
    "tie_distance",
    "tie_bearing",
    "closure_or_pob",
}


def supported_decision_keys() -> set[str]:
    return set(_SUPPORTED_DECISION_KEYS)


def build_feedback_override_plan(
    *,
    decision_key: str,
    selected_value: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
    note: str | None = None,
) -> dict[str, Any] | None:
    key = str(decision_key or "").strip().lower()
    if key not in _SUPPORTED_DECISION_KEYS:
        return None
    text = load_transcript_text_for_seeds(source_transcript_ref)
    if not text:
        return None
    value = str(selected_value or "").strip()
    if not value:
        return None

    if key == "range":
        op = _build_range_op(text=text, selected_value=value)
    elif key == "township":
        op = _build_township_op(text=text, selected_value=value)
    elif key == "section":
        op = _build_section_op(text=text, selected_value=value)
    elif key == "tie_distance":
        op = _build_tie_distance_op(text=text, selected_value=value)
    elif key == "tie_bearing":
        op = _build_tie_bearing_op(text=text, selected_value=value)
    elif key == "closure_or_pob":
        op = _build_closure_or_pob_op(text=text, selected_value=value)
    else:
        op = None
    if op is None:
        return None
    return _plan_from_ops(
        decision_key=key,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        ops=[op],
        note=note,
    )


def _build_range_op(*, text: str, selected_value: str) -> dict[str, Any] | None:
    selected_num = _extract_int_token(selected_value)
    if selected_num is None:
        return None
    pattern = re.compile(r"\bRange\b[^()\n]{0,100}\((\d{1,3})\)\s*(West|East)\b", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    current = str(match.group(1))
    if current == str(selected_num):
        return None
    return _replace_span_op(
        op_id="hitl-range-1",
        reason="Human selected range token to resolve blocking conflict.",
        start_char=int(match.start(1)),
        end_char=int(match.end(1)),
        old_excerpt=current,
        new_text=str(selected_num),
    )


def _build_township_op(*, text: str, selected_value: str) -> dict[str, Any] | None:
    selected_num = _extract_int_token(selected_value)
    if selected_num is None:
        return None
    pattern = re.compile(r"\bTownship\b[^()\n]{0,80}\((\d{1,3})\)\s*(North|South|N|S)\b", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    current = str(match.group(1))
    if current == str(selected_num):
        return None
    return _replace_span_op(
        op_id="hitl-township-1",
        reason="Human selected township token to resolve blocking conflict.",
        start_char=int(match.start(1)),
        end_char=int(match.end(1)),
        old_excerpt=current,
        new_text=str(selected_num),
    )


def _build_section_op(*, text: str, selected_value: str) -> dict[str, Any] | None:
    selected_num = _extract_int_token(selected_value)
    if selected_num is None:
        return None
    pattern = re.compile(r"\bSection\s+(\d{1,3})\b", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    current = str(match.group(1))
    if current == str(selected_num):
        return None
    return _replace_span_op(
        op_id="hitl-section-1",
        reason="Human selected section token to resolve blocking conflict.",
        start_char=int(match.start(1)),
        end_char=int(match.end(1)),
        old_excerpt=current,
        new_text=str(selected_num),
    )


def _build_tie_distance_op(*, text: str, selected_value: str) -> dict[str, Any] | None:
    selected_num = _extract_float_token(selected_value)
    if selected_num is None:
        return None
    pattern = re.compile(r"\b(\d+(?:\.\d+)?)\s*(feet|foot|ft)\b", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    current = str(match.group(1))
    if _float_equals(current, selected_num):
        return None
    return _replace_span_op(
        op_id="hitl-tie-distance-1",
        reason="Human selected tie-distance value to resolve blocking conflict.",
        start_char=int(match.start(1)),
        end_char=int(match.end(1)),
        old_excerpt=current,
        new_text=_format_numeric(selected_num),
    )


def _build_tie_bearing_op(*, text: str, selected_value: str) -> dict[str, Any] | None:
    selected_bearing = _extract_bearing_token(selected_value)
    if not selected_bearing:
        return None
    pattern = re.compile(
        r"\b[NS]\s*\d{1,3}(?:\s*[°º]\s*\d{1,2}(?:\s*'\s*\d{1,2}\")?)?\s*[EW]\b",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    current = str(match.group(0)).strip()
    if current.lower() == selected_bearing.lower():
        return None
    return _replace_span_op(
        op_id="hitl-tie-bearing-1",
        reason="Human selected tie-bearing value to resolve blocking conflict.",
        start_char=int(match.start(0)),
        end_char=int(match.end(0)),
        old_excerpt=current,
        new_text=selected_bearing,
    )


def _build_closure_or_pob_op(*, text: str, selected_value: str) -> dict[str, Any] | None:
    replacement = str(selected_value or "").strip()
    if not replacement:
        return None
    pattern = re.compile(r"\b(point of beginning|pob|closure)\b", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    current = str(match.group(0)).strip()
    if current.lower() == replacement.lower():
        return None
    return _replace_span_op(
        op_id="hitl-closure-1",
        reason="Human selected closure/POB phrasing to resolve blocking conflict.",
        start_char=int(match.start(0)),
        end_char=int(match.end(0)),
        old_excerpt=current,
        new_text=replacement,
    )


def _replace_span_op(
    *,
    op_id: str,
    reason: str,
    start_char: int,
    end_char: int,
    old_excerpt: str,
    new_text: str,
) -> dict[str, Any]:
    return {
        "op_id": op_id,
        "op_type": "replace_span",
        "change_class": "semantic",
        "confidence": "medium",
        "review_required": True,
        "reason": reason,
        "evidence_refs": [],
        "target": {
            "locator_type": "offsets",
            "start_char": int(start_char),
            "end_char": int(end_char),
        },
        "expected_old": {"old_excerpt": str(old_excerpt)},
        "new_text": str(new_text),
    }


def _plan_from_ops(
    *,
    decision_key: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
    ops: list[dict[str, Any]],
    note: str | None,
) -> dict[str, Any]:
    rationale = "Human-guided semantic correction."
    if note:
        rationale = f"{rationale} Note: {str(note)[:200]}"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return {
        "plan_version": "edit_plan_v0",
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "plan_id": f"hitl-{decision_key}-{ts}",
        "summary": f"Apply human-selected {decision_key} override to resolve blocking conflict.",
        "ops": ops,
        "global_flags": {
            "review_required": True,
            "rationale": rationale,
        },
    }


def _extract_int_token(text: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\b", str(text or ""))
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    if value <= 0:
        return None
    return value


def _extract_float_token(text: str) -> float | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", str(text or ""))
    if not match:
        return None
    try:
        value = float(match.group(1))
    except Exception:
        return None
    if value <= 0:
        return None
    return value


def _extract_bearing_token(text: str) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = re.search(
        r"\b([NS]\s*\d{1,3}(?:\s*[°º]\s*\d{1,2}(?:\s*'\s*\d{1,2}\")?)?\s*[EW])\b",
        raw,
        re.IGNORECASE,
    )
    if match:
        return str(match.group(1)).strip()
    if re.search(r"[NSEW]", raw, re.IGNORECASE) and re.search(r"\d", raw):
        return raw[:40]
    return None


def _float_equals(left: str, right: float) -> bool:
    try:
        return abs(float(left) - float(right)) < 0.000001
    except Exception:
        return False


def _format_numeric(value: float) -> str:
    if abs(value - int(value)) < 0.000001:
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")
