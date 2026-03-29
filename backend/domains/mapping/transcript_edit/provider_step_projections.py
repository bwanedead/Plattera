"""Transcript-edit domain: map provider step outputs into run artifact refs (Phase 33).

Owned by the transcript-edit pack — not ``agent_kernel.session``. Session only dispatches
``ActionExecutorDeps.provider_step_projectors`` by action id.
"""

from __future__ import annotations

from agent_kernel.actions import ProviderStepResultProjector
from agent_kernel.ref_coercion import extract_inline_ref, extract_output_ref, put_artifact_ref
from agent_kernel.run_artifact import RunArtifact, StepRecord

from .execution_action_ids import (
    TX_APPLY_EDIT_PLAN,
    TX_AUDIT_TRANSCRIPT,
    TX_OPEN_TRANSCRIPT_SPANS,
    TX_ORIENT_AND_BASELINE,
    TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
    TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
    TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
)


def project_transcript_edit_step(run_artifact: RunArtifact, step: StepRecord) -> None:
    """Update ``artifact_refs`` from transcript-edit tool outputs for one step."""
    a = step.action
    if a == TX_AUDIT_TRANSCRIPT:
        put_artifact_ref(run_artifact, "tx_validator_report_ref", extract_output_ref(step.outputs, "tx_validator_report_ref"))
        source_ref = extract_inline_ref(step.outputs_inline, "tx_source_transcript_ref")
        if source_ref is not None:
            put_artifact_ref(run_artifact, "tx_source_transcript_ref", source_ref)
    if a == TX_ORIENT_AND_BASELINE:
        put_artifact_ref(run_artifact, "tx_orient_baseline_ref", extract_output_ref(step.outputs, "tx_orient_baseline_ref"))
        source_ref = extract_inline_ref(step.outputs_inline, "tx_source_transcript_ref")
        if source_ref is not None:
            put_artifact_ref(run_artifact, "tx_source_transcript_ref", source_ref)
    if a == TX_OPEN_TRANSCRIPT_SPANS:
        put_artifact_ref(run_artifact, "tx_open_spans_ref", extract_output_ref(step.outputs, "tx_open_spans_ref"))
        source_ref = extract_inline_ref(step.outputs_inline, "tx_source_transcript_ref")
        if source_ref is not None:
            put_artifact_ref(run_artifact, "tx_source_transcript_ref", source_ref)
    if a == TX_VERIFY_TRANSCRIPT_WITH_IMAGE:
        put_artifact_ref(run_artifact, "tx_image_verify_ref", extract_output_ref(step.outputs, "tx_image_verify_ref"))
        source_ref = extract_inline_ref(step.outputs_inline, "tx_source_transcript_ref")
        if source_ref is not None:
            put_artifact_ref(run_artifact, "tx_source_transcript_ref", source_ref)
        region_ref = extract_inline_ref(step.outputs_inline, "tx_image_evidence_region_ref")
        if region_ref is not None:
            put_artifact_ref(run_artifact, "tx_image_evidence_region_ref", region_ref)
        context_ref = extract_inline_ref(step.outputs_inline, "tx_image_evidence_context_ref")
        if context_ref is not None:
            put_artifact_ref(run_artifact, "tx_image_evidence_context_ref", context_ref)
    if a == TX_APPLY_EDIT_PLAN:
        put_artifact_ref(run_artifact, "tx_apply_report_ref", extract_output_ref(step.outputs, "tx_apply_report_ref"))
        plan_ref = extract_inline_ref(step.outputs_inline, "tx_edit_plan_ref")
        if plan_ref is not None:
            put_artifact_ref(run_artifact, "tx_edit_plan_ref", plan_ref)
        source_ref = extract_inline_ref(step.outputs_inline, "tx_source_transcript_ref")
        if source_ref is not None:
            put_artifact_ref(run_artifact, "tx_source_transcript_ref", source_ref)
        edited_ref = extract_inline_ref(step.outputs_inline, "tx_edited_transcript_ref")
        if edited_ref is not None:
            put_artifact_ref(run_artifact, "tx_edited_transcript_ref", edited_ref)
    if a == TX_SAVE_TRANSCRIPT_SPAN_SEEDS:
        seeds_ref = extract_output_ref(step.outputs, "tx_span_seeds_ref")
        if seeds_ref is None:
            seeds_ref = extract_inline_ref(step.outputs_inline, "tx_span_seeds_ref")
        if seeds_ref is not None:
            put_artifact_ref(run_artifact, "tx_span_seeds_ref", seeds_ref)
        source_ref = extract_inline_ref(step.outputs_inline, "tx_source_transcript_ref")
        if source_ref is not None:
            put_artifact_ref(run_artifact, "tx_source_transcript_ref", source_ref)
    if a == TX_PROMOTE_TRANSCRIPT_FOR_MAPPING:
        put_artifact_ref(run_artifact, "tx_mapping_pointer_ref", extract_output_ref(step.outputs, "tx_mapping_pointer_ref"))
        seeds_ref = extract_inline_ref(step.outputs_inline, "tx_span_seeds_ref")
        if seeds_ref is not None:
            put_artifact_ref(run_artifact, "tx_span_seeds_ref", seeds_ref)


def build_transcript_edit_provider_step_projectors() -> dict[str, ProviderStepResultProjector]:
    """One projector entry per transcript-edit execution action id (same keys as provider_actions)."""
    fn: ProviderStepResultProjector = project_transcript_edit_step
    return {
        TX_AUDIT_TRANSCRIPT: fn,
        TX_ORIENT_AND_BASELINE: fn,
        TX_OPEN_TRANSCRIPT_SPANS: fn,
        TX_VERIFY_TRANSCRIPT_WITH_IMAGE: fn,
        TX_APPLY_EDIT_PLAN: fn,
        TX_SAVE_TRANSCRIPT_SPAN_SEEDS: fn,
        TX_PROMOTE_TRANSCRIPT_FOR_MAPPING: fn,
    }
