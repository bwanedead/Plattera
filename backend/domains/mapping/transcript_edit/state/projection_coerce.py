"""Low-level coercion helpers for transcript-edit projection (keep ``projection.py`` as the lens only)."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    CandidateRepair,
    DownstreamReadinessPosture,
    EvidencePosture,
    FinalSelectionPosture,
    TranscriptAmbiguity,
    TranscriptDefect,
    VerificationPosture,
)


def pick_str(m: Mapping[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = m.get(k)
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return v
    return None


def as_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value
    return None


def tuple_strs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for x in value:
            if isinstance(x, str) and x:
                out.append(x)
        return tuple(out)
    return ()


def coerce_ambiguities(raw: Any) -> tuple[TranscriptAmbiguity, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[TranscriptAmbiguity] = []
    for i, item in enumerate(raw):
        if isinstance(item, TranscriptAmbiguity):
            out.append(item)
            continue
        m = as_mapping(item)
        if not m:
            continue
        summary = pick_str(m, "summary", "description", "text") or ""
        issue_id = pick_str(m, "issue_id", "id") or f"ambiguity_{i}"
        out.append(
            TranscriptAmbiguity(
                issue_id=issue_id,
                summary=summary,
                segment_ref=pick_str(m, "segment_ref", "segment_id"),
                run_ref=pick_str(m, "run_ref", "run_id"),
                span_hint=pick_str(m, "span_hint", "span"),
                notes=pick_str(m, "notes"),
            )
        )
    return tuple(out)


def coerce_defects(raw: Any) -> tuple[TranscriptDefect, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[TranscriptDefect] = []
    for i, item in enumerate(raw):
        if isinstance(item, TranscriptDefect):
            out.append(item)
            continue
        m = as_mapping(item)
        if not m:
            continue
        desc = pick_str(m, "description", "summary", "text") or ""
        kind = pick_str(m, "kind", "type") or "unknown"
        defect_id = pick_str(m, "defect_id", "id") or f"defect_{i}"
        out.append(
            TranscriptDefect(
                defect_id=defect_id,
                kind=kind,
                description=desc,
                segment_ref=pick_str(m, "segment_ref", "segment_id"),
                run_ref=pick_str(m, "run_ref", "run_id"),
            )
        )
    return tuple(out)


def coerce_repairs(raw: Any) -> tuple[CandidateRepair, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[CandidateRepair] = []
    for i, item in enumerate(raw):
        if isinstance(item, CandidateRepair):
            out.append(item)
            continue
        m = as_mapping(item)
        if not m:
            continue
        rationale = pick_str(m, "rationale", "reason", "summary") or ""
        repair_id = pick_str(m, "repair_id", "id") or f"repair_{i}"
        out.append(
            CandidateRepair(
                repair_id=repair_id,
                rationale=rationale,
                proposed_text=pick_str(m, "proposed_text", "text"),
                target_draft_ref=pick_str(m, "target_draft_ref", "draft_ref"),
                target_segment_ref=pick_str(m, "target_segment_ref", "segment_ref"),
            )
        )
    return tuple(out)


def coerce_evidence(m: Mapping[str, Any] | None) -> EvidencePosture | None:
    if not m:
        return None
    narrative = pick_str(m, "narrative", "summary", "description")
    if not narrative:
        return None
    return EvidencePosture(
        narrative=narrative,
        image_refs=tuple_strs(m.get("image_refs")),
        draft_refs=tuple_strs(m.get("draft_refs")),
        sufficiency_summary=pick_str(m, "sufficiency_summary"),
    )


def coerce_verification(m: Mapping[str, Any] | None) -> VerificationPosture | None:
    if not m:
        return None
    narrative = pick_str(m, "narrative", "summary", "description")
    if not narrative:
        return None
    return VerificationPosture(
        narrative=narrative,
        blocking_issues=tuple_strs(m.get("blocking_issues")),
        needs_more_image_evidence=bool(m.get("needs_more_image_evidence")),
        needs_more_draft_evidence=bool(m.get("needs_more_draft_evidence")),
        needs_human_input=bool(m.get("needs_human_input")),
    )


def coerce_final_selection(m: Mapping[str, Any] | None) -> FinalSelectionPosture | None:
    if not m:
        return None
    narrative = pick_str(m, "narrative", "summary", "description")
    if not narrative:
        return None
    return FinalSelectionPosture(
        narrative=narrative,
        selected_final_ref=pick_str(m, "selected_final_ref", "final_ref"),
        head_ref=pick_str(m, "head_ref"),
        conflicts_remain=bool(m.get("conflicts_remain")),
    )


def coerce_downstream(m: Mapping[str, Any] | None) -> DownstreamReadinessPosture | None:
    if not m:
        return None
    narrative = pick_str(m, "narrative", "summary", "description")
    if not narrative:
        return None
    return DownstreamReadinessPosture(
        narrative=narrative,
        ready_for_mapping=bool(m.get("ready_for_mapping")),
        explicit_blockers=tuple_strs(m.get("explicit_blockers")),
    )
