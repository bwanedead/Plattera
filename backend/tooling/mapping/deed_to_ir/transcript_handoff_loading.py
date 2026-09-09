"""Mechanical loading of transcript-edit output for deed-to-IR startup handoff.

Copies fields from published output JSON without semantic inference or mutation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from domains.mapping.transcript_edit.payloads.dossier_publication_candidate import (
    CANDIDATE_SCHEMA_VERSION,
)
from tooling.mapping.transcript_edit.dossier_publication_persistence import (
    OUTPUT_SCHEMA_VERSION,
)
from tooling.mapping.transcript_edit.transcript_edit_decision_summary import (
    TranscriptEditDecisionProjectionError,
    project_decision_summary_from_payload,
    project_transcript_edit_decision_summary,
)


class TranscriptHandoffLoadError(ValueError):
    """Raised when output JSON cannot be read or lacks required mechanical shape."""


MAX_EXCERPT_CHARS = 600
LOADED_SOURCE_LABEL = "transcript_edit_output"
LOADED_DOSSIER_SOURCE_LABEL = "transcript_edit_dossier_output"
_SEGMENT_JOIN = "\n\n"


def load_transcript_edit_output_handoff(*, output_path: str | Path) -> dict[str, Any]:
    """Load and summarize transcript-edit output for deed-to-IR startup (copy-only)."""
    path = Path(output_path)
    if not path.is_file():
        raise TranscriptHandoffLoadError(f"transcript_edit_output_not_found:{path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranscriptHandoffLoadError(f"transcript_edit_output_unreadable:{path}") from exc

    if not isinstance(raw, Mapping):
        raise TranscriptHandoffLoadError("transcript_edit_output_not_object")

    # Dossier publication revision wire shape.
    candidate = raw.get("candidate")
    if isinstance(candidate, Mapping) and "segments" in candidate:
        return _load_dossier_candidate_handoff(raw=raw, candidate=candidate)

    snapshot = raw.get("revision_snapshot")
    if not isinstance(snapshot, Mapping):
        raise TranscriptHandoffLoadError("transcript_edit_output_missing_revision_snapshot")

    payload = snapshot.get("payload")
    if not isinstance(payload, Mapping):
        raise TranscriptHandoffLoadError("transcript_edit_output_missing_payload")

    normalized = _optional_text(payload.get("normalized_or_mapping_transcript"))
    verbatim = _optional_text(payload.get("source_transcript_verbatim"))
    issues = _copy_list(payload.get("issues"))
    hitl = _copy_list(payload.get("hitl_decisions"))
    parcel_metadata = _copy_mapping(payload.get("parcel_metadata"))
    evidence_refs = _bounded_str_list(payload.get("evidence_refs"))
    decision_summary = _project_leaf_decision_summary(payload)

    return {
        "source": {
            "loaded_source_label": LOADED_SOURCE_LABEL,
            "source_revision_ref": _optional_text(raw.get("source_revision_ref"))
            or _optional_text(snapshot.get("ref_id")),
            "published_at": _optional_text(raw.get("published_at")),
        },
        "normalized_or_mapping_transcript": normalized,
        "source_transcript_verbatim": verbatim,
        "issues": issues,
        "hitl_decisions": hitl,
        "parcel_metadata": parcel_metadata,
        "evidence_refs": evidence_refs,
        "transcript_edit_decision_summary": decision_summary,
        "counts": {
            "issues": len(issues),
            "hitl_decisions": len(hitl),
            "parcels": len(_parcel_rows(parcel_metadata)),
            "evidence_refs": len(evidence_refs),
            "transcript_edit_decisions": int(
                (decision_summary.get("counts") or {}).get("source") or 0
            ),
        },
        "excerpts": {
            "normalized_or_mapping_transcript": _excerpt(normalized),
            "source_transcript_verbatim": _excerpt(verbatim),
        },
    }


def _load_dossier_candidate_handoff(
    *,
    raw: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_dossier_publication_document(raw=raw, candidate=candidate)

    segments_raw = candidate.get("segments")
    if type(segments_raw) is not list:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_missing_segments")
    if not segments_raw:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_empty_segments")

    ordered_segments = _ordered_dossier_segments(segments_raw)
    candidate_source_refs = _validate_exact_nonblank_string_list(
        candidate.get("source_revision_refs"),
        error_code="transcript_edit_dossier_source_revision_refs_invalid",
    )
    ordered_segment_refs = [seg["source_revision_ref"] for seg in ordered_segments]
    if candidate_source_refs != ordered_segment_refs:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_source_revision_refs_mismatch")

    sources: list[dict[str, Any]] = []
    issues: list[Any] = []
    hitl: list[Any] = []
    evidence_from_segments: list[str] = []
    seen_evidence: set[str] = set()
    verbatim_parts: list[str] = []
    normalized_parts: list[str] = []
    parcel_metadatas: list[dict[str, Any] | None] = []

    for segment in ordered_segments:
        snapshot = segment["revision_snapshot"]
        payload = snapshot["payload"]
        segment_id = segment["segment_id"]
        transcription_id = segment["transcription_id"]
        sources.append(
            {
                "payload": dict(payload),
                "segment_id": segment_id,
                "transcription_id": transcription_id,
            }
        )
        issues.extend(_copy_list(payload.get("issues")))
        hitl.extend(_copy_list(payload.get("hitl_decisions")))

        segment_evidence = _validate_segment_evidence_refs(segment)
        for ref in segment_evidence:
            if ref not in seen_evidence:
                seen_evidence.add(ref)
                evidence_from_segments.append(ref)

        # Segment lane fields are required on the candidate wire (may be empty string).
        verbatim = segment.get("source_transcript_verbatim")
        normalized = segment.get("normalized_or_mapping_transcript")
        if type(verbatim) is not str or type(normalized) is not str:
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_segment_lane_invalid"
            )
        payload_verbatim = payload.get("source_transcript_verbatim")
        payload_normalized = payload.get("normalized_or_mapping_transcript")
        if type(payload_verbatim) is str:
            if payload_verbatim != verbatim:
                raise TranscriptHandoffLoadError(
                    "transcript_edit_dossier_segment_lane_mismatch"
                )
        if type(payload_normalized) is str:
            if payload_normalized != normalized:
                raise TranscriptHandoffLoadError(
                    "transcript_edit_dossier_segment_lane_mismatch"
                )
        verbatim_parts.append(verbatim)
        normalized_parts.append(normalized)

        if "parcel_metadata" in payload:
            meta = payload.get("parcel_metadata")
            if meta is None:
                parcel_metadatas.append(None)
            elif isinstance(meta, Mapping):
                parcel_metadatas.append(dict(meta))
            else:
                raise TranscriptHandoffLoadError(
                    "transcript_edit_dossier_parcel_metadata_invalid"
                )
        else:
            parcel_metadatas.append(None)

    stitched_verbatim = _SEGMENT_JOIN.join(verbatim_parts)
    stitched_normalized = _SEGMENT_JOIN.join(normalized_parts)
    candidate_verbatim = candidate.get("source_transcript_verbatim")
    candidate_normalized = candidate.get("normalized_or_mapping_transcript")
    if type(candidate_verbatim) is not str or type(candidate_normalized) is not str:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_stitched_lanes_invalid")
    if candidate_verbatim != stitched_verbatim or candidate_normalized != stitched_normalized:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_stitched_content_mismatch")

    candidate_evidence = _validate_exact_nonblank_string_list(
        candidate.get("evidence_refs"),
        error_code="transcript_edit_dossier_evidence_refs_invalid",
    )
    if candidate_evidence != evidence_from_segments:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_evidence_mismatch")

    parcel_metadata = _resolve_parcel_metadata(parcel_metadatas)

    try:
        decision_summary = project_transcript_edit_decision_summary(sources=sources)
    except TranscriptEditDecisionProjectionError as exc:
        raise TranscriptHandoffLoadError(
            f"transcript_edit_decision_summary_invalid:{exc.reason_code}"
        ) from exc

    output_revision_ref = _optional_text(raw.get("output_revision_ref"))
    if not output_revision_ref:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_missing_output_revision_ref")

    return {
        "source": {
            "loaded_source_label": LOADED_DOSSIER_SOURCE_LABEL,
            "source_revision_ref": output_revision_ref,
            "published_at": _optional_text(raw.get("published_at"))
            or _optional_text(candidate.get("published_at")),
        },
        "normalized_or_mapping_transcript": stitched_normalized or None,
        "source_transcript_verbatim": stitched_verbatim or None,
        "issues": issues,
        "hitl_decisions": hitl,
        "parcel_metadata": parcel_metadata,
        "evidence_refs": candidate_evidence,
        "transcript_edit_decision_summary": decision_summary,
        "counts": {
            "issues": len(issues),
            "hitl_decisions": len(hitl),
            "parcels": len(_parcel_rows(parcel_metadata)),
            "evidence_refs": len(candidate_evidence),
            "segments": len(sources),
            "transcript_edit_decisions": int(
                (decision_summary.get("counts") or {}).get("source") or 0
            ),
        },
        "excerpts": {
            "normalized_or_mapping_transcript": _excerpt(stitched_normalized or None),
            "source_transcript_verbatim": _excerpt(stitched_verbatim or None),
        },
    }


def _validate_dossier_publication_document(
    *,
    raw: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> None:
    schema = raw.get("schema_version")
    if schema != OUTPUT_SCHEMA_VERSION:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_schema_invalid")
    if type(raw.get("output_revision_ref")) is not str or not str(
        raw.get("output_revision_ref")
    ).strip():
        raise TranscriptHandoffLoadError("transcript_edit_dossier_missing_output_revision_ref")
    candidate_schema = candidate.get("schema_version")
    if candidate_schema != CANDIDATE_SCHEMA_VERSION:
        raise TranscriptHandoffLoadError("transcript_edit_dossier_candidate_schema_invalid")
    for key in (
        "dossier_id",
        "workspace_id",
        "topology_fingerprint",
        "candidate_fingerprint",
        "source_revision_refs",
        "segments",
        "source_transcript_verbatim",
        "normalized_or_mapping_transcript",
        "evidence_refs",
    ):
        if key not in candidate:
            raise TranscriptHandoffLoadError(
                f"transcript_edit_dossier_candidate_missing_{key}"
            )


def _ordered_dossier_segments(segments_raw: list[Any]) -> list[dict[str, Any]]:
    seen_positions: set[int] = set()
    seen_segment_ids: set[str] = set()
    seen_transcription_ids: set[str] = set()
    seen_source_refs: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for index, segment in enumerate(segments_raw):
        if not isinstance(segment, Mapping):
            raise TranscriptHandoffLoadError(
                f"transcript_edit_dossier_segment_not_object:{index}"
            )
        segment_id = segment.get("segment_id")
        transcription_id = segment.get("transcription_id")
        position = segment.get("position")
        source_revision_ref = segment.get("source_revision_ref")
        if type(segment_id) is not str or not segment_id.strip():
            raise TranscriptHandoffLoadError("transcript_edit_dossier_segment_id_blank")
        if segment_id != segment_id.strip():
            raise TranscriptHandoffLoadError("transcript_edit_dossier_segment_id_blank")
        if type(transcription_id) is not str or not transcription_id.strip():
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_transcription_id_blank"
            )
        if transcription_id != transcription_id.strip():
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_transcription_id_blank"
            )
        if type(position) is not int or isinstance(position, bool):
            raise TranscriptHandoffLoadError("transcript_edit_dossier_position_invalid")
        if type(source_revision_ref) is not str or not source_revision_ref.strip():
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_source_revision_ref_blank"
            )
        if source_revision_ref != source_revision_ref.strip():
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_source_revision_ref_blank"
            )
        if segment_id in seen_segment_ids:
            raise TranscriptHandoffLoadError("transcript_edit_dossier_duplicate_segment_id")
        if transcription_id in seen_transcription_ids:
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_duplicate_transcription_id"
            )
        if position in seen_positions:
            raise TranscriptHandoffLoadError("transcript_edit_dossier_duplicate_position")
        if source_revision_ref in seen_source_refs:
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_duplicate_source_revision_ref"
            )
        seen_segment_ids.add(segment_id)
        seen_transcription_ids.add(transcription_id)
        seen_positions.add(position)
        seen_source_refs.add(source_revision_ref)
        snapshot = segment.get("revision_snapshot")
        if not isinstance(snapshot, Mapping):
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_segment_missing_revision_snapshot"
            )
        payload = snapshot.get("payload")
        if not isinstance(payload, Mapping):
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_segment_missing_payload"
            )
        ordered.append(
            {
                "segment_id": segment_id,
                "transcription_id": transcription_id,
                "position": position,
                "source_revision_ref": source_revision_ref,
                "evidence_refs": segment.get("evidence_refs"),
                "source_transcript_verbatim": segment.get("source_transcript_verbatim"),
                "normalized_or_mapping_transcript": segment.get(
                    "normalized_or_mapping_transcript"
                ),
                "revision_snapshot": snapshot,
            }
        )
    ordered.sort(key=lambda item: item["position"])
    return ordered


def _validate_exact_nonblank_string_list(value: Any, *, error_code: str) -> list[str]:
    """Validate a list of nonblank strings without filtering, stripping, or deduping."""
    if type(value) is not list:
        raise TranscriptHandoffLoadError(error_code)
    out: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip():
            raise TranscriptHandoffLoadError(error_code)
        if item != item.strip():
            raise TranscriptHandoffLoadError(error_code)
        out.append(item)
    return out


def _validate_segment_evidence_refs(segment: Mapping[str, Any]) -> list[str]:
    """Fail-closed segment evidence vs revision snapshot evidence representation."""
    snapshot = segment["revision_snapshot"]
    payload = snapshot["payload"]
    segment_evidence = _validate_exact_nonblank_string_list(
        segment.get("evidence_refs"),
        error_code="transcript_edit_dossier_segment_evidence_refs_invalid",
    )
    if "evidence_refs" not in snapshot:
        raise TranscriptHandoffLoadError(
            "transcript_edit_dossier_snapshot_evidence_refs_missing"
        )
    snapshot_evidence = _validate_exact_nonblank_string_list(
        snapshot.get("evidence_refs"),
        error_code="transcript_edit_dossier_snapshot_evidence_refs_invalid",
    )
    if segment_evidence != snapshot_evidence:
        raise TranscriptHandoffLoadError(
            "transcript_edit_dossier_segment_snapshot_evidence_mismatch"
        )
    if "evidence_refs" in payload:
        payload_evidence = _validate_exact_nonblank_string_list(
            payload.get("evidence_refs"),
            error_code="transcript_edit_dossier_payload_evidence_refs_invalid",
        )
        if payload_evidence != snapshot_evidence:
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_payload_snapshot_evidence_mismatch"
            )
    return segment_evidence


def _resolve_parcel_metadata(
    parcel_metadatas: list[dict[str, Any] | None],
) -> dict[str, Any]:
    present = [meta for meta in parcel_metadatas if meta]
    if not present:
        return {}
    first = present[0]
    first_canon = _canonical_json(first)
    for meta in present[1:]:
        if _canonical_json(meta) != first_canon:
            raise TranscriptHandoffLoadError(
                "transcript_edit_dossier_conflicting_parcel_metadata"
            )
    return dict(first)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _project_leaf_decision_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return project_decision_summary_from_payload(payload)
    except TranscriptEditDecisionProjectionError as exc:
        raise TranscriptHandoffLoadError(
            f"transcript_edit_decision_summary_invalid:{exc.reason_code}"
        ) from exc


def _parcel_rows(parcel_metadata: Mapping[str, Any]) -> list[Any]:
    parcels = parcel_metadata.get("parcels")
    return list(parcels) if isinstance(parcels, list) else []


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _copy_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, (dict, list, str, int, float, bool)) or item is None
    ]


def _copy_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _bounded_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        text = entry.strip()
        if text and text not in out:
            out.append(text)
    return out


def _excerpt(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) <= MAX_EXCERPT_CHARS:
        return text
    return text[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"
