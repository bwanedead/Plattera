"""Build a read-only dossier transcript publication candidate from explicit revisions.

Agent-authored exact working revisions are validated and mechanically assembled.
This module performs no writes and does not choose among runs or drafts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from domains.mapping.transcript_edit.payloads.dossier_publication_candidate import (
    CANDIDATE_SCHEMA_VERSION,
    DossierPublicationCandidate,
    DossierPublicationSegment,
)
from domains.mapping.transcript_edit.payloads.dossier_startup_inventory import (
    DossierTranscriptSegmentInventory,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefError,
    parse_dossier_qualified_ref,
)
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryBundle,
)
from tooling.mapping.transcript_edit.draft_loading import (
    ExactWorkingRevisionLoadError,
    load_exact_working_revision_document,
)
from tooling.mapping.transcript_edit.draft_persistence import (
    parse_working_revision_ref,
    resolve_workspace_key,
)

_SEGMENT_JOIN = "\n\n"
_TRANSCRIPT_LANES = (
    "source_transcript_verbatim",
    "normalized_or_mapping_transcript",
)


class DossierPublicationCandidateError(Exception):
    """Mechanical refusal while building a dossier publication candidate."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail or "")
        message = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(message)


def build_dossier_publication_candidate(
    *,
    bundle: DossierStartupInventoryBundle,
    workspace_key: str,
    source_revision_refs: Sequence[str],
) -> DossierPublicationCandidate:
    """Assemble a path-free publication candidate from explicit exact revisions."""
    if not isinstance(bundle, DossierStartupInventoryBundle):
        raise DossierPublicationCandidateError("invalid_selection_collection")
    ws = str(workspace_key or "").strip()
    if not ws:
        raise DossierPublicationCandidateError("invalid_workspace_scope")

    inventory = bundle.inventory
    ref_index = bundle.ref_index
    if inventory.scope.dossier_id != ref_index.dossier_id:
        raise DossierPublicationCandidateError("ref_outside_topology")
    if inventory.topology_fingerprint != ref_index.topology_fingerprint:
        raise DossierPublicationCandidateError("ref_outside_topology")

    expected_workspace = resolve_workspace_key(
        workspace_id=inventory.scope.workspace_id,
        run_id=inventory.scope.run_id,
    )
    if not expected_workspace or expected_workspace != ws:
        raise DossierPublicationCandidateError("invalid_workspace_scope")

    topology_segments = _ordered_topology_segments(inventory.segments)
    if not topology_segments:
        raise DossierPublicationCandidateError("incomplete_segment_coverage")

    selected = _normalize_selection(
        source_revision_refs,
        bundle=bundle,
    )

    # Exactly one selection per topology segment; no extras.
    selected_by_segment = {item.segment_id: item for item in selected}
    expected_ids = [segment.segment_id for segment in topology_segments]
    expected_set = set(expected_ids)
    selected_set = set(selected_by_segment)
    missing = expected_set - selected_set
    if missing:
        raise DossierPublicationCandidateError(
            "incomplete_segment_coverage",
            ",".join(sorted(missing)),
        )
    extra = selected_set - expected_set
    if extra:
        raise DossierPublicationCandidateError(
            "unexpected_segment_selection",
            ",".join(sorted(extra)),
        )

    built_segments: list[DossierPublicationSegment] = []
    ordered_refs: list[str] = []
    verbatim_parts: list[str] = []
    normalized_parts: list[str] = []
    evidence_union: list[str] = []
    seen_evidence: set[str] = set()
    fingerprint_segments: list[dict[str, Any]] = []

    for segment in topology_segments:
        choice = selected_by_segment[segment.segment_id]
        try:
            loaded = load_exact_working_revision_document(
                dossier_id=ref_index.dossier_id,
                transcription_id=choice.transcription_id,
                revision_ref=choice.leaf_ref,
                workspace_id=ws,
            )
        except ExactWorkingRevisionLoadError as exc:
            raise DossierPublicationCandidateError(exc.code, exc.detail) from exc

        payload = loaded.document["payload"]
        verbatim = _extract_transcript_lane(
            payload,
            lane="source_transcript_verbatim",
            qualified_ref=choice.qualified_ref,
        )
        normalized = _extract_transcript_lane(
            payload,
            lane="normalized_or_mapping_transcript",
            qualified_ref=choice.qualified_ref,
        )
        evidence_refs = _validate_evidence_refs(
            loaded.document["evidence_refs"],
            bundle=bundle,
            qualified_ref=choice.qualified_ref,
        )

        built_segments.append(
            DossierPublicationSegment(
                segment_id=segment.segment_id,
                position=segment.position,
                transcription_id=choice.transcription_id,
                source_revision_ref=choice.qualified_ref,
                source_revision_sha256=loaded.content_sha256,
                source_transcript_verbatim=verbatim,
                normalized_or_mapping_transcript=normalized,
                evidence_refs=evidence_refs,
                revision_snapshot=loaded.document,
            )
        )
        ordered_refs.append(choice.qualified_ref)
        verbatim_parts.append(verbatim)
        normalized_parts.append(normalized)
        for ref in evidence_refs:
            if ref not in seen_evidence:
                seen_evidence.add(ref)
                evidence_union.append(ref)
        fingerprint_segments.append(
            {
                "segment_id": segment.segment_id,
                "transcription_id": choice.transcription_id,
                "source_revision_ref": choice.qualified_ref,
                "source_revision_sha256": loaded.content_sha256,
            }
        )

    fingerprint = _candidate_fingerprint(
        dossier_id=ref_index.dossier_id,
        workspace_id=ws,
        topology_fingerprint=inventory.topology_fingerprint,
        segments=fingerprint_segments,
    )
    return DossierPublicationCandidate(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        dossier_id=ref_index.dossier_id,
        workspace_id=ws,
        topology_fingerprint=inventory.topology_fingerprint,
        candidate_fingerprint=fingerprint,
        source_revision_refs=tuple(ordered_refs),
        segments=tuple(built_segments),
        source_transcript_verbatim=_SEGMENT_JOIN.join(verbatim_parts),
        normalized_or_mapping_transcript=_SEGMENT_JOIN.join(normalized_parts),
        evidence_refs=tuple(evidence_union),
    )


