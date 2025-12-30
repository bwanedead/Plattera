from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from retrieval.evidence.formatters import EvidenceFormatter
from retrieval.evidence.models import RetrievalResult


@dataclass
class ContextBuilder:
    """
    Turns retrieved evidence into compact LLM context.
    """

    formatter: EvidenceFormatter = EvidenceFormatter()

    def build(self, result: RetrievalResult, *, max_cards: int = 8) -> str:
        return self.formatter.format_cards(result.cards, limit=max_cards)


