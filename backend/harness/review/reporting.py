from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..run_state import SharedRunStateEnvelope
from ..tracing.schema import CanonicalTraceRecord

_MAX_TOP_ITEMS = 6
_MAX_FLAGS = 12


class RunReviewSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    loop_family: str = Field(min_length=1, max_length=64)
    terminal_class: str | None = Field(default=None, max_length=64)
    reason_code: str | None = Field(default=None, max_length=256)
    event_count: int = Field(ge=0)
    iteration_count: int = Field(ge=0)
    waiting_human_present: bool
    waiting_evidence_present: bool
    verification_present: bool
    blocker_transition_present: bool
    partial_trace: bool
    normalization_warnings: list[str] = Field(default_factory=list, max_length=40)
    review_flags: list[str] = Field(default_factory=list, max_length=_MAX_FLAGS)
    recurring_event_kinds: list[dict[str, Any]] = Field(default_factory=list, max_length=_MAX_TOP_ITEMS)
    recurring_phases: list[dict[str, Any]] = Field(default_factory=list, max_length=_MAX_TOP_ITEMS)
    recurring_action_shapes: list[dict[str, Any]] = Field(default_factory=list, max_length=_MAX_TOP_ITEMS)
    synthesized_event_ratio: float = Field(ge=0.0, le=1.0)
    emitted_pattern_summary: str = Field(default="", max_length=280)


class ReviewAggregateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_count: int = Field(ge=0)
    terminal_class_distribution: dict[str, int] = Field(default_factory=dict)
    reason_code_distribution: dict[str, int] = Field(default_factory=dict)
    loop_family_distribution: dict[str, int] = Field(default_factory=dict)
    partial_trace_rate: float = Field(ge=0.0, le=1.0)
    waiting_human_rate: float = Field(ge=0.0, le=1.0)
    waiting_evidence_rate: float = Field(ge=0.0, le=1.0)
    verification_missing_on_completion_count: int = Field(ge=0)
    recurring_pattern_summary: list[dict[str, Any]] = Field(default_factory=list, max_length=12)


def build_run_review_summary(
    *,
    trace: CanonicalTraceRecord,
    run_state: SharedRunStateEnvelope | None = None,
) -> RunReviewSummary:
    event_kinds = [event.event_kind for event in trace.events]
    phases = [event.phase for event in trace.events if event.phase]
    event_count = len(trace.events)
    iteration_count = _iteration_count(trace)
    verification_present = any(kind == "verification" for kind in event_kinds)
    blocker_transition_present = any(kind == "blocker_transition" for kind in event_kinds)
    waiting_human_present = _waiting_human_present(trace=trace, run_state=run_state)
    waiting_evidence_present = _waiting_evidence_present(trace=trace, run_state=run_state)
    synthesized_count = sum(
        1 for event in trace.events if isinstance(event.payload, dict) and bool(event.payload.get("synthesized"))
    )
    synthesized_ratio = (synthesized_count / event_count) if event_count > 0 else 0.0
    recurring_kinds = _top_counter_items(Counter(event_kinds))
    recurring_phases = _top_counter_items(Counter(phases))
    recurring_action_shapes = _action_shape_patterns(trace)

    flags = _derive_review_flags(
        trace=trace,
        verification_present=verification_present,
        blocker_transition_present=blocker_transition_present,
        waiting_human_present=waiting_human_present,
        waiting_evidence_present=waiting_evidence_present,
        iteration_count=iteration_count,
        event_count=event_count,
    )
    emitted_pattern_summary = _emitted_pattern_summary(
        recurring_event_kinds=recurring_kinds,
        recurring_phases=recurring_phases,
        synthesized_ratio=synthesized_ratio,
    )

    terminal_class = run_state.terminal_summary.terminal_class if run_state else trace.terminal.terminal_class
    reason_code = run_state.terminal_summary.reason_code if run_state else trace.terminal.terminal_reason_code
    return RunReviewSummary(
        run_id=trace.run_id,
        loop_family=trace.loop_family,
        terminal_class=terminal_class,
        reason_code=reason_code,
        event_count=event_count,
        iteration_count=iteration_count,
        waiting_human_present=waiting_human_present,
        waiting_evidence_present=waiting_evidence_present,
        verification_present=verification_present,
        blocker_transition_present=blocker_transition_present,
        partial_trace=trace.completeness_status == "partial",
        normalization_warnings=list(trace.normalization_warnings),
        review_flags=flags,
        recurring_event_kinds=recurring_kinds,
        recurring_phases=recurring_phases,
        recurring_action_shapes=recurring_action_shapes,
        synthesized_event_ratio=round(synthesized_ratio, 4),
        emitted_pattern_summary=emitted_pattern_summary,
    )


