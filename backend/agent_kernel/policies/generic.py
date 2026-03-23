"""Generic kernel policy interface and neutral default policy."""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence, runtime_checkable

from ..models import ActionType, KernelState


@runtime_checkable
class KernelPolicy(Protocol):
    """Shared policy interface used by the compatibility loop."""

    def routing_order(
        self,
        state: KernelState,
        available_actions: Sequence[ActionType],
    ) -> tuple[ActionType, ...]: ...

    def score_gap(
        self,
        gap_code: str,
        base_score: float,
        metadata: Mapping[str, object] | None = None,
    ) -> float: ...


class DefaultKernelPolicy:
    """Neutral shared-core default: preserve caller order and use unweighted gap scoring."""

    def routing_order(
        self,
        state: KernelState,
        available_actions: Sequence[ActionType],
    ) -> tuple[ActionType, ...]:
        del state
        return tuple(available_actions)

    def score_gap(
        self,
        gap_code: str,
        base_score: float,
        metadata: Mapping[str, object] | None = None,
    ) -> float:
        del gap_code, metadata
        return max(0.0, base_score)
