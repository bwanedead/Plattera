from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from corpus.types import CorpusChunkRef, CorpusEntryRef


@dataclass(frozen=True)
class MatchTrace:
    """
    Optional provenance trace for how a span was found.
    """

    space: Literal["normalized"]
    normalized_start: int
    normalized_end: int
    normalized_preview: str
    mapping_kind: Literal["normalized_to_raw"]
    normalizer_version: str


@dataclass(frozen=True)
class EvidenceSpan:
    """
    A citeable span of evidence. Offsets always refer to canonical/raw text.
    """

    entry: CorpusEntryRef
    text: str
    chunk: Optional[CorpusChunkRef] = None
    start: Optional[int] = None
    end: Optional[int] = None
    content_hash: Optional[str] = None
    preview: Optional[str] = None
    trace: Optional[MatchTrace] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceCard:
    """
    Primary retrieval output object for downstream agents/UI.
    """

    id: str
    spans: List[EvidenceSpan]
    score: float = 0.0
    lane: str = "unknown"  # lexical|semantic|hybrid|rerank
    title: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """
    Normalized result container returned by the retrieval engine/tool wrappers.
    """

    query: str
    cards: List[EvidenceCard] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)


