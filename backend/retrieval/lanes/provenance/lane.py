from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider

from ...evidence.models import EvidenceCard, EvidenceSpan, RetrievalResult
from ...filters.models import RetrievalFilters
from .recipes import ProvenanceRecipe


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
                debug={"lane": self.lane_name, "error": "missing_dossier_id"},
            )

        refs: List[CorpusEntryRef] = []
        debug: Dict[str, Any] = {
            "lane": self.lane_name,
            "recipe": recipe.value,
            "missing": [],
            "dossier_id": anchor,
        }

        if recipe in {ProvenanceRecipe.CANONICAL_STACK, ProvenanceRecipe.FINAL_ONLY}:
            finalized_refs = list(
                self.provider.list_entry_refs(
                    CorpusView.FINALIZED,
                    dossier_id=anchor,
                    kinds={CorpusEntryKind.FINALIZED_DOSSIER_TEXT},
                )
            )
            refs.extend(finalized_refs)
            if not finalized_refs:
                debug["missing"].append(CorpusEntryKind.FINALIZED_DOSSIER_TEXT.value)

        if recipe in {ProvenanceRecipe.CANONICAL_STACK, ProvenanceRecipe.ARTIFACTS_ONLY}:
            artifact_kinds: Set[CorpusEntryKind] = {
                CorpusEntryKind.SCHEMA_JSON,
                CorpusEntryKind.GEOREF_JSON,
            }
            artifact_refs = list(
                self.provider.list_entry_refs(
                    CorpusView.ARTIFACTS,
                    dossier_id=anchor,
                    kinds=artifact_kinds,
                )
            )
            refs.extend(artifact_refs)
            if artifact_refs:
                present = {ref.kind for ref in artifact_refs}
                missing = [k.value for k in artifact_kinds if k not in present]
                debug["missing"].extend(missing)
            else:
                debug["missing"].extend([k.value for k in artifact_kinds])

        cards = [self._entry_to_card(ref) for ref in refs]
        return RetrievalResult(query=str(anchor), cards=cards, debug=debug)

    def _entry_to_card(self, ref: CorpusEntryRef) -> EvidenceCard:
        entry = self.provider.hydrate_entry(ref)
        span = EvidenceSpan(entry=ref, text=entry.text)
        return EvidenceCard(
            id=f"prov:{ref.entry_id}",
            spans=[span],
            score=1.0,
            lane=self.lane_name,
            title=entry.title or ref.entry_id,
            provenance=dict(entry.provenance or {}),
        )
