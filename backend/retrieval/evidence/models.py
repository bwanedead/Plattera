from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from corpus.types import CorpusChunkRef, CorpusEntryRef


@dataclass(frozen=True)
class EvidenceSpan:
    """
    A citeable span of evidence.
    """

    entry: CorpusEntryRef
    text: str
    chunk: Optional[CorpusChunkRef] = None
    start: Optional[int] = None
    end: Optional[int] = None
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


