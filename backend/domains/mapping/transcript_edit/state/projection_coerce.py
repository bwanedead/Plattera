"""Low-level coercion helpers for transcript-edit projection (keep ``projection.py`` as the lens only)."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    CandidateRepair,
    DownstreamReadinessPosture,
    EvidencePosture,
    TranscriptAmbiguity,
    TranscriptEditClosureLayerPosture,
    TranscriptEditClosureLedger,
    TranscriptDefect,
    TranscriptEditAuthoredDraftPosture,
    VerificationPosture,
)

_TRANSCRIPT_EDIT_LAYER_TITLES = {
    "layer_1_delta_convergence": "Layer 1 — Delta convergence",
    "layer_2_intrinsic_source_integrity": "Layer 2 — Intrinsic source integrity",
    "layer_3_external_dependency_completeness": "Layer 3 — External dependency completeness",
    "layer_4_mapping_blocking_relevance": "Layer 4 — Mapping-blocking relevance",
}


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


def coerce_authored_draft_posture(m: Mapping[str, Any] | None) -> TranscriptEditAuthoredDraftPosture | None:
    if not m:
        return None
    narrative = pick_str(m, "narrative", "summary", "description")
    if not narrative:
        return None
    return TranscriptEditAuthoredDraftPosture(
        narrative=narrative,
        working_draft_ref=pick_str(m, "working_draft_ref", "authored_transcript_edit_ref", "transcript_edit_work_ref"),
        output_draft_ref=pick_str(m, "output_draft_ref", "authored_output_draft_ref"),
    )


def coerce_authored_draft_posture_from_legacy_final_selection(
    m: Mapping[str, Any] | None,
) -> TranscriptEditAuthoredDraftPosture | None:
    """Tolerate old ``final_selection`` payloads without surfacing ``selected_final_ref`` in the domain shape."""
    if not m:
        return None
    narrative = pick_str(m, "narrative", "summary", "description")
    if not narrative:
        return None
    return TranscriptEditAuthoredDraftPosture(
        narrative=narrative,
        working_draft_ref=pick_str(m, "authored_transcript_edit_ref", "transcript_edit_work_ref", "working_draft_ref"),
        output_draft_ref=pick_str(m, "output_draft_ref", "authored_output_draft_ref"),
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


def coerce_closure_layer(
    m: Mapping[str, Any] | None,
    *,
    layer_id: str,
) -> TranscriptEditClosureLayerPosture | None:
    if not m:
        return None
    status = pick_str(m, "status")
    summary = pick_str(m, "summary", "description", "narrative")
    if not status and not summary:
        return None
    return TranscriptEditClosureLayerPosture(
        layer_id=layer_id,
        title=pick_str(m, "title") or _TRANSCRIPT_EDIT_LAYER_TITLES.get(layer_id, layer_id),
        status=status or "open",
        summary=summary or "",
        mapping_blocking=(
            bool(m.get("mapping_blocking"))
            if "mapping_blocking" in m
            else bool(m.get("blocking"))
            if "blocking" in m
            else None
        ),
        requires_hitl=bool(m.get("requires_hitl")),
        no_further_progress=bool(m.get("no_further_progress")),
        evidence_refs=tuple_strs(m.get("evidence_refs")),
        verification_basis=pick_str(m, "verification_basis"),
        next_needed_step=pick_str(m, "next_needed_step"),
    )


def coerce_closure_ledger(m: Mapping[str, Any] | None) -> TranscriptEditClosureLedger | None:
    if not m:
        return None
    dims_raw = m.get("dimensions")
    dims: dict[str, Mapping[str, Any]] = {}
    if isinstance(dims_raw, list):
        for row in dims_raw:
            row_map = as_mapping(row)
            if not row_map:
                continue
            dim_id = pick_str(row_map, "dimension_id")
            if not dim_id:
                continue
            dims[dim_id] = row_map

    opaque = as_mapping(m.get("opaque_payload")) or {}
    layer_1 = coerce_closure_layer(dims.get("layer_1_delta_convergence"), layer_id="layer_1_delta_convergence")
    layer_2 = coerce_closure_layer(
        dims.get("layer_2_intrinsic_source_integrity"),
        layer_id="layer_2_intrinsic_source_integrity",
    )
    layer_3 = coerce_closure_layer(
        dims.get("layer_3_external_dependency_completeness"),
        layer_id="layer_3_external_dependency_completeness",
    )
    layer_4 = coerce_closure_layer(
        dims.get("layer_4_mapping_blocking_relevance"),
        layer_id="layer_4_mapping_blocking_relevance",
    )

    overall_status = pick_str(m, "overall_status")
    summary = pick_str(m, "summary")
    publish_ready = bool(opaque.get("publish_ready"))
    complete_ready = bool(m.get("ready_to_close") or opaque.get("complete_ready"))
    requires_hitl = bool(m.get("requires_hitl"))
    no_further_progress = bool(m.get("no_further_progress"))

    if not any(
        (
            overall_status,
            summary,
            publish_ready,
            complete_ready,
            requires_hitl,
            no_further_progress,
            layer_1,
            layer_2,
            layer_3,
            layer_4,
        )
    ):
        return None

    return TranscriptEditClosureLedger(
        overall_status=overall_status,
        summary=summary,
        publish_ready=publish_ready,
        complete_ready=complete_ready,
        requires_hitl=requires_hitl,
        no_further_progress=no_further_progress,
        layer_1_delta_convergence=layer_1,
        layer_2_intrinsic_source_integrity=layer_2,
        layer_3_external_dependency_completeness=layer_3,
        layer_4_mapping_blocking_relevance=layer_4,
    )
