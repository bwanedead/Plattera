from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Optional, Sequence


class CorpusView(str, Enum):
    """
    High-level corpus routing modes ("views") used by retrieval and agents.
    """

    FINALIZED = "finalized"
    EVERYTHING = "everything"
    ARTIFACTS = "artifacts"


class CorpusEntryKind(str, Enum):
    """
    Coarse kind for a retrievable corpus entry.

    Keep the initial set small; we can extend as new artifact types become
    retrieval targets.
    """

    FINALIZED_DOSSIER_TEXT = "finalized_dossier_text"
    TRANSCRIPT = "transcript"
    SCHEMA_JSON = "schema_json"
    GEOREF_JSON = "georef_json"
    IMAGE_OCR_TEXT = "image_ocr_text"


@dataclass(frozen=True)
class CorpusEntryRef:
    """
    Stable identifier for a corpus entry.

    This should be used everywhere instead of raw filesystem paths. The corpus
    adapters decide how to resolve this reference into the actual stored
    content.
    """

    view: CorpusView
    entry_id: str
    kind: CorpusEntryKind
    dossier_id: Optional[str] = None
    transcription_id: Optional[str] = None
    artifact_type: Optional[str] = None  # e.g., "schema", "georef"
    artifact_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CorpusChunkRef:
    """
    Stable pointer to a span/chunk inside an entry.

    For v0, we keep this minimal; later we can add token offsets, byte offsets,
    and chunk identifiers tied to a materialized corpus.
    """

    entry: CorpusEntryRef
    chunk_id: str
    start: Optional[int] = None
    end: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorpusEntry:
    """
    Hydrated corpus entry payload.
    """

    ref: CorpusEntryRef
    text: str
    mime_type: str = "text/plain"
    title: Optional[str] = None
    created_at: Optional[str] = None  # ISO-8601 when available
    content_hash: Optional[str] = None
    structured_json: Optional[Dict[str, Any]] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


def iter_entry_texts(entries: Sequence[CorpusEntry]) -> Iterable[str]:
    """
    Convenience generator to iterate over entry text payloads.
    """

    for e in entries:
        yield e.text



