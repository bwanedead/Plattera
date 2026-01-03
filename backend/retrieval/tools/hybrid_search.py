from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..evidence.models import RetrievalResult


@dataclass
class HybridSearchTool:
    engine: RetrievalEngine

    # Defaults:
    # - uses engine hybrid orchestration ("hybrid" lane)
    # - engine controls lexical internal limit + anchor cap + recipe
    def __call__(self, query: str, *, filters: Optional[RetrievalFilters] = None, limit: int = 10) -> RetrievalResult:
        result = self.engine.search(query, filters=filters, limit=limit, lanes=["hybrid"])
        cfg = self.engine.hybrid_config
        result.debug.update(
            {
                "tool": "HybridSearchTool",
                "tool_lanes": ["hybrid"],
                "tool_defaults": {
                    "lexical_internal_limit": cfg.lexical_internal_limit,
                    "max_anchor_dossiers": cfg.max_anchor_dossiers,
                    "provenance_recipe": cfg.provenance_recipe.value,
                },
            }
        )
        return result


