from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider

from ...evidence.models import EvidenceCard, EvidenceSpan, RetrievalResult
from ...filters.models import RetrievalFilters
from .recipes import ProvenanceRecipe, RECIPE_KINDS


@dataclass
class ProvenanceLane:
    """
    Deterministic lane that assembles canonical dossier artifacts as evidence.
    """

    provider: CorpusProvider = field(default_factory=VirtualCorpusProvider)
    lane_name: str = "provenance"

    def search(
        self,
        dossier_id: str,
        *,
        recipe: ProvenanceRecipe = ProvenanceRecipe.CANONICAL_STACK,
        filters: Optional[RetrievalFilters] = None,
    ) -> RetrievalResult:
        anchor = dossier_id or (filters.dossier_id if filters else None)
        if not anchor:
            return RetrievalResult(
                query="",
                cards=[],
                debug={"lane": self.lane_name, "error": "provenance_requires_dossier_id"},
            )

        debug: Dict[str, Any] = {
            "lane": self.lane_name,
            "recipe": recipe.value,
            "missing_kinds": [],
            "dossier_id": anchor,
        }

        cards: List[EvidenceCard] = []
        for kind in RECIPE_KINDS[recipe]:
            ref = self._entry_ref_for_kind(anchor, kind)
            entry = self.provider.hydrate_entry(ref)
            if not entry.text:
                debug["missing_kinds"].append(kind.value)
                continue
            span = EvidenceSpan(entry=ref, text=entry.text)
            cards.append(
                EvidenceCard(
                    id=f"prov:{recipe.value}:{anchor}:{kind.value}",
                    spans=[span],
                    score=1.0,
                    lane=self.lane_name,
                    title=entry.title or ref.entry_id,
                    provenance=dict(entry.provenance or {}),
                )
            )

        return RetrievalResult(query=str(anchor), cards=cards, debug=debug)

    def _entry_ref_for_kind(self, dossier_id: str, kind: CorpusEntryKind) -> CorpusEntryRef:
        if kind == CorpusEntryKind.FINALIZED_DOSSIER_TEXT:
            return CorpusEntryRef(
                view=CorpusView.FINALIZED,
                entry_id=f"final:{dossier_id}",
                kind=kind,
                dossier_id=dossier_id,
            )
        if kind == CorpusEntryKind.SCHEMA_JSON:
            return CorpusEntryRef(
                view=CorpusView.ARTIFACTS,
                entry_id=f"schema_latest:{dossier_id}",
                kind=kind,
                dossier_id=dossier_id,
                artifact_type="schema",
            )
        if kind == CorpusEntryKind.GEOREF_JSON:
            return CorpusEntryRef(
                view=CorpusView.ARTIFACTS,
                entry_id=f"georef_latest:{dossier_id}",
                kind=kind,
                dossier_id=dossier_id,
                artifact_type="georef",
            )
        return CorpusEntryRef(
            view=CorpusView.ARTIFACTS,
            entry_id=f"artifact:{dossier_id}:{kind.value}",
            kind=kind,
            dossier_id=dossier_id,
        )
