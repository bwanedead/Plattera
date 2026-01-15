from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView

from ..evidence.models import EvidenceCard, EvidenceSpan, RetrievalResult
from ..filters.models import RetrievalFilters
from ..lanes.provenance.recipes import ProvenanceRecipe
from .retrieval_engine import HybridConfig, RetrievalEngine


def _entry_ref(entry_id: str, dossier_id: str | None) -> CorpusEntryRef:
    return CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=entry_id,
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=dossier_id,
    )


def _lex_card(entry_id: str, dossier_id: str | None, lane: str) -> EvidenceCard:
    ref = _entry_ref(entry_id, dossier_id)
    span = EvidenceSpan(entry=ref, text="match", start=0, end=5)
    return EvidenceCard(
        id=f"lex:{lane}:{entry_id}:0:5",
        spans=[span],
        score=1.0,
        lane=lane,
    )


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
class FakeProvenanceLane:
    calls: List[str] = field(default_factory=list)

    def search(
        self,
        dossier_id: str,
        *,
        recipe: ProvenanceRecipe = ProvenanceRecipe.CANONICAL_STACK,
        filters: RetrievalFilters | None = None,
    ) -> RetrievalResult:
        self.calls.append(dossier_id)
        ref = _entry_ref(f"prov:{dossier_id}", dossier_id)
        span = EvidenceSpan(entry=ref, text="bundle")
        card = EvidenceCard(
            id=f"prov:{dossier_id}",
            spans=[span],
            score=1.0,
            lane="provenance",
        )
        return RetrievalResult(query=dossier_id, cards=[card], debug={"recipe": recipe.value})


def test_hybrid_runs_provenance_for_anchors() -> None:
    raw_cards = [
        _lex_card("raw:A", "A", "lexical.raw"),
    ]
    norm_cards = [
        _lex_card("norm:B", "B", "lexical.normalized"),
    ]
    provenance = FakeProvenanceLane()
    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        provenance_lane=provenance,
    )

    result = engine.search("query", lanes=["hybrid"], limit=5)

    assert provenance.calls == ["A", "B"]
    assert result.debug["lane_debug"]["hybrid"]["anchors_used"] == ["A", "B"]
    prov_ids = [card.id for card in result.cards if card.lane == "provenance"]
    assert prov_ids == ["prov:A", "prov:B"]


def test_hybrid_skips_provenance_without_anchors() -> None:
    raw_cards = [_lex_card("raw:1", None, "lexical.raw")]
    norm_cards = [_lex_card("norm:1", None, "lexical.normalized")]
    provenance = FakeProvenanceLane()
    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        provenance_lane=provenance,
    )

    result = engine.search("query", lanes=["hybrid"], limit=5)

    assert provenance.calls == []
    assert result.debug["lane_debug"]["hybrid"]["note"] == "no_anchors_found"


def test_hybrid_respects_max_anchor_dossiers() -> None:
    raw_cards = [
        _lex_card("raw:A", "A", "lexical.raw"),
        _lex_card("raw:B", "B", "lexical.raw"),
        _lex_card("raw:C", "C", "lexical.raw"),
    ]
    norm_cards = [
        _lex_card("norm:D", "D", "lexical.normalized"),
    ]
    provenance = FakeProvenanceLane()
    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        provenance_lane=provenance,
        hybrid_config=HybridConfig(max_anchor_dossiers=2),
    )

    result = engine.search("query", lanes=["hybrid"], limit=5)

    assert provenance.calls == ["A", "B"]
    assert result.debug["lane_debug"]["hybrid"]["anchors_used"] == ["A", "B"]


def test_provenance_requires_dossier_id() -> None:
    provenance = FakeProvenanceLane()
    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane([]),
        lexical_normalized_lane=FakeLexicalLane([]),
        provenance_lane=provenance,
    )

    result = engine.search("query", lanes=["provenance"], filters=None, limit=5)

    assert provenance.calls == []
    assert result.debug["lane_debug"]["provenance"]["error"] == "provenance_requires_dossier_id"


