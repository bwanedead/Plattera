"""Prompt-safe projection for unintegrated delegate observation worklists."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .delegate_observation_worklist import KIND, build_delegate_observation_worklist

MAX_PROMPT_ROWS = 12
DELEGATE_OBSERVATION_WORKLIST_REMINDER_KEY = "delegate_observation_worklist_reminder"

GENERIC_DELEGATE_OBSERVATION_REMINDER = (
    "Completed delegate observations are available. "
    "Before rerunning equivalent delegate work, integrate target reads into durable "
    "state via exact ref citation."
)


def build_delegate_observation_worklist_for_prompt(
    *,
    delegate_result_records: Sequence[Mapping[str, Any]] | None,
    mission_state: Mapping[str, Any] | None = None,
    resolution_state: Mapping[str, Any] | None = None,
    repair_bundle: Mapping[str, Any] | None = None,
    current_turn: int = 0,
    reminder: str | None = None,
) -> dict[str, Any] | None:
    """Build bounded prompt observability block when unintegrated rows exist."""
    full = build_delegate_observation_worklist(
        delegate_result_records=delegate_result_records,
        mission_state=mission_state,
        resolution_state=resolution_state,
        repair_bundle=repair_bundle,
        current_turn=current_turn,
    )
    return project_delegate_observation_worklist_for_prompt(full, reminder=reminder)


def project_delegate_observation_worklist_for_prompt(
    full_worklist: Mapping[str, Any] | None,
    *,
    reminder: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(full_worklist, Mapping):
        return None

    rows_raw = full_worklist.get("rows")
    if not isinstance(rows_raw, list) or not rows_raw:
        return None

    rows = [dict(row) for row in rows_raw[:MAX_PROMPT_ROWS] if isinstance(row, Mapping)]
    if not rows:
        return None

    counts = full_worklist.get("counts")
    if not isinstance(counts, Mapping):
        counts = {"unintegrated_completed": len(rows)}
    else:
        counts = dict(counts)

    return {
        "counts": counts,
        "reminder": resolve_delegate_observation_reminder(reminder),
        "rows": rows,
    }


def compact_delegate_observation_worklist_for_prompt(
    block: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Drop-only compaction: counts, reminder, bounded rows."""
    if not isinstance(block, Mapping):
        return None

    rows = block.get("rows")
    if not isinstance(rows, list) or not rows:
        return None

    reminder = str(block.get("reminder") or "").strip() or GENERIC_DELEGATE_OBSERVATION_REMINDER
    out: dict[str, Any] = {
        "counts": dict(block.get("counts") or {"unintegrated_completed": len(rows)}),
        "reminder": reminder,
        "rows": [dict(row) for row in rows[:MAX_PROMPT_ROWS] if isinstance(row, Mapping)],
    }
    return out


def delegate_observation_reminder_from_context(
    launch_context: Mapping[str, Any] | None,
) -> str | None:
    """Read optional domain-injected reminder text from opaque launch/run context."""
    if not isinstance(launch_context, Mapping):
        return None
    text = str(launch_context.get(DELEGATE_OBSERVATION_WORKLIST_REMINDER_KEY) or "").strip()
    return text or None


def resolve_delegate_observation_reminder(reminder: str | None) -> str:
    text = str(reminder or "").strip()
    return text or GENERIC_DELEGATE_OBSERVATION_REMINDER


def state_as_mapping(state: Any) -> Mapping[str, Any] | None:
    if state is None:
        return None
    if hasattr(state, "model_dump"):
        return state.model_dump(mode="json")
    if isinstance(state, Mapping):
        return state
    return None


def repair_bundle_from_feedback(feedback: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(feedback, Mapping):
        return None
    bundle = feedback.get("state_patch_repair_bundle")
    return dict(bundle) if isinstance(bundle, Mapping) else None
