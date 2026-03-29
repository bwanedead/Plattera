"""Deed-to-IR handoff posture declaration.

The domain may declare downstream posture here, but mission runtime owns any
actual transition mechanics.
"""

from __future__ import annotations

from typing import Any

from domains.common.domain_pack_contracts import DomainHandoffPosture


def build_deed_to_ir_supported_handoffs() -> tuple[DomainHandoffPosture, ...]:
    """Return the downstream handoff posture the deed pack declares."""

    return (
        DomainHandoffPosture(
            posture="ready_for_downstream_domain",
            target_domain_id="transcript_edit",
            target_family_id="mapping",
            reason_code="deed_to_ir_output_requires_transcript_edit_review",
            summary="Validated deed output can hand off to transcript-edit review.",
        ),
    )


def build_deed_to_ir_handoff_posture(
    *,
    failure_classification: dict[str, Any] | None,
    claimability: dict[str, Any] | None,
) -> DomainHandoffPosture:
    """Derive the deed runtime handoff posture from existing domain state."""

    failure_cls = failure_classification if isinstance(failure_classification, dict) else {}
    claimability_state = claimability if isinstance(claimability, dict) else {}
    claimable_ready = bool(claimability_state.get("claimable_ready"))
    missing_claimability = (
        [str(v) for v in claimability_state.get("missing_claimability", []) if isinstance(v, str)]
        if isinstance(claimability_state.get("missing_claimability"), list)
        else []
    )
    stop_reason = _read_str(failure_cls.get("stop_reason"))
    reason_code = _read_str(failure_cls.get("reason_code"))

    if claimable_ready:
        return DomainHandoffPosture(
            posture="ready_for_downstream_domain",
            target_domain_id="transcript_edit",
            target_family_id="mapping",
            reason_code="deed_to_ir_output_requires_transcript_edit_review",
            summary="Validated deed output can hand off to transcript-edit review.",
            domain_payload={
                "claimability": claimability_state,
                "failure_classification": failure_cls,
            },
        )

    if stop_reason in {"needs_user_choice", "waiting_human"}:
        return DomainHandoffPosture(
            posture="waiting_on_human",
            target_domain_id="transcript_edit",
            target_family_id="mapping",
            reason_code=reason_code or "deed_to_ir_waiting_on_human",
            summary="Deed output is waiting on human input before downstream review.",
            domain_payload={
                "claimability": claimability_state,
                "failure_classification": failure_cls,
                "missing_claimability": missing_claimability,
            },
        )

    if missing_claimability or stop_reason in {"needs_upload", "needs_capability", "no_progress", "internal_error", "blocked"}:
        return DomainHandoffPosture(
            posture="blocked_pending_dependency",
            target_domain_id="transcript_edit",
            target_family_id="mapping",
            reason_code=reason_code or "deed_to_ir_missing_required_dependency",
            summary="Deed output remains blocked by unresolved structural requirements before transcript-edit review.",
            domain_payload={
                "claimability": claimability_state,
                "failure_classification": failure_cls,
                "missing_claimability": missing_claimability,
            },
        )

    return DomainHandoffPosture(
        posture="no_handoff",
        summary="No downstream handoff posture is currently declared.",
        domain_payload={
            "claimability": claimability_state,
            "failure_classification": failure_cls,
        },
    )


def _read_str(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value else None

