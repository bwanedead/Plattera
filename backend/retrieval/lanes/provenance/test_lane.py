from __future__ import annotations

from typing import Iterable, Optional, Set

from corpus.interfaces import CorpusProvider
from corpus.types import (
    CorpusEntry,
    CorpusEntryKind,
    CorpusEntryRef,
    CorpusView,
)

from .lane import ProvenanceLane
from .recipes import ProvenanceRecipe


class FakeCorpusProvider(CorpusProvider):
    def __init__(self, entries: dict[tuple[str, CorpusEntryKind], CorpusEntry]) -> None:
        self._entries = entries

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
        kinds: Optional[Set[CorpusEntryKind]] = None,
    ) -> Iterable[CorpusEntryRef]:
        return []

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        key = (ref.dossier_id or "", ref.kind)
        if key in self._entries:
            return self._entries[key]
        return CorpusEntry(ref=ref, text="", provenance={"error": "missing"})


def _entry_for(dossier_id: str, kind: CorpusEntryKind, text: str) -> CorpusEntry:
    ref = CorpusEntryRef(
        view=CorpusView.ARTIFACTS,
        entry_id=f"{kind.value}:{dossier_id}",
        kind=kind,
        dossier_id=dossier_id,
    )
    return CorpusEntry(ref=ref, text=text, provenance={"source": "fake"})


def test_final_only_returns_single_card() -> None:
    dossier_id = "D1"
    entries = {
        (dossier_id, CorpusEntryKind.FINALIZED_DOSSIER_TEXT): _entry_for(
            dossier_id, CorpusEntryKind.FINALIZED_DOSSIER_TEXT, "final text"
        )
    }
    lane = ProvenanceLane(provider=FakeCorpusProvider(entries))
    result = lane.search(dossier_id, recipe=ProvenanceRecipe.FINAL_ONLY)

    assert [card.id for card in result.cards] == [
        f"prov:{ProvenanceRecipe.FINAL_ONLY.value}:{dossier_id}:{CorpusEntryKind.FINALIZED_DOSSIER_TEXT.value}"
    ]


def test_artifacts_only_returns_two_cards_in_order() -> None:
    dossier_id = "D2"
    entries = {
        (dossier_id, CorpusEntryKind.SCHEMA_JSON): _entry_for(
            dossier_id, CorpusEntryKind.SCHEMA_JSON, '{"schema": true}'
        ),
        (dossier_id, CorpusEntryKind.GEOREF_JSON): _entry_for(
            dossier_id, CorpusEntryKind.GEOREF_JSON, '{"georef": true}'
        ),
    }
    lane = ProvenanceLane(provider=FakeCorpusProvider(entries))
    result = lane.search(dossier_id, recipe=ProvenanceRecipe.ARTIFACTS_ONLY)

    assert [card.id for card in result.cards] == [
        f"prov:{ProvenanceRecipe.ARTIFACTS_ONLY.value}:{dossier_id}:{CorpusEntryKind.SCHEMA_JSON.value}",
        f"prov:{ProvenanceRecipe.ARTIFACTS_ONLY.value}:{dossier_id}:{CorpusEntryKind.GEOREF_JSON.value}",
    ]


def test_missing_schema_reports_missing_kind() -> None:
    dossier_id = "D3"
    entries = {
        (dossier_id, CorpusEntryKind.GEOREF_JSON): _entry_for(
            dossier_id, CorpusEntryKind.GEOREF_JSON, '{"georef": true}'
        ),
    }
    lane = ProvenanceLane(provider=FakeCorpusProvider(entries))
    result = lane.search(dossier_id, recipe=ProvenanceRecipe.ARTIFACTS_ONLY)

    assert [card.id for card in result.cards] == [
        f"prov:{ProvenanceRecipe.ARTIFACTS_ONLY.value}:{dossier_id}:{CorpusEntryKind.GEOREF_JSON.value}"
    ]
    assert CorpusEntryKind.SCHEMA_JSON.value in result.debug.get("missing_kinds", [])


def test_canonical_stack_orders_kinds() -> None:
    dossier_id = "D4"
    entries = {
        (dossier_id, CorpusEntryKind.FINALIZED_DOSSIER_TEXT): _entry_for(
            dossier_id, CorpusEntryKind.FINALIZED_DOSSIER_TEXT, "final"
        ),
        (dossier_id, CorpusEntryKind.SCHEMA_JSON): _entry_for(
            dossier_id, CorpusEntryKind.SCHEMA_JSON, '{"schema": true}'
        ),
        (dossier_id, CorpusEntryKind.GEOREF_JSON): _entry_for(
            dossier_id, CorpusEntryKind.GEOREF_JSON, '{"georef": true}'
        ),
    }
    lane = ProvenanceLane(provider=FakeCorpusProvider(entries))
    result = lane.search(dossier_id, recipe=ProvenanceRecipe.CANONICAL_STACK)

    assert [card.id for card in result.cards] == [
        f"prov:{ProvenanceRecipe.CANONICAL_STACK.value}:{dossier_id}:{CorpusEntryKind.FINALIZED_DOSSIER_TEXT.value}",
        f"prov:{ProvenanceRecipe.CANONICAL_STACK.value}:{dossier_id}:{CorpusEntryKind.SCHEMA_JSON.value}",
        f"prov:{ProvenanceRecipe.CANONICAL_STACK.value}:{dossier_id}:{CorpusEntryKind.GEOREF_JSON.value}",
    ]
