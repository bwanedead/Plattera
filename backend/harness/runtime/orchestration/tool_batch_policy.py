"""Resolve per-tool batching policy from surface tool_specs and launch overrides.

Harness-owned mechanical policy only — no semantic inference from tool names.
Tools must declare ``batching.allowed = true`` in their spec to be batchable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

_RUN_CONTEXT_POLICIES_KEY = "__tool_batch_policies"

ALLOWED_SIDE_EFFECT_CLASSES: frozenset[str] = frozenset({"read_only", "derived_artifact"})
DISALLOWED_SIDE_EFFECT_CLASSES: frozenset[str] = frozenset({
    "workspace_write", "publish", "terminal", "hitl",
})


@dataclass(frozen=True)
class ToolBatchPolicy:
    tool_id: str
    allowed: bool
    max_calls_per_batch: int
    side_effect_class: str
    can_run_parallel: bool = False
    conflict_key: str | None = None

    @property
    def continues_after_item_failure(self) -> bool:
        return self.side_effect_class in ALLOWED_SIDE_EFFECT_CLASSES


@dataclass(frozen=True)
class DomainActionBatchPolicy:
    max_batch_size: int | None = None
    max_resolved_actions: int | None = None
    tool_caps: Mapping[str, int] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> DomainActionBatchPolicy | None:
        if raw is None or not isinstance(raw, Mapping):
            return None
        max_batch = raw.get("max_batch_size")
        max_resolved = raw.get("max_resolved_actions")
        tool_caps_raw = raw.get("tool_caps") or {}
        tool_caps: dict[str, int] = {}
        if isinstance(tool_caps_raw, Mapping):
            for key, value in tool_caps_raw.items():
                try:
                    tool_caps[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
        return cls(
            max_batch_size=int(max_batch) if max_batch is not None else None,
            max_resolved_actions=int(max_resolved) if max_resolved is not None else None,
            tool_caps=tool_caps,
        )


def _coerce_tool_batch_policy(tool_id: str, batching: Mapping[str, Any]) -> ToolBatchPolicy | None:
    if not isinstance(batching, Mapping):
        return None
    allowed = batching.get("allowed") is True
    if not allowed:
        return ToolBatchPolicy(
            tool_id=tool_id,
            allowed=False,
            max_calls_per_batch=0,
            side_effect_class=str(batching.get("side_effect_class") or ""),
        )
    side_effect = str(batching.get("side_effect_class") or "").strip()
    if side_effect in DISALLOWED_SIDE_EFFECT_CLASSES:
        return ToolBatchPolicy(
            tool_id=tool_id,
            allowed=False,
            max_calls_per_batch=0,
            side_effect_class=side_effect,
        )
    if side_effect not in ALLOWED_SIDE_EFFECT_CLASSES:
        return None
    try:
        max_calls = int(batching.get("max_calls_per_batch", 1))
    except (TypeError, ValueError):
        max_calls = 1
    max_calls = max(1, max_calls)
    conflict_key = batching.get("conflict_key")
    conflict_out = str(conflict_key).strip() if isinstance(conflict_key, str) and conflict_key.strip() else None
    return ToolBatchPolicy(
        tool_id=tool_id,
        allowed=True,
        max_calls_per_batch=max_calls,
        side_effect_class=side_effect,
        can_run_parallel=bool(batching.get("can_run_parallel")),
        conflict_key=conflict_out,
    )


def policy_from_tool_spec_row(row: Mapping[str, Any]) -> ToolBatchPolicy | None:
    tool_id = str(row.get("tool_id") or "").strip()
    if not tool_id:
        return None
    batching = row.get("batching")
    if batching is None:
        return None
    if not isinstance(batching, Mapping):
        return None
    return _coerce_tool_batch_policy(tool_id, batching)


def resolve_tool_batch_policies(
    surface_payloads: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, ToolBatchPolicy]:
    """Collect explicit batching policies from nested surface ``tool_specs`` arrays."""
    policies: dict[str, ToolBatchPolicy] = {}
    if not surface_payloads:
        return policies
    for payload in surface_payloads.values():
        if not isinstance(payload, Mapping):
            continue
        specs = payload.get("tool_specs")
        if not isinstance(specs, (list, tuple)):
            continue
        for row in specs:
            if not isinstance(row, Mapping):
                continue
            policy = policy_from_tool_spec_row(row)
            if policy is not None:
                policies[policy.tool_id] = policy
    return policies


def resolve_domain_action_batch_policy(
    launch_context: Mapping[str, Any] | None,
) -> DomainActionBatchPolicy | None:
    if not launch_context:
        return None
    raw = launch_context.get("action_batch_policy")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        return None
    return DomainActionBatchPolicy.from_mapping(raw)


def effective_max_batch_size(
    *,
    global_default: int,
    domain_policy: DomainActionBatchPolicy | None,
) -> int:
    if domain_policy is not None and domain_policy.max_batch_size is not None:
        return min(global_default, max(1, int(domain_policy.max_batch_size)))
    return global_default


def enrich_run_context_with_tool_batch_policies(
    context: Mapping[str, Any],
    surface_payloads: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Attach resolved tool batch policies for orchestrator + parser reuse."""
    out = dict(context)
    policies = resolve_tool_batch_policies(surface_payloads)
    if policies:
        out[_RUN_CONTEXT_POLICIES_KEY] = {
            tool_id: asdict(policy) for tool_id, policy in policies.items()
        }
    return out


def tool_batch_policies_from_run_context(
    context: Mapping[str, Any] | None,
) -> dict[str, ToolBatchPolicy]:
    if not context:
        return {}
    raw = context.get(_RUN_CONTEXT_POLICIES_KEY)
    if not isinstance(raw, Mapping):
        return {}
    policies: dict[str, ToolBatchPolicy] = {}
    for tool_id, row in raw.items():
        if not isinstance(row, Mapping):
            continue
        try:
            max_calls = int(row.get("max_calls_per_batch", 0))
        except (TypeError, ValueError):
            max_calls = 0
        conflict_key = row.get("conflict_key")
        policies[str(tool_id)] = ToolBatchPolicy(
            tool_id=str(tool_id),
            allowed=bool(row.get("allowed")),
            max_calls_per_batch=max(0, max_calls),
            side_effect_class=str(row.get("side_effect_class") or ""),
            can_run_parallel=bool(row.get("can_run_parallel")),
            conflict_key=(
                str(conflict_key).strip()
                if isinstance(conflict_key, str) and conflict_key.strip()
                else None
            ),
        )
    return policies


def effective_tool_cap(
    *,
    tool_id: str,
    tool_policy: ToolBatchPolicy,
    global_default: int,
    domain_policy: DomainActionBatchPolicy | None,
) -> int:
    cap = min(global_default, tool_policy.max_calls_per_batch)
    if domain_policy is not None:
        domain_cap = domain_policy.tool_caps.get(tool_id)
        if domain_cap is not None:
            cap = min(cap, max(1, int(domain_cap)))
    return cap
