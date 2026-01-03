from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..evidence.models import RetrievalResult


@dataclass
class SemanticSearchTool:
    engine: RetrievalEngine

    # Defaults:
    # - semantic lane (noop until implemented)
    def __call__(self, query: str, *, filters: Optional[RetrievalFilters] = None, limit: int = 10) -> RetrievalResult:
        result = self.engine.search(query, filters=filters, limit=limit, lanes=["semantic"])
        result.debug.update(
            {
                "tool": "SemanticSearchTool",
                "tool_lanes": ["semantic"],
            }
        )
        return result


