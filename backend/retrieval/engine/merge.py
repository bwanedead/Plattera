from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from ..evidence.models import EvidenceCard


LaneName = str


@dataclass
class MergeConfig:
    """
    Hybrid merge configuration.
    """

    max_results: int = 20


@dataclass
class FusionConfig:
    """
    Configuration for multi-lane fusion merge.
    Defines per-lane caps and ordering.
    """

    per_lane_cap: int = 10
    lane_order: List[LaneName] = None

    def __post_init__(self):
        if self.lane_order is None:
            # Default deterministic lane order per PRD
            self.lane_order = ["lexical.raw", "lexical.normalized", "semantic"]


def dedupe_by_id(cards: List[EvidenceCard]) -> List[EvidenceCard]:
    """
    Deduplicate cards by card.id, preserving first occurrence order.

    Args:
        cards: List of cards that may contain duplicates

    Returns:
        Deduplicated list with first occurrence of each ID preserved in order
    """
    seen: set[str] = set()
    deduped: List[EvidenceCard] = []
    for c in cards:
        if c.id not in seen:
            seen.add(c.id)
            deduped.append(c)
    return deduped


def sort_by_score(cards: List[EvidenceCard]) -> List[EvidenceCard]:
    return sorted(cards, key=lambda c: float(c.score), reverse=True)


def fusion_merge(
    lane_results: Dict[str, List[EvidenceCard]],
    config: FusionConfig | None = None,
    stable_key_fn: Callable[[EvidenceCard], str] | None = None,
) -> List[EvidenceCard]:
    """
    Merge multi-lane candidates with deterministic ordering.

    Process:
    1. Take top-K from each lane in fixed order
    2. Concatenate in lane order
    3. Dedupe by card.id (first occurrence wins; no cross-lane merge by default)
    4. Sort by score desc, with stable tie-breaker (lane order, then card.id)

    Args:
        lane_results: Dict mapping lane names to their result cards
        config: Optional fusion configuration (defaults provided)
        stable_key_fn: Optional function to compute a stable dedupe key across lanes.
            If None, dedupe uses card.id only.

    Returns:
        Merged and deduplicated list of evidence cards
    """
    if config is None:
        config = FusionConfig()

    # Build lane order index for tie-breaking
    lane_order_index = {lane: idx for idx, lane in enumerate(config.lane_order)}

    # Step 1 & 2: Take per-lane top-K in fixed order and concatenate
    candidates: List[EvidenceCard] = []
    for lane_name in config.lane_order:
        if lane_name in lane_results:
            lane_cards = lane_results[lane_name][: config.per_lane_cap]
            candidates.extend(lane_cards)

    # Step 3: Dedupe by stable key (card.id by default; cross-lane merge optional)
    seen: Dict[str, EvidenceCard] = {}
    deduped: List[EvidenceCard] = []
    for card in candidates:
        key = stable_key_fn(card) if stable_key_fn is not None else card.id
        if key not in seen:
            seen[key] = card
            deduped.append(card)

    # Step 4: Sort by score (desc), with stable tie-breaker
    # Tie-breaker: lane order index, then card.id
    def sort_key(card: EvidenceCard):
        lane_idx = lane_order_index.get(card.lane, 999)
        if lane_idx == 999:
            for lane, idx in lane_order_index.items():
                if card.lane == lane or card.lane.startswith(f"{lane}:"):
                    lane_idx = idx
                    break
        return (-card.score, lane_idx, card.id)

    sorted_cards = sorted(deduped, key=sort_key)

    return sorted_cards





