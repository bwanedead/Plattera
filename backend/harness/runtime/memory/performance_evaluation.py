"""Generic harness-owned performance evaluation metrics (observability only).

Computes mechanical run-economics facts from loop memory and optional turn
records. Must not gate control flow or assign semantic scores.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE

from .loop_state import LoopMemoryState

SCHEMA_VERSION = 1
SCOPE = "generic_harness"
ACCURACY_STATUS = "not_live_scored"
ACCURACY_NOTE = (
    "Exact accuracy is evaluated by user/reviewer truth checks; "
    "do not trade accuracy for density."
)

INPUT_CHARS_GROWTH_THRESHOLD = 5000
HIGH_WALL_SECONDS_THRESHOLD = 90.0
DELEGATES_SINCE_LAST_DETERMINATION_THRESHOLD = 5
TURNS_SINCE_LAST_DETERMINATION_THRESHOLD = 4
TURNS_SINCE_LAST_CLOSURE_THRESHOLD = 4


def build_performance_evaluation(
    loop_memory: LoopMemoryState,
    *,
    turn_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return mechanical performance metrics for prompts, audit, and timeline."""
    records = _resolve_turn_records(loop_memory, turn_records)
    total_turns = int(loop_memory.iterations or 0)

    block: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "accuracy_status": ACCURACY_STATUS,
        "accuracy_note": ACCURACY_NOTE,
    }

    turns_block = _build_turns_block(records, total_turns=total_turns)
    if turns_block:
        block["turns"] = turns_block

    input_chars_block = _build_input_chars_block(records)
    if input_chars_block:
        block["input_chars"] = input_chars_block

    work_graph = _build_work_graph_block(loop_memory)
    if work_graph:
        block["work_graph"] = work_graph

    productivity, delegate_yield = _build_productivity_blocks(records, total_turns=total_turns)
    if productivity:
        block["productivity"] = productivity
    if delegate_yield:
        block["delegate_yield"] = delegate_yield

    pressure = _build_pressure_flags(
        total_turns=total_turns,
        input_chars_block=input_chars_block,
        turns_block=turns_block,
        productivity=productivity,
        delegate_yield=delegate_yield,
    )
    if pressure:
        block["current_pressure"] = pressure

    return block


