from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider

from ...evidence.models import EvidenceCard, EvidenceSpan, RetrievalResult
from ...filters.models import RetrievalFilters
from .normalize import NormalizationResult, normalize_text_v1, normalize_text_with_mapping_v1


@dataclass
class GrepBackendLexicalLane:
    """
    v0 lexical lane: raw or normalized substring scanning.
    """

    mode: str = "raw"
    provider: CorpusProvider = field(default_factory=VirtualCorpusProvider)
    default_view: CorpusView = CorpusView.FINALIZED
    max_hits_per_entry: int = 25
    max_entries: int = 200
    max_total_cards: int = 200
    lane_name: str = "lexical:grep_backend"

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        view = (filters.view if filters and filters.view else self.default_view)
        dossier_id = filters.dossier_id if filters else None
        effective_limit = limit if limit else self.max_total_cards

        dbg: Dict[str, Any] = {
            "lane": self.lane_name,
            "mode": self.mode,
            "view": view.value,
            "dossier_id": dossier_id,
            "query": query,
        }

        if not query:
            dbg["note"] = "empty_query"
            return RetrievalResult(query=query, cards=[], debug=dbg)

        kinds = self._kinds_for_view(view)
        if not kinds:
            dbg["note"] = "no_kinds_for_view"
            return RetrievalResult(query=query, cards=[], debug=dbg)

        refs = list(self.provider.list_entry_refs(view, dossier_id=dossier_id, kinds=kinds))
        if self.max_entries:
            refs = refs[: self.max_entries]

        cards: List[EvidenceCard] = []
        total_hits = 0
        for ref in refs:
            if effective_limit and len(cards) >= effective_limit:
                break
            entry = self.provider.hydrate_entry(ref)
            entry_cards = self._search_entry(entry, query, effective_limit - len(cards))
            cards.extend(entry_cards)
            total_hits += len(entry_cards)

        dbg["hits_total"] = total_hits
        dbg["entries_scanned"] = len(refs)
        return RetrievalResult(query=query, cards=cards, debug=dbg)

    def _kinds_for_view(self, view: CorpusView) -> set[CorpusEntryKind]:
        if view == CorpusView.FINALIZED:
            return {CorpusEntryKind.FINALIZED_DOSSIER_TEXT}
        if view == CorpusView.EVERYTHING:
            return {CorpusEntryKind.TRANSCRIPT}
        return set()

    def _search_entry(self, entry: CorpusEntry, query: str, remaining: int) -> List[EvidenceCard]:
        if remaining <= 0:
            return []
        if self.mode == "normalized":
            return self._search_entry_normalized(entry, query, remaining)
        return self._search_entry_raw(entry, query, remaining)

    def _search_entry_raw(self, entry: CorpusEntry, query: str, remaining: int) -> List[EvidenceCard]:
        return self._emit_matches(
            entry,
            query=query,
            haystack=entry.text,
            norm_result=None,
            remaining=remaining,
        )

    def _search_entry_normalized(self, entry: CorpusEntry, query: str, remaining: int) -> List[EvidenceCard]:
        norm_result = normalize_text_with_mapping_v1(entry.text)
        norm_query = normalize_text_v1(query)
        if not norm_query:
            return []
        return self._emit_matches(
            entry,
            query=query,
            haystack=norm_result.normalized,
            norm_result=norm_result,
            remaining=remaining,
        )

    def _emit_matches(
        self,
        entry: CorpusEntry,
        *,
        query: str,
        haystack: str,
        norm_result: Optional[NormalizationResult],
        remaining: int,
    ) -> List[EvidenceCard]:
        if not haystack:
            return []

        cards: List[EvidenceCard] = []
        query_norm = normalize_text_v1(query) if self.mode == "normalized" else None

        start = 0
        hits = 0
        while True:
            idx = haystack.find(query_norm if query_norm is not None else query, start)
            if idx == -1:
                break
            match_len = len(query_norm if query_norm is not None else query)
            norm_start = idx
            norm_end = idx + match_len
            if norm_result is not None:
                orig_start, orig_end = self._map_norm_span(norm_result, norm_start, norm_end)
            else:
                orig_start, orig_end = norm_start, norm_end

            if orig_end <= orig_start:
                start = idx + 1
                continue

            span_text = _excerpt(entry.text, orig_start, orig_end)
            span = EvidenceSpan(entry=entry.ref, text=span_text, start=orig_start, end=orig_end)
            card = EvidenceCard(
                id=f"lex:{self.mode}:{entry.ref.entry_id}:{orig_start}:{orig_end}",
                spans=[span],
                score=1.0,
                lane=f"lexical.{self.mode}",
                title=entry.title or entry.ref.entry_id,
                provenance=self._build_provenance(
                    entry,
                    query=query,
                    query_norm=query_norm,
                    norm_result=norm_result,
                    norm_start=norm_start,
                    norm_end=norm_end,
                    orig_start=orig_start,
                    orig_end=orig_end,
                ),
            )
            cards.append(card)
            hits += 1
            if hits >= self.max_hits_per_entry or (remaining and len(cards) >= remaining):
                break
            start = idx + 1

        return cards

    def _map_norm_span(
        self, norm_result: NormalizationResult, norm_start: int, norm_end: int
    ) -> tuple[int, int]:
        if not norm_result.map_norm_to_orig:
            return (norm_start, norm_end)
        if norm_start >= len(norm_result.map_norm_to_orig):
            return (norm_start, norm_start)
        norm_end_idx = max(norm_end - 1, norm_start)
        norm_end_idx = min(norm_end_idx, len(norm_result.map_norm_to_orig) - 1)
        orig_start = norm_result.map_norm_to_orig[norm_start]
        orig_end = norm_result.map_norm_to_orig[norm_end_idx] + 1
        return (orig_start, orig_end)

    def _build_provenance(
        self,
        entry: CorpusEntry,
        *,
        query: str,
        query_norm: Optional[str],
        norm_result: Optional[NormalizationResult],
        norm_start: int,
        norm_end: int,
        orig_start: int,
        orig_end: int,
    ) -> Dict[str, Any]:
        provenance: Dict[str, Any] = {
            "lane_mode": self.mode,
            "entry_id": entry.ref.entry_id,
            "dossier_id": entry.ref.dossier_id,
            "transcription_id": entry.ref.transcription_id,
            "query": query,
            "start": orig_start,
            "end": orig_end,
        }
        if self.mode == "normalized":
            provenance["normalization_version"] = "v1"
            provenance["query_normalized"] = query_norm
            if norm_result is not None:
                matched_norm = norm_result.normalized[norm_start:norm_end]
                provenance["matched_normalized_snippet"] = matched_norm
            provenance["matched_original_snippet"] = entry.text[orig_start:orig_end]
        return provenance


def _excerpt(text: str, start: int, end: int, window: int = 120) -> str:
    if not text:
        return ""
    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right]