def build_review_aggregate(*, summaries: list[RunReviewSummary]) -> ReviewAggregateSummary:
    run_count = len(summaries)
    terminal_dist: Counter[str] = Counter()
    reason_dist: Counter[str] = Counter()
    family_dist: Counter[str] = Counter()
    partial_count = 0
    waiting_human_count = 0
    waiting_evidence_count = 0
    verification_missing_on_completion_count = 0
    pattern_counter: Counter[str] = Counter()

    for summary in summaries:
        if summary.terminal_class:
            terminal_dist[str(summary.terminal_class)] += 1
        if summary.reason_code:
            reason_dist[str(summary.reason_code)] += 1
        family_dist[str(summary.loop_family)] += 1
        if summary.partial_trace:
            partial_count += 1
        if summary.waiting_human_present:
            waiting_human_count += 1
        if summary.waiting_evidence_present:
            waiting_evidence_count += 1
        if summary.terminal_class == "completed" and not summary.verification_present:
            verification_missing_on_completion_count += 1
        for row in summary.recurring_action_shapes[:3]:
            signature = str(row.get("signature") or "").strip()
            if signature:
                pattern_counter[signature] += int(row.get("count") or 0)

    return ReviewAggregateSummary(
        run_count=run_count,
        terminal_class_distribution=dict(terminal_dist),
        reason_code_distribution=dict(reason_dist),
        loop_family_distribution=dict(family_dist),
        partial_trace_rate=_safe_rate(partial_count, run_count),
        waiting_human_rate=_safe_rate(waiting_human_count, run_count),
        waiting_evidence_rate=_safe_rate(waiting_evidence_count, run_count),
        verification_missing_on_completion_count=verification_missing_on_completion_count,
        recurring_pattern_summary=[
            {"signature": signature, "count": count}
            for signature, count in pattern_counter.most_common(12)
        ],
    )


def _iteration_count(trace: CanonicalTraceRecord) -> int:
    max_idx = max((event.iteration_index for event in trace.events if event.iteration_index is not None), default=-1)
    return max_idx + 1 if max_idx >= 0 else 0


def _waiting_human_present(*, trace: CanonicalTraceRecord, run_state: SharedRunStateEnvelope | None) -> bool:
    if run_state is not None:
        return bool(run_state.waiting_summary.waiting and run_state.waiting_summary.waiting_kind == "human_feedback")
    if trace.terminal.terminal_class == "waiting_human":
        return True
    return any(event.event_kind == "hitl_escalation" for event in trace.events)


def _waiting_evidence_present(*, trace: CanonicalTraceRecord, run_state: SharedRunStateEnvelope | None) -> bool:
    if run_state is not None:
        return bool(run_state.waiting_summary.waiting and run_state.waiting_summary.waiting_kind == "evidence")
    if trace.terminal.terminal_class == "waiting_evidence":
        return True
    return any(
        event.event_kind == "retrieval_evidence" and event.status in {"waiting", "failed"}
        for event in trace.events
    )


def _derive_review_flags(
    *,
    trace: CanonicalTraceRecord,
    verification_present: bool,
    blocker_transition_present: bool,
    waiting_human_present: bool,
    waiting_evidence_present: bool,
    iteration_count: int,
    event_count: int,
) -> list[str]:
    flags: list[str] = []
    terminal_class = trace.terminal.terminal_class
    if terminal_class == "completed" and not verification_present:
        flags.append("missing_verification_before_completion")

    kind_counter = Counter(event.event_kind for event in trace.events)
    dominant_kind, dominant_count = kind_counter.most_common(1)[0] if kind_counter else ("", 0)
    if dominant_kind in {"tool_execution", "model_proposal"} and dominant_count >= 4:
        flags.append("repeated_same_kind_actions")

    if terminal_class in {"failed", "blocked", "exhausted"} and not verification_present and event_count <= 6:
        flags.append("premature_failure_sparse_evidence")

    has_hitl = any(event.event_kind == "hitl_escalation" for event in trace.events)
    if waiting_human_present and not has_hitl and not blocker_transition_present:
        flags.append("waiting_human_without_blocker_hitl_evidence")

    if waiting_evidence_present:
        has_retrieval = any(event.event_kind == "retrieval_evidence" for event in trace.events)
        if not has_retrieval:
            flags.append("waiting_evidence_without_retrieval_signal")

    if iteration_count >= 8 or event_count >= 60:
        flags.append("high_churn_many_iterations")

    if trace.completeness_status == "partial":
        flags.append("partial_trace_needs_caution")
    return flags[:_MAX_FLAGS]


def _top_counter_items(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in counter.most_common(_MAX_TOP_ITEMS) if key]


def _action_shape_patterns(trace: CanonicalTraceRecord) -> list[dict[str, Any]]:
    pattern_counts: Counter[str] = Counter()
    for event in trace.events:
        if event.event_kind not in {"model_proposal", "tool_execution", "retrieval_evidence", "verification"}:
            continue
        keys = sorted(str(key) for key in event.payload.keys() if str(key).strip())[:8]
        if not keys:
            continue
        signature = f"{event.event_kind}:{'|'.join(keys)}"
        pattern_counts[signature] += 1
    return [
        {"signature": signature, "count": count}
        for signature, count in pattern_counts.most_common(_MAX_TOP_ITEMS)
    ]


def _emitted_pattern_summary(
    *,
    recurring_event_kinds: list[dict[str, Any]],
    recurring_phases: list[dict[str, Any]],
    synthesized_ratio: float,
) -> str:
    dominant_kind = str(recurring_event_kinds[0]["value"]) if recurring_event_kinds else "none"
    dominant_phase = str(recurring_phases[0]["value"]) if recurring_phases else "none"
    synth_pct = int(round(max(0.0, min(1.0, synthesized_ratio)) * 100))
    return f"dominant_kind={dominant_kind}; dominant_phase={dominant_phase}; synthesized={synth_pct}%"


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)
