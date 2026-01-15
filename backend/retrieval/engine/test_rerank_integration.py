from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView

from ..evidence.models import EvidenceCard, EvidenceSpan, RetrievalResult
from ..filters.models import RetrievalFilters
from .retrieval_engine import RetrievalEngine


@dataclass
class FakeLexicalLane:
    cards: List[EvidenceCard] = field(default_factory=list)

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        if limit:
            cards = self.cards[:limit]
        else:
            cards = list(self.cards)
        return RetrievalResult(query=query, cards=cards, debug={"lane": "fake_lexical"})


@dataclass
class FakeRerankLane:
    """Fake reranker that reverses the order of cards."""

    calls: List[tuple[str, int]] = field(default_factory=list)

    def rerank(self, query: str, cards: List[EvidenceCard]) -> List[EvidenceCard]:
        self.calls.append((query, len(cards)))
        # Reverse order to demonstrate rerank occurred
        return list(reversed(cards))


def _make_card(card_id: str, score: float, lane: str) -> EvidenceCard:
    """Helper to create a minimal evidence card."""
    ref = CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=card_id,
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=None,
    )
    span = EvidenceSpan(entry=ref, text="test")
    return EvidenceCard(id=card_id, spans=[span], score=score, lane=lane)


def test_rerank_disabled_by_default() -> None:
    """Rerank should not run by default."""
    cards = [_make_card("card1", 0.9, "lexical.raw")]
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    result = engine.search("query", lanes=["lexical.raw"], limit=10)

    # Rerank should not be called
    assert reranker.calls == []
    assert result.debug["lane_debug"]["rerank"]["enabled"] is False


def test_rerank_enabled_via_filters_extra() -> None:
    """Rerank should run when filters.extra['rerank'] is True."""
    cards = [
        _make_card("card1", 0.9, "lexical.raw"),
        _make_card("card2", 0.8, "lexical.raw"),
        _make_card("card3", 0.7, "lexical.raw"),
    ]
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # Rerank should be called
    assert reranker.calls == [("query", 3)]
    assert result.debug["lane_debug"]["rerank"]["pre_rerank_count"] == 3
    assert result.debug["lane_debug"]["rerank"]["post_rerank_count"] == 3


def test_rerank_reorders_cards() -> None:
    """Rerank should reorder cards and mark reorder_occurred."""
    cards = [
        _make_card("card1", 0.9, "lexical.raw"),
        _make_card("card2", 0.8, "lexical.raw"),
        _make_card("card3", 0.7, "lexical.raw"),
    ]
    reranker = FakeRerankLane()  # Reverses order

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # Check reordering occurred
    rerank_debug = result.debug["lane_debug"]["rerank"]
    assert rerank_debug["reorder_occurred"] is True
    assert rerank_debug["pre_rerank_ids"][:3] == ["card1", "card2", "card3"]
    assert rerank_debug["post_rerank_ids"][:3] == ["card3", "card2", "card1"]


def test_rerank_annotates_provenance() -> None:
    """Rerank should annotate cards with provenance."""
    cards = [
        _make_card("card1", 0.9, "lexical.raw"),
        _make_card("card2", 0.8, "lexical.raw"),
    ]
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # All cards should have rerank provenance
    for card in result.cards:
        assert "rerank" in card.provenance
        assert card.provenance["rerank"]["applied"] is True
        assert card.provenance["rerank"]["query"] == "query"


def test_rerank_preserves_card_shape() -> None:
    """Rerank should not change EvidenceCard schema."""
    cards = [_make_card("card1", 0.9, "lexical.raw")]
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # Card should still have all standard fields
    card = result.cards[0]
    assert hasattr(card, "id")
    assert hasattr(card, "spans")
    assert hasattr(card, "score")
    assert hasattr(card, "lane")
    assert hasattr(card, "provenance")


def test_rerank_not_enabled_with_false_value() -> None:
    """Rerank should not run if filters.extra['rerank'] is False."""
    cards = [_make_card("card1", 0.9, "lexical.raw")]
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": False})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # Rerank should not be called
    assert reranker.calls == []
    assert result.debug["lane_debug"]["rerank"]["enabled"] is False