# --- Tests for hybrid_semantic lane ---


@dataclass
class FakeSemanticLane:
    cards: List[EvidenceCard] = field(default_factory=list)

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        if limit:
            cards = self.cards[:limit]
        else:
            cards = list(self.cards)
        return RetrievalResult(query=query, cards=cards, debug={"lane": "fake_semantic"})


def _sem_card(entry_id: str, score: float) -> EvidenceCard:
    ref = _entry_ref(entry_id, None)
    span = EvidenceSpan(entry=ref, text="semantic_match", start=0, end=14)
    return EvidenceCard(
        id=f"sem:{entry_id}:0:14",
        spans=[span],
        score=score,
        lane="semantic",
    )


def test_hybrid_semantic_fuses_three_lanes() -> None:
    """hybrid_semantic should run lexical.raw, lexical.normalized, and semantic, then fuse."""
    raw_cards = [
        EvidenceCard(id="raw:A", spans=[EvidenceSpan(entry=_entry_ref("A", None), text="raw")], score=0.9, lane="lexical.raw"),
    ]
    norm_cards = [
        EvidenceCard(id="norm:B", spans=[EvidenceSpan(entry=_entry_ref("B", None), text="norm")], score=0.8, lane="lexical.normalized"),
    ]
    sem_cards = [_sem_card("C", 0.7)]

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        semantic_lane=FakeSemanticLane(sem_cards),
    )

    result = engine.search("query", lanes=["hybrid_semantic"], limit=10)

    # Should have all 3 cards
    assert len(result.cards) == 3
    ids = [c.id for c in result.cards]
    assert "raw:A" in ids
    assert "norm:B" in ids
    assert "sem:C:0:14" in ids

    # Should be sorted by score (0.9, 0.8, 0.7)
    assert result.cards[0].id == "raw:A"
    assert result.cards[1].id == "norm:B"
    assert result.cards[2].id == "sem:C:0:14"


def test_hybrid_semantic_debug_output() -> None:
    """hybrid_semantic debug should include per-lane diagnostics and fusion config."""
    raw_cards = [
        EvidenceCard(id="raw:1", spans=[EvidenceSpan(entry=_entry_ref("1", None), text="raw")], score=0.5, lane="lexical.raw"),
    ]
    norm_cards = [
        EvidenceCard(id="norm:2", spans=[EvidenceSpan(entry=_entry_ref("2", None), text="norm")], score=0.6, lane="lexical.normalized"),
    ]
    sem_cards = [_sem_card("3", 0.7)]

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        semantic_lane=FakeSemanticLane(sem_cards),
    )

    result = engine.search("query", lanes=["hybrid_semantic"], limit=5)

    hybrid_debug = result.debug["lane_debug"]["hybrid_semantic"]

    # Should have fusion config
    assert "fusion_config" in hybrid_debug
    assert hybrid_debug["fusion_config"]["per_lane_cap"] == 5
    assert hybrid_debug["fusion_config"]["lane_order"] == ["lexical.raw", "lexical.normalized", "semantic"]

    # Should have per-lane debug
    assert "per_lane_debug" in hybrid_debug
    assert "lexical.raw" in hybrid_debug["per_lane_debug"]
    assert "lexical.normalized" in hybrid_debug["per_lane_debug"]
    assert "semantic" in hybrid_debug["per_lane_debug"]

    # Should have per-lane counts
    assert hybrid_debug["per_lane_counts"]["lexical.raw"] == 1
    assert hybrid_debug["per_lane_counts"]["lexical.normalized"] == 1
    assert hybrid_debug["per_lane_counts"]["semantic"] == 1

    # Should have fusion counts
    assert hybrid_debug["fused_count"] == 3
    assert hybrid_debug["fused_unique_ids"] == 3


