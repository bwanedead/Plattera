"""Mechanical application of model-authored ``state_patch`` into mission/resolution state.

The harness validates structure and merges; it does not invent work semantics,
infer closure from tools, or interpret domain vocabulary in patch *keys*.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, MutableMapping
from typing import Any

from pydantic import ValidationError

from ...mission_state import (
    ClosureDimension,
    ClosureState,
    MissionState,
    ResolutionItem,
    ResolutionItemHistoryEntry,
    ResolutionRelation,
    ResolutionState,
)
from ..memory import LoopMemoryState
from .contracts import ActionPlan
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

MAX_STATE_PATCH_JSON_BYTES = 200_000
MAX_PATCH_ITEMS_DELTA = 64
MAX_PATCH_RELATIONS_DELTA = 64
MAX_RESOLUTION_ITEMS_TOTAL = 128
MAX_RESOLUTION_RELATIONS_TOTAL = 128

ALLOWED_PATCH_TOP_LEVEL = frozenset({"resolution", "mission"})
ALLOWED_RESOLUTION_KEYS = frozenset({"active_item_id", "items", "relations", "opaque_payload"})
# Mission patch: model-authored fields only. Host/observability code owns latest_refs_summary,
# terminal_summary, and prompt_observability_summary (not writable via state_patch).
ALLOWED_MISSION_KEYS = frozenset(
    {
        "objective",
        "active_mode",
        "high_signal_artifact_refs",
        "blocker_summary",
        "verification_summary",
        "waiting_summary",
        "continuity_summary",
        "mission_mode_summary",
        "closure_state",
        "opaque_payload",
    }
)


def _empty_row_skip_report() -> dict[str, Any]:
    return {"resolution": {"items": {}, "relations": {}}}


def _bump_skips(target: MutableMapping[str, int], key: str, n: int = 1) -> None:
    target[key] = int(target.get(key, 0)) + n


def _nonzero_counts(raw: dict[str, int]) -> dict[str, int]:
    return {k: v for k, v in raw.items() if v}


def row_skip_report_has_skips(report: Mapping[str, Any]) -> bool:
    res = report.get("resolution")
    if not isinstance(res, dict):
        return False
    for branch in ("items", "relations"):
        b = res.get(branch)
        if not isinstance(b, dict):
            continue
        if any(isinstance(v, int) and v > 0 for v in b.values()):
            return True
    return False


class StatePatchError(ValueError):
    """Invalid ``state_patch`` shape or bounds; patch must be dropped, not reinterpreted."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def record_state_patch_no_patch_in_plan(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector | None,
    iteration: int,
) -> None:
    """Mechanical feedback when the plan carried no ``state_patch`` (prompt/runtime state; no trace row)."""
    del tracer
    loop_memory.continuity.state_patch_feedback = {
        "outcome": "no_patch",
        "iteration": iteration,
    }


def record_state_patch_not_applied(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector | None,
    iteration: int,
    execution_reason_code: str,
) -> None:
    """Patch was not merged because the mechanical step did not succeed (e.g. refusal)."""
    loop_memory.continuity.state_patch_feedback = {
        "outcome": "not_applied",
        "iteration": iteration,
        "execution_reason_code": execution_reason_code,
    }
    if tracer is not None:
        tracer.emit_state_patch_outcome(
            iteration=iteration,
            outcome="not_applied",
            reason_code=execution_reason_code,
            execution_reason_code=execution_reason_code,
        )


