from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..evidence.models import RetrievalResult


@dataclass
class LexicalSearchTool:
    engine: RetrievalEngine

    def __call__(
        self,
        query: str,
        *,
        filters: Optional[RetrievalFilters] = None,
        mode: str = "raw",
        limit: int = 10,
    ) -> RetrievalResult:
        mode_key = mode.strip().lower()
        if mode_key == "raw":
            lanes = ["lexical.raw"]
        elif mode_key == "normalized":
            lanes = ["lexical.normalized"]
        elif mode_key == "both":
            lanes = ["lexical.raw", "lexical.normalized"]
        else:
            raise ValueError(f"Unknown lexical mode: {mode!r}")
        return self.engine.search(query, filters=filters, limit=limit, lanes=lanes)


