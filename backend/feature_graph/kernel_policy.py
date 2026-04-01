"""Legacy product-owned policy doctrine for feature-graph execution.

This module exists for product-layer compatibility and tests. It is not shared
harness doctrine and should not be treated as the canonical runtime contract.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from agent_kernel.harness_action_ids import ActionType
from agent_kernel.models import KernelState
from agent_kernel.policies.generic import KernelPolicy


class FeatureGraphDeedToMapPolicyV0:
    """Feature-graph routing and scoring doctrine, owned by the product layer."""

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
        del state
        available = set(available_actions)
        return tuple(action for action in self._ACTION_PRIORITY if action in available)

    def score_gap(
        self,
        gap_code: str,
        base_score: float,
        metadata: Mapping[str, object] | None = None,
    ) -> float:
        del metadata
        return max(0.0, base_score) * self._GAP_WEIGHTS.get(gap_code, 1.0)