class _Selection:
    __slots__ = ("qualified_ref", "segment_id", "transcription_id", "leaf_ref")

    def __init__(
        self,
        *,
        qualified_ref: str,
        segment_id: str,
        transcription_id: str,
        leaf_ref: str,
    ) -> None:
        self.qualified_ref = qualified_ref
        self.segment_id = segment_id
        self.transcription_id = transcription_id
        self.leaf_ref = leaf_ref


def _ordered_topology_segments(
    segments: Sequence[DossierTranscriptSegmentInventory],
) -> list[DossierTranscriptSegmentInventory]:
    """Validate segment identities/positions and return canonical position order."""
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        raise DossierPublicationCandidateError("invalid_topology_segments")
    seen_ids: set[str] = set()
    seen_positions: set[int] = set()
    ordered: list[DossierTranscriptSegmentInventory] = []
    for segment in segments:
        if not isinstance(segment, DossierTranscriptSegmentInventory):
            raise DossierPublicationCandidateError("invalid_topology_segments")
        segment_id = segment.segment_id
        position = segment.position
        if type(segment_id) is not str or not segment_id.strip():
            raise DossierPublicationCandidateError("invalid_topology_segments")
        if type(position) is not int:
            raise DossierPublicationCandidateError("invalid_topology_segments")
        if segment_id in seen_ids:
            raise DossierPublicationCandidateError(
                "invalid_topology_segments",
                segment_id,
            )
        if position in seen_positions:
            raise DossierPublicationCandidateError(
                "invalid_topology_segments",
                str(position),
            )
        seen_ids.add(segment_id)
        seen_positions.add(position)
        ordered.append(segment)
    ordered.sort(key=lambda item: item.position)
    return ordered


