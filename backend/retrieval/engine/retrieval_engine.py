from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..evidence.models import EvidenceCard, RetrievalResult
from ..filters.models import RetrievalFilters
from ..lanes.lexical.grep_backend import GrepBackendLexicalLane
from ..lanes.lexical.lane import LexicalLane
from ..lanes.provenance.lane import ProvenanceLane
from ..lanes.provenance.recipes import ProvenanceRecipe, parse_provenance_recipe
from ..lanes.semantic.lane import SemanticLane, NoopSemanticLane
from .merge import dedupe_by_id, sort_by_score


@dataclass(frozen=True)
class HybridConfig:
    lexical_internal_limit: int = 50
    max_anchor_dossiers: int = 5
    provenance_recipe: ProvenanceRecipe = ProvenanceRecipe.CANONICAL_STACK


def extract_dossier_anchors(
    cards: List[EvidenceCard], *, max_anchors: Optional[int] = None
) -> List[str]:
    anchors: List[str] = []
    seen = set()
    for card in cards:
        for span in card.spans:
            dossier_id = span.entry.dossier_id
            if not dossier_id or dossier_id in seen:
                continue
            seen.add(dossier_id)
            anchors.append(dossier_id)
            if max_anchors is not None and len(anchors) >= max_anchors:
                return anchors
    return anchors


@dataclass
class RetrievalEngine:
    """
    Orchestrates retrieval lanes and returns normalized evidence objects.

    v0: placeholder that wires into lane modules later.
    """

    lexical_raw_lane: LexicalLane = field(default_factory=lambda: GrepBackendLexicalLane(mode="raw"))
    lexical_normalized_lane: LexicalLane = field(default_factory=lambda: GrepBackendLexicalLane(mode="normalized"))
    semantic_lane: SemanticLane = field(default_factory=NoopSemanticLane)
    provenance_lane: ProvenanceLane = field(default_factory=ProvenanceLane)
    hybrid_config: HybridConfig = field(default_factory=HybridConfig)

    def search(
        self,
        query: str,
        *,
        filters: Optional[RetrievalFilters] = None,
        limit: int = 10,
        lanes: Optional[List[str]] = None,
    ) -> RetrievalResult:
        requested_lanes = lanes or []
        anchor = filters.dossier_id if filters else None

        dbg: Dict[str, Any] = {
            "filters": (filters.__dict__ if filters else None),
            "limit": limit,
            "lanes": requested_lanes,
            "anchor": anchor,
            "lane_debug": {},
        }

        cards = []
        for lane_name in requested_lanes:
            if lane_name == "lexical":
                raw_result = self.lexical_raw_lane.search(query, filters=filters, limit=limit)
                norm_result = self.lexical_normalized_lane.search(query, filters=filters, limit=limit)
                dbg["lane_debug"]["lexical.raw"] = raw_result.debug
                dbg["lane_debug"]["lexical.normalized"] = norm_result.debug
                cards.extend(raw_result.cards)
                cards.extend(norm_result.cards)
                continue
            if lane_name == "hybrid":
                hybrid_debug: Dict[str, Any] = {}
                internal_limit = max(limit * 5, self.hybrid_config.lexical_internal_limit)
                hybrid_debug["lexical_internal_limit"] = internal_limit

                raw_result = self.lexical_raw_lane.search(query, filters=filters, limit=internal_limit)
                norm_result = self.lexical_normalized_lane.search(query, filters=filters, limit=internal_limit)
                dbg["lane_debug"]["lexical.raw"] = raw_result.debug
                dbg["lane_debug"]["lexical.normalized"] = norm_result.debug
                cards.extend(raw_result.cards)
                cards.extend(norm_result.cards)

                anchors_found = extract_dossier_anchors(cards)
                hybrid_debug["anchors_found"] = anchors_found
                anchors_used = anchors_found[: self.hybrid_config.max_anchor_dossiers]
                hybrid_debug["anchors_used"] = anchors_used
                if not anchors_used:
                    hybrid_debug["note"] = "no_anchors_found"
                    dbg["lane_debug"]["hybrid"] = hybrid_debug
                    continue

                for dossier_id in anchors_used:
                    prov_filters = _with_dossier_id(filters, dossier_id)
                    prov_result = self.provenance_lane.search(
                        dossier_id,
                        recipe=self.hybrid_config.provenance_recipe,
                        filters=prov_filters,
                    )
                    cards.extend(prov_result.cards)
                dbg["lane_debug"]["hybrid"] = hybrid_debug
                continue
            if lane_name == "lexical.raw":
                result = self.lexical_raw_lane.search(query, filters=filters, limit=limit)
            elif lane_name == "lexical.normalized":
                result = self.lexical_normalized_lane.search(query, filters=filters, limit=limit)
            elif lane_name == "semantic":
                result = self.semantic_lane.search(query, filters=filters, limit=limit)
            elif lane_name == "provenance":
                if not anchor:
                    dbg["lane_debug"]["provenance"] = {"error": "provenance_requires_dossier_id"}
                    continue
                recipe = self._resolve_provenance_recipe(filters)
                result = self.provenance_lane.search(anchor, recipe=recipe, filters=filters)
            else:
                continue
            dbg["lane_debug"][lane_name] = result.debug
            cards.extend(result.cards)

        cards = sort_by_score(dedupe_by_id(cards))
        if limit:
            cards = cards[:limit]

        return RetrievalResult(query=query, cards=cards, debug=dbg)

    def _resolve_provenance_recipe(self, filters: Optional[RetrievalFilters]) -> ProvenanceRecipe:
        if not filters or not filters.extra:
            return self.hybrid_config.provenance_recipe
        raw = (filters.extra or {}).get("provenance_recipe")
        if not raw:
            return self.hybrid_config.provenance_recipe
        return parse_provenance_recipe(raw)


def _with_dossier_id(filters: Optional[RetrievalFilters], dossier_id: str) -> RetrievalFilters:
    if not filters:
        return RetrievalFilters(dossier_id=dossier_id)
    return RetrievalFilters(
        view=filters.view,
        dossier_id=dossier_id,
        transcription_id=filters.transcription_id,
        artifact_type=filters.artifact_type,
        since_iso=filters.since_iso,
        until_iso=filters.until_iso,
        extra=dict(filters.extra or {}),
    )


