from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..run_state import (
    SharedRunStateEnvelope,
    build_controller_kernel_run_state,
    build_transcript_edit_run_state,
)
from ..tracing.schema import CanonicalTraceRecord
from ..tracing.service import build_canonical_trace_from_payload
from .reporting import (
    ReviewAggregateSummary,
    RunReviewSummary,
    build_review_aggregate,
    build_run_review_summary,
)


def build_single_run_review(
    *,
    payload: dict[str, Any],
    loop_family: str | None = None,
) -> dict[str, Any]:
    trace = _build_trace(payload=payload, loop_family=loop_family)
    run_state = _build_run_state(payload=payload, loop_family=trace.loop_family)
    review = build_run_review_summary(trace=trace, run_state=run_state)
    return _review_artifact(trace=trace, run_state=run_state, review=review)


def build_single_run_review_from_path(
    *,
    payload_path: str,
    loop_family: str | None = None,
) -> dict[str, Any]:
    payload = _load_json_object(payload_path)
    return build_single_run_review(payload=payload, loop_family=loop_family)


def build_multi_run_review(
    *,
    payloads: list[dict[str, Any]],
    loop_family: str | None = None,
) -> dict[str, Any]:
    per_run: list[dict[str, Any]] = []
    review_summaries: list[RunReviewSummary] = []
    for payload in payloads:
        trace = _build_trace(payload=payload, loop_family=loop_family)
        run_state = _build_run_state(payload=payload, loop_family=trace.loop_family)
        review = build_run_review_summary(trace=trace, run_state=run_state)
        review_summaries.append(review)
        per_run.append(_review_artifact(trace=trace, run_state=run_state, review=review))

    aggregate = build_review_aggregate(summaries=review_summaries)
    return {
        "run_count": len(per_run),
        "runs": per_run,
        "aggregate": aggregate.model_dump(mode="json"),
    }


def build_multi_run_review_from_paths(
    *,
    payload_paths: list[str],
    loop_family: str | None = None,
) -> dict[str, Any]:
    payloads = [_load_json_object(path) for path in payload_paths]
    return build_multi_run_review(payloads=payloads, loop_family=loop_family)


def maybe_write_review_output(*, review_output: dict[str, Any], output_path: str | None = None) -> dict[str, Any]:
    if not output_path:
        return review_output
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(review_output, indent=2, sort_keys=True), encoding="utf-8")
    return review_output


def _build_trace(*, payload: dict[str, Any], loop_family: str | None) -> CanonicalTraceRecord:
    if loop_family is None:
        return build_canonical_trace_from_payload(payload=payload)
    if loop_family not in {"controller_kernel", "transcript_edit"}:
        raise ValueError(f"unsupported loop_family: {loop_family}")
    return build_canonical_trace_from_payload(payload=payload, loop_family=loop_family)


def _build_run_state(*, payload: dict[str, Any], loop_family: str) -> SharedRunStateEnvelope:
    if loop_family == "controller_kernel":
        controller_transcript = payload.get("controller_transcript")
        run_artifact = payload.get("run_artifact")
        if not isinstance(controller_transcript, dict) or not isinstance(run_artifact, dict):
            raise ValueError(
                "invalid controller_kernel payload for run-state build: expected object fields "
                "'controller_transcript' and 'run_artifact'"
            )
        return build_controller_kernel_run_state(
            controller_transcript=controller_transcript,
            run_artifact=run_artifact,
        )
    if loop_family == "transcript_edit":
        return build_transcript_edit_run_state(run_snapshot=payload)
    raise ValueError(f"unsupported loop_family: {loop_family}")


def _review_artifact(
    *,
    trace: CanonicalTraceRecord,
    run_state: SharedRunStateEnvelope,
    review: RunReviewSummary,
) -> dict[str, Any]:
    return {
        "trace": {
            "trace_id": trace.trace_id,
            "run_id": trace.run_id,
            "loop_family": trace.loop_family,
            "terminal_class": trace.terminal.terminal_class,
            "terminal_reason_code": trace.terminal.terminal_reason_code,
            "completeness_status": trace.completeness_status,
            "missing_components": list(trace.missing_components),
            "normalization_warnings": list(trace.normalization_warnings),
            "event_count": len(trace.events),
        },
        "run_state": run_state.model_dump(mode="json"),
        "review": review.model_dump(mode="json"),
    }


def _load_json_object(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object payload at {path}")
    return payload

