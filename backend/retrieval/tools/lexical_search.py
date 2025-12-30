from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..evidence.models import RetrievalResult


@dataclass
class LexicalSearchTool:
    engine: RetrievalEngine

    def __call__(self, query: str, *, filters: Optional[RetrievalFilters] = None, limit: int = 10) -> RetrievalResult:
        return self.engine.search(query, filters=filters, limit=limit, lanes=["lexical"])


