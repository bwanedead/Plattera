"""Mechanical per-turn action flags for human timeline audit rendering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE

POINT_CROP_SUB_ACTIONS = frozenset({"point_crops", "point_crops_adjust", "point_crops_view"})
SAVE_ACTIONS = frozenset({"save_workspace_artifact"})
PUBLISH_ACTIONS = frozenset({"publish_workspace_artifact"})
STATE_PATCH_ACTIONS = frozenset({"apply_state_patch", "state_patch"})
_MAX_FLAG_REFS = 8


def render_turn_action_flags(turn: Mapping[str, Any]) -> list[str]:
    flags = compute_turn_action_flags(turn)
    lines = ["Action flags:"]
    if flags.batch:
        lines.append(f"- batch: yes ({flags.action_rows} rows)")
    else:
        lines.append("- batch: no")
    if flags.delegate:
        delegate_line = f"- delegate: yes ({flags.delegate_count} subtasks)"
        if flags.delegate_parallel:
            delegate_line += "; parallel: yes"
        lines.append(delegate_line)
    else:
        lines.append("- delegate: no")
    if flags.delegate_wall_seconds_total is not None:
        lines.append(f"- delegate_wall_seconds_total: {flags.delegate_wall_seconds_total}")
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
    lines.extend(_render_ref_motion_flag("hydrate_next", flags.hydrate_next_refs))
    lines.extend(_render_ref_motion_flag("pinned_refs", flags.pin_refs))
    lines.extend(_render_ref_motion_flag("pinned_refs_expiring", flags.pin_refs_expiring))
    lines.extend(_render_ref_motion_flag("unpin_refs", flags.unpin_refs))
    lines.extend(_render_mission_posture_flags(turn))
    if flags.determinations_changed:
        lines.append(f"- determinations_changed: {flags.determinations_changed}")
    if flags.units_closed:
        lines.append(f"- units_closed: {flags.units_closed}")
    if flags.items_or_units_added:
        lines.append(f"- items_or_units_added: {flags.items_or_units_added}")
    if flags.save:
        lines.append("- save: yes")
    if flags.publish:
        lines.append("- publish: yes")
    if flags.state_patch_only:
        lines.append("- state_patch_only: yes")
    lines.append("")
    return lines


def _render_ref_motion_flag(label: str, refs: list[str]) -> list[str]:
    if not refs:
        return [f"- {label}: no"]
    lines = [f"- {label}: yes ({len(refs)} refs)"]
    for ref in refs[:_MAX_FLAG_REFS]:
        lines.append(f"  - {ref}")
    return lines


def _render_mission_posture_flags(turn: Mapping[str, Any]) -> list[str]:
    before = _coerce_mapping(turn.get("mission_state_before"))
    after = _coerce_mapping(turn.get("mission_state_after"))
    mission = after or before
    if not mission:
        return []
    lines: list[str] = []
    for field in ("motion_posture", "work_universe_posture"):
        before_val = _posture_value(before, field)
        after_val = _posture_value(after, field) or _posture_value(before, field)
        if not after_val:
            continue
        if before_val and before_val != after_val:
            lines.append(f"- {field}: {before_val} -> {after_val}")
        else:
            lines.append(f"- {field}: {after_val}")
    return lines


def _posture_value(mission: Mapping[str, Any], field: str) -> str:
    if not mission:
        return ""
    return str(mission.get(field) or "").strip()


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
    delegate_parallel = False
    delegate_wall_seconds_total = None
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
    if sequence.get("delegate_parallel") is True:
        delegate_parallel = True
    wall_raw = sequence.get("delegate_wall_seconds_total")
    if wall_raw is not None:
        try:
            delegate_wall_seconds_total = round(float(wall_raw), 3)
        except (TypeError, ValueError):
            delegate_wall_seconds_total = None

    image_refs = _count_image_refs(turn, actions=actions, tool_result=tool_result, sequence=sequence)
    hitl = _detect_hitl(turn, tool_request=tool_request, parsed=parsed)
    state_patch_only = _detect_state_patch_only(
        turn,
        actions=actions,
        state_patch_actions=state_patch_actions,
        tool_result=tool_result,
    )
    hydrate_next_refs = _collect_hydrate_next_refs(actions, tool_request=tool_request, parsed=parsed)
    pin_refs = _collect_pin_refs(turn, tool_request=tool_request, parsed=parsed)
    pin_refs_expiring = _collect_pinned_refs_expiring(turn)
    unpin_refs = _collect_unpin_refs(turn, tool_request=tool_request, parsed=parsed)
    graph_delta = _compute_resolution_graph_delta(
        _coerce_mapping(turn.get("resolution_state_before")),
        _coerce_mapping(turn.get("resolution_state_after")),
    )

    return TurnActionFlags(
        batch=action_rows > 1,
        action_rows=action_rows,
        delegate=delegate_count > 0,
        delegate_count=delegate_count,
        delegate_parallel=delegate_parallel,
        delegate_wall_seconds_total=delegate_wall_seconds_total,
        point_crops=point_crop_sets > 0 or point_crop_points > 0,
        point_crop_sets=max(point_crop_sets, 1 if point_crop_points else 0),
        point_crop_points=point_crop_points,
        image_refs=image_refs,
        hitl=hitl,
        hydrate_next_refs=hydrate_next_refs,
        pin_refs=pin_refs,
        pin_refs_expiring=pin_refs_expiring,
        unpin_refs=unpin_refs,
        determinations_changed=graph_delta.determinations_changed,
        units_closed=graph_delta.units_closed,
        items_or_units_added=graph_delta.items_or_units_added,
        save=save,
        publish=publish,
        state_patch_only=state_patch_only,
    )


class GraphDeltaFlags:
    __slots__ = ("determinations_changed", "units_closed", "items_or_units_added")

    def __init__(
        self,
        *,
        determinations_changed: int,
        units_closed: int,
        items_or_units_added: int,
    ) -> None:
        self.determinations_changed = determinations_changed
        self.units_closed = units_closed
        self.items_or_units_added = items_or_units_added


class TurnActionFlags:
    __slots__ = (
        "batch",
        "action_rows",
        "delegate",
        "delegate_count",
        "delegate_parallel",
        "delegate_wall_seconds_total",
        "point_crops",
        "point_crop_sets",
        "point_crop_points",
        "image_refs",
        "hitl",
        "hydrate_next_refs",
        "pin_refs",
        "pin_refs_expiring",
        "unpin_refs",
        "determinations_changed",
        "units_closed",
        "items_or_units_added",
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
        delegate_parallel: bool,
        delegate_wall_seconds_total: float | None,
        point_crops: bool,
        point_crop_sets: int,
        point_crop_points: int,
        image_refs: int,
        hitl: bool,
        hydrate_next_refs: list[str],
        pin_refs: list[str],
        pin_refs_expiring: list[str],
        unpin_refs: list[str],
        determinations_changed: int,
        units_closed: int,
        items_or_units_added: int,
        save: bool,
        publish: bool,
        state_patch_only: bool,
    ) -> None:
        self.batch = batch
        self.action_rows = action_rows
        self.delegate = delegate
        self.delegate_count = delegate_count
        self.delegate_parallel = delegate_parallel
        self.delegate_wall_seconds_total = delegate_wall_seconds_total
        self.point_crops = point_crops
        self.point_crop_sets = point_crop_sets
        self.point_crop_points = point_crop_points
        self.image_refs = image_refs
        self.hitl = hitl
        self.hydrate_next_refs = hydrate_next_refs
        self.pin_refs = pin_refs
        self.pin_refs_expiring = pin_refs_expiring
        self.unpin_refs = unpin_refs
        self.determinations_changed = determinations_changed
        self.units_closed = units_closed
        self.items_or_units_added = items_or_units_added
        self.save = save
        self.publish = publish
        self.state_patch_only = state_patch_only


def _collect_hydrate_next_refs(
    actions: list[Mapping[str, Any]],
    *,
    tool_request: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for row in actions:
        hydrate_next = row.get("hydrate_next")
        if isinstance(hydrate_next, list):
            _append_unique_refs(refs, seen, hydrate_next)
    for source in (tool_request, parsed):
        hydrate_next = source.get("hydrate_next")
        if isinstance(hydrate_next, list):
            _append_unique_refs(refs, seen, hydrate_next)
    return refs


def _collect_pin_refs(
    turn: Mapping[str, Any],
    *,
    tool_request: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for source in (tool_request, parsed):
        pin_refs = source.get("pin_refs")
        if isinstance(pin_refs, list):
            _append_unique_refs(refs, seen, pin_refs)
    pin_this_turn = turn.get("pin_refs_this_turn")
    if isinstance(pin_this_turn, list):
        _append_unique_refs(refs, seen, pin_this_turn)
    return refs


def _collect_pinned_refs_expiring(turn: Mapping[str, Any]) -> list[str]:
    pinned = _coerce_mapping(turn.get("pinned_refs"))
    if not pinned:
        return []
    rows = pinned.get("expiring_soon")
    if not isinstance(rows, list):
        return []
    refs: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        ref = str(row.get("ref") or "").strip()
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _collect_unpin_refs(
    turn: Mapping[str, Any],
    *,
    tool_request: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for source in (tool_request, parsed):
        unpin_refs = source.get("unpin_refs")
        if isinstance(unpin_refs, list):
            _append_unique_refs(refs, seen, unpin_refs)
    unpin_this_turn = turn.get("unpin_refs_this_turn")
    if isinstance(unpin_this_turn, list):
        _append_unique_refs(refs, seen, unpin_this_turn)
    return refs


def _append_unique_refs(refs: list[str], seen: set[str], values: list[Any]) -> None:
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        refs.append(text)


def _compute_resolution_graph_delta(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> GraphDeltaFlags:
    if not before and not after:
        return GraphDeltaFlags(
            determinations_changed=0,
            units_closed=0,
            items_or_units_added=0,
        )
    before_atoms = _resolution_atoms(before)
    after_atoms = _resolution_atoms(after)
    if not before_atoms and not after_atoms:
        return GraphDeltaFlags(
            determinations_changed=0,
            units_closed=0,
            items_or_units_added=0,
        )

    before_ids = set(before_atoms)
    after_ids = set(after_atoms)
    items_or_units_added = len(after_ids - before_ids)

    determinations_changed = 0
    units_closed = 0
    for atom_id in before_ids & after_ids:
        prior = before_atoms[atom_id]
        current = after_atoms[atom_id]
        if _determination_signature(prior) != _determination_signature(current):
            determinations_changed += 1
        if not _is_closed_status(prior.get("status")) and _is_closed_status(current.get("status")):
            units_closed += 1

    return GraphDeltaFlags(
        determinations_changed=determinations_changed,
        units_closed=units_closed,
        items_or_units_added=items_or_units_added,
    )


def _resolution_atoms(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    items = state.get("items")
    if not isinstance(items, list):
        return {}
    atoms: dict[str, Mapping[str, Any]] = {}
    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            continue
        item_id = str(raw_item.get("item_id") or "").strip()
        if item_id:
            atoms[f"item:{item_id}"] = raw_item
        covered_units = raw_item.get("covered_units")
        if not isinstance(covered_units, list):
            continue
        for raw_unit in covered_units:
            if not isinstance(raw_unit, Mapping):
                continue
            unit_id = str(raw_unit.get("unit_id") or "").strip()
            if unit_id:
                atoms[f"unit:{item_id}:{unit_id}"] = raw_unit
    return atoms


def _determination_signature(atom: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(atom.get("determined_value") or "").strip(),
        str(atom.get("determination") or "").strip(),
    )


def _is_closed_status(status: Any) -> bool:
    return str(status or "").strip().lower() == "closed"


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