def test_hybrid_semantic_deduplication() -> None:
    """hybrid_semantic should dedupe cards with same id, keeping first occurrence."""
    duplicate_id = "lex:dup:0:5"
    raw_cards = [
        EvidenceCard(
            id=duplicate_id,
            spans=[EvidenceSpan(entry=_entry_ref("dup", None), text="match")],
            score=0.5,
            lane="lexical.raw",
        ),
    ]
    norm_cards = [
        EvidenceCard(
            id=duplicate_id,
            spans=[EvidenceSpan(entry=_entry_ref("dup", None), text="match")],
            score=0.9,  # Higher score but later lane
            lane="lexical.normalized",
        ),
    ]

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        semantic_lane=FakeSemanticLane([]),
    )

    result = engine.search("query", lanes=["hybrid_semantic"], limit=10)

    # Should only have 1 card (deduped)
    assert len(result.cards) == 1
    assert result.cards[0].id == duplicate_id
    # Should be from lexical.raw (first occurrence)
    assert result.cards[0].lane == "lexical.raw"
    assert result.cards[0].score == 0.5


def test_hybrid_semantic_respects_per_lane_cap() -> None:
    """hybrid_semantic should respect per-lane cap based on limit."""
    raw_cards = [
        EvidenceCard(id=f"raw:{i}", spans=[EvidenceSpan(entry=_entry_ref(f"raw{i}", None), text="raw")], score=0.5, lane="lexical.raw")
        for i in range(20)
    ]
    norm_cards = [
        EvidenceCard(id=f"norm:{i}", spans=[EvidenceSpan(entry=_entry_ref(f"norm{i}", None), text="norm")], score=0.5, lane="lexical.normalized")
        for i in range(20)
    ]

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        semantic_lane=FakeSemanticLane([]),
    )

    result = engine.search("query", lanes=["hybrid_semantic"], limit=5)

    # Each lane should be capped at 5, so max 15 total before final limit
    # But final limit is also 5, so we get 5 cards
    assert len(result.cards) <= 5

    # Check debug shows correct per-lane cap
    assert result.debug["lane_debug"]["hybrid_semantic"]["fusion_config"]["per_lane_cap"] == 5


def test_hybrid_vs_hybrid_semantic_are_independent() -> None:
    """Existing 'hybrid' (lexical→provenance) should remain unchanged."""
    raw_cards = [_lex_card("raw:A", "A", "lexical.raw")]
    norm_cards = [_lex_card("norm:B", "B", "lexical.normalized")]
    provenance = FakeProvenanceLane()

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        semantic_lane=FakeSemanticLane([]),
        provenance_lane=provenance,
    )

    # Test old hybrid still works (lexical → provenance)
    result_hybrid = engine.search("query", lanes=["hybrid"], limit=5)
    assert provenance.calls == ["A", "B"]
    assert result_hybrid.debug["lane_debug"]["hybrid"]["anchors_used"] == ["A", "B"]

    # Reset provenance calls
    provenance.calls = []

    # Test new hybrid_semantic (no provenance)
    result_hybrid_semantic = engine.search("query", lanes=["hybrid_semantic"], limit=5)
    assert provenance.calls == []  # Should not call provenance
    assert "hybrid_semantic" in result_hybrid_semantic.debug["lane_debug"]
    assert "fusion_config" in result_hybrid_semantic.debug["lane_debug"]["hybrid_semantic"]


def test_hybrid_semantic_with_filters() -> None:
    """hybrid_semantic should pass filters to all lanes."""
    raw_cards = [_lex_card("raw:A", "doss1", "lexical.raw")]
    norm_cards = []
    sem_cards = []

    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        semantic_lane=FakeSemanticLane(sem_cards),
    )

    filters = RetrievalFilters(dossier_id="doss1")
    result = engine.search("query", lanes=["hybrid_semantic"], filters=filters, limit=10)

    # Filters should be in debug
    assert result.debug["filters"]["dossier_id"] == "doss1"
    # Should still return results (fake lanes don't enforce filters, but real ones would)
    assert len(result.cards) >= 1
