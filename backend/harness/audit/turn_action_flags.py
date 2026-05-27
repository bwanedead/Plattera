"""Mechanical per-turn action flags for human timeline audit rendering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE

POINT_CROP_SUB_ACTIONS = frozenset({"point_crops", "point_crops_adjust", "point_crops_view"})
SAVE_ACTIONS = frozenset({"save_workspace_artifact"})
PUBLISH_ACTIONS = frozenset({"publish_workspace_artifact"})
STATE_PATCH_ACTIONS = frozenset({"apply_state_patch", "state_patch"})


def render_turn_action_flags(turn: Mapping[str, Any]) -> list[str]:
    flags = compute_turn_action_flags(turn)
    lines = ["Action flags:"]
    if flags.batch:
        lines.append(f"- batch: yes ({flags.action_rows} rows)")
    else:
        lines.append("- batch: no")
    if flags.delegate:
        lines.append(f"- delegate: yes ({flags.delegate_count} subtasks)")
    else:
        lines.append("- delegate: no")
    if flags.point_crops:
        detail = f"{flags.point_crop_sets} set"
        if flags.point_crop_sets != 1:
            detail = f"{flags.point_crop_sets} sets"
        if flags.point_crop_points:
            detail = f"{detail}, {flags.point_crop_points} points"
        lines.append(f"- point_crops: yes ({detail})")
    else:
        lines.append("- point_crops: no")
    lines.append(f"- image_refs: {flags.image_refs}")
    lines.append(f"- HITL: {'yes' if flags.hitl else 'no'}")
    if flags.save:
        lines.append("- save: yes")
    if flags.publish:
        lines.append("- publish: yes")
    if flags.state_patch_only:
        lines.append("- state_patch_only: yes")
    lines.append("")
    return lines


def compute_turn_action_flags(turn: Mapping[str, Any]) -> "TurnActionFlags":
    tool_request = _coerce_mapping(turn.get("tool_request"))
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    actions = _extract_actions(tool_request, parsed)
    action_rows = len(actions)

    delegate_count = sum(
        1 for row in actions if str(row.get("action_type") or "") == DELEGATE_SUBTASK_ACTION_TYPE
    )
    point_crop_sets = 0
    point_crop_points = 0
    save = False
    publish = False
    state_patch_actions = 0
    for row in actions:
        action_type = str(row.get("action_type") or "")
        if action_type in SAVE_ACTIONS:
            save = True
        if action_type in PUBLISH_ACTIONS:
            publish = True
        if action_type in STATE_PATCH_ACTIONS:
            state_patch_actions += 1
        if action_type != "transform_artifact":
            continue
        inputs = _coerce_mapping(row.get("action_inputs"))
        sub_action = str(inputs.get("sub_action") or "").strip()
        if sub_action in POINT_CROP_SUB_ACTIONS:
            point_crop_sets += 1

    tool_result = _coerce_mapping(turn.get("tool_result_raw"))
    outputs = _coerce_mapping(tool_result.get("outputs"))
    output_sub_action = str(outputs.get("sub_action") or "").strip()
    if output_sub_action in POINT_CROP_SUB_ACTIONS:
        if point_crop_sets == 0:
            point_crop_sets = 1
        crop_set = _coerce_mapping(outputs.get("crop_set"))
        points = crop_set.get("points") or outputs.get("crop_records") or []
        if isinstance(points, list):
            point_crop_points = max(point_crop_points, len(points))

    sequence = _coerce_mapping(turn.get("recent_action_sequence_result"))
    items = sequence.get("items")
    if isinstance(items, list):
        action_rows = max(action_rows, len(items))
        delegate_count = max(
            delegate_count,
            sum(
                1
                for item in items
                if isinstance(item, Mapping)
                and str(item.get("action_type") or "") == DELEGATE_SUBTASK_ACTION_TYPE
            ),
        )

    image_refs = _count_image_refs(turn, actions=actions, tool_result=tool_result, sequence=sequence)
    hitl = _detect_hitl(turn, tool_request=tool_request, parsed=parsed)
    state_patch_only = _detect_state_patch_only(
        turn,
        actions=actions,
        state_patch_actions=state_patch_actions,
        tool_result=tool_result,
    )

    return TurnActionFlags(
        batch=action_rows > 1,
        action_rows=action_rows,
        delegate=delegate_count > 0,
        delegate_count=delegate_count,
        point_crops=point_crop_sets > 0 or point_crop_points > 0,
        point_crop_sets=max(point_crop_sets, 1 if point_crop_points else 0),
        point_crop_points=point_crop_points,
        image_refs=image_refs,
        hitl=hitl,
        save=save,
        publish=publish,
        state_patch_only=state_patch_only,
    )


class TurnActionFlags:
    __slots__ = (
        "batch",
        "action_rows",
        "delegate",
        "delegate_count",
        "point_crops",
        "point_crop_sets",
        "point_crop_points",
        "image_refs",
        "hitl",
        "save",
        "publish",
        "state_patch_only",
    )

    def __init__(
        self,
        *,
        batch: bool,
        action_rows: int,
        delegate: bool,
        delegate_count: int,
        point_crops: bool,
        point_crop_sets: int,
        point_crop_points: int,
        image_refs: int,
        hitl: bool,
        save: bool,
        publish: bool,
        state_patch_only: bool,
    ) -> None:
        self.batch = batch
        self.action_rows = action_rows
        self.delegate = delegate
        self.delegate_count = delegate_count
        self.point_crops = point_crops
        self.point_crop_sets = point_crop_sets
        self.point_crop_points = point_crop_points
        self.image_refs = image_refs
        self.hitl = hitl
        self.save = save
        self.publish = publish
        self.state_patch_only = state_patch_only


def _detect_hitl(
    turn: Mapping[str, Any],
    *,
    tool_request: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> bool:
    if tool_request.get("wait_for_human") or parsed.get("wait_for_human"):
        return True
    if _coerce_mapping(parsed.get("hitl_request")) or _coerce_mapping(tool_request.get("hitl_request")):
        return True
    pending = turn.get("pending_hitl_requests")
    if isinstance(pending, list) and pending:
        return True
    answered = turn.get("answered_hitl_responses")
    if isinstance(answered, list) and answered:
        return True
    state = str(turn.get("hitl_state") or "").strip()
    return bool(state and state not in {"no_prompt", "none"})


def _detect_state_patch_only(
    turn: Mapping[str, Any],
    *,
    actions: list[Mapping[str, Any]],
    state_patch_actions: int,
    tool_result: Mapping[str, Any],
) -> bool:
    feedback = _coerce_mapping(turn.get("state_patch_feedback"))
    outcome = str(feedback.get("outcome") or "").strip().lower()
    if outcome not in {"applied", "success", "patched"}:
        return False
    if tool_result and str(tool_result.get("execution_state") or "") not in {"", "skipped", "none"}:
        if state_patch_actions == 0:
            return False
    non_patch_actions = [
        row
        for row in actions
        if str(row.get("action_type") or "") not in STATE_PATCH_ACTIONS
    ]
    return not non_patch_actions and state_patch_actions > 0


def _count_image_refs(
    turn: Mapping[str, Any],
    *,
    actions: list[Mapping[str, Any]],
    tool_result: Mapping[str, Any],
    sequence: Mapping[str, Any],
) -> int:
    refs: set[str] = set()
    for key in ("artifact_refs",):
        values = tool_result.get(key)
        if isinstance(values, list):
            for value in values:
                ref = str(value or "").strip()
                if ref.startswith("image:"):
                    refs.add(ref)
    outputs = _coerce_mapping(tool_result.get("outputs"))
    for key in (
        "derived_ref_id",
        "parent_ref_id",
        "previous_crop_set_overlay_ref",
        "view_of_crop_set_overlay_ref",
    ):
        ref = str(outputs.get(key) or "").strip()
        if ref.startswith("image:"):
            refs.add(ref)
    crop_set = _coerce_mapping(outputs.get("crop_set"))
    for key in ("master_overlay_ref", "source_ref"):
        ref = str(crop_set.get(key) or "").strip()
        if ref.startswith("image:"):
            refs.add(ref)
    points = crop_set.get("points") or outputs.get("crop_records") or []
    if isinstance(points, list):
        for point in points:
            if not isinstance(point, Mapping):
                continue
            crop_ref = str(point.get("crop_ref") or "").strip()
            if crop_ref.startswith("image:"):
                refs.add(crop_ref)
    items = sequence.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            artifact_refs = item.get("artifact_refs")
            if isinstance(artifact_refs, list):
                for value in artifact_refs:
                    ref = str(value or "").strip()
                    if ref.startswith("image:"):
                        refs.add(ref)
    for row in actions:
        inputs = _coerce_mapping(row.get("action_inputs"))
        ref_id = str(inputs.get("ref_id") or "").strip()
        if ref_id.startswith("image:"):
            refs.add(ref_id)
        context_refs = inputs.get("context_refs")
        if isinstance(context_refs, list):
            for value in context_refs:
                ref = str(value or "").strip()
                if ref.startswith("image:"):
                    refs.add(ref)
        hydrate_next = row.get("hydrate_next")
        if isinstance(hydrate_next, list):
            for value in hydrate_next:
                ref = str(value or "").strip()
                if ref.startswith("image:"):
                    refs.add(ref)
    host = _coerce_mapping(turn.get("host_hydration_before_turn"))
    for lane_key in ("agent_requested_hydration", "pinned_refs_auto_hydration"):
        lane = _coerce_mapping(host.get(lane_key))
        for key in ("requested_refs", "resolved_refs", "refs", "hydrated_ref_ids"):
            values = lane.get(key)
            if isinstance(values, list):
                for value in values:
                    ref = str(value or "").strip()
                    if ref.startswith("image:"):
                        refs.add(ref)
    return len(refs)


def _extract_actions(
    tool_request: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    for source in (tool_request, parsed):
        raw = source.get("actions")
        if isinstance(raw, list) and raw:
            return [_coerce_mapping(row) for row in raw if isinstance(row, Mapping)]
    legacy_batch = tool_request.get("action_batch") or parsed.get("action_batch")
    if isinstance(legacy_batch, list) and legacy_batch:
        return [_coerce_mapping(row) for row in legacy_batch if isinstance(row, Mapping)]
    return []


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
