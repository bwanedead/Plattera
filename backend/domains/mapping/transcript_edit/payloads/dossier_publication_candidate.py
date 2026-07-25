"""Dossier transcript publication candidate contracts (semantic shapes only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CANDIDATE_SCHEMA_VERSION = "dossier_transcript_edit_publication_candidate.v1"


@dataclass(frozen=True)
class DossierPublicationSegment:
    segment_id: str
    position: int
    transcription_id: str
    source_revision_ref: str
    source_revision_sha256: str
    source_transcript_verbatim: str
    normalized_or_mapping_transcript: str
    evidence_refs: tuple[str, ...]
    revision_snapshot: dict[str, Any]


@dataclass(frozen=True)
class DossierPublicationCandidate:
    schema_version: str
    dossier_id: str
    workspace_id: str
    topology_fingerprint: str
    candidate_fingerprint: str
    source_revision_refs: tuple[str, ...]
    segments: tuple[DossierPublicationSegment, ...]
    source_transcript_verbatim: str
    normalized_or_mapping_transcript: str
    evidence_refs: tuple[str, ...]
