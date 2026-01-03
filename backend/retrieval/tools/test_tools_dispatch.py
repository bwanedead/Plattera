from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pytest
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView

from ..evidence.models import EvidenceCard, EvidenceSpan, RetrievalResult
from ..filters.models import RetrievalFilters
from ..lanes.provenance.recipes import ProvenanceRecipe
from ..engine.retrieval_engine import HybridConfig, RetrievalEngine
from .hybrid_search import HybridSearchTool
from .lexical_search import LexicalSearchTool
from .provenance_search import ProvenanceSearchTool


@dataclass
class FakeEngine:
    last_query: Optional[str] = None
    last_filters: Optional[RetrievalFilters] = None
    last_limit: Optional[int] = None
    last_lanes: Optional[list[str]] = None
    called: bool = False
    hybrid_config: HybridConfig = field(default_factory=HybridConfig)

    def search(
        self,
        query: str,
        *,
        filters: Optional[RetrievalFilters] = None,
        limit: int = 10,
        lanes: Optional[list[str]] = None,
    ) -> RetrievalResult:
        self.called = True
        self.last_query = query
        self.last_filters = filters
        self.last_limit = limit
        self.last_lanes = lanes or []
        return RetrievalResult(query=query, cards=[], debug={"engine": "fake"})


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
        ref = CorpusEntryRef(
            view=CorpusView.FINALIZED,
            entry_id=f"prov:{dossier_id}",
            kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
            dossier_id=dossier_id,
        )
        span = EvidenceSpan(entry=ref, text="bundle")
        card = EvidenceCard(id=f"prov:{dossier_id}", spans=[span], score=1.0, lane="provenance")
        return RetrievalResult(query=dossier_id, cards=[card], debug={"recipe": recipe.value})


def _lex_card(entry_id: str, dossier_id: Optional[str], lane: str) -> EvidenceCard:
    ref = CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=entry_id,
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=dossier_id,
    )
    span = EvidenceSpan(entry=ref, text="match", start=0, end=5)
    return EvidenceCard(id=f"lex:{lane}:{entry_id}:0:5", spans=[span], score=1.0, lane=lane)


@pytest.mark.parametrize(
    "mode, expected_lanes",
    [
        ("raw", ["lexical.raw"]),
        ("normalized", ["lexical.normalized"]),
        ("both", ["lexical.raw", "lexical.normalized"]),
    ],
)
def test_lexical_tool_mode_mapping(mode: str, expected_lanes: list[str]) -> None:
    engine = FakeEngine()
    tool = LexicalSearchTool(engine=engine)

    result = tool("query", mode=mode)

    assert engine.last_lanes == expected_lanes
    assert engine.last_filters is not None
    assert engine.last_filters.view == CorpusView.FINALIZED
    assert result.debug["tool"] == "lexical_search"
    assert result.debug["lanes"] == expected_lanes
    assert result.debug["defaults"]["view"] == CorpusView.FINALIZED.value
    assert result.debug["gating_errors"] == []


def test_provenance_tool_requires_dossier_id() -> None:
    engine = FakeEngine()
    tool = ProvenanceSearchTool(engine=engine)

    result = tool(None)

    assert engine.called is False
    assert result.debug["gating_errors"] == ["provenance_requires_dossier_id"]


def test_provenance_tool_calls_engine_with_recipe() -> None:
    engine = FakeEngine()
    tool = ProvenanceSearchTool(engine=engine)

    result = tool("D1", recipe="FINAL_ONLY")

    assert engine.called is True
    assert engine.last_lanes == ["provenance"]
    assert engine.last_filters is not None
    assert engine.last_filters.dossier_id == "D1"
    assert engine.last_filters.extra.get("provenance_recipe") == "FINAL_ONLY"
    assert result.debug["overrides"]["recipe"] == "FINAL_ONLY"


def test_hybrid_tool_calls_hybrid_lane() -> None:
    engine = FakeEngine()
    tool = HybridSearchTool(engine=engine)

    result = tool("query")

    assert engine.last_lanes == ["hybrid"]
    assert result.debug["tool"] == "hybrid_search"
    assert result.debug["lanes"] == ["hybrid"]
    assert result.debug["gating_errors"] == []


def test_hybrid_tool_returns_provenance_cards() -> None:
    raw_cards = [_lex_card("raw:A", "A", "lexical.raw")]
    norm_cards = [_lex_card("norm:B", "B", "lexical.normalized")]
    provenance = FakeProvenanceLane()
    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane(raw_cards),
        lexical_normalized_lane=FakeLexicalLane(norm_cards),
        provenance_lane=provenance,
    )
    tool = HybridSearchTool(engine=engine)

    result = tool("query", limit=10)

    prov_ids = [card.id for card in result.cards if card.lane == "provenance"]
    assert prov_ids == ["prov:A", "prov:B"]
    assert result.debug["lane_debug"]["hybrid"]["anchors_used"] == ["A", "B"]


def test_provenance_recipe_typo_fallback_notes() -> None:
    provenance = FakeProvenanceLane()
    engine = RetrievalEngine(
        lexical_raw_lane=FakeLexicalLane([]),
        lexical_normalized_lane=FakeLexicalLane([]),
        provenance_lane=provenance,
    )
    tool = ProvenanceSearchTool(engine=engine)

    result = tool("D9", recipe="CANONCIAL_STACK")

    assert provenance.calls == ["D9"]
    assert any("unknown_provenance_recipe_fallback:" in note for note in result.debug["notes"])
