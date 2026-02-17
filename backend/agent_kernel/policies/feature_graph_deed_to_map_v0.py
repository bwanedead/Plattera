"""Policy interface and default FeatureGraph deed-to-map policy scaffold."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Mapping, Sequence

from ..models import ActionType, KernelState


class KernelPolicy(ABC):
    """Policy hooks used by kernel orchestration logic."""

    @abstractmethod
    def routing_order(
        self,
        state: KernelState,
        available_actions: Sequence[ActionType],
    ) -> tuple[ActionType, ...]:
        """Return a deterministic preferred action order."""

    @abstractmethod
    def score_gap(
        self,
        gap_code: str,
        base_score: float,
        metadata: Mapping[str, object] | None = None,
    ) -> float:
        """Return weighted gap severity used by deterministic no-progress logic."""


class FeatureGraphDeedToMapPolicyV0(KernelPolicy):
    """Default v0 scaffold for feature-graph deed-to-map routing and scoring."""

    _ACTION_PRIORITY: tuple[ActionType, ...] = (
        ActionType.SET_GRAPH_REQUIREMENTS,
        ActionType.RETRIEVE_EVIDENCE,
        ActionType.COMPILE,
        ActionType.JUDGE,
        ActionType.BUNDLE,
        ActionType.GEOREFERENCE,
        ActionType.VALIDATE,
        ActionType.PROPOSE_PATCH,
        ActionType.SUMMARIZE_STATUS,
    )

    _GAP_WEIGHTS: Mapping[str, float] = {
        "global_anchor_missing": 2.0,
        "insufficient_evidence": 1.5,
        "compile_failure": 1.25,
        "validation_failure": 1.0,
    }

    def routing_order(
        self,
        state: KernelState,
        available_actions: Sequence[ActionType],
    ) -> tuple[ActionType, ...]:
        del state  # state-specific overrides are intentionally deferred in this scaffold.
        available = set(available_actions)
        return tuple(action for action in self._ACTION_PRIORITY if action in available)

    def score_gap(
        self,
        gap_code: str,
        base_score: float,
        metadata: Mapping[str, object] | None = None,
    ) -> float:
        del metadata  # reserved for future policy refinement.
        return max(0.0, base_score) * self._GAP_WEIGHTS.get(gap_code, 1.0)
