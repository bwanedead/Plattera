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
    return CorpusEntry(ref=ref, text=text, title=entry_id)


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
    assert card.provenance["lane_mode"] == "normalized"
    assert card.provenance["normalization_version"] == "v1"
    assert card.provenance["matched_original_snippet"] == "can\u2019t"
