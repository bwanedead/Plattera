"""Host-authored loop-health facts for prompt observability.

These summaries are mechanical only. They expose prompt/turn cadence facts to the
model and to operators without deciding semantic meaning or choosing the next
move on the agent's behalf.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..memory import LoopMemoryState


def build_prompt_observability_summary(loop_memory: LoopMemoryState) -> dict[str, Any]:
    """Return host-owned loop-health facts safe to expose in prompts and audits."""
    telemetry = loop_memory.telemetry
    cont = loop_memory.continuity
    step_records = list(cont.kernel_step_records)

    feedback = dict(cont.state_patch_feedback) if isinstance(cont.state_patch_feedback, Mapping) else {}

    return {
        "prompt_event_count": int(telemetry.prompt_event_count),
        "last_prompt_event_id": telemetry.last_prompt_event_id,
        "last_prompt_event_surface": telemetry.last_prompt_event_surface,
        "consecutive_no_dispatch_turns": _consecutive_no_dispatch_turns(step_records),
        "turns_since_last_tool_execution": _turns_since_last_tool_execution(step_records),
        "turns_since_latest_refs_change": _turns_since_latest_refs_change(step_records),
        "last_state_patch_outcome": _as_optional_text(feedback.get("outcome")),
        "last_state_patch_reason_code": _as_optional_text(feedback.get("reason_code")),
    }


def _consecutive_no_dispatch_turns(step_records: list[dict[str, Any]]) -> int:
    count = 0
    for row in reversed(step_records):
        if bool(row.get("skip_execution")):
            count += 1
            continue
        break
    return count


def _turns_since_last_tool_execution(step_records: list[dict[str, Any]]) -> int | None:
    turns = 0
    for row in reversed(step_records):
        if str(row.get("execution_state") or "") == "executed":
            return turns
        turns += 1
    return None


def _turns_since_latest_refs_change(step_records: list[dict[str, Any]]) -> int | None:
    if not step_records:
        return None
    latest_sig = _stable_signature(step_records[-1].get("latest_refs_snapshot"))
    trailing_same = 0
    for row in reversed(step_records):
        if _stable_signature(row.get("latest_refs_snapshot")) != latest_sig:
            break
        trailing_same += 1
    return max(0, trailing_same - 1)


def _stable_signature(value: Any) -> str:
    try:
        return json.dumps(value if isinstance(value, Mapping) else {}, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}"


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