def apply_action_plan_state_patch_to_loop_memory(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    tracer: KernelTraceCollector | None = None,
    iteration: int = 0,
    gate: str = "",
) -> None:
    """Merge model ``state_patch`` into continuity; surface rejections via feedback + trace (not only logs)."""
    if not action_plan.state_patch:
        return
    try:
        ms_applied, rs_applied, row_skips = apply_state_patch(
            mission_state=loop_memory.continuity.mission_state,
            resolution_state=loop_memory.continuity.resolution_state,
            state_patch=action_plan.state_patch,
        )
        loop_memory.continuity.mission_state = ms_applied
        loop_memory.continuity.resolution_state = rs_applied
        loop_memory.continuity.active_item_id = rs_applied.active_item_id
        fb_applied: dict[str, Any] = {
            "outcome": "applied",
            "iteration": iteration,
            "gate": gate,
        }
        if row_skip_report_has_skips(row_skips):
            fb_applied["row_skips"] = row_skips
            fb_applied["skipped_resolution_rows"] = True
            hint = _row_skip_feedback_hint(row_skips)
            if hint is not None:
                fb_applied["repair_hint"] = hint
        loop_memory.continuity.state_patch_feedback = fb_applied
        trace_detail: dict[str, Any] | None = None
        if row_skip_report_has_skips(row_skips):
            trace_detail = {"row_skips": row_skips, "skipped_resolution_rows": True}
            if fb_applied.get("repair_hint") is not None:
                trace_detail["repair_hint"] = fb_applied["repair_hint"]
        if tracer is not None:
            tracer.emit_state_patch_outcome(
                iteration=iteration, outcome="applied", gate=gate, detail=trace_detail
            )
    except StatePatchError as exc:
        loop_memory.continuity.state_patch_feedback = {
            "outcome": "rejected",
            "iteration": iteration,
            "reason_code": exc.reason_code,
            "message": str(exc),
        }
        if tracer is not None:
            tracer.emit_state_patch_outcome(
                iteration=iteration,
                outcome="rejected",
                reason_code=exc.reason_code,
                message=str(exc),
            )
        _LOG.warning(
            "kernel state_patch rejected: reason_code=%s message=%s",
            exc.reason_code,
            str(exc),
        )


def _row_skip_feedback_hint(row_skips: Mapping[str, Any]) -> str | None:
    resolution = row_skips.get("resolution")
    if not isinstance(resolution, Mapping):
        return None
    item_skips = resolution.get("items")
    if not isinstance(item_skips, Mapping):
        return None
    if int(item_skips.get("missing_item_id") or 0) > 0:
        return "Each resolution item row must include a non-empty item_id."
    if int(item_skips.get("validation_failed") or 0) > 0:
        return (
            "Resolution item rows failed validation. Each item should usually include "
            "item_id, title, kind, and status with bounded field types."
        )
    return None


def sync_state_patch_after_committed_gate(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    tracer: KernelTraceCollector,
    iteration: int,
    gate: str,
) -> None:
    """Apply patch or record ``no_patch`` after a gate where persistence is allowed (step succeeded or non-step terminal)."""
    if action_plan.state_patch:
        apply_action_plan_state_patch_to_loop_memory(
            loop_memory=loop_memory,
            action_plan=action_plan,
            tracer=tracer,
            iteration=iteration,
            gate=gate,
        )
    else:
        record_state_patch_no_patch_in_plan(
            loop_memory=loop_memory, tracer=tracer, iteration=iteration
        )


def sync_state_patch_after_step_refusal(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector,
    iteration: int,
    patch_present: bool,
    execution_reason_code: str,
) -> None:
    if patch_present:
        record_state_patch_not_applied(
            loop_memory=loop_memory,
            tracer=tracer,
            iteration=iteration,
            execution_reason_code=execution_reason_code,
        )
    else:
        record_state_patch_no_patch_in_plan(
            loop_memory=loop_memory, tracer=tracer, iteration=iteration
        )


def sync_state_patch_when_no_step_dispatched(
    *,
    loop_memory: LoopMemoryState,
    action_plan: ActionPlan,
    tracer: KernelTraceCollector,
    iteration: int,
    patch_present: bool,
    skip_execution: bool,
) -> None:
    """No execution attempt: ``skip_execution`` commits patch; otherwise patch is deferred with ``not_applied``."""
    if skip_execution:
        sync_state_patch_after_committed_gate(
            loop_memory=loop_memory,
            action_plan=action_plan,
            tracer=tracer,
            iteration=iteration,
            gate="skip_execution",
        )
    elif patch_present:
        record_state_patch_not_applied(
            loop_memory=loop_memory,
            tracer=tracer,
            iteration=iteration,
            execution_reason_code="no_step_dispatched",
        )
    else:
        record_state_patch_no_patch_in_plan(
            loop_memory=loop_memory, tracer=tracer, iteration=iteration
        )


