"""Review-bundle inspection is the canonical human path for prompt events.

The bundle keeps trace, derived run-summary envelope, review summary, and prompt-event
snapshots together so prompt observability remains inspectable without adding a
parallel reporting regime.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..observability.summary import (
    SharedRunSummaryEnvelope,
    build_mission_flow_run_summary,
    build_registered_run_summary,
)
from ..tracing.schema import CanonicalTraceRecord
from ..tracing.service import build_canonical_trace_from_payload
from .reporting import (
    ReviewAggregateSummary,
    RunReviewSummary,
    build_review_aggregate,
    build_run_review_summary,
)

REVIEW_BUNDLE_VERSION = "review_bundle.v1"
REVIEW_TOOL_VERSION = "review.tool.v1"


def build_single_run_review(
    *,
    payload: dict[str, Any],
    loop_family: str | None = None,
) -> dict[str, Any]:
    trace, run_summary, review = _assemble_run_review(payload=payload, loop_family=loop_family)
    return _review_artifact(trace=trace, run_summary=run_summary, review=review)


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
        trace, run_summary, review = _assemble_run_review(payload=payload, loop_family=loop_family)
        review_summaries.append(review)
        per_run.append(_review_artifact(trace=trace, run_summary=run_summary, review=review))

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


def build_single_run_review_bundle(
    *,
    payload: dict[str, Any],
    loop_family: str | None = None,
    input_ref: str | None = None,
) -> dict[str, Any]:
    trace, run_summary, review = _assemble_run_review(payload=payload, loop_family=loop_family)
    return _build_review_bundle(
        mode="single_run",
        runs=[
            _review_bundle_run(
                trace=trace,
                run_summary=run_summary,
                review=review,
                input_ref=input_ref,
            )
        ],
        aggregate=build_review_aggregate(summaries=[review]),
        input_payload_paths=[input_ref] if input_ref else [],
    )


def build_single_run_review_bundle_from_path(
    *,
    payload_path: str,
    loop_family: str | None = None,
) -> dict[str, Any]:
    payload = _load_json_object(payload_path)
    return build_single_run_review_bundle(
        payload=payload,
        loop_family=loop_family,
        input_ref=payload_path,
    )


def build_multi_run_review_bundle(
    *,
    payloads: list[dict[str, Any]],
    loop_family: str | None = None,
    input_refs: list[str] | None = None,
) -> dict[str, Any]:
    per_run: list[dict[str, Any]] = []
    review_summaries: list[RunReviewSummary] = []
    refs = input_refs if isinstance(input_refs, list) else []
    for idx, payload in enumerate(payloads):
        trace, run_summary, review = _assemble_run_review(payload=payload, loop_family=loop_family)
        review_summaries.append(review)
        input_ref = refs[idx] if idx < len(refs) and isinstance(refs[idx], str) else None
        per_run.append(
            _review_bundle_run(
                trace=trace,
                run_summary=run_summary,
                review=review,
                input_ref=input_ref,
            )
        )

    aggregate = build_review_aggregate(summaries=review_summaries)
    return _build_review_bundle(
        mode="multi_run",
        runs=per_run,
        aggregate=aggregate,
        input_payload_paths=[path for path in refs if isinstance(path, str) and path.strip()],
    )


def build_multi_run_review_bundle_from_paths(
    *,
    payload_paths: list[str],
    loop_family: str | None = None,
) -> dict[str, Any]:
    payloads = [_load_json_object(path) for path in payload_paths]
    return build_multi_run_review_bundle(
        payloads=payloads,
        loop_family=loop_family,
        input_refs=payload_paths,
    )


def maybe_write_review_output(*, review_output: dict[str, Any], output_path: str | None = None) -> dict[str, Any]:
    if not output_path:
        return review_output
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(review_output, indent=2, sort_keys=True), encoding="utf-8")
    return review_output


def _assemble_run_review(
    *,
    payload: dict[str, Any],
    loop_family: str | None,
) -> tuple[CanonicalTraceRecord, SharedRunSummaryEnvelope, RunReviewSummary]:
    trace = _build_trace(payload=payload, loop_family=loop_family)
    run_summary = _build_run_summary(payload=payload, loop_family=trace.loop_family)
    review = build_run_review_summary(trace=trace, run_summary=run_summary)
    return trace, run_summary, review


def _build_trace(*, payload: dict[str, Any], loop_family: str | None) -> CanonicalTraceRecord:
    if loop_family is None:
        return build_canonical_trace_from_payload(payload=payload)
    return build_canonical_trace_from_payload(payload=payload, loop_family=loop_family)


def _build_run_summary(*, payload: dict[str, Any], loop_family: str) -> SharedRunSummaryEnvelope:
    if loop_family == "mission_flow":
        mission_flow_payload: dict[str, Any] | None = None
        nested = payload.get("mission_flow")
        if isinstance(nested, dict):
            mission_flow_payload = nested
        if mission_flow_payload is None:
            mission_flow_payload = payload if isinstance(payload, dict) else {}
        if not isinstance(mission_flow_payload, dict):
            raise ValueError("invalid mission_flow payload for run-summary build")
        return build_mission_flow_run_summary(mission_flow_payload=mission_flow_payload)
    return build_registered_run_summary(loop_family=loop_family, payload=payload)


def _review_artifact(
    *,
    trace: CanonicalTraceRecord,
    run_summary: SharedRunSummaryEnvelope,
    review: RunReviewSummary,
) -> dict[str, Any]:
    dumped = run_summary.model_dump(mode="json")
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
        "run_summary": dumped,
        "review": review.model_dump(mode="json"),
        "prompt_events": extract_prompt_events_from_trace(trace=trace),
    }


def _review_bundle_run(
    *,
    trace: CanonicalTraceRecord,
    run_summary: SharedRunSummaryEnvelope,
    review: RunReviewSummary,
    input_ref: str | None,
) -> dict[str, Any]:
    inferred_refs = _infer_input_refs(trace=trace)
    run_input: dict[str, Any] = {"source_refs": inferred_refs}
    if isinstance(input_ref, str) and input_ref.strip():
        run_input["payload_path"] = input_ref
    dumped = run_summary.model_dump(mode="json")
    return {
        "run_id": trace.run_id,
        "loop_family": trace.loop_family,
        "input": run_input,
        "trace": trace.model_dump(mode="json"),
        "run_summary": dumped,
        "review": review.model_dump(mode="json"),
        "prompt_events": extract_prompt_events_from_trace(trace=trace),
    }


def _build_review_bundle(
    *,
    mode: str,
    runs: list[dict[str, Any]],
    aggregate: ReviewAggregateSummary,
    input_payload_paths: list[str],
) -> dict[str, Any]:
    run_count = len(runs)
    families = sorted({str(run.get("loop_family") or "").strip() for run in runs if str(run.get("loop_family") or "").strip()})
    bundle_loop_family = families[0] if len(families) == 1 else "mixed"
    partial_run_ids = [
        str(run.get("run_id") or "")
        for run in runs
        if isinstance(run.get("trace"), dict) and str((run.get("trace") or {}).get("completeness_status") or "") == "partial"
    ]
    partial_run_ids = [run_id for run_id in partial_run_ids if run_id][:20]
    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": "harness.review.tool",
            "tool_version": REVIEW_TOOL_VERSION,
            "artifact_version": REVIEW_BUNDLE_VERSION,
            "mode": mode,
            "loop_family": bundle_loop_family,
            "run_count": run_count,
            "input_payload_paths": input_payload_paths,
            "partial_trace_note": {
                "contains_partial_traces": len(partial_run_ids) > 0,
                "partial_run_count": len(partial_run_ids),
                "partial_run_ids": partial_run_ids,
            },
        },
        "runs": runs,
        "aggregate": aggregate.model_dump(mode="json"),
    }


def _infer_input_refs(*, trace: CanonicalTraceRecord) -> list[str]:
    refs: list[str] = []
    for key in ("run_artifact_ref", "snapshot_ref", "trace_ref"):
        value = trace.start_context_summary.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
    for row in trace.start_context_summary.get("latest_ref_keys") or []:
        if isinstance(row, str) and row.strip():
            refs.append(f"latest_ref:{row.strip()}")
    return refs[:16]


def extract_prompt_events_from_trace(*, trace: CanonicalTraceRecord) -> list[dict[str, Any]]:
    prompt_events: list[dict[str, Any]] = []
    for event in trace.events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        prompt_event = payload.get("prompt_event") if isinstance(payload.get("prompt_event"), dict) else None
        if not (event.phase == "prompt_event" or prompt_event is not None):
            continue
        prompt_event_data = prompt_event or payload
        metadata = prompt_event_data.get("metadata") if isinstance(prompt_event_data.get("metadata"), dict) else {}
        prompt_events.append(
            {
                "event_id": event.event_id,
                "event_index": event.event_index,
                "iteration_index": event.iteration_index,
                "phase": event.phase,
                "surface": str(metadata.get("surface") or payload.get("surface") or "").strip(),
                "pack_id": str(metadata.get("pack_id") or payload.get("pack_id") or "").strip(),
                "model": str(metadata.get("model") or payload.get("model") or "").strip(),
                "prompt_event_id": str(metadata.get("prompt_event_id") or payload.get("prompt_event_id") or "").strip() or None,
                "outcome_kind": str(prompt_event_data.get("outcome_kind") or "").strip() or None,
                "outcome_ref": str(prompt_event_data.get("outcome_ref") or "").strip() or None,
                "prompt_event": prompt_event_data,
            }
        )
    return prompt_events


def _load_json_object(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object payload at {path}")
    return payload
