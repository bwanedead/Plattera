from __future__ import annotations

from typing import Iterable

from .contracts import ModePolicy


class ModePolicyLookupError(KeyError):
    """Raised when a requested mode policy is not registered."""


class ModePolicyRegistry:
    """Small registry seam for runtime mode-policy lookup."""

    def __init__(self, policies: Iterable[ModePolicy] | None = None) -> None:
        self._policies: dict[str, ModePolicy] = {}
        for policy in policies or ():
            self.register(policy)

    def register(self, policy: ModePolicy) -> None:
        name = policy.mode_name.strip()
        if not name:
            raise ValueError("mode_policy_name_required")
        if name in self._policies:
            raise ValueError(f"mode_policy_already_registered:{name}")
        self._policies[name] = policy

    def resolve(self, mode_name: str) -> ModePolicy | None:
        return self._policies.get(mode_name)

    def require(self, mode_name: str) -> ModePolicy:
        policy = self.resolve(mode_name)
        if policy is None:
            raise ModePolicyLookupError(f"mode_policy_not_registered:{mode_name}")
        return policy