def apply_state_patch(
    *,
    mission_state: MissionState,
    resolution_state: ResolutionState,
    state_patch: Mapping[str, Any] | None,
) -> tuple[MissionState, ResolutionState, dict[str, Any]]:
    """
    Merge a bounded generic patch into existing state.

    Returns ``(mission_state, resolution_state, row_skips)`` where ``row_skips`` counts
    resolution rows the kernel dropped (non-destructive mechanical visibility for the model).

    - Unknown top-level or section keys → ``StatePatchError`` (reject whole patch).
    - Invalid ``ResolutionItem`` / ``ResolutionRelation`` rows are skipped (no repair).
    - ``items`` upsert by ``item_id`` with per-field merge (only keys present in the patch row overwrite).
    - ``relations`` append validated entries (capped).
    """
    if not state_patch:
        ms = mission_state.model_copy(update={"resolution_state": resolution_state})
        return ms, resolution_state, _empty_row_skip_report()

    patch = dict(state_patch)
    try:
        blob = json.dumps(patch, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        raise StatePatchError("state_patch_not_jsonable", str(exc)) from exc
    if len(blob.encode("utf-8")) > MAX_STATE_PATCH_JSON_BYTES:
        raise StatePatchError("state_patch_too_large", f"patch exceeds {MAX_STATE_PATCH_JSON_BYTES} bytes")

    unknown_top = set(patch.keys()) - ALLOWED_PATCH_TOP_LEVEL
    if unknown_top:
        raise StatePatchError(
            "state_patch_unknown_keys",
            f"unknown top-level keys: {sorted(unknown_top)}",
        )

    row_skips = _empty_row_skip_report()
    rs = resolution_state
    if "resolution" in patch:
        rs, res_skips = _apply_resolution_branch(rs, patch["resolution"])
        row_skips["resolution"] = res_skips

    ms = mission_state
    if "mission" in patch:
        ms = _apply_mission_branch(ms, patch["mission"])

    ms = ms.model_copy(update={"resolution_state": rs})
    return ms, rs, row_skips


def _merge_resolution_item_row(existing: ResolutionItem | None, row: dict[str, Any]) -> ResolutionItem | None:
    """Overlay patch keys onto an existing item; absent keys keep prior values (additive updates)."""
    base: dict[str, Any] = existing.model_dump(mode="json") if existing is not None else {}
    field_names = ResolutionItem.model_fields.keys()

    for key, val in row.items():
        if key not in field_names:
            continue
        if key == "opaque_payload" and isinstance(val, dict):
            prior = base.get("opaque_payload") if isinstance(base.get("opaque_payload"), dict) else {}
            base["opaque_payload"] = {**prior, **val}
        elif key == "scope" and isinstance(val, dict):
            prior = base.get("scope") if isinstance(base.get("scope"), dict) else {}
            base["scope"] = {**prior, **val}
        elif key == "history" and isinstance(val, list):
            normalized: list[dict[str, Any]] = []
            bad = False
            for h in val:
                if not isinstance(h, dict):
                    bad = True
                    break
                try:
                    normalized.append(ResolutionItemHistoryEntry.model_validate(h).model_dump(mode="json"))
                except ValidationError:
                    bad = True
                    break
            if not bad:
                base["history"] = normalized
        elif key == "context_notes" and isinstance(val, list):
            base["context_notes"] = list(val)
        else:
            base[key] = val

    try:
        return ResolutionItem.model_validate(base)
    except ValidationError:
        return None


def _apply_resolution_branch(rs: ResolutionState, raw: Any) -> tuple[ResolutionState, dict[str, dict[str, int]]]:
    if not isinstance(raw, dict):
        raise StatePatchError("resolution_not_object", "resolution must be a JSON object")

    unknown = set(raw.keys()) - ALLOWED_RESOLUTION_KEYS
    if unknown:
        raise StatePatchError(
            "resolution_unknown_keys",
            f"unknown resolution keys: {sorted(unknown)}",
        )

    item_skips: dict[str, int] = {}
    relation_skips: dict[str, int] = {}

    items = list(rs.items)
    relations = list(rs.relations)
    active = rs.active_item_id
    opaque = dict(rs.opaque_payload)

    if "items" in raw:
        patch_items = raw["items"]
        if not isinstance(patch_items, list):
            raise StatePatchError("items_not_array", "resolution.items must be an array")
        if len(patch_items) > MAX_PATCH_ITEMS_DELTA:
            raise StatePatchError("items_delta_too_large", f"max {MAX_PATCH_ITEMS_DELTA} items per patch")

        by_id: dict[str, ResolutionItem] = {i.item_id: i for i in items}
        for row in patch_items:
            if not isinstance(row, dict):
                _bump_skips(item_skips, "not_object")
                continue
            item_id_raw = row.get("item_id")
            item_id = str(item_id_raw).strip() if item_id_raw is not None else ""
            if not item_id:
                _bump_skips(item_skips, "missing_item_id")
                continue
            existing = by_id.get(item_id)
            merged = _merge_resolution_item_row(existing, row)
            if merged is None:
                _bump_skips(item_skips, "validation_failed")
                continue
            by_id[merged.item_id] = merged
        items = list(by_id.values())
        if len(items) > MAX_RESOLUTION_ITEMS_TOTAL:
            raise StatePatchError("items_total_too_large", f"max {MAX_RESOLUTION_ITEMS_TOTAL} items")

    if "relations" in raw:
        patch_rel = raw["relations"]
        if not isinstance(patch_rel, list):
            raise StatePatchError("relations_not_array", "resolution.relations must be an array")
        if len(patch_rel) > MAX_PATCH_RELATIONS_DELTA:
            raise StatePatchError(
                "relations_delta_too_large",
                f"max {MAX_PATCH_RELATIONS_DELTA} relations per patch",
            )
        for row in patch_rel:
            if not isinstance(row, dict):
                _bump_skips(relation_skips, "not_object")
                continue
            try:
                relations.append(ResolutionRelation.model_validate(row))
            except ValidationError:
                _bump_skips(relation_skips, "validation_failed")
                continue
        if len(relations) > MAX_RESOLUTION_RELATIONS_TOTAL:
            overflow = len(relations) - MAX_RESOLUTION_RELATIONS_TOTAL
            relations = relations[:MAX_RESOLUTION_RELATIONS_TOTAL]
            _bump_skips(relation_skips, "truncated_to_cap", overflow)

    if "active_item_id" in raw:
        v = raw["active_item_id"]
        if v is None:
            active = None
        else:
            text = str(v).strip()[:128]
            active = text or None

    if "opaque_payload" in raw:
        op = raw["opaque_payload"]
        if op is None:
            opaque = {}
        elif isinstance(op, dict):
            opaque = {**opaque, **op}
        else:
            raise StatePatchError("opaque_payload_not_object", "resolution.opaque_payload must be an object or null")

    out = rs.model_copy(
        update={
            "items": items,
            "relations": relations,
            "active_item_id": active,
            "opaque_payload": opaque,
            "updated_at_epoch_seconds": time.time(),
        }
    )
    return out, {
        "items": _nonzero_counts(item_skips),
        "relations": _nonzero_counts(relation_skips),
    }


def _apply_mission_branch(ms: MissionState, raw: Any) -> MissionState:
    if not isinstance(raw, dict):
        raise StatePatchError("mission_not_object", "mission must be a JSON object")

    unknown = set(raw.keys()) - ALLOWED_MISSION_KEYS
    if unknown:
        raise StatePatchError("mission_unknown_keys", f"unknown mission keys: {sorted(unknown)}")

    updates: dict[str, Any] = {}
    opaque = dict(ms.opaque_payload)

    if "objective" in raw:
        v = raw["objective"]
        updates["objective"] = None if v is None else (str(v).strip()[:240] or None)

    if "active_mode" in raw:
        v = raw["active_mode"]
        updates["active_mode"] = None if v is None else (str(v).strip()[:64] or None)

    for key in (
        "blocker_summary",
        "verification_summary",
        "waiting_summary",
        "continuity_summary",
        "mission_mode_summary",
    ):
        if key not in raw:
            continue
        val = raw[key]
        if val is None:
            updates[key] = {}
        elif isinstance(val, str):
            # String shorthand: normalizes to {"summary": "<string>"} or {} if blank.
            val_stripped = val.strip()
            updates[key] = {"summary": val_stripped} if val_stripped else {}
        elif isinstance(val, dict):
            prior = getattr(ms, key)
            if isinstance(prior, dict):
                updates[key] = {**prior, **val}
            else:
                updates[key] = dict(val)
        else:
            raise StatePatchError(f"{key}_not_object", f"mission.{key} must be an object, string, or null")

    if "closure_state" in raw:
        updates["closure_state"] = _apply_closure_state(ms.closure_state, raw["closure_state"])

    if "high_signal_artifact_refs" in raw:
        refs = raw["high_signal_artifact_refs"]
        if refs is None:
            updates["high_signal_artifact_refs"] = []
        elif isinstance(refs, list):
            cleaned: list[str] = []
            for item in refs:
                t = str(item).strip()[:240]
                if t and t not in cleaned:
                    cleaned.append(t)
                if len(cleaned) >= 16:
                    break
            updates["high_signal_artifact_refs"] = cleaned
        else:
            raise StatePatchError("high_signal_not_array", "mission.high_signal_artifact_refs must be an array or null")

    if "opaque_payload" in raw:
        op = raw["opaque_payload"]
        if op is None:
            opaque = {}
        elif isinstance(op, dict):
            opaque = {**opaque, **op}
        else:
            raise StatePatchError("mission_opaque_not_object", "mission.opaque_payload must be an object or null")

    updates["opaque_payload"] = opaque
    updates["updated_at_epoch_seconds"] = time.time()
    return ms.model_copy(update=updates)


def _merge_closure_dimension_row(
    existing: ClosureDimension | None,
    row: dict[str, Any],
) -> ClosureDimension | None:
    base: dict[str, Any] = existing.model_dump(mode="json") if existing is not None else {}
    field_names = ClosureDimension.model_fields.keys()

    for key, val in row.items():
        if key not in field_names:
            continue
        if key == "opaque_payload" and isinstance(val, dict):
            prior = base.get("opaque_payload") if isinstance(base.get("opaque_payload"), dict) else {}
            base["opaque_payload"] = {**prior, **val}
        else:
            base[key] = val

    try:
        return ClosureDimension.model_validate(base)
    except ValidationError:
        return None


def _apply_closure_state(current: ClosureState, raw: Any) -> ClosureState:
    if raw is None:
        return ClosureState(updated_at_epoch_seconds=time.time())
    if not isinstance(raw, dict):
        raise StatePatchError("closure_state_not_object", "mission.closure_state must be an object or null")

    allowed = {
        "overall_status",
        "summary",
        "ready_to_publish",
        "ready_to_close",
        "requires_hitl",
        "no_further_progress",
        "dimensions",
        "opaque_payload",
    }
    unknown = set(raw.keys()) - allowed
    if unknown:
        raise StatePatchError(
            "closure_state_unknown_keys",
            f"unknown mission.closure_state keys: {sorted(unknown)}",
        )

    updates: dict[str, Any] = {}
    if "overall_status" in raw:
        v = raw["overall_status"]
        updates["overall_status"] = None if v is None else (str(v).strip()[:64] or None)
    if "summary" in raw:
        v = raw["summary"]
        updates["summary"] = None if v is None else (str(v).strip()[:500] or None)
    for key in ("ready_to_publish", "ready_to_close", "requires_hitl", "no_further_progress"):
        if key not in raw:
            continue
        val = raw[key]
        if not isinstance(val, bool):
            raise StatePatchError(f"{key}_not_boolean", f"mission.closure_state.{key} must be a boolean")
        updates[key] = val

    if "dimensions" in raw:
        dims = raw["dimensions"]
        if not isinstance(dims, list):
            raise StatePatchError("closure_dimensions_not_array", "mission.closure_state.dimensions must be an array")
        by_id: dict[str, ClosureDimension] = {d.dimension_id: d for d in current.dimensions}
        next_order: list[str] = [d.dimension_id for d in current.dimensions]
        for row in dims:
            if not isinstance(row, dict):
                raise StatePatchError(
                    "closure_dimension_not_object",
                    "mission.closure_state.dimensions rows must be objects",
                )
            dim_id_raw = row.get("dimension_id")
            dim_id = str(dim_id_raw).strip() if dim_id_raw is not None else ""
            if not dim_id:
                raise StatePatchError(
                    "closure_dimension_missing_id",
                    "mission.closure_state.dimensions rows require dimension_id",
                )
            merged = _merge_closure_dimension_row(by_id.get(dim_id), row)
            if merged is None:
                raise StatePatchError(
                    "closure_dimension_validation_failed",
                    f"mission.closure_state.dimensions[{dim_id}] failed validation",
                )
            by_id[dim_id] = merged
            if dim_id not in next_order:
                next_order.append(dim_id)
        updates["dimensions"] = [by_id[dim_id] for dim_id in next_order]

    if "opaque_payload" in raw:
        op = raw["opaque_payload"]
        if op is None:
            updates["opaque_payload"] = {}
        elif isinstance(op, dict):
            updates["opaque_payload"] = {**current.opaque_payload, **op}
        else:
            raise StatePatchError(
                "closure_state_opaque_not_object",
                "mission.closure_state.opaque_payload must be an object or null",
            )

    updates["updated_at_epoch_seconds"] = time.time()
    return current.model_copy(update=updates)
