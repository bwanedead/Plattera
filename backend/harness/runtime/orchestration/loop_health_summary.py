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
    resolution_items = list(getattr(cont.resolution_state, "items", ()) or ())
    success_conditions = list(getattr(cont.mission_state, "success_conditions", ()) or ())
    closure_dimensions = list(getattr(cont.mission_state.closure_state, "dimensions", ()) or ())

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
        "success_condition_count": len(success_conditions),
        "success_conditions_with_earned_determination_count": sum(
            1 for row in success_conditions if _has_earned_determination(getattr(row, "determination", None))
        ),
        "success_conditions_with_verification_basis_count": sum(
            1 for row in success_conditions if _has_text(getattr(row, "verification_basis", None))
        ),
        "resolution_item_count": len(resolution_items),
        "items_with_evidence_count": sum(
            1 for row in resolution_items if bool(getattr(row, "evidence_refs", ()) or ())
        ),
        "items_with_verification_basis_count": sum(
            1 for row in resolution_items if _has_text(getattr(row, "verification_basis", None))
        ),
        "closed_items_count": sum(1 for row in resolution_items if _is_closed_status(getattr(row, "status", None))),
        "closed_items_without_earned_determination_count": sum(
            1
            for row in resolution_items
            if _is_closed_status(getattr(row, "status", None))
            and not _has_earned_determination(getattr(row, "determination", None))
        ),
        "closed_items_without_basis_count": sum(
            1
            for row in resolution_items
            if _is_closed_status(getattr(row, "status", None))
            and not _has_text(getattr(row, "verification_basis", None))
        ),
        "closed_items_without_completion_criteria_count": sum(
            1
            for row in resolution_items
            if _is_closed_status(getattr(row, "status", None))
            and not _has_text(getattr(row, "completion_criteria", None))
        ),
        "closure_dimension_count": len(closure_dimensions),
        "closure_dimensions_with_earned_determination_count": sum(
            1 for row in closure_dimensions if _has_earned_determination(getattr(row, "determination", None))
        ),
        "closed_dimensions_without_earned_determination_count": sum(
            1
            for row in closure_dimensions
            if _is_closed_status(getattr(row, "status", None))
            and not _has_earned_determination(getattr(row, "determination", None))
        ),
        "closed_dimensions_without_basis_count": sum(
            1
            for row in closure_dimensions
            if _is_closed_status(getattr(row, "status", None))
            and not _has_text(getattr(row, "verification_basis", None))
        ),
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


def _is_closed_status(value: Any) -> bool:
    return str(value or "").strip().lower() == "closed"


def _has_earned_determination(value: Any) -> bool:
    return str(value or "").strip().lower() == "earned"


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())
