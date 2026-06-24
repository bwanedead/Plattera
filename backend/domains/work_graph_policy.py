"""Domain-subscribed work-graph observability policy (mechanical transport only)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DomainWorkGraphPolicy:
    claim_inventory_pressure_enabled: bool = False


def default_work_graph_policy() -> DomainWorkGraphPolicy:
    return DomainWorkGraphPolicy(claim_inventory_pressure_enabled=False)


def work_graph_policy_to_json(policy: DomainWorkGraphPolicy) -> dict[str, Any]:
    return asdict(policy)


def claim_inventory_pressure_enabled(opaque_launch_context: Mapping[str, Any] | None) -> bool:
    """Return whether claim-inventory mechanical flags may surface in prompts."""
    if not isinstance(opaque_launch_context, Mapping):
        return False
    raw = opaque_launch_context.get("domain_work_graph_policy")
    if not isinstance(raw, Mapping):
        return False
    return bool(raw.get("claim_inventory_pressure_enabled"))
