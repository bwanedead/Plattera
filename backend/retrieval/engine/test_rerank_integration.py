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
