"""
Read-Mode Service for Evidence Expansion
=========================================

Provides a clean separation between lightweight evidence locators (from lanes)
and heavy corpus entry hydration.

Design principle:
- Lanes return lightweight EvidenceCard/EvidenceSpan with refs (locators)
- Read service does the heavy lifting of hydrating full CorpusEntry when needed

This keeps lanes fast and lets consumers decide when to pay the hydration cost.
"""

from __future__ import annotations

from typing import Optional

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusEntryRef

from .evidence.models import EvidenceCard, EvidenceSpan


def expand_evidence_to_entry(
    evidence: EvidenceCard | EvidenceSpan,
    corpus_provider: CorpusProvider,
) -> Optional[CorpusEntry]:
    """
    Expand an evidence locator to its full parent CorpusEntry.

    Takes a lightweight evidence reference (from a retrieval lane) and hydrates
    the full parent corpus entry using the corpus provider.

    Args:
        evidence: EvidenceCard or EvidenceSpan from a retrieval lane
        corpus_provider: Corpus provider for hydration

    Returns:
        Hydrated CorpusEntry if successful, None if hydration fails

    Example:
        >>> from corpus.virtual_corpus import get_virtual_corpus_provider
        >>> provider = get_virtual_corpus_provider()
        >>> 
        >>> # Semantic lane returns lightweight evidence
        >>> result = semantic_lane.search("query text")
        >>> card = result.cards[0]
        >>> 
        >>> # Expand to full entry when needed
        >>> entry = expand_evidence_to_entry(card, provider)
        >>> print(entry.text)  # Full hydrated text
    """
    # Extract the CorpusEntryRef
    if isinstance(evidence, EvidenceCard):
        if not evidence.spans:
            return None
        ref = evidence.spans[0].entry
    elif isinstance(evidence, EvidenceSpan):
        ref = evidence.entry
    else:
        return None

    # Hydrate the entry
    try:
        entry = corpus_provider.hydrate_entry(ref)
        return entry
    except Exception:
        # Hydration failed (entry not found, provider error, etc.)
        return None


def expand_span_to_entry(
    span: EvidenceSpan,
    corpus_provider: CorpusProvider,
) -> Optional[CorpusEntry]:
    """
    Convenience wrapper for expanding an EvidenceSpan to CorpusEntry.

    Args:
        span: EvidenceSpan from a retrieval lane
        corpus_provider: Corpus provider for hydration

    Returns:
        Hydrated CorpusEntry if successful, None otherwise
    """
    return expand_evidence_to_entry(span, corpus_provider)
