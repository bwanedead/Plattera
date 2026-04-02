"""Transcript-edit projection lens: scope merge + semantic-state assembly (coercion lives in ``projection_coerce``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import TranscriptEditSemanticState
from .projection_coerce import (
    as_mapping,
    coerce_ambiguities,
    coerce_authored_draft_posture,
    coerce_authored_draft_posture_from_legacy_final_selection,
    coerce_defects,
    coerce_downstream,
    coerce_evidence,
    coerce_repairs,
    coerce_verification,
    pick_str,
    tuple_strs,
)


@dataclass(frozen=True)
class TranscriptEditProjectedView:
    """Lens for prompts and tool-result interpretation—not orchestration, not persistence."""

    scope_ids: Mapping[str, str | None]
    semantic_state: TranscriptEditSemanticState
    artifact_fingerprint: str | None


def _merge_scope_ids(
    dossier: Mapping[str, Any],
    mission: Mapping[str, Any],
) -> dict[str, str | None]:
    """Mission opaque state wins over dossier slice; nested ``scope`` overrides flat keys."""

    scope: dict[str, str | None] = {}
    inner_d = as_mapping(dossier.get("scope"))
    inner_s = as_mapping(mission.get("scope"))
    for key in (
        "dossier_id",
        "segment_id",
        "run_id",
        "transcription_id",
        "draft_id",
    ):
        scope[key] = pick_str(mission, key) or pick_str(dossier, key)
        if inner_s and key in inner_s:
            v = inner_s.get(key)
            if isinstance(v, str) and v:
                scope[key] = v
        if inner_d and key in inner_d:
            v = inner_d.get(key)
            if isinstance(v, str) and v:
                scope[key] = v
    return scope


def _prefer_mission_then_dossier(
    mission: Mapping[str, Any],
    dossier: Mapping[str, Any],
    key: str,
) -> Any:
    if key in mission:
        return mission.get(key)
    return dossier.get(key)


def project_transcript_edit_view(
    *,
    dossier_artifact_slice: Mapping[str, Any] | None = None,
    mission_opaque_state: Mapping[str, Any] | None = None,
) -> TranscriptEditProjectedView:
    """Merge optional dossier-shaped and mission-opaque maps into a transcript-edit lens."""

    d = dossier_artifact_slice or {}
    s = mission_opaque_state or {}

    scope = _merge_scope_ids(d, s)

    ambiguities = coerce_ambiguities(_prefer_mission_then_dossier(s, d, "ambiguities"))
    defects = coerce_defects(_prefer_mission_then_dossier(s, d, "defects"))
    repairs = coerce_repairs(_prefer_mission_then_dossier(s, d, "candidate_repairs"))

    evidence = coerce_evidence(as_mapping(s.get("evidence"))) or coerce_evidence(as_mapping(d.get("evidence")))
    verification = coerce_verification(as_mapping(s.get("verification"))) or coerce_verification(
        as_mapping(d.get("verification"))
    )
    authored_draft_posture = (
        coerce_authored_draft_posture(as_mapping(s.get("authored_draft_posture")))
        or coerce_authored_draft_posture(as_mapping(s.get("transcript_edit_authored")))
        or coerce_authored_draft_posture_from_legacy_final_selection(as_mapping(s.get("final_selection")))
        or coerce_authored_draft_posture(as_mapping(d.get("authored_draft_posture")))
        or coerce_authored_draft_posture(as_mapping(d.get("transcript_edit_authored")))
        or coerce_authored_draft_posture_from_legacy_final_selection(as_mapping(d.get("final_selection")))
    )
    downstream = coerce_downstream(as_mapping(s.get("downstream"))) or coerce_downstream(
        as_mapping(d.get("downstream"))
    )

    hf = s.get("human_feedback_notes", d.get("human_feedback_notes"))
    human_notes = tuple_strs(hf)

    fp = pick_str(s, "artifact_fingerprint", "fingerprint") or pick_str(
        d, "artifact_fingerprint", "fingerprint"
    )

    state = TranscriptEditSemanticState(
        ambiguities=ambiguities,
        defects=defects,
        evidence=evidence,
        candidate_repairs=repairs,
        verification=verification,
        authored_draft_posture=authored_draft_posture,
        downstream=downstream,
        human_feedback_notes=human_notes,
    )

    return TranscriptEditProjectedView(
        scope_ids=scope,
        semantic_state=state,
        artifact_fingerprint=fp,
    )
