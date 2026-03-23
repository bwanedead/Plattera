from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_kernel.models import StepExecutionState

from .execution_action_ids import TX_OPEN_TRANSCRIPT_SPANS

from .disagreement_analysis import extract_numeric_literals
from .span_seeds import load_transcript_text_for_seeds


def open_planner_context_spans(
    *,
    session_manager: Any,
    session_id: str,
    iteration: int,
    dossier_id: str | None,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
    step_fn: Callable[..., Any],
    read_step_outputs_inline_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
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
                sid = finding.get("observation_ref") or finding.get("finding_id") or finding.get("span_id")
                spans.append({"start_char": max(0, start - 100), "end_char": end + 100, "span_id": sid})
    if not spans:
        spans = fallback_spans_for_findings(
            source_transcript_ref=source_transcript_ref,
            top_findings=top_findings,
        )
    step = step_fn(
        session_manager=session_manager,
        session_id=session_id,
        prefix="tx_open_spans",
        iteration=iteration,
        action_type=TX_OPEN_TRANSCRIPT_SPANS,
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
    inline = read_step_outputs_inline_fn(step.step_record)
    raw_spans = inline.get("spans")
    if isinstance(raw_spans, list):
        return [s for s in raw_spans[:8] if isinstance(s, dict)]
    return []


def fallback_spans_for_findings(
    *,
    source_transcript_ref: str,
    top_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    text = load_transcript_text_for_seeds(source_transcript_ref)
    if not text:
        return []
    spans: list[dict[str, Any]] = []
    text_len = len(text)
    window = 1400

    def _add_window(center: int, span_id: str) -> None:
        start = max(0, center - (window // 2))
        end = min(text_len, start + window)
        if end <= start:
            return
        for existing in spans:
            if int(existing["start_char"]) == start and int(existing["end_char"]) == end:
                return
        spans.append({"start_char": start, "end_char": end, "span_id": span_id})

    _add_window(0, "fallback_head")
    _add_window(text_len, "fallback_tail")

    search_terms: list[tuple[str, str]] = []
    for finding in top_findings[:8]:
        if not isinstance(finding, dict):
            continue
        message = str(finding.get("message") or "")
        ml = message.lower()
        if any(t in ml for t in ("range", "township", "section", "plss", "west", "east")):
            search_terms.extend(
                [
                    ("Range seventy-four (74) West", "ctx_plss_r74"),
                    ("Range seventy-five (75) West", "ctx_plss_r75"),
                    ("Township Fourteen (14) North", "ctx_plss_t14"),
                ]
            )
        if "bearing" in ml or "thence" in ml:
            search_terms.extend(
                [
                    ("N. 4°00' W., 1638 feet", "ctx_bearing_tie"),
                    ("thence N.", "ctx_bearing_thence"),
                    ("to the point of beginning", "ctx_bearing_closure"),
                ]
            )
        if "acre" in ml or "feet" in ml:
            search_terms.extend(
                [
                    ("1.4 acres", "ctx_acreage_14"),
                    ("1.9 acres", "ctx_acreage_19"),
                    ("1638 feet", "ctx_distance_1638"),
                ]
            )
        for literal in extract_numeric_literals(message):
            search_terms.append((literal, f"ctx_literal_{literal[:24]}"))

    for term, sid in search_terms:
        idx = text.find(term)
        if idx >= 0:
            _add_window(idx, sid)

    return spans[:8]
