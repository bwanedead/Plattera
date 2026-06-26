"""Operand suite payload assembly for deed-to-IR (copy-only projection)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .mapping_operands_projection import build_mapping_operands, build_operand_groups
from .operand_suite_refs import build_operand_suite_ref


def build_operand_suite_payload(
    handoff: Mapping[str, Any],
    *,
    operand_suite_ref: str | None = None,
) -> dict[str, Any] | None:
    """Project mapping operands plus optional mechanical grouping lane."""
    snapshot = handoff.get("resolution_state_snapshot")
    if not isinstance(snapshot, Mapping):
        return None
    scope = handoff.get("scope") if isinstance(handoff.get("scope"), Mapping) else {}
    ref = operand_suite_ref or build_operand_suite_ref(
        run_id=_opt_str(scope.get("run_id")),
        workspace_id=_opt_str(scope.get("workspace_id")),
    )
    resolution_state_ref = handoff.get("resolution_state_ref")
    payload = build_mapping_operands(
        snapshot,
        resolution_state_ref=str(resolution_state_ref) if resolution_state_ref is not None else None,
    )
    payload["operand_suite_ref"] = ref
    groups = build_operand_groups(payload.get("operands") if isinstance(payload.get("operands"), list) else [])
    if groups:
        payload["operand_groups"] = groups
    return payload


def _opt_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
