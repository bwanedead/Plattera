from __future__ import annotations

from typing import Any

from domains.common.domain_pack_contracts import DomainHandoffPosture
from .contracts import TranscriptEditAgentRunResult


def build_transcript_edit_handoff_postures() -> tuple[DomainHandoffPosture, ...]:
    return (
        DomainHandoffPosture(
            posture="no_handoff",
            target_family_id="mapping",
            reason_code="tx_agent_no_handoff",
            summary="Transcript-edit has no downstream handoff.",
        ),
        DomainHandoffPosture(
            posture="ready_for_downstream_domain",
            target_domain_id="deed_to_ir",
            target_family_id="mapping",
            reason_code="tx_agent_clean_complete",
            summary="Transcript-edit can hand off validated artifacts downstream.",
        ),
        DomainHandoffPosture(
            posture="blocked_pending_dependency",
            target_domain_id="deed_to_ir",
            target_family_id="mapping",
            reason_code="tx_agent_blocked_pending_dependency",
            summary="Transcript-edit is blocked pending dependency resolution.",
        ),
        DomainHandoffPosture(
            posture="waiting_on_human",
            target_family_id="mapping",
            reason_code="tx_agent_waiting_feedback",
            summary="Transcript-edit is waiting on human feedback.",
        ),
    )


def build_transcript_edit_handoff_posture(
    *,
    result: TranscriptEditAgentRunResult,
    terminal_summary: dict[str, Any] | None = None,
) -> DomainHandoffPosture:
    """Derive transcript-edit downstream posture from result and terminal summary."""

    summary = terminal_summary if isinstance(terminal_summary, dict) else {}
    status = str(result.status or "").strip().lower()
    reason_code = str(result.reason_code or "").strip() or None
    mapping_ready = bool(summary.get("mapping_ready"))
    human_feedback_pending = bool(summary.get("human_feedback_pending")) or status == "waiting_feedback"
    closure_state = str(summary.get("closure_state") or "").strip().lower()
    readiness_blocker = str(summary.get("readiness_blocker") or "").strip() or None
    terminal_classification = str(summary.get("terminal_classification") or "").strip().lower()
    dependency_blocked = (
        terminal_classification == "blocked_dependency_evidence_missing"
        or readiness_blocker == "mapping_critical_dependency_unresolved"
    )
    review_required = bool(getattr(result, "review_required", False))

    if human_feedback_pending:
        return DomainHandoffPosture(
            posture="waiting_on_human",
            target_family_id="mapping",
            reason_code=reason_code or "tx_agent_waiting_feedback",
            summary="Transcript-edit is waiting on human feedback.",
            domain_payload={
                "status": status or None,
                "review_required": review_required,
                "human_feedback_pending": True,
            },
        )

    if status == "completed" and mapping_ready:
        return DomainHandoffPosture(
            posture="ready_for_downstream_domain",
            target_domain_id="deed_to_ir",
            target_family_id="mapping",
            reason_code=reason_code or "tx_agent_clean_complete",
            summary="Transcript-edit can hand off validated artifacts downstream.",
            domain_payload={
                "status": status or None,
                "review_required": review_required,
                "mapping_ready": True,
            },
        )

    if dependency_blocked:
        return DomainHandoffPosture(
            posture="blocked_pending_dependency",
            target_domain_id="deed_to_ir",
            target_family_id="mapping",
            reason_code=readiness_blocker or reason_code or "tx_agent_blocked_pending_dependency",
            summary="Transcript-edit is blocked pending dependency resolution.",
            domain_payload={
                "status": status or None,
                "review_required": review_required,
                "mapping_ready": mapping_ready,
                "readiness_blocker": readiness_blocker,
            },
        )

    return DomainHandoffPosture(
        posture="no_handoff",
        target_family_id="mapping",
        reason_code=reason_code or "tx_agent_no_handoff",
        summary="Transcript-edit has no downstream handoff.",
        domain_payload={
            "status": status or None,
            "review_required": review_required,
            "mapping_ready": mapping_ready,
        },
    )

