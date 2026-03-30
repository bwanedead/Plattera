from __future__ import annotations

from typing import Iterable

from .contracts import MissionModeAdapter


class ModeAdapterLookupError(KeyError):
    """Raised when a requested mode adapter is not registered."""


class MissionModeAdapterRegistry:
    """Small registry seam for runtime mode-adapter lookup."""

    def __init__(self, policies: Iterable[MissionModeAdapter] | None = None) -> None:
        self._policies: dict[str, MissionModeAdapter] = {}
        for policy in policies or ():
            self.register(policy)

    def register(self, policy: MissionModeAdapter) -> None:
        name = policy.mode_name.strip()
        if not name:
            raise ValueError("mode_adapter_name_required")
        if name in self._policies:
            raise ValueError(f"mode_adapter_already_registered:{name}")
        self._policies[name] = policy

    def resolve(self, mode_name: str) -> MissionModeAdapter | None:
        return self._policies.get(mode_name)

    def require(self, mode_name: str) -> MissionModeAdapter:
        policy = self.resolve(mode_name)
        if policy is None:
            raise ModeAdapterLookupError(f"mode_adapter_not_registered:{mode_name}")
        return policy
