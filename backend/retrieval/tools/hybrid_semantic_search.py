from __future__ import annotations

"""
Hybrid semantic retrieval tool wrapper (fusion of lexical + semantic).

Defaults:
- uses engine hybrid_semantic orchestration ("hybrid_semantic" lane)
- limit: 10

Debug schema keys:
tool, lanes, defaults, overrides, gating_errors, notes
"""

from dataclasses import dataclass
from typing import Optional

from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..evidence.models import RetrievalResult


@dataclass
class HybridSemanticSearchTool:
    engine: RetrievalEngine

    def __call__(self, query: str, *, filters: Optional[RetrievalFilters] = None, limit: int = 10) -> RetrievalResult:
        result = self.engine.search(query, filters=filters, limit=limit, lanes=["hybrid_semantic"])
        notes = []
        notes.append("fuses lexical.raw + lexical.normalized + semantic lanes")

        defaults = {"limit": 10}
        overrides = {}
        if limit != 10:
            overrides["limit"] = limit
        if filters is not None:
            overrides["filters"] = True

        result.debug.update(
            {
                "tool": "hybrid_semantic_search",
                "lanes": ["hybrid_semantic"],
                "defaults": defaults,
                "overrides": overrides,
                "gating_errors": [],
                "notes": notes,
            }
        )
        return result
