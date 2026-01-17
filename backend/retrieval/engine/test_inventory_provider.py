from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView

from .inventory_provider import InventoryProvider


@dataclass
class StubCorpusProvider(CorpusProvider):
    entries: List[CorpusEntry]

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
        kinds: Optional[Set[CorpusEntryKind]] = None,
    ) -> Iterable[CorpusEntryRef]:
        for entry in self.entries:
            if entry.ref.view != view:
                continue
            if dossier_id and entry.ref.dossier_id != dossier_id:
                continue
            if kinds and entry.ref.kind not in kinds:
                continue
            yield entry.ref

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        for entry in self.entries:
            if entry.ref == ref:
                return entry
        raise ValueError(f"Entry not found: {ref.entry_id}")


def test_inventory_provider_final_segments_signatures():
    text_a = "Segment A text."
    text_b = "Segment B text."
    ref_a = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="segment_final:D1:seg_001:T1",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="D1",
        segment_id="seg_001",
        transcription_id="T1",
    )
    ref_b = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="segment_final:D1:seg_002:T1",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="D1",
        segment_id="seg_002",
        transcription_id="T1",
    )

    entry_a = CorpusEntry(
        ref=ref_a,
        text=text_a,
        content_hash=hashlib.sha256(text_a.encode()).hexdigest(),
    )
    entry_b = CorpusEntry(
        ref=ref_b,
        text=text_b,
        content_hash=hashlib.sha256(text_b.encode()).hexdigest(),
    )

    corpus = StubCorpusProvider(entries=[entry_a, entry_b])
    provider = InventoryProvider(corpus_provider=corpus, view=CorpusView.FINAL_SEGMENTS)

    slices = provider.list_slices(pool_identifier="FINAL_SEGMENTS")
    assert len(slices) == 2

    by_entry = {s.entry_id: s for s in slices}
    assert by_entry[ref_a.entry_id].dossier_id == "D1"
    assert by_entry[ref_a.entry_id].desired_signature == entry_a.content_hash
    assert by_entry[ref_b.entry_id].desired_signature == entry_b.content_hash
