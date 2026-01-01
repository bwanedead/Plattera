from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..evidence.models import RetrievalResult
from ..filters.models import RetrievalFilters
from ..lanes.lexical.lane import LexicalLane, NoopLexicalLane
from ..lanes.provenance.lane import ProvenanceLane
from ..lanes.semantic.lane import SemanticLane, NoopSemanticLane
from .merge import dedupe_by_id, sort_by_score


@dataclass
class RetrievalEngine:
    """
    Orchestrates retrieval lanes and returns normalized evidence objects.

    v0: placeholder that wires into lane modules later.
    """

    lexical_lane: LexicalLane = field(default_factory=NoopLexicalLane)
    semantic_lane: SemanticLane = field(default_factory=NoopSemanticLane)
    provenance_lane: ProvenanceLane = field(default_factory=ProvenanceLane)

    def search(
        self,
        query: str,
        *,
        filters: Optional[RetrievalFilters] = None,
        limit: int = 10,
        lanes: Optional[List[str]] = None,
    ) -> RetrievalResult:
        requested_lanes = lanes or []
        anchor = (filters.dossier_id if filters else None) or query

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
                result = self.lexical_lane.search(query, filters=filters, limit=limit)
            elif lane_name == "semantic":
                result = self.semantic_lane.search(query, filters=filters, limit=limit)
            elif lane_name == "provenance":
                result = self.provenance_lane.search(anchor, filters=filters)
            else:
                continue
            dbg["lane_debug"][lane_name] = result.debug
            cards.extend(result.cards)

        cards = sort_by_score(dedupe_by_id(cards))
        if limit:
            cards = cards[:limit]

        return RetrievalResult(query=query, cards=cards, debug=dbg)


