from __future__ import annotations

from typing import Iterable, Optional, Set

from corpus.interfaces import CorpusProvider
from corpus.types import (
    CorpusEntry,
    CorpusEntryKind,
    CorpusEntryRef,
    CorpusView,
)

from ...filters.models import RetrievalFilters
from .grep_backend import GrepBackendLexicalLane
from .normalize import NORMALIZER_VERSION


class FakeCorpusProvider(CorpusProvider):
    def __init__(self, entries: dict[str, CorpusEntry]) -> None:
        self._entries = entries

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
        kinds: Optional[Set[CorpusEntryKind]] = None,
    ) -> Iterable[CorpusEntryRef]:
        refs = []
        for entry in self._entries.values():
            if entry.ref.view != view:
                continue
            if dossier_id and entry.ref.dossier_id != dossier_id:
                continue
            if kinds and entry.ref.kind not in kinds:
                continue
            refs.append(entry.ref)
        return refs

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        return self._entries[ref.entry_id]


def _entry(
    entry_id: str,
    *,
    text: str,
    view: CorpusView = CorpusView.FINALIZED,
    kind: CorpusEntryKind = CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
    dossier_id: str = "D1",
) -> CorpusEntry:
    ref = CorpusEntryRef(
        view=view,
        entry_id=entry_id,
        kind=kind,
        dossier_id=dossier_id,
    )
    return CorpusEntry(ref=ref, text=text, title=entry_id, content_hash=f"hash:{entry_id}")


def test_raw_grep_finds_exact_match() -> None:
    entry = _entry("final:D1", text="alpha beta gamma")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)
    filters = RetrievalFilters(view=CorpusView.FINALIZED)

    result = lane.search("beta", filters=filters, limit=10)
    assert len(result.cards) == 1
    card = result.cards[0]
    assert card.spans[0].start == 6
    assert card.spans[0].end == 10
    assert card.spans[0].content_hash == "hash:final:D1"
    assert card.spans[0].trace is None
    assert card.spans[0].preview
    assert card.provenance["lane_mode"] == "raw"


def test_normalized_grep_finds_unicode_variant() -> None:
    text = "can\u2019t stop"
    entry = _entry("final:D2", text=text, dossier_id="D2")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="normalized", provider=provider)
    filters = RetrievalFilters(view=CorpusView.FINALIZED, dossier_id="D2")

    result = lane.search("can't", filters=filters, limit=10)
    assert len(result.cards) == 1
    card = result.cards[0]
    assert card.spans[0].text.endswith("can\u2019t stop")
    assert card.spans[0].content_hash == "hash:final:D2"
    assert card.spans[0].trace is not None
    assert card.spans[0].trace.space == "normalized"
    assert card.spans[0].trace.mapping_kind == "normalized_to_raw"
    assert card.spans[0].trace.normalizer_version == NORMALIZER_VERSION
    assert card.provenance["lane_mode"] == "normalized"
    assert card.provenance["normalization_version"] == "v1"
    assert card.provenance["matched_original_snippet"] == "can\u2019t"


# --- Scoring tests ---


def test_scoring_reflects_match_density() -> None:
    """Cards from entries with more matches should score higher."""
    # Entry with 3 matches
    entry1 = _entry("entry1", text="test word test again test more")
    # Entry with 1 match
    entry2 = _entry("entry2", text="test once")

    provider = FakeCorpusProvider({
        entry1.ref.entry_id: entry1,
        entry2.ref.entry_id: entry2,
    })
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)

    result = lane.search("test", limit=10)

    # Find cards from each entry
    entry1_cards = [c for c in result.cards if c.title == "entry1"]
    entry2_cards = [c for c in result.cards if c.title == "entry2"]

    assert len(entry1_cards) == 3
    assert len(entry2_cards) == 1

    # First match from dense entry should score higher than match from sparse entry
    assert entry1_cards[0].score > entry2_cards[0].score


def test_scoring_is_deterministic() -> None:
    """Same query on same entry should produce same scores."""
    entry = _entry("entry1", text="word word word")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)

    result1 = lane.search("word", limit=10)
    result2 = lane.search("word", limit=10)

    assert len(result1.cards) == len(result2.cards)
    for c1, c2 in zip(result1.cards, result2.cards):
        assert c1.score == c2.score


def test_scoring_earlier_matches_weighted_higher() -> None:
    """Earlier matches in text should have slightly higher scores."""
    # Long text with matches at start and end
    entry = _entry("entry1", text="match at start" + (" filler" * 100) + " match at end")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)

    result = lane.search("match", limit=10)

    assert len(result.cards) == 2
    # First match should have higher score due to position bonus
    assert result.cards[0].score > result.cards[1].score


def test_scores_within_valid_range() -> None:
    """All scores should be between 0.0 and 1.0."""
    entry = _entry("entry1", text="test test test test test")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)

    result = lane.search("test", limit=10)

    for card in result.cards:
        assert 0.0 <= card.score <= 1.0


def test_scoring_does_not_break_existing_match_fidelity() -> None:
    """Scoring should not change which matches are found."""
    entry = _entry("entry1", text="alpha beta gamma delta")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})

    # Old behavior: all scores were 1.0, but matches were still found correctly
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)
    result = lane.search("beta", limit=10)

    # Should still find the match at the same position
    assert len(result.cards) == 1
    assert result.cards[0].spans[0].start == 6
    assert result.cards[0].spans[0].end == 10


def test_scoring_preserves_card_id_format() -> None:
    """Card IDs should maintain the same format: lex:mode:entry_id:start:end."""
    entry = _entry("entry1", text="test word")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)

    result = lane.search("test", limit=10)

    assert len(result.cards) == 1
    card = result.cards[0]
    # ID format should be unchanged
    assert card.id.startswith("lex:raw:entry1:")
    assert ":" in card.id
    parts = card.id.split(":")
    assert len(parts) == 5  # lex, mode, entry_id, start, end


def test_scoring_with_normalized_mode() -> None:
    """Scoring should work correctly in normalized mode."""
    entry = _entry("entry1", text="can\u2019t can\u2019t can\u2019t")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="normalized", provider=provider)

    result = lane.search("can't", limit=10)

    assert len(result.cards) == 3
    # All cards should have valid scores
    for card in result.cards:
        assert 0.0 < card.score <= 1.0
    # First card should have highest or equal score
    assert result.cards[0].score >= result.cards[1].score


def test_scoring_with_single_match() -> None:
    """Single match should still get reasonable score."""
    entry = _entry("entry1", text="unique word here")
    provider = FakeCorpusProvider({entry.ref.entry_id: entry})
    lane = GrepBackendLexicalLane(mode="raw", provider=provider)

    result = lane.search("unique", limit=10)

    assert len(result.cards) == 1
    # Single match should have a score >= 0.5 (density_score base)
    assert result.cards[0].score >= 0.5