def _resolve_turn_records(
    loop_memory: LoopMemoryState,
    turn_records: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if turn_records is not None:
        return [_normalize_turn_record(row) for row in turn_records if isinstance(row, Mapping)]
    contacts = getattr(loop_memory.telemetry, "turn_contact_records", None) or ()
    return [_normalize_turn_record(row) for row in contacts if isinstance(row, Mapping)]


def _normalize_turn_record(row: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(row)
    turn_index = record.get("turn_index")
    if turn_index is None:
        turn_index = record.get("kernel_turn_index")
    if turn_index is not None:
        try:
            record["turn_index"] = int(turn_index)
        except (TypeError, ValueError):
            pass
    return record


def _build_turns_block(
    records: list[dict[str, Any]],
    *,
    total_turns: int,
) -> dict[str, Any]:
    block: dict[str, Any] = {}
    if total_turns > 0:
        block["total"] = total_turns
        after_20 = max(0, total_turns - 20)
        if after_20 > 0:
            block["after_20"] = after_20

    durations = _turn_wall_durations(records)
    if durations:
        block["wall_seconds_total"] = round(sum(durations), 1)
        block["wall_seconds_last_turn"] = round(durations[-1], 1)
        last_five = durations[-5:]
        if last_five:
            block["avg_wall_seconds_last_5"] = round(sum(last_five) / len(last_five), 1)
    return block


def _build_input_chars_block(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = [_prompt_char_count(row) for row in records]
    counts = [count for count in counts if count is not None]
    if not counts:
        return {}

    block: dict[str, Any] = {
        "last_turn": counts[-1],
        "max_turn": max(counts),
        "cumulative": sum(counts),
    }
    if len(counts) >= 2:
        block["growth_last_turn"] = counts[-1] - counts[-2]
    last_three = counts[-3:]
    if last_three:
        block["avg_last_3"] = int(round(sum(last_three) / len(last_three)))
    return block


def _build_work_graph_block(loop_memory: LoopMemoryState) -> dict[str, Any]:
    atoms = _resolution_atoms_from_state(loop_memory)
    if not atoms:
        resolution_items = _resolution_items(loop_memory)
        if not resolution_items:
            return {}
        top_level = len(resolution_items)
        return {
            "resolution_items_total": top_level,
            "covered_units_total": 0,
            "work_units_total": top_level,
            "closed_units": 0,
            "open_units": top_level,
            "blocked_units": 0,
            "determined_units": 0,
        }

    top_level = len(_resolution_items(loop_memory))
    covered_units_total = sum(1 for atom_id in atoms if atom_id.startswith("unit:"))
    closed_units = sum(1 for atom in atoms.values() if _is_closed_status(atom.get("status")))
    blocked_units = sum(
        1
        for atom in atoms.values()
        if bool(atom.get("blocking")) or _is_blocked_status(atom.get("status"))
    )
    determined_units = sum(1 for atom in atoms.values() if _is_determined(atom))
    work_units_total = len(atoms)

    return {
        "resolution_items_total": top_level,
        "covered_units_total": covered_units_total,
        "work_units_total": work_units_total,
        "closed_units": closed_units,
        "open_units": work_units_total - closed_units,
        "blocked_units": blocked_units,
        "determined_units": determined_units,
    }


def _build_productivity_blocks(
    records: list[dict[str, Any]],
    *,
    total_turns: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not records and total_turns <= 0:
        return {}, {}

    determinations_changed_total = 0
    units_closed_total = 0
    delegates_total = 0
    last_determination_turn: int | None = None
    last_closure_turn: int | None = None
    delegates_since_last_determination = 0

    sorted_records = sorted(
        records,
        key=lambda row: int(row.get("turn_index") or 0),
    )
    for row in sorted_records:
        turn_index = int(row.get("turn_index") or 0)
        delta = _turn_graph_delta(row)
        if delta["determinations_changed"]:
            determinations_changed_total += delta["determinations_changed"]
            last_determination_turn = turn_index
            delegates_since_last_determination = 0
        if delta["units_closed"]:
            units_closed_total += delta["units_closed"]
            last_closure_turn = turn_index

        delegate_count = _delegate_count_for_turn(row)
        delegates_total += delegate_count
        if last_determination_turn is not None and turn_index > last_determination_turn:
            delegates_since_last_determination += delegate_count

    denominator = total_turns if total_turns > 0 else None
    productivity: dict[str, Any] = {}
    if determinations_changed_total:
        productivity["determinations_changed_total"] = determinations_changed_total
    if units_closed_total:
        productivity["units_closed_total"] = units_closed_total
    if denominator:
        if determinations_changed_total:
            productivity["determinations_per_turn"] = round(
                determinations_changed_total / denominator, 2
            )
        if units_closed_total:
            productivity["units_closed_per_turn"] = round(units_closed_total / denominator, 2)

    if last_determination_turn is not None and total_turns > last_determination_turn:
        productivity["turns_since_last_determination"] = total_turns - last_determination_turn
    if last_closure_turn is not None and total_turns > last_closure_turn:
        productivity["turns_since_last_closure"] = total_turns - last_closure_turn

    delegate_yield: dict[str, Any] = {}
    if delegates_total:
        delegate_yield["delegates_total"] = delegates_total
        if determinations_changed_total:
            delegate_yield["determinations_per_delegate"] = round(
                determinations_changed_total / delegates_total, 2
            )
    if last_determination_turn is not None:
        delegate_yield["delegates_since_last_determination"] = delegates_since_last_determination

    return productivity, delegate_yield


def _build_pressure_flags(
    *,
    total_turns: int,
    input_chars_block: Mapping[str, Any],
    turns_block: Mapping[str, Any],
    productivity: Mapping[str, Any],
    delegate_yield: Mapping[str, Any],
) -> list[str]:
    flags: list[str] = ["accuracy_not_live_scored"]

    after_20 = max(0, total_turns - 20)
    if after_20 > 0:
        flags.append(f"turns_after_20:{after_20}")

    delegates_since = delegate_yield.get("delegates_since_last_determination")
    if isinstance(delegates_since, int) and delegates_since >= DELEGATES_SINCE_LAST_DETERMINATION_THRESHOLD:
        flags.append(f"delegates_since_last_determination:{delegates_since}")

    turns_since_det = productivity.get("turns_since_last_determination")
    if isinstance(turns_since_det, int) and turns_since_det >= TURNS_SINCE_LAST_DETERMINATION_THRESHOLD:
        flags.append(f"turns_since_last_determination:{turns_since_det}")

    turns_since_close = productivity.get("turns_since_last_closure")
    if isinstance(turns_since_close, int) and turns_since_close >= TURNS_SINCE_LAST_CLOSURE_THRESHOLD:
        flags.append(f"turns_since_last_closure:{turns_since_close}")

    growth = input_chars_block.get("growth_last_turn")
    if isinstance(growth, int) and growth > INPUT_CHARS_GROWTH_THRESHOLD:
        flags.append(f"input_chars_growth_high:{growth}")

    last_wall = turns_block.get("wall_seconds_last_turn")
    if isinstance(last_wall, (int, float)) and float(last_wall) > HIGH_WALL_SECONDS_THRESHOLD:
        flags.append(f"high_last_turn_wall_seconds:{round(float(last_wall), 1)}")

    return flags


def _turn_wall_durations(records: list[dict[str, Any]]) -> list[float]:
    durations: list[float] = []
    for row in records:
        started = row.get("started_at_epoch_seconds")
        finished = row.get("finished_at_epoch_seconds")
        try:
            if started is None or finished is None:
                continue
            duration = float(finished) - float(started)
        except (TypeError, ValueError):
            continue
        if duration >= 0:
            durations.append(duration)
    return durations


def _prompt_char_count(row: Mapping[str, Any]) -> int | None:
    if row.get("prompt_char_count") is not None:
        try:
            return int(row["prompt_char_count"])
        except (TypeError, ValueError):
            pass
    raw_prompt = row.get("raw_prompt_text")
    if isinstance(raw_prompt, str):
        return len(raw_prompt)
    return None


def turn_graph_delta(row: Mapping[str, Any]) -> dict[str, int]:
    """Mechanical resolution-graph delta for one turn record."""
    return _turn_graph_delta(row)


def delegate_count_for_turn(row: Mapping[str, Any]) -> int:
    """Count delegate_subtask actions attempted on one turn record."""
    return _delegate_count_for_turn(row)


def _turn_graph_delta(row: Mapping[str, Any]) -> dict[str, int]:
    if row.get("determinations_changed") is not None or row.get("units_closed") is not None:
        return {
            "determinations_changed": int(row.get("determinations_changed") or 0),
            "units_closed": int(row.get("units_closed") or 0),
        }
    before = _coerce_mapping(row.get("resolution_state_before"))
    after = _coerce_mapping(row.get("resolution_state_after"))
    delta = _compute_resolution_graph_delta(before, after)
    return {
        "determinations_changed": delta["determinations_changed"],
        "units_closed": delta["units_closed"],
    }


def _delegate_count_for_turn(row: Mapping[str, Any]) -> int:
    if row.get("delegate_count") is not None:
        try:
            return int(row["delegate_count"])
        except (TypeError, ValueError):
            pass

    tool_request = _coerce_mapping(row.get("tool_request"))
    parsed = _coerce_mapping(row.get("parsed_action_plan"))
    actions = _extract_actions(tool_request, parsed)
    delegate_count = sum(
        1 for action in actions if str(action.get("action_type") or "") == DELEGATE_SUBTASK_ACTION_TYPE
    )
    sequence = _coerce_mapping(row.get("recent_action_sequence_result"))
    items = sequence.get("items")
    if isinstance(items, list):
        delegate_count = max(
            delegate_count,
            sum(
                1
                for item in items
                if isinstance(item, Mapping)
                and str(item.get("action_type") or "") == DELEGATE_SUBTASK_ACTION_TYPE
            ),
        )
    return delegate_count


def _resolution_items(loop_memory: LoopMemoryState) -> list[Any]:
    return list(getattr(loop_memory.continuity.resolution_state, "items", ()) or ())


def _resolution_atoms_from_state(loop_memory: LoopMemoryState) -> dict[str, dict[str, Any]]:
    items = _resolution_items(loop_memory)
    state = {"items": [_resolution_row_to_mapping(item) for item in items]}
    return _resolution_atoms(state)


def _resolution_row_to_mapping(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        payload = dict(row)
    elif hasattr(row, "model_dump"):
        payload = row.model_dump(mode="python")
    else:
        return {}
    covered_units = payload.get("covered_units")
    if isinstance(covered_units, list):
        payload["covered_units"] = [
            dict(unit) if isinstance(unit, Mapping) else (
                unit.model_dump(mode="python") if hasattr(unit, "model_dump") else unit
            )
            for unit in covered_units
        ]
    return payload


def _resolution_atoms(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    items = state.get("items")
    if not isinstance(items, list):
        return {}
    atoms: dict[str, dict[str, Any]] = {}
    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            continue
        item_id = str(raw_item.get("item_id") or "").strip()
        if item_id:
            atoms[f"item:{item_id}"] = dict(raw_item)
        covered_units = raw_item.get("covered_units")
        if not isinstance(covered_units, list):
            continue
        for raw_unit in covered_units:
            if not isinstance(raw_unit, Mapping):
                continue
            unit_id = str(raw_unit.get("unit_id") or "").strip()
            if unit_id:
                atoms[f"unit:{item_id}:{unit_id}"] = dict(raw_unit)
    return atoms


def _compute_resolution_graph_delta(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, int]:
    before_atoms = _resolution_atoms(before)
    after_atoms = _resolution_atoms(after)
    if not before_atoms and not after_atoms:
        return {"determinations_changed": 0, "units_closed": 0}

    determinations_changed = 0
    units_closed = 0
    for atom_id in set(before_atoms) & set(after_atoms):
        prior = before_atoms[atom_id]
        current = after_atoms[atom_id]
        if _determination_signature(prior) != _determination_signature(current):
            determinations_changed += 1
        if not _is_closed_status(prior.get("status")) and _is_closed_status(current.get("status")):
            units_closed += 1
    return {
        "determinations_changed": determinations_changed,
        "units_closed": units_closed,
    }


def _determination_signature(atom: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(atom.get("determined_value") or "").strip(),
        str(atom.get("determination") or "").strip(),
    )


def _is_closed_status(status: Any) -> bool:
    return str(status or "").strip().lower() == "closed"


def _is_blocked_status(status: Any) -> bool:
    return str(status or "").strip().lower() == "blocked"


def _is_determined(atom: Mapping[str, Any]) -> bool:
    if str(atom.get("determined_value") or "").strip():
        return True
    return bool(str(atom.get("determination") or "").strip())


def _extract_actions(
    tool_request: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> list[dict[str, Any]]:
    for source in (tool_request, parsed):
        raw = source.get("actions")
        if isinstance(raw, list) and raw:
            return [dict(row) for row in raw if isinstance(row, Mapping)]
    return []


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
