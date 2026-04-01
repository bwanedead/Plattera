"""Semantic tool menu for transcript edit—IDs, intent, and expected shapes only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticToolSpec:
    tool_id: str
    category: str
    purpose: str
    expected_request_shape: str
    expected_result_shape: str


def build_transcript_edit_tool_specs() -> tuple[SemanticToolSpec, ...]:
    return (
        SemanticToolSpec(
            tool_id="load_transcript_run_bundle",
            category="observation",
            purpose="Load dossier/run/head/final/version context as one semantic bundle for orientation.",
            expected_request_shape="Refs: dossier_id, segment_id or transcription scope, run_id optional; optional focus issue id.",
            expected_result_shape="Structured bundle: scope ids, draft head pointers, finals, variant inventory summary, key artifact refs.",
        ),
        SemanticToolSpec(
            tool_id="list_transcript_variants",
            category="observation",
            purpose="Enumerate raw, alignment, consensus, and other draft candidates for comparison.",
            expected_request_shape="Scope refs plus optional filters (e.g. segment, run, version kind).",
            expected_result_shape="List of variant descriptors: id, kind, label, status, short preview, lineage hints.",
        ),
        SemanticToolSpec(
            tool_id="load_transcript_variant",
            category="observation",
            purpose="Fetch one specific draft/version body for close reading.",
            expected_request_shape="Variant ref (draft id + version key or logical label).",
            expected_result_shape="Full text (or segment-scoped text), metadata, provenance summary.",
        ),
        SemanticToolSpec(
            tool_id="image_verify",
            category="image_evidence",
            purpose="Ground a textual claim in image evidence (confirm, refute, or narrow uncertainty).",
            expected_request_shape="Image ref(s), optional crop/box, transcript span or claim under test.",
            expected_result_shape="Visual finding narrative, confidence posture, suggested next evidence if inconclusive.",
        ),
        SemanticToolSpec(
            tool_id="image_crop_refine",
            category="image_evidence",
            purpose="Refine the region of interest when the current crop is insufficient.",
            expected_request_shape="Prior crop ref, adjustment intent (expand, shift, higher resolution request).",
            expected_result_shape="New crop ref or refusal with reason; ties back to same claim id if provided.",
        ),
        SemanticToolSpec(
            tool_id="load_source_image_context",
            category="image_evidence",
            purpose="Load imagery associated with the transcription or segment under edit.",
            expected_request_shape="Dossier/transcription/segment/run scope; optional page or asset hint.",
            expected_result_shape="Image handles, dimensions, page ordering, linkage to segments/runs.",
        ),
        SemanticToolSpec(
            tool_id="compare_transcript_variants",
            category="comparison",
            purpose="Contrast two or more draft candidates for divergence and merge decisions.",
            expected_request_shape="List of variant refs; optional alignment hints or focus spans.",
            expected_result_shape="Diff-style summary: agreements, conflicts, recommended reconciliation angles.",
        ),
        SemanticToolSpec(
            tool_id="compare_transcript_to_image",
            category="comparison",
            purpose="Align claimed text to pixels—spot OCR slips, line breaks, missing tokens.",
            expected_request_shape="Transcript span ref + image ref/crop; optional character-level ask.",
            expected_result_shape="Span-to-image mapping narrative, defect candidates, crop suggestions.",
        ),
        SemanticToolSpec(
            tool_id="save_transcript_edit",
            category="mutation",
            purpose="Persist an evidence-grounded edit to an appropriate draft/version (tooling chooses storage rules).",
            expected_request_shape="Target draft/version ref, new text or patch, rationale summary, evidence refs.",
            expected_result_shape="Updated variant ref, version stamp, confirmation of persistence outcome.",
        ),
        SemanticToolSpec(
            tool_id="set_transcript_head",
            category="mutation",
            purpose="Select or revise which draft/version acts as the working head when policy allows.",
            expected_request_shape="Head target ref + reason tied to evidence or consensus posture.",
            expected_result_shape="New head pointer, prior head preserved per product rules.",
        ),
        SemanticToolSpec(
            tool_id="set_segment_final",
            category="mutation",
            purpose="Pin the per-segment final draft selection when the transcript is ready.",
            expected_request_shape="Segment ref, final draft ref, verification summary pointer.",
            expected_result_shape="Final registry acknowledgment, blockers if policy rejects.",
        ),
        SemanticToolSpec(
            tool_id="clear_segment_final",
            category="mutation",
            purpose="Clear a pinned final when evidence shows the selection is wrong or stale.",
            expected_request_shape="Segment ref, reason, optional replacement candidate ref.",
            expected_result_shape="Cleared state confirmation, downstream readiness downgrade flags.",
        ),
        SemanticToolSpec(
            tool_id="request_alignment_refresh",
            category="refresh_request",
            purpose="Ask the system to re-run or refresh alignment-derived drafts for stale or ambiguous spans.",
            expected_request_shape="Scope + span or variant refs + reason; no orchestration guarantees.",
            expected_result_shape="Job or ticket ref, expected artifact keys when complete (semantic, not polling).",
        ),
        SemanticToolSpec(
            tool_id="request_consensus_refresh",
            category="refresh_request",
            purpose="Ask for refreshed consensus/LLM-merge output when drafts diverge materially.",
            expected_request_shape="Variant set ref or run ref; reason tied to ambiguity or defect ids.",
            expected_result_shape="Job or ticket ref, semantic description of pending outputs.",
        ),
        SemanticToolSpec(
            tool_id="request_human_verification",
            category="refresh_request",
            purpose="Escalate to human verification when automated evidence is insufficient.",
            expected_request_shape="Issue summary, minimal repro refs (image + spans), urgency note.",
            expected_result_shape="Ticket ref; semantic expectation of human response shape when it arrives.",
        ),
    )