def _normalize_selection(
    source_revision_refs: Sequence[str],
    *,
    bundle: DossierStartupInventoryBundle,
) -> list[_Selection]:
    if isinstance(source_revision_refs, (str, bytes)) or not isinstance(
        source_revision_refs, Sequence
    ):
        raise DossierPublicationCandidateError("invalid_selection_collection")
    if type(source_revision_refs) not in (list, tuple):
        raise DossierPublicationCandidateError("invalid_selection_collection")

    selected: list[_Selection] = []
    seen_refs: set[str] = set()
    seen_segments: set[str] = set()
    for item in source_revision_refs:
        if not isinstance(item, str):
            raise DossierPublicationCandidateError("invalid_selection_entry")
        text = item.strip()
        if not text:
            raise DossierPublicationCandidateError("invalid_selection_entry")
        if text in seen_refs:
            raise DossierPublicationCandidateError("duplicate_selected_ref", text)
        seen_refs.add(text)
        if not text.startswith("dossier_segment:"):
            raise DossierPublicationCandidateError("ref_not_exact_working_revision", text)
        try:
            target = bundle.ref_index.resolve(text)
        except DossierArtifactRefError as exc:
            if exc.code in {"dossier_ref_run_not_in_topology", "dossier_ref_required"}:
                raise DossierPublicationCandidateError("ref_outside_topology", text) from exc
            if exc.code in {
                "dossier_ref_kind_not_runtime_resolvable",
                "dossier_base_revision_invalid",
                "dossier_ref_invalid",
            }:
                raise DossierPublicationCandidateError(
                    "ref_not_exact_working_revision",
                    text,
                ) from exc
            raise DossierPublicationCandidateError("ref_outside_topology", text) from exc
        if parse_working_revision_ref(target.leaf_ref) is None:
            raise DossierPublicationCandidateError(
                "ref_not_exact_working_revision",
                text,
            )
        try:
            parsed = parse_dossier_qualified_ref(text)
        except DossierArtifactRefError as exc:
            raise DossierPublicationCandidateError(
                "ref_not_exact_working_revision",
                text,
            ) from exc
        if (
            parsed.segment_id != target.segment_id
            or parsed.transcription_id != target.transcription_id
            or parsed.leaf_ref != target.leaf_ref
        ):
            raise DossierPublicationCandidateError("ref_outside_topology", text)
        if target.segment_id in seen_segments:
            raise DossierPublicationCandidateError(
                "segment_selection_conflict",
                target.segment_id,
            )
        seen_segments.add(target.segment_id)
        selected.append(
            _Selection(
                qualified_ref=text,
                segment_id=target.segment_id,
                transcription_id=target.transcription_id,
                leaf_ref=target.leaf_ref,
            )
        )
    return selected


def _extract_transcript_lane(
    payload: dict[str, Any],
    *,
    lane: str,
    qualified_ref: str,
) -> str:
    if lane not in _TRANSCRIPT_LANES:
        raise DossierPublicationCandidateError("transcript_lane_invalid", lane)
    raw = payload.get(lane)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise DossierPublicationCandidateError("transcript_lane_invalid", qualified_ref)
        return text
    if isinstance(raw, dict):
        nested = raw.get("text")
        if not isinstance(nested, str):
            raise DossierPublicationCandidateError("transcript_lane_invalid", qualified_ref)
        text = nested.strip()
        if not text:
            raise DossierPublicationCandidateError("transcript_lane_invalid", qualified_ref)
        return text
    raise DossierPublicationCandidateError("transcript_lane_invalid", qualified_ref)


def _validate_evidence_refs(
    evidence_refs: Any,
    *,
    bundle: DossierStartupInventoryBundle,
    qualified_ref: str,
) -> tuple[str, ...]:
    if type(evidence_refs) is not list:
        raise DossierPublicationCandidateError("invalid_evidence_ref", qualified_ref)
    out: list[str] = []
    for item in evidence_refs:
        if not isinstance(item, str) or not item.strip():
            raise DossierPublicationCandidateError("invalid_evidence_ref", qualified_ref)
        text = item.strip()
        if not text.startswith("dossier_segment:"):
            raise DossierPublicationCandidateError("invalid_evidence_ref", text)
        try:
            bundle.ref_index.resolve(text)
        except DossierArtifactRefError as exc:
            raise DossierPublicationCandidateError("invalid_evidence_ref", text) from exc
        out.append(text)
    return tuple(out)


def _candidate_fingerprint(
    *,
    dossier_id: str,
    workspace_id: str,
    topology_fingerprint: str,
    segments: list[dict[str, Any]],
) -> str:
    payload = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "dossier_id": dossier_id,
        "workspace_id": workspace_id,
        "topology_fingerprint": topology_fingerprint,
        "segments": segments,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
