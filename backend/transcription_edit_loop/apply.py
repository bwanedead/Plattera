"""Apply engine for transcription edit loop v0."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import (
    ApplyOpResultV0,
    ApplyReportV0,
    CanonicalTranscriptInputV0,
    EditLoopStartRequestV0,
    EditPlanV0,
    LocatorAnchorsV0,
    LocatorOffsetsV0,
    TranscriptDocumentV0,
    TranscriptSectionV0,
    transcript_text_hash,
)
from .section_adapter import (
    locate_section_for_absolute_span,
    normalize_transcript_payload_to_document,
    sections_to_text_with_index_map,
)


def materialize_canonical_input(request: EditLoopStartRequestV0) -> CanonicalTranscriptInputV0:
    """Materialize canonical transcript text from either artifact ref or direct text."""
    if request.source_text and request.source_text.strip():
        document = TranscriptDocumentV0(
            source_transcript_ref="inline://source_text",
            sections=[TranscriptSectionV0(id="section_001", body=request.source_text)],
        )
        source_ref = "inline://source_text"
    else:
        source_ref = str(request.source_transcript_ref or "").strip()
        payload = json.loads(Path(source_ref).read_text(encoding="utf-8"))
        document = normalize_transcript_payload_to_document(
            payload=payload,
            source_transcript_ref=source_ref,
        )
    text, _ = sections_to_text_with_index_map(document.sections)
    return CanonicalTranscriptInputV0(
        source_transcript_ref=source_ref,
        source_transcript_hash=transcript_text_hash(text),
        transcript_text=text,
        transcript_sections=document.sections,
        source_image_refs=list(request.source_image_refs),
        dossier_id=request.dossier_id,
        mode=request.mode,
    )


def apply_plan(
    *,
    plan: EditPlanV0,
    transcript_text: str,
    ) -> ApplyReportV0:
    """Apply plan to transcript text with global and per-op drift checks."""
    current_text = transcript_text
    actual_source_hash = transcript_text_hash(current_text)
    if actual_source_hash != plan.source_transcript_hash:
        return ApplyReportV0(
            plan_id=plan.plan_id,
            source_transcript_ref=plan.source_transcript_ref,
            source_transcript_hash_expected=plan.source_transcript_hash,
            source_transcript_hash_actual=actual_source_hash,
            root_status="refused",
            root_reason_code="source_transcript_hash_mismatch",
            applied_count=0,
            refused_count=len(plan.ops),
            op_results=[
                ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="root_hash_mismatch") for op in plan.ops
            ],
            output_transcript_ref=plan.source_transcript_ref,
            output_transcript_text=transcript_text,
            output_transcript_hash=actual_source_hash,
        )

    results: list[ApplyOpResultV0] = []
    applied = 0
    refused = 0
    for op in plan.ops:
        resolved = _resolve_target_span(current_text, op.target)
        if resolved is None:
            refused += 1
            results.append(ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="locator_not_found"))
            continue
        span_start, span_end = resolved
        target_text = current_text[span_start:span_end]
        match_start = target_text.find(op.expected_old.old_excerpt)
        if match_start < 0:
            refused += 1
            results.append(ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="drift_mismatch"))
            continue
        matched_old = op.expected_old.old_excerpt
        if op.expected_old.old_hash and transcript_text_hash(matched_old) != op.expected_old.old_hash:
            refused += 1
            results.append(ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="old_hash_mismatch"))
            continue

        op_abs_start = span_start + match_start
        op_abs_end = op_abs_start + len(matched_old)
        current_text = current_text[:op_abs_start] + op.new_text + current_text[op_abs_end:]
        applied += 1
        results.append(
            ApplyOpResultV0(
                op_id=op.op_id,
                status="applied",
                locator_span={"start_char": op_abs_start, "end_char": op_abs_start + len(op.new_text)},
            )
        )

    final_hash = transcript_text_hash(current_text)
    return ApplyReportV0(
        plan_id=plan.plan_id,
        source_transcript_ref=plan.source_transcript_ref,
        source_transcript_hash_expected=plan.source_transcript_hash,
        source_transcript_hash_actual=actual_source_hash,
        root_status="applied",
        applied_count=applied,
        refused_count=refused,
        op_results=results,
        output_transcript_ref=plan.source_transcript_ref,
        output_transcript_text=current_text,
        output_transcript_hash=final_hash,
    )


def apply_plan_to_sections(
    *,
    plan: EditPlanV0,
    document: TranscriptDocumentV0,
) -> tuple[ApplyReportV0, TranscriptDocumentV0]:
    """Apply plan against section-preserving transcript document."""
    current_sections = [section.model_copy(deep=True) for section in document.sections]
    current_text, _ = sections_to_text_with_index_map(current_sections)
    actual_source_hash = transcript_text_hash(current_text)
    if actual_source_hash != plan.source_transcript_hash:
        report = ApplyReportV0(
            plan_id=plan.plan_id,
            source_transcript_ref=plan.source_transcript_ref,
            source_transcript_hash_expected=plan.source_transcript_hash,
            source_transcript_hash_actual=actual_source_hash,
            root_status="refused",
            root_reason_code="source_transcript_hash_mismatch",
            applied_count=0,
            refused_count=len(plan.ops),
            op_results=[
                ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="root_hash_mismatch")
                for op in plan.ops
            ],
            output_transcript_ref=plan.source_transcript_ref,
            output_transcript_text=current_text,
            output_transcript_hash=actual_source_hash,
        )
        return report, document.model_copy(deep=True)

    results: list[ApplyOpResultV0] = []
    applied = 0
    refused = 0
    for op in plan.ops:
        current_text, spans = sections_to_text_with_index_map(current_sections)
        resolved = _resolve_target_span(current_text, op.target)
        if resolved is None:
            refused += 1
            results.append(ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="locator_not_found"))
            continue

        span_start, span_end = resolved
        target_text = current_text[span_start:span_end]
        match_start = target_text.find(op.expected_old.old_excerpt)
        if match_start < 0:
            refused += 1
            results.append(ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="drift_mismatch"))
            continue
        matched_old = op.expected_old.old_excerpt
        if op.expected_old.old_hash and transcript_text_hash(matched_old) != op.expected_old.old_hash:
            refused += 1
            results.append(ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="old_hash_mismatch"))
            continue

        op_abs_start = span_start + match_start
        op_abs_end = op_abs_start + len(matched_old)
        section_span = locate_section_for_absolute_span(spans, abs_start=op_abs_start, abs_end=op_abs_end)
        if section_span is None:
            refused += 1
            results.append(
                ApplyOpResultV0(op_id=op.op_id, status="refused", reason_code="cross_section_edit_not_supported")
            )
            continue
        section = current_sections[section_span.section_index]
        local_start = op_abs_start - section_span.start_char
        local_end = op_abs_end - section_span.start_char
        section.body = section.body[:local_start] + op.new_text + section.body[local_end:]
        applied += 1
        results.append(
            ApplyOpResultV0(
                op_id=op.op_id,
                status="applied",
                locator_span={"start_char": op_abs_start, "end_char": op_abs_start + len(op.new_text)},
            )
        )

    output_text, _ = sections_to_text_with_index_map(current_sections)
    output_hash = transcript_text_hash(output_text)
    output_document = document.model_copy(deep=True)
    output_document.sections = current_sections
    output_document.source_transcript_hash = output_hash
    report = ApplyReportV0(
        plan_id=plan.plan_id,
        source_transcript_ref=plan.source_transcript_ref,
        source_transcript_hash_expected=plan.source_transcript_hash,
        source_transcript_hash_actual=actual_source_hash,
        root_status="applied",
        applied_count=applied,
        refused_count=refused,
        op_results=results,
        output_transcript_ref=plan.source_transcript_ref,
        output_transcript_text=output_text,
        output_transcript_hash=output_hash,
    )
    return report, output_document


def _resolve_target_span(text: str, locator: LocatorAnchorsV0 | LocatorOffsetsV0) -> tuple[int, int] | None:
    if isinstance(locator, LocatorOffsetsV0):
        if locator.end_char > len(text):
            return None
        return (locator.start_char, locator.end_char)
    return _resolve_anchor_span(text, locator)


def _resolve_anchor_span(text: str, locator: LocatorAnchorsV0) -> tuple[int, int] | None:
    start_from = 0
    start_idx = -1
    end_idx = -1
    for _ in range(locator.occurrence):
        start_idx = text.find(locator.start_anchor, start_from)
        if start_idx < 0:
            return None
        end_search_from = start_idx + len(locator.start_anchor)
        end_idx = text.find(locator.end_anchor, end_search_from)
        if end_idx < 0:
            return None
        start_from = end_idx + len(locator.end_anchor)
    return (start_idx, end_idx + len(locator.end_anchor))
