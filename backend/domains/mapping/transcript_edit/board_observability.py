"""Compact board posture for terminal/runtime summaries (no full board dump)."""
from __future__ import annotations

from typing import Any

from .work_board_projection import HARNESS_EMERGENT_ITEM_PREFIX


def compact_emergent_board_run_posture(
    emergent_items: list[dict[str, Any]] | None,
    *,
    last_focus_key: str | None,
) -> dict[str, Any]:
    """Bounded end-of-run signal for reviewers (harness-emergent rows only)."""
    rows = [dict(r) for r in (emergent_items or []) if isinstance(r, dict)]
    lf = str(last_focus_key or "").strip().lower()
    non_terminal = 0
    blocked_or_waiting = 0
    for r in rows:
        st = str(r.get("state") or "open").strip().lower()
        if st not in {"resolved", "superseded"}:
            non_terminal += 1
        if st in {"blocked", "waiting_human", "waiting_evidence"}:
            blocked_or_waiting += 1
    return {
        "schema_version": "board_run_posture.v1",
        "emergent_row_count": len(rows),
        "emergent_non_terminal_count": non_terminal,
        "emergent_has_blocked_or_waiting": bool(blocked_or_waiting),
        "last_focus_was_emergent": bool(lf.startswith(HARNESS_EMERGENT_ITEM_PREFIX)),
    }
