from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence


class CorpusView(str, Enum):
    """
    High-level corpus routing modes ("channels") used by retrieval and agents.
    """

    FINALIZED = "finalized"
    EVERYTHING = "everything"
    ARTIFACTS = "artifacts"


@dataclass(frozen=True)
class CorpusDocRef:
    """
    Stable identifier for a corpus document.

    This should be used everywhere instead of raw filesystem paths. The corpus adapters
    decide how to resolve this reference into the actual stored content.
    """

    view: CorpusView
    doc_id: str
    dossier_id: Optional[str] = None
    transcription_id: Optional[str] = None
    artifact_type: Optional[str] = None  # e.g., "schema", "georef"
    artifact_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CorpusChunkRef:
    """
    Stable pointer to a span/chunk inside a document.

    For v0, we keep this minimal; later we can add token offsets, byte offsets, etc.
    """

    doc: CorpusDocRef
    chunk_id: str
    start: Optional[int] = None
    end: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorpusDoc:
    """
    Hydrated corpus document payload.
    """

    ref: CorpusDocRef
    text: str
    mime_type: str = "text/plain"
    provenance: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


def iter_doc_texts(docs: Sequence[CorpusDoc]) -> Iterable[str]:
    for d in docs:
        yield d.text


