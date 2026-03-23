"""Register transcript-edit provider actions with the execution kernel (Phase 32).

Wires domain tools into ``ActionExecutorDeps.provider_actions`` — not as built-in core enum members.
"""

from __future__ import annotations

from typing import Any

from agent_kernel.actions import RegisteredProviderAction


def build_transcript_edit_provider_actions(
    *,
    transcript_auditor: Any | None,
    transcript_orient_baseliner: Any | None,
    transcript_span_opener: Any | None,
    transcript_image_verifier: Any | None,
    transcript_plan_applier: Any | None,
    transcript_span_seeds_saver: Any | None,
    transcript_promoter: Any | None,
) -> dict[str, RegisteredProviderAction]:
    out: dict[str, RegisteredProviderAction] = {}
    from agents.transcript_edit.execution_action_ids import (
        TX_APPLY_EDIT_PLAN,
        TX_AUDIT_TRANSCRIPT,
        TX_OPEN_TRANSCRIPT_SPANS,
        TX_ORIENT_AND_BASELINE,
        TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
        TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
        TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
    )

    if transcript_auditor is not None:
        out[TX_AUDIT_TRANSCRIPT] = RegisteredProviderAction(
            output_key="tx_validator_report_ref",
            reason_code="tx_audit_completed",
            missing_reason="missing_transcript_auditor_interface",
            handler=transcript_auditor.audit_transcript,
        )
    if transcript_orient_baseliner is not None:
        out[TX_ORIENT_AND_BASELINE] = RegisteredProviderAction(
            output_key="tx_orient_baseline_ref",
            reason_code="tx_orient_baseline_completed",
            missing_reason="missing_transcript_orient_baseliner_interface",
            handler=transcript_orient_baseliner.orient_and_baseline,
        )
    if transcript_span_opener is not None:
        out[TX_OPEN_TRANSCRIPT_SPANS] = RegisteredProviderAction(
            output_key="tx_open_spans_ref",
            reason_code="tx_spans_opened",
            missing_reason="missing_transcript_span_opener_interface",
            handler=transcript_span_opener.open_transcript_spans,
        )
    if transcript_image_verifier is not None:
        out[TX_VERIFY_TRANSCRIPT_WITH_IMAGE] = RegisteredProviderAction(
            output_key="tx_image_verify_ref",
            reason_code="tx_image_verified",
            missing_reason="missing_transcript_image_verifier_interface",
            handler=transcript_image_verifier.verify_transcript_with_image,
        )
    if transcript_plan_applier is not None:
        out[TX_APPLY_EDIT_PLAN] = RegisteredProviderAction(
            output_key="tx_apply_report_ref",
            reason_code="tx_apply_completed",
            missing_reason="missing_transcript_plan_applier_interface",
            handler=transcript_plan_applier.apply_edit_plan,
        )
    if transcript_span_seeds_saver is not None:
        out[TX_SAVE_TRANSCRIPT_SPAN_SEEDS] = RegisteredProviderAction(
            output_key="tx_span_seeds_ref",
            reason_code="tx_span_seeds_saved",
            missing_reason="missing_transcript_span_seeds_saver_interface",
            handler=transcript_span_seeds_saver.save_transcript_span_seeds,
        )
    if transcript_promoter is not None:
        out[TX_PROMOTE_TRANSCRIPT_FOR_MAPPING] = RegisteredProviderAction(
            output_key="tx_mapping_pointer_ref",
            reason_code="tx_promote_completed",
            missing_reason="missing_transcript_promoter_interface",
            handler=transcript_promoter.promote_transcript_for_mapping,
        )
    return out
