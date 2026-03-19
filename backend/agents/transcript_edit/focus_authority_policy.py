"""Explicit authority between domain-projected ledger rows and harness-emergent items.

Applies to the **single unified harness decision ledger** envelope. Ranking intent:

- When material mapping-blocking closure rows exist (reconstructed from projected
  ``te:ledger:*`` items), those keys outrank harness-emergent rows (emergent defers).
- When none exist, emergent rows compete with other candidates on the unified ledger.
"""
from __future__ import annotations

from typing import Any, Literal

FocusAuthorityMode = Literal["ledger_absolute_precedence", "emergent_may_lead"]


def resolve_focus_authority_mode(*, mapping_blocking_by_key: dict[str, Any]) -> FocusAuthorityMode:
    """Derive policy mode from material mapping-blocking closure keys (ledger-derived)."""
    return "ledger_absolute_precedence" if mapping_blocking_by_key else "emergent_may_lead"


def authority_rank_for_candidate(
    candidate: dict[str, Any],
    *,
    mapping_blocking_by_key: dict[str, Any],
) -> int:
    """Sort key component: lower wins earlier. Must stay aligned with Phase 5 behavior."""
    mode = resolve_focus_authority_mode(mapping_blocking_by_key=mapping_blocking_by_key)
    src = str(candidate.get("_candidate_source") or "")
    key = str(candidate.get("key") or "").strip().lower()
    if src == "ledger_decision":
        mapped = mapping_blocking_by_key.get(key)
        if isinstance(mapped, dict) and bool(mapped.get("mapping_blocking")):
            return 0
        return 1
    if src == "harness_emergent":
        if mode == "ledger_absolute_precedence":
            return 2
        return 0
    return 1


def focus_authority_audit(
    *,
    mapping_blocking_by_key: dict[str, Any],
    winner: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact, inspectable policy snapshot for packets and progress detail."""
    mode = resolve_focus_authority_mode(mapping_blocking_by_key=mapping_blocking_by_key)
    n = len(mapping_blocking_by_key)
    note = (
        "Material ledger mapping-blocking closure rows exist; emergent board rows defer in sort."
        if mode == "ledger_absolute_precedence"
        else "No material ledger mapping-blocking closure rows; emergent board rows may lead sorting."
    )
    out: dict[str, Any] = {
        "schema_version": "focus_authority.v1",
        "mode": mode,
        "material_mapping_blocker_key_count": n,
        "policy_summary": note[:320],
    }
    if isinstance(winner, dict) and winner:
        out["winner_authority_rank"] = authority_rank_for_candidate(
            winner,
            mapping_blocking_by_key=mapping_blocking_by_key,
        )
        out["winner_candidate_source"] = str(winner.get("_candidate_source") or "") or None
    return out