def test_rerank_not_enabled_with_missing_key() -> None:
    """Rerank should not run if filters.extra doesn't have 'rerank' key."""
    cards = [_make_card("card1", 0.9, "lexical.raw")]
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"other_key": "value"})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # Rerank should not be called
    assert reranker.calls == []
    assert result.debug["lane_debug"]["rerank"]["enabled"] is False


def test_rerank_with_empty_cards() -> None:
    """Rerank should handle empty card list gracefully."""
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane([]),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # Rerank should be called with empty list
    assert reranker.calls == [("query", 0)]
    assert result.debug["lane_debug"]["rerank"]["pre_rerank_count"] == 0
    assert result.debug["lane_debug"]["rerank"]["post_rerank_count"] == 0


def test_rerank_with_hybrid_semantic_lane() -> None:
    """Rerank should work with hybrid_semantic fusion."""
    raw_cards = [_make_card("raw1", 0.9, "lexical.raw")]
    norm_cards = [_make_card("norm1", 0.8, "lexical.normalized")]
    reranker = FakeRerankLane()

    # Need a minimal fake semantic lane
    @dataclass
    class FakeSemanticLane:
        def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
            return RetrievalResult(query=query, cards=[], debug={})

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        semantic_lane=FakeSemanticLane(),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["hybrid_semantic"], filters=filters, limit=10)

    # Rerank should be called after fusion
    assert len(reranker.calls) == 1
    assert reranker.calls[0][0] == "query"
    # Should have fused cards from raw and norm lanes
    assert reranker.calls[0][1] == 2  # 2 cards fused


def test_rerank_ordering_is_not_undone_by_subsequent_sort() -> None:
    """
    CRITICAL: Verify rerank ordering is preserved and not undone by score sorting.

    This test guards against the footgun where rerank reorders cards but then
    a subsequent sort_by_score() call undoes the reranking.
    """
    # Create cards with scores that would sort differently than rerank order
    cards = [
        _make_card("card1", 0.9, "lexical.raw"),  # High score
        _make_card("card2", 0.5, "lexical.raw"),  # Low score  
        _make_card("card3", 0.7, "lexical.raw"),  # Medium score
    ]

    # Fake reranker reverses order (so card3, card2, card1)
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=10)

    # Critical assertion: final order should match rerank's reversed order
    # NOT the original score-sorted order
    assert len(result.cards) == 3
    assert result.cards[0].id == "card3"  # Reversed by rerank
    assert result.cards[1].id == "card2"  # Reversed by rerank
    assert result.cards[2].id == "card1"  # Reversed by rerank

    # If this fails, it means rerank was undone by subsequent sorting
    # (cards would be: card1[0.9], card3[0.7], card2[0.5] if sorted by score)


def test_rerank_ordering_respects_limit_but_not_score() -> None:
    """Verify limit truncates reranked results without re-sorting them."""
    cards = [
        _make_card("card1", 0.9, "lexical.raw"),
        _make_card("card2", 0.8, "lexical.raw"),
        _make_card("card3", 0.7, "lexical.raw"),
        _make_card("card4", 0.6, "lexical.raw"),
        _make_card("card5", 0.5, "lexical.raw"),
    ]

    # Reranker reverses order
    reranker = FakeRerankLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=reranker,
    )

    filters = RetrievalFilters(extra={"rerank": True})
    result = engine.search("query", lanes=["lexical.raw"], filters=filters, limit=3)

    # Should get first 3 from reversed order, not top 3 by score
    assert len(result.cards) == 3
    assert result.cards[0].id == "card5"  # First in reranked order
    assert result.cards[1].id == "card4"  # Second in reranked order
    assert result.cards[2].id == "card3"  # Third in reranked order


def test_rerank_disabled_allows_score_sorting() -> None:
    """When rerank disabled, cards should still be sorted by score."""
    cards = [
        _make_card("card1", 0.5, "lexical.raw"),  # Low score
        _make_card("card2", 0.9, "lexical.raw"),  # High score
        _make_card("card3", 0.7, "lexical.raw"),  # Medium score
    ]

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(cards),
        rerank_lane=FakeRerankLane(),  # Won't be called
    )

    # No rerank enabled
    result = engine.search("query", lanes=["lexical.raw"], limit=10)

    # Should be sorted by score
    assert result.cards[0].id == "card2"  # 0.9
    assert result.cards[1].id == "card3"  # 0.7
    assert result.cards[2].id == "card1"  # 0.5
