from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import MappingFamilyCoordination, ModeTransitionRecommendation, TerminalRecommendation


def build_mapping_family_coordination(
    *,
    current_mode: str,
    handoff_posture: Mapping[str, Any] | None,
    terminal: TerminalRecommendation | None,
    transition_allowed: bool,
    handed_forward_artifact_refs: list[str] | None = None,
    expected_next_work: str | None = None,
    resume_note_for_prior_mode: str | None = None,
) -> MappingFamilyCoordination:
    """Interpret a domain handoff posture at the mapping-family runtime layer."""

    posture_payload = handoff_posture if isinstance(handoff_posture, Mapping) else {}
    posture = _read_str(posture_payload.get("posture")) or "no_handoff"
    target_domain_id = _read_str(posture_payload.get("target_domain_id"))
    target_family_id = _read_str(posture_payload.get("target_family_id"))
    reason_code = _read_str(posture_payload.get("reason_code"))
    refs = _normalize_refs(handed_forward_artifact_refs)

    if posture == "ready_for_downstream_domain":
        transition_recommendation = None
        coordination_state = "ready_but_gated"
        summary = (
            f"mapping family sees {current_mode} posture ready_for_downstream_domain"
            + (f" toward {target_domain_id}" if target_domain_id else "")
        )
        if transition_allowed and terminal is not None and terminal.terminal_class == "completed" and target_domain_id:
            transition_recommendation = ModeTransitionRecommendation(
                next_mode=target_domain_id,
                reason=reason_code or f"{current_mode}_handoff_ready_for_{target_domain_id}",
                handed_forward_artifact_refs=refs,
                expected_next_work=expected_next_work,
                resume_note_for_prior_mode=resume_note_for_prior_mode,
            )
            coordination_state = "transition_recommended"
            summary = (
                f"mapping family recommends transition from {current_mode} to {target_domain_id}"
                " for ready_for_downstream_domain posture"
            )
        return MappingFamilyCoordination(
            current_mode=current_mode,
            posture=posture,
            target_domain_id=target_domain_id,
            target_family_id=target_family_id,
            reason_code=reason_code,
            coordination_state=coordination_state,
            summary=summary,
            transition_recommendation=transition_recommendation,
        )

    if posture == "waiting_on_human":
        return MappingFamilyCoordination(
            current_mode=current_mode,
            posture=posture,
            target_domain_id=target_domain_id,
            target_family_id=target_family_id,
            reason_code=reason_code,
            coordination_state="waiting_on_human",
            summary=f"mapping family sees {current_mode} posture waiting_on_human; no transition recommended",
        )

    if posture == "blocked_pending_dependency":
        return MappingFamilyCoordination(
            current_mode=current_mode,
            posture=posture,
            target_domain_id=target_domain_id,
            target_family_id=target_family_id,
            reason_code=reason_code,
            coordination_state="blocked_pending_dependency",
            summary=f"mapping family sees {current_mode} posture blocked_pending_dependency; no transition recommended",
        )

    return MappingFamilyCoordination(
        current_mode=current_mode,
        posture="no_handoff",
        target_domain_id=target_domain_id,
        target_family_id=target_family_id,
        reason_code=reason_code,
        coordination_state="no_handoff",
        summary=f"mapping family sees {current_mode} posture no_handoff; no transition recommended",
    )


def _normalize_refs(values: list[str] | None) -> list[str]:
    refs: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        ref = value.strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _read_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
