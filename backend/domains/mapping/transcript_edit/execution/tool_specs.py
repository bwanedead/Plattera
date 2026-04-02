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
            tool_id="load_transcript_edit_startup_inventory",
            category="observation",
            purpose="First-contact ref inventory: dossier scope, peer T0 draft refs, source image refs, transcript-edit draft refs, lightweight metadata only.",
            expected_request_shape="dossier_id, transcription_id; optional segment_id, run_id.",
            expected_result_shape="TranscriptEditStartupInventory: refs + descriptors; no full draft bodies; structured missing_resource entries if gaps.",
        ),
        SemanticToolSpec(
            tool_id="hydrate_t0_draft_refs",
            category="observation",
            purpose="Load full text for one or more T0 raw draft refs from the startup inventory (peer inputs; no merge or ranking).",
            expected_request_shape="dossier_id, transcription_id, list of t0:raw:<stem> ref_ids; optional max_refs cap.",
            expected_result_shape="Per-ref bodies + metadata; explicit errors for unknown or invalid refs.",
        ),
        SemanticToolSpec(
            tool_id="hydrate_transcript_edit_working_draft",
            category="observation",
            purpose="Load authored transcript-edit working or output artifact when present (refs transcript_edit:working | transcript_edit:output).",
            expected_request_shape="dossier_id, transcription_id, ref_id from startup inventory.",
            expected_result_shape="JSON payload + path metadata, or structured not_found / invalid_ref.",
        ),
        SemanticToolSpec(
            tool_id="load_source_image_context",
            category="image_evidence",
            purpose="Resolve one source image ref from the startup inventory to paths, size, optional dimensions (no image bytes in the declaration).",
            expected_request_shape="dossier_id, transcription_id, image:assoc:<transcription_id>:original|processed ref_id.",
            expected_result_shape="Absolute path, exists flag, size_bytes, optional width_height, basename.",
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
            tool_id="compare_transcript_variants",
            category="comparison",
            purpose="Contrast two or more hydrated draft texts (by ref) for divergence; agent-authored reconciliation.",
            expected_request_shape="List of t0:raw refs or hydrated spans the agent selected; no automatic best pick.",
            expected_result_shape="Diff-style summary of agreements/conflicts; no ranked winner unless agent states one.",
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
            purpose="(Deferred) Persist evidence-grounded edits to the transcript-edit working/output draft; tooling/storage not guaranteed in this slice.",
            expected_request_shape="Target ref from inventory, new text or patch, rationale, evidence refs.",
            expected_result_shape="When implemented: updated ref + confirmation; until then explicit deferred / unavailable signal from runtime.",
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
