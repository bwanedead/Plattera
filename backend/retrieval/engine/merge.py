from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from ..evidence.models import EvidenceCard


@dataclass
class MergeConfig:
    """
    Hybrid merge configuration.
    """

    max_results: int = 20


def dedupe_by_id(cards: List[EvidenceCard]) -> List[EvidenceCard]:
    seen: Dict[str, EvidenceCard] = {}
    for c in cards:
        if c.id not in seen:
            seen[c.id] = c
    return list(seen.values())


def sort_by_score(cards: List[EvidenceCard]) -> List[EvidenceCard]:
    return sorted(cards, key=lambda c: float(c.score), reverse=True)


