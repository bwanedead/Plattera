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
