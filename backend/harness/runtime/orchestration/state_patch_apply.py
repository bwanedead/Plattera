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
    MissionSuccessCondition,
    ResolutionCoveredUnit,
    ResolutionItem,
    ResolutionItemHistoryEntry,
    ResolutionRelation,
    ResolutionState,
)
from ..memory import LoopMemoryState
from ..memory.stable_context import (
    StableContextValidationError,
    apply_stable_context_patch,
)
from .contracts import ActionPlan
from .evidence_sequencing import apply_sequencing_debt_from_patch
from .state_patch_repair_bundle import build_state_patch_repair_bundle
from .state_patch_shape_repair import repair_state_patch_container_shapes
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)

MAX_STATE_PATCH_JSON_BYTES = 200_000
MAX_PATCH_ITEMS_DELTA = 64
MAX_PATCH_RELATIONS_DELTA = 64
MAX_RESOLUTION_ITEMS_TOTAL = 128
MAX_RESOLUTION_RELATIONS_TOTAL = 128
MAX_STATE_PATCH_DETAIL_ROWS = 4
MAX_STATE_PATCH_VALIDATION_ERRORS = 4
_WORK_UNIVERSE_POSTURES = frozenset({"initial", "partial", "believed_adequate", "audited"})
_MOTION_POSTURES = frozenset({"inventory", "resolution"})
_MAX_MOTION_POSTURE_BASIS_CHARS = 500

# Salvageable optional prose/display fields: may be omitted when invalid without
# destroying core semantic content. Only top-level string-overlong failures on these
# fields are eligible. Identity fields, semantic/evidence fields, structural lists,
# and boolean flags must never be silently omitted.
_SALVAGEABLE_ITEM_FIELDS: frozenset[str] = frozenset({"summary", "notes", "closure_summary"})
_SALVAGEABLE_UNIT_FIELDS: frozenset[str] = frozenset({"summary", "closure_summary"})
_SALVAGE_OMIT_NOTE: str = (
    "Optional prose field omitted (invalid); field was not rewritten. "
    "Re-author shorter text if this field matters."
)

ALLOWED_PATCH_TOP_LEVEL = frozenset({"resolution", "mission", "stable_context"})
_STATE_PATCH_ALIAS_KEYS = {"mission_state": "mission", "resolution_state": "resolution"}
ALLOWED_RESOLUTION_KEYS = frozenset({"active_item_id", "items", "relations", "opaque_payload"})
# Mission patch: model-authored fields only. Host/observability code owns latest_refs_summary,
# terminal_summary, and prompt_observability_summary (not writable via state_patch).
ALLOWED_MISSION_KEYS = frozenset(
    {
        "objective",
        "active_mode",
        "work_universe_posture",
        "motion_posture",
        "motion_posture_basis",
        "high_signal_artifact_refs",
        "blocker_summary",
        "verification_summary",
        "waiting_summary",
        "continuity_summary",
        "mission_mode_summary",
        "success_conditions",
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
    if isinstance(res, dict):
        for branch in ("items", "relations"):
            b = res.get(branch)
            if isinstance(b, dict):
                if any(isinstance(v, int) and v > 0 for v in b.values()):
                    return True
    stable = report.get("stable_context")
    if isinstance(stable, dict):
        if any(isinstance(v, int) and v > 0 for v in stable.values()):
            return True
    return False


class StatePatchError(ValueError):
    """Invalid ``state_patch`` shape or bounds; patch must be dropped, not reinterpreted."""

    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.detail = dict(detail or {})


def _format_validation_error_row(row: Mapping[str, Any], *, path_prefix: str = "") -> str:
    """Render one Pydantic v2 error into a compact single-line repair hint.

    Includes bound details (max_length, actual size) and reason kind where possible
    so the agent can repair the exact field without rereading evidence.
    """
    loc_parts = [str(part) for part in row.get("loc", ())]
    sub_path = ".".join(loc_parts) if loc_parts else "$"
    if path_prefix:
        path = f"{path_prefix}.{sub_path}" if sub_path != "$" else path_prefix
    else:
        path = sub_path
    err_type = str(row.get("type") or "")
    msg = str(row.get("msg") or err_type or "validation error")
    ctx = row.get("ctx") if isinstance(row.get("ctx"), Mapping) else {}
    input_value = row.get("input")

    extras: list[str] = []
    if err_type == "string_too_long":
        max_len = ctx.get("max_length")
        actual = len(input_value) if isinstance(input_value, str) else None
        if max_len is not None and actual is not None:
            extras.append(f"string too long, {actual} > {max_len}")
        elif max_len is not None:
            extras.append(f"max_length {max_len}")
    elif err_type == "string_too_short":
        min_len = ctx.get("min_length")
        actual = len(input_value) if isinstance(input_value, str) else None
        if min_len is not None and actual is not None:
            extras.append(f"string too short, {actual} < {min_len}")
        elif min_len is not None:
            extras.append(f"min_length {min_len}")
    elif err_type == "too_long":
        max_len = ctx.get("max_length")
        actual = ctx.get("actual_length")
        if isinstance(input_value, list) and actual is None:
            actual = len(input_value)
        if max_len is not None and actual is not None:
            extras.append(f"too many items, {actual} > {max_len}")
        elif max_len is not None:
            extras.append(f"max items {max_len}")
    elif err_type == "missing":
        extras.append("required")
    elif err_type == "extra_forbidden":
        extras.append("extra field forbidden")
    elif err_type.startswith("type_"):
        expected = err_type.removeprefix("type_") or "value"
        extras.append(f"wrong type: expected {expected}")

    detail = "; ".join(extras) if extras else msg
    return f"{path}: {detail}"


def _validation_error_summaries(
    exc: ValidationError,
    *,
    path_prefix: str = "",
) -> list[str]:
    out: list[str] = []
    for row in exc.errors()[:MAX_STATE_PATCH_VALIDATION_ERRORS]:
        out.append(_format_validation_error_row(row, path_prefix=path_prefix))
    return out


def _collect_salvageable_errors(
    exc: ValidationError,
    *,
    salvageable: frozenset[str],
    path_prefix: str = "",
) -> tuple[frozenset[str], list[str]]:
    """Return (failing_salvageable_fields, compact_errors) if ALL errors are top-level and salvageable.

    Salvageable means: single-element loc, and the field name is in the allowlist.
    Any validation failure type (string too long, wrong type, wrong format) is
    eligible — the constraint is the field being optional prose, not the error kind.
    Returns (frozenset(), []) when any error touches a non-salvageable field or is nested
    (multi-element loc). Nested errors cannot be safely dropped at this level.
    """
    failing: set[str] = set()
    compact: list[str] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        if len(loc) != 1:
            return frozenset(), []
        field = str(loc[0])
        if field not in salvageable:
            return frozenset(), []
        failing.add(field)
        compact.append(_format_validation_error_row(err, path_prefix=path_prefix))
    return frozenset(failing), compact


def _detail_row(
    *,
    path: str,
    reason_code: str,
    row_id: str | None = None,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    detail = {
        "path": path,
        "reason_code": reason_code,
    }
    if row_id:
        detail["row_id"] = row_id
    if validation_errors:
        detail["validation_errors"] = list(validation_errors[:MAX_STATE_PATCH_VALIDATION_ERRORS])
    return detail


def _normalize_state_patch_aliases(state_patch: Mapping[str, Any]) -> dict[str, Any]:
    patch = dict(state_patch)
    for alias, canonical in _STATE_PATCH_ALIAS_KEYS.items():
        if alias not in patch:
            continue
        if canonical in patch:
            raise StatePatchError(
                "state_patch_alias_conflict",
                f"state_patch contains both {canonical} and its alias {alias}",
                detail={
                    "failing_path": "state_patch",
                    "repair_hint": f"Use only state_patch.{canonical}; do not also emit state_patch.{alias}.",
                },
            )
        patch[canonical] = patch.pop(alias)
    return patch


def _append_detail(target: list[dict[str, Any]], detail: dict[str, Any]) -> None:
    if len(target) < MAX_STATE_PATCH_DETAIL_ROWS:
        target.append(detail)


def _derive_repair_targets_from_feedback(
    *,
    reason_code: str | None = None,
    row_skip_details: Mapping[str, Any] | None = None,
) -> list[str]:
    targets: list[str] = []
    reason = str(reason_code or "").strip()
    if reason.startswith("success_condition_"):
        targets.append("repair_success_condition_row")
    elif reason.startswith("closure_dimension_") or reason.startswith("closure_state_"):
        targets.append("repair_closure_dimension_row")
    elif reason.startswith("mission_"):
        targets.append("repair_mission_patch_shape")
    elif reason.startswith("resolution_") or reason.startswith("items_") or reason.startswith("relations_"):
        targets.append("repair_resolution_patch_shape")

    if isinstance(row_skip_details, Mapping):
        resolution = row_skip_details.get("resolution")
        if isinstance(resolution, Mapping):
            if resolution.get("items"):
                targets.append("repair_resolution_item_rows")
            if resolution.get("relations"):
                targets.append("repair_resolution_relation_rows")
    out: list[str] = []
    for target in targets:
        if target not in out:
            out.append(target)
    return out


def _repair_hint_from_rejection(
    *,
    reason_code: str,
    failing_path: str | None,
) -> str | None:
    path = str(failing_path or "").strip()
    if reason_code.startswith("success_condition_"):
        return (
            f"Patch only {path or 'mission.success_conditions'} and include condition_id, title, and status."
        )
    if reason_code.startswith("closure_dimension_") or reason_code.startswith("closure_state_"):
        return (
            f"Patch only {path or 'mission.closure_state'} and include the required closure keys for that row."
        )
    if reason_code.startswith("mission_"):
        return "Patch only allowed mission keys inside state_patch.mission."
    if reason_code == "resolution_terminal_row_has_live_work":
        return (
            "Resolution item and covered-unit patches are sparse per-field overlays. "
            "Omitting a field preserves its existing value. "
            "To clear next_needed_step, send it explicitly as null. "
            "To clear requires_hitl or no_further_progress, send false. "
            "A closed/earned/resolved row still carries live-work posture. "
            "Either clear the stale live-work fields because closure is genuinely earned, "
            "or reopen/reclassify the row because work remains. "
            "The harness does not choose which is correct and does not apply clears automatically."
        )
    if reason_code.startswith("resolution_") or reason_code.startswith("items_") or reason_code.startswith("relations_"):
        return "Patch only allowed resolution keys inside state_patch.resolution."
    return None


_SEMANTIC_INTENT_STATUS_TOKENS = frozenset(
    {"closed", "blocked", "earned", "in_review", "exhausted", "no_further_progress"}
)


def _detect_semantic_intent_kinds(
    *,
    state_patch: Mapping[str, Any] | None,
    hitl_consumed_prompt_ids: tuple[str, ...] | list[str] | None,
) -> list[str]:
    """Return mechanical kinds of semantic persistence the patch *attempted* to encode.

    The runtime does not decide semantic truth here; it only detects whether the
    patch carried fields whose loss would represent lost semantic intent (HITL
    consumption, claim values/evidence, status changes, closure changes).
    """
    kinds: list[str] = []
    if hitl_consumed_prompt_ids:
        kinds.append("hitl_consumed_prompt_ids")
    if not isinstance(state_patch, Mapping):
        return list(dict.fromkeys(kinds))

    res = state_patch.get("resolution")
    if isinstance(res, Mapping):
        for row in (res.get("items") or ()):
            if not isinstance(row, Mapping):
                continue
            status = str(row.get("status") or "").strip().lower()
            if status in _SEMANTIC_INTENT_STATUS_TOKENS:
                kinds.append("item_status_change")
            for boolean_key in ("requires_hitl", "no_further_progress", "blocking"):
                if boolean_key in row:
                    kinds.append("item_status_change")
                    break
            if "determination" in row and str(row.get("determination") or "").strip().lower() == "earned":
                kinds.append("item_status_change")
            if row.get("evidence_refs"):
                kinds.append("evidence_refs")
            for unit in (row.get("covered_units") or ()):
                if not isinstance(unit, Mapping):
                    continue
                if unit.get("determined_value") not in (None, ""):
                    kinds.append("determined_value")
                if unit.get("candidate_values"):
                    kinds.append("candidate_values")
                if unit.get("evidence_refs"):
                    kinds.append("evidence_refs")
                u_status = str(unit.get("status") or "").strip().lower()
                if u_status in _SEMANTIC_INTENT_STATUS_TOKENS:
                    kinds.append("unit_status_change")
                if "determination" in unit and str(unit.get("determination") or "").strip().lower() == "earned":
                    kinds.append("unit_status_change")
                for boolean_key in ("requires_hitl", "no_further_progress"):
                    if boolean_key in unit:
                        kinds.append("unit_status_change")
                        break

    mission = state_patch.get("mission")
    if isinstance(mission, Mapping):
        if "closure_state" in mission:
            kinds.append("closure_state_change")
        if "success_conditions" in mission:
            kinds.append("success_conditions_change")

    return list(dict.fromkeys(kinds))


def _carry_pending_hitl_integration(
    previous_feedback: Mapping[str, Any] | None,
) -> list[str]:
    if not isinstance(previous_feedback, Mapping):
        return []
    raw = previous_feedback.get("pending_hitl_integration_prompt_ids")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


def _build_state_patch_feedback(
    previous_feedback: Mapping[str, Any] | None,
    *,
    outcome: str,
    iteration: int,
    gate: str | None = None,
    reason_code: str | None = None,
    message: str | None = None,
    execution_reason_code: str | None = None,
    detail: Mapping[str, Any] | None = None,
    semantic_intent_kinds: list[str] | None = None,
    attempted_hitl_consumed_prompt_ids: tuple[str, ...] | list[str] | None = None,
    cleared_hitl_consumed_prompt_ids: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    previous = dict(previous_feedback or {})
    feedback: dict[str, Any] = {
        "outcome": outcome,
        "iteration": iteration,
        "same_outcome_streak": (
            int(previous.get("same_outcome_streak") or 0) + 1
            if str(previous.get("outcome") or "").strip() == outcome
            else 1
        ),
    }
    if gate:
        feedback["gate"] = gate
    if message:
        feedback["message"] = message
    if execution_reason_code:
        feedback["execution_reason_code"] = execution_reason_code
    if reason_code:
        feedback["reason_code"] = reason_code
        feedback["same_reason_code_streak"] = (
            int(previous.get("same_reason_code_streak") or 0) + 1
            if str(previous.get("reason_code") or "").strip() == reason_code
            else 1
        )
    last_applied_iteration = previous.get("last_applied_iteration")
    if outcome == "applied":
        feedback["last_applied_iteration"] = iteration
    elif isinstance(last_applied_iteration, int):
        feedback["last_applied_iteration"] = last_applied_iteration

    if isinstance(detail, Mapping):
        for key in (
            "row_skips",
            "skipped_resolution_rows",
            "row_skip_details",
            "salvaged_rows",
            "shape_repairs",
            "state_patch_repair_bundle",
            "stable_context",
            "failing_path",
            "validation_errors",
            "repair_hint",
            "repair_targets",
            "conflicts",
            "conflicts_omitted_count",
            "conflict_identity",
            "same_conflict_streak",
        ):
            if key in detail:
                feedback[key] = detail[key]
    if "repair_targets" not in feedback:
        repair_targets = _derive_repair_targets_from_feedback(
            reason_code=reason_code,
            row_skip_details=feedback.get("row_skip_details") if isinstance(feedback.get("row_skip_details"), Mapping) else None,
        )
        if repair_targets:
            feedback["repair_targets"] = repair_targets
    if "repair_hint" not in feedback and reason_code:
        hint = _repair_hint_from_rejection(
            reason_code=reason_code,
            failing_path=feedback.get("failing_path") if isinstance(feedback.get("failing_path"), str) else None,
        )
        if hint is not None:
            feedback["repair_hint"] = hint

    # Semantic repair debt: when a patch tried to persist meaningful state but did
    # not land cleanly, expose the kinds of intent that remain pending so the next
    # turn can repair before rereading or re-asking. Trivial malformed/no-op patches
    # produce no debt because semantic_intent_kinds is empty.
    has_skipped_rows = bool(
        isinstance(detail, Mapping) and detail.get("skipped_resolution_rows")
    )
    failed_persistence = outcome in ("rejected", "not_applied") or has_skipped_rows
    intent_kinds = list(semantic_intent_kinds or [])
    new_debt: list[str] = []
    if failed_persistence and intent_kinds:
        new_debt = list(intent_kinds)

    prior_debt = (
        list(previous.get("semantic_repair_debt"))
        if isinstance(previous.get("semantic_repair_debt"), list)
        else []
    )
    if outcome == "applied" and prior_debt:
        # Only clear prior debt kinds the current patch plausibly repaired
        # (intent_kinds present in the patch). An unrelated clean apply must NOT
        # silently erase a still-open obligation. The agent can still abandon a
        # debt kind by including that kind in a clean patch with a rationale.
        repaired = set(intent_kinds)
        carried = [kind for kind in prior_debt if kind not in repaired]
        merged = list(dict.fromkeys(carried))
    else:
        merged = list(dict.fromkeys([*prior_debt, *new_debt]))
    if merged:
        feedback["semantic_repair_debt"] = merged

    # HITL integration stickiness: a rejected patch that *attempted* to consume
    # HITL prompt ids leaves them as pending integration debt until a later
    # successful patch consumes them. The runtime does not interpret answers; it
    # only tracks attempted-consumed ids vs successfully-consumed ids.
    pending_hitl = _carry_pending_hitl_integration(previous)
    attempted_ids = [
        str(p).strip()
        for p in (attempted_hitl_consumed_prompt_ids or ())
        if str(p).strip()
    ]
    if outcome != "applied" and attempted_ids:
        for pid in attempted_ids:
            if pid not in pending_hitl:
                pending_hitl.append(pid)
    if outcome == "applied":
        cleared = {str(p).strip() for p in (cleared_hitl_consumed_prompt_ids or ()) if str(p).strip()}
        if cleared:
            pending_hitl = [pid for pid in pending_hitl if pid not in cleared]
    if pending_hitl:
        feedback["pending_hitl_integration_prompt_ids"] = pending_hitl

    prior_bundle = previous.get("state_patch_repair_bundle")
    new_bundle = (
        detail.get("state_patch_repair_bundle")
        if isinstance(detail, Mapping) and isinstance(detail.get("state_patch_repair_bundle"), Mapping)
        else None
    )
    if outcome in ("no_patch", "not_applied"):
        if isinstance(prior_bundle, Mapping) and prior_bundle.get("fragments"):
            feedback["state_patch_repair_bundle"] = prior_bundle
    elif outcome == "applied":
        if isinstance(new_bundle, Mapping) and new_bundle.get("fragments"):
            feedback["state_patch_repair_bundle"] = new_bundle
        elif not has_skipped_rows and not merged:
            pass
        elif isinstance(prior_bundle, Mapping) and prior_bundle.get("fragments"):
            feedback["state_patch_repair_bundle"] = prior_bundle
    elif outcome == "rejected":
        if isinstance(new_bundle, Mapping) and new_bundle.get("fragments"):
            feedback["state_patch_repair_bundle"] = new_bundle
        elif isinstance(prior_bundle, Mapping) and prior_bundle.get("fragments"):
            feedback["state_patch_repair_bundle"] = prior_bundle

    return feedback


def record_state_patch_no_patch_in_plan(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector | None,
    iteration: int,
) -> None:
    """Mechanical feedback when the plan carried no ``state_patch`` (prompt/runtime state; no trace row)."""
    del tracer
    # No patch → no new attempted persistence; preserve any pending HITL integration
    # debt and prior semantic repair debt unchanged via the carry-forward path.
    loop_memory.continuity.state_patch_feedback = _build_state_patch_feedback(
        loop_memory.continuity.state_patch_feedback,
        outcome="no_patch",
        iteration=iteration,
    )


def record_state_patch_not_applied(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector | None,
    iteration: int,
    execution_reason_code: str,
    state_patch: Mapping[str, Any] | None = None,
    hitl_consumed_prompt_ids: tuple[str, ...] | list[str] | None = None,
) -> None:
    """Patch was not merged because the mechanical step did not succeed (e.g. refusal)."""
    intent_kinds = _detect_semantic_intent_kinds(
        state_patch=state_patch,
        hitl_consumed_prompt_ids=tuple(hitl_consumed_prompt_ids or ()),
    )
    loop_memory.continuity.state_patch_feedback = _build_state_patch_feedback(
        loop_memory.continuity.state_patch_feedback,
        outcome="not_applied",
        iteration=iteration,
        execution_reason_code=execution_reason_code,
        semantic_intent_kinds=intent_kinds,
        attempted_hitl_consumed_prompt_ids=tuple(hitl_consumed_prompt_ids or ()),
    )
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
    attempted_consumed = tuple(action_plan.hitl_consumed_prompt_ids or ())
    intent_kinds = _detect_semantic_intent_kinds(
        state_patch=action_plan.state_patch,
        hitl_consumed_prompt_ids=attempted_consumed,
    )
    try:
        before_rs = loop_memory.continuity.resolution_state
        ms_applied, rs_applied, row_skips, row_skip_details, salvage_events, shape_repairs = _apply_state_patch_detailed(
            mission_state=loop_memory.continuity.mission_state,
            resolution_state=before_rs,
            state_patch=action_plan.state_patch,
        )
        stable_context_detail: dict[str, Any] | None = None
        stable_context_applied: list[dict[str, Any]] | None = None
        if isinstance(action_plan.state_patch, Mapping) and "stable_context" in action_plan.state_patch:
            try:
                stable_context_applied, stable_context_detail = apply_stable_context_patch(
                    loop_memory.continuity.stable_context,
                    action_plan.state_patch.get("stable_context"),
                    current_turn=int(iteration),
                )
            except StableContextValidationError as exc:
                raise StatePatchError(
                    "stable_context_invalid",
                    str(exc),
                    detail={
                        "failing_path": "state_patch.stable_context",
                        "repair_hint": "Use stable_context.upsert[] and stable_context.retire[] only.",
                    },
                ) from exc
        loop_memory.continuity.mission_state = ms_applied
        loop_memory.continuity.resolution_state = rs_applied
        loop_memory.continuity.active_item_id = rs_applied.active_item_id
        if stable_context_applied is not None:
            loop_memory.continuity.stable_context = stable_context_applied
        # Advisory sequencing-debt detection: compare before/after resolution state.
        # Must run after the state is committed so the continuity debt dicts are
        # updated atomically with the rest of the patch outcome.
        apply_sequencing_debt_from_patch(
            loop_memory, before_rs=before_rs, after_rs=rs_applied, iteration=iteration
        )
        detail: dict[str, Any] = {}
        if shape_repairs:
            detail["shape_repairs"] = shape_repairs
        if salvage_events:
            detail["salvaged_rows"] = salvage_events
        if stable_context_detail is not None:
            detail["stable_context"] = stable_context_detail
            if stable_context_detail.get("skipped_rows"):
                row_skips.setdefault("stable_context", {})["validation_failed"] = len(
                    stable_context_detail.get("skipped_rows") or []
                )
        if row_skip_report_has_skips(row_skips):
            detail["row_skips"] = row_skips
            if row_skip_details:
                detail["row_skip_details"] = row_skip_details
        resolution_skips = row_skips.get("resolution")
        if isinstance(resolution_skips, Mapping) and any(
            isinstance(v, int) and v > 0
            for branch in (resolution_skips.get("items"), resolution_skips.get("relations"))
            if isinstance(branch, Mapping)
            for v in branch.values()
        ):
            detail["skipped_resolution_rows"] = True
            repair_bundle = build_state_patch_repair_bundle(
                state_patch=action_plan.state_patch,
                row_skip_details=row_skip_details,
            )
            if repair_bundle:
                detail["state_patch_repair_bundle"] = repair_bundle
            hint = _row_skip_feedback_hint(row_skips)
            if hint is not None:
                detail["repair_hint"] = hint
        # Successfully applied (clean or with row skips). Treat fully-clean apply
        # as clearing the consumed ids; partial apply still carries the attempt as
        # pending integration debt because the rows that needed the answer may
        # have been the ones that failed.
        cleared = attempted_consumed if not row_skip_report_has_skips(row_skips) else ()
        loop_memory.continuity.state_patch_feedback = _build_state_patch_feedback(
            loop_memory.continuity.state_patch_feedback,
            outcome="applied",
            iteration=iteration,
            gate=gate,
            detail=detail,
            semantic_intent_kinds=intent_kinds,
            attempted_hitl_consumed_prompt_ids=attempted_consumed,
            cleared_hitl_consumed_prompt_ids=cleared,
        )
        trace_detail: dict[str, Any] | None = None
        if row_skip_report_has_skips(row_skips):
            trace_detail = dict(detail)
        if tracer is not None:
            tracer.emit_state_patch_outcome(
                iteration=iteration, outcome="applied", gate=gate, detail=trace_detail
            )
    except StatePatchError as exc:
        loop_memory.continuity.state_patch_feedback = _build_state_patch_feedback(
            loop_memory.continuity.state_patch_feedback,
            outcome="rejected",
            iteration=iteration,
            reason_code=exc.reason_code,
            message=str(exc),
            detail=exc.detail,
            semantic_intent_kinds=intent_kinds,
            attempted_hitl_consumed_prompt_ids=attempted_consumed,
        )
        if tracer is not None:
            tracer.emit_state_patch_outcome(
                iteration=iteration,
                outcome="rejected",
                reason_code=exc.reason_code,
                message=str(exc),
                detail=exc.detail or None,
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
    action_plan: ActionPlan | None = None,
) -> None:
    if patch_present:
        record_state_patch_not_applied(
            loop_memory=loop_memory,
            tracer=tracer,
            iteration=iteration,
            execution_reason_code=execution_reason_code,
            state_patch=action_plan.state_patch if action_plan is not None else None,
            hitl_consumed_prompt_ids=tuple(action_plan.hitl_consumed_prompt_ids) if action_plan is not None else (),
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
            state_patch=action_plan.state_patch,
            hitl_consumed_prompt_ids=tuple(action_plan.hitl_consumed_prompt_ids or ()),
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
    ms, rs, row_skips, _row_skip_details, _salvage, _shape_repairs = _apply_state_patch_detailed(
        mission_state=mission_state,
        resolution_state=resolution_state,
        state_patch=state_patch,
    )
    return ms, rs, row_skips


def _apply_state_patch_detailed(
    *,
    mission_state: MissionState,
    resolution_state: ResolutionState,
    state_patch: Mapping[str, Any] | None,
) -> tuple[MissionState, ResolutionState, dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    """
    Merge a bounded generic patch into existing state.

    Returns ``(mission_state, resolution_state, row_skips, row_skip_details)`` where ``row_skips`` counts
    resolution rows the kernel dropped (non-destructive mechanical visibility for the model).

    - Unknown top-level or section keys → ``StatePatchError`` (reject whole patch).
    - Invalid ``ResolutionItem`` / ``ResolutionRelation`` rows are skipped (no repair).
    - ``items`` upsert by ``item_id`` with per-field merge (only keys present in the patch row overwrite).
    - ``relations`` append validated entries (capped).
    """
    if not state_patch:
        ms = mission_state.model_copy(update={"resolution_state": resolution_state})
        return ms, resolution_state, _empty_row_skip_report(), {}, [], []

    patch = dict(state_patch)
    patch = _normalize_state_patch_aliases(patch)
    patch, shape_repairs = repair_state_patch_container_shapes(patch)
    resolution_raw = patch.get("resolution")
    if isinstance(resolution_raw, dict):
        items_raw = resolution_raw.get("items")
        if isinstance(items_raw, dict):
            raise StatePatchError(
                "items_not_array",
                "resolution.items must be an array",
                detail={
                    "failing_path": "state_patch.resolution.items",
                    "expected_shape": "array",
                    "shape_repairs": shape_repairs,
                    "repair_hint": (
                        "Use a canonical array for resolution.items, or fix keyed-map "
                        "key/id alignment before resubmitting."
                    ),
                },
            )
        relations_raw = resolution_raw.get("relations")
        if isinstance(relations_raw, dict):
            raise StatePatchError(
                "relations_not_array",
                "resolution.relations must be an array",
                detail={
                    "failing_path": "state_patch.resolution.relations",
                    "expected_shape": "array",
                    "shape_repairs": shape_repairs,
                },
            )
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
            detail={
                "failing_path": "state_patch",
                "repair_hint": "Use only state_patch.mission, state_patch.resolution, and state_patch.stable_context at the top level.",
            },
        )

    row_skips = _empty_row_skip_report()
    row_skip_details: dict[str, Any] = {}
    salvage_events: list[dict[str, Any]] = []
    rs = resolution_state
    if "resolution" in patch:
        rs, res_skips, res_details, res_salvage = _apply_resolution_branch(rs, patch["resolution"])
        row_skips["resolution"] = res_skips
        if res_details:
            row_skip_details["resolution"] = res_details
        if res_salvage:
            salvage_events.extend(res_salvage)

    ms = mission_state
    if "mission" in patch:
        ms = _apply_mission_branch(ms, patch["mission"])

    ms = ms.model_copy(update={"resolution_state": rs})
    return ms, rs, row_skips, row_skip_details, salvage_events, shape_repairs


def _merge_covered_units_rows(
    existing: Any,
    patch_rows: list[Any],
    *,
    item_id: str = "",
) -> tuple[list[dict[str, Any]] | None, list[str] | None, list[dict[str, Any]]]:
    """Merge ``covered_units`` by ``unit_id`` with per-field overlay.

    An empty list never wipes prior units (additive-only at this level). New units
    must carry a ``unit_id`` and a ``title``; existing units accept per-field deltas.
    Returns ``(merged, None, salvage_events)`` on success.
    Returns ``(None, errors, [])`` on the first invalid row where ``errors`` is a list
    of compact, path-precise repair hints. When only optional prose fields are invalid,
    attempts a one-time salvage (omit the prose fields, retry) before reporting failure.
    """
    prior_list = existing if isinstance(existing, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    unit_field_names = ResolutionCoveredUnit.model_fields.keys()
    for row in prior_list:
        if not isinstance(row, dict):
            continue
        uid = row.get("unit_id")
        if isinstance(uid, str) and uid:
            by_id[uid] = dict(row)
            order.append(uid)

    item_anchor = f"resolution.items[{item_id}]" if item_id else "resolution.items[?]"
    salvage_events: list[dict[str, Any]] = []
    for index, row in enumerate(patch_rows):
        if not isinstance(row, dict):
            return None, [
                f"{item_anchor}.covered_units[{index}]: not an object"
            ], []
        uid_raw = row.get("unit_id")
        uid = str(uid_raw).strip() if uid_raw is not None else ""
        if not uid:
            return None, [
                f"{item_anchor}.covered_units[{index}].unit_id: required"
            ], []
        # Detect forbidden fields explicitly so the path points at the exact key.
        for key in row.keys():
            if key not in unit_field_names:
                return None, [
                    f"{item_anchor}.covered_units[{uid}].{key}: extra field forbidden"
                ], []
        base = dict(by_id.get(uid) or {})
        for key, val in row.items():
            if key == "opaque_payload" and isinstance(val, dict):
                prior_payload = base.get("opaque_payload") if isinstance(base.get("opaque_payload"), dict) else {}
                base["opaque_payload"] = {**prior_payload, **val}
            else:
                base[key] = val
        try:
            validated = ResolutionCoveredUnit.model_validate(base).model_dump(mode="json")
        except ValidationError as exc:
            prefix = f"{item_anchor}.covered_units[{uid}]"
            omit_fields, omit_errors = _collect_salvageable_errors(
                exc, salvageable=_SALVAGEABLE_UNIT_FIELDS, path_prefix=prefix
            )
            if omit_fields:
                salvaged_base = {k: v for k, v in base.items() if k not in omit_fields}
                try:
                    validated = ResolutionCoveredUnit.model_validate(salvaged_base).model_dump(mode="json")
                except ValidationError as retry_exc:
                    return None, _validation_error_summaries(retry_exc, path_prefix=prefix), []
                salvage_events.append({
                    "path": prefix,
                    "row_id": uid,
                    "omitted_invalid_fields": omit_errors,
                    "note": _SALVAGE_OMIT_NOTE,
                })
            else:
                return None, _validation_error_summaries(exc, path_prefix=prefix), []
        by_id[uid] = validated
        if uid not in order:
            order.append(uid)

    return [by_id[uid] for uid in order], None, salvage_events


def _merge_resolution_item_row(
    existing: ResolutionItem | None,
    row: dict[str, Any],
) -> tuple[ResolutionItem | None, list[str] | None, list[dict[str, Any]]]:
    """Overlay patch keys onto an existing item; absent keys keep prior values (additive updates).

    Returns ``(item, None, salvage_events)`` on success. ``salvage_events`` is non-empty
    when optional prose fields were omitted to rescue a valid compact update.
    Returns ``(None, errors, [])`` when non-salvageable fields are invalid.
    """
    base: dict[str, Any] = existing.model_dump(mode="json") if existing is not None else {}
    field_names = ResolutionItem.model_fields.keys()
    item_id = str(row.get("item_id") or (existing.item_id if existing is not None else "")).strip()
    item_anchor = f"resolution.items[{item_id}]" if item_id else "resolution.items[?]"
    salvage_events: list[dict[str, Any]] = []

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
        elif key == "covered_units" and isinstance(val, list):
            merged_units, unit_errors, unit_salvage = _merge_covered_units_rows(
                base.get("covered_units"), val, item_id=item_id
            )
            if merged_units is None:
                return None, unit_errors or [f"{item_anchor}.covered_units: invalid row shape"], []
            base["covered_units"] = merged_units
            salvage_events = list(unit_salvage)
        else:
            base[key] = val

    try:
        return ResolutionItem.model_validate(base), None, salvage_events
    except ValidationError as exc:
        omit_fields, omit_errors = _collect_salvageable_errors(
            exc, salvageable=_SALVAGEABLE_ITEM_FIELDS, path_prefix=item_anchor
        )
        if omit_fields:
            salvaged_base = {k: v for k, v in base.items() if k not in omit_fields}
            try:
                item = ResolutionItem.model_validate(salvaged_base)
            except ValidationError as retry_exc:
                return None, _validation_error_summaries(retry_exc, path_prefix=item_anchor), []
            salvage_events.append({
                "path": item_anchor,
                "row_id": item_id,
                "omitted_invalid_fields": omit_errors,
                "note": _SALVAGE_OMIT_NOTE,
            })
            return item, None, salvage_events
        return None, _validation_error_summaries(exc, path_prefix=item_anchor), []


def _apply_resolution_branch(
    rs: ResolutionState,
    raw: Any,
) -> tuple[ResolutionState, dict[str, dict[str, int]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
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
    item_details: list[dict[str, Any]] = []
    relation_details: list[dict[str, Any]] = []
    salvage_details: list[dict[str, Any]] = []

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
        for index, row in enumerate(patch_items):
            if not isinstance(row, dict):
                _bump_skips(item_skips, "not_object")
                _append_detail(
                    item_details,
                    _detail_row(
                        path=f"resolution.items[{index}]",
                        reason_code="not_object",
                    ),
                )
                continue
            item_id_raw = row.get("item_id")
            item_id = str(item_id_raw).strip() if item_id_raw is not None else ""
            if not item_id:
                _bump_skips(item_skips, "missing_item_id")
                _append_detail(
                    item_details,
                    _detail_row(
                        path=f"resolution.items[{index}].item_id",
                        reason_code="missing_item_id",
                    ),
                )
                continue
            existing = by_id.get(item_id)
            merged, validation_errors, row_salvage = _merge_resolution_item_row(existing, row)
            if merged is None:
                _bump_skips(item_skips, "validation_failed")
                _append_detail(
                    item_details,
                    _detail_row(
                        path=f"resolution.items[{item_id}]",
                        reason_code="validation_failed",
                        row_id=item_id,
                        validation_errors=validation_errors,
                    ),
                )
                continue
            if row_salvage:
                for event in row_salvage:
                    if len(salvage_details) < MAX_STATE_PATCH_DETAIL_ROWS:
                        salvage_details.append(event)
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
        for index, row in enumerate(patch_rel):
            if not isinstance(row, dict):
                _bump_skips(relation_skips, "not_object")
                _append_detail(
                    relation_details,
                    _detail_row(
                        path=f"resolution.relations[{index}]",
                        reason_code="not_object",
                    ),
                )
                continue
            try:
                relations.append(ResolutionRelation.model_validate(row))
            except ValidationError as exc:
                _bump_skips(relation_skips, "validation_failed")
                _append_detail(
                    relation_details,
                    _detail_row(
                        path=f"resolution.relations[{index}]",
                        reason_code="validation_failed",
                        validation_errors=_validation_error_summaries(exc),
                    ),
                )
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
    }, {
        "items": item_details,
        "relations": relation_details,
    }, salvage_details


def _apply_mission_branch(ms: MissionState, raw: Any) -> MissionState:
    if not isinstance(raw, dict):
        raise StatePatchError("mission_not_object", "mission must be a JSON object")

    unknown = set(raw.keys()) - ALLOWED_MISSION_KEYS
    if unknown:
        raise StatePatchError(
            "mission_unknown_keys",
            f"unknown mission keys: {sorted(unknown)}",
            detail={
                "failing_path": "state_patch.mission",
            },
        )

    updates: dict[str, Any] = {}
    opaque = dict(ms.opaque_payload)

    if "objective" in raw:
        v = raw["objective"]
        updates["objective"] = None if v is None else (str(v).strip()[:240] or None)

    if "active_mode" in raw:
        v = raw["active_mode"]
        updates["active_mode"] = None if v is None else (str(v).strip()[:64] or None)

    if "work_universe_posture" in raw:
        posture = str(raw["work_universe_posture"] or "").strip()
        if posture not in _WORK_UNIVERSE_POSTURES:
            raise StatePatchError(
                "work_universe_posture_invalid",
                (
                    "mission.work_universe_posture must be one of "
                    f"{sorted(_WORK_UNIVERSE_POSTURES)}"
                ),
                detail={"failing_path": "mission.work_universe_posture"},
            )
        updates["work_universe_posture"] = posture

    if "motion_posture" in raw:
        posture = str(raw["motion_posture"] or "").strip()
        if posture not in _MOTION_POSTURES:
            raise StatePatchError(
                "motion_posture_invalid",
                (
                    "mission.motion_posture must be one of "
                    f"{sorted(_MOTION_POSTURES)}"
                ),
                detail={"failing_path": "mission.motion_posture"},
            )
        updates["motion_posture"] = posture
        if posture != ms.motion_posture and "motion_posture_basis" not in raw:
            updates["motion_posture_basis"] = None

    if "motion_posture_basis" in raw:
        v = raw["motion_posture_basis"]
        if v is None:
            updates["motion_posture_basis"] = None
        elif isinstance(v, str):
            text = v.strip()
            updates["motion_posture_basis"] = text[:_MAX_MOTION_POSTURE_BASIS_CHARS] or None
        else:
            raise StatePatchError(
                "motion_posture_basis_invalid",
                "mission.motion_posture_basis must be a string or null",
                detail={"failing_path": "mission.motion_posture_basis"},
            )

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
            raise StatePatchError(
                f"{key}_not_object",
                f"mission.{key} must be an object, string, or null",
                detail={"failing_path": f"mission.{key}"},
            )

    if "success_conditions" in raw:
        updates["success_conditions"] = _apply_success_conditions(ms.success_conditions, raw["success_conditions"])

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
            raise StatePatchError(
                "high_signal_not_array",
                "mission.high_signal_artifact_refs must be an array or null",
                detail={"failing_path": "mission.high_signal_artifact_refs"},
            )

    if "opaque_payload" in raw:
        op = raw["opaque_payload"]
        if op is None:
            opaque = {}
        elif isinstance(op, dict):
            opaque = {**opaque, **op}
        else:
            raise StatePatchError(
                "mission_opaque_not_object",
                "mission.opaque_payload must be an object or null",
                detail={"failing_path": "mission.opaque_payload"},
            )

    updates["opaque_payload"] = opaque
    updates["updated_at_epoch_seconds"] = time.time()
    return ms.model_copy(update=updates)


def _merge_success_condition_row(
    existing: MissionSuccessCondition | None,
    row: dict[str, Any],
) -> tuple[MissionSuccessCondition | None, list[str] | None]:
    base: dict[str, Any] = existing.model_dump(mode="json") if existing is not None else {}
    field_names = MissionSuccessCondition.model_fields.keys()

    for key, val in row.items():
        if key not in field_names:
            continue
        if key == "opaque_payload" and isinstance(val, dict):
            prior = base.get("opaque_payload") if isinstance(base.get("opaque_payload"), dict) else {}
            base["opaque_payload"] = {**prior, **val}
        else:
            base[key] = val

    try:
        return MissionSuccessCondition.model_validate(base), None
    except ValidationError as exc:
        return None, _validation_error_summaries(exc)


def _apply_success_conditions(
    current: list[MissionSuccessCondition],
    raw: Any,
) -> list[MissionSuccessCondition]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise StatePatchError("success_conditions_not_array", "mission.success_conditions must be an array or null")

    by_id: dict[str, MissionSuccessCondition] = {row.condition_id: row for row in current}
    next_order: list[str] = [row.condition_id for row in current]
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise StatePatchError(
                "success_condition_not_object",
                "mission.success_conditions rows must be objects",
                detail={"failing_path": f"mission.success_conditions[{index}]"},
            )
        cond_id_raw = row.get("condition_id")
        condition_id = str(cond_id_raw).strip() if cond_id_raw is not None else ""
        if not condition_id:
            raise StatePatchError(
                "success_condition_missing_id",
                "mission.success_conditions rows require condition_id",
                detail={
                    "failing_path": f"mission.success_conditions[{index}].condition_id",
                    "repair_targets": ["repair_success_condition_row"],
                    "repair_hint": "Patch only the failing mission.success_conditions row and include condition_id, title, and status.",
                },
            )
        merged, validation_errors = _merge_success_condition_row(by_id.get(condition_id), row)
        if merged is None:
            raise StatePatchError(
                "success_condition_validation_failed",
                f"mission.success_conditions[{condition_id}] failed validation",
                detail={
                    "failing_path": f"mission.success_conditions[{condition_id}]",
                    "validation_errors": validation_errors or [],
                    "repair_targets": ["repair_success_condition_row"],
                    "repair_hint": "Patch only the failing mission.success_conditions row and include condition_id, title, and status.",
                },
            )
        by_id[condition_id] = merged
        if condition_id not in next_order:
            next_order.append(condition_id)
    return [by_id[condition_id] for condition_id in next_order]


def _merge_closure_dimension_row(
    existing: ClosureDimension | None,
    row: dict[str, Any],
) -> tuple[ClosureDimension | None, list[str] | None]:
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
        return ClosureDimension.model_validate(base), None
    except ValidationError as exc:
        return None, _validation_error_summaries(exc)


def _apply_closure_state(current: ClosureState, raw: Any) -> ClosureState:
    if raw is None:
        return ClosureState(updated_at_epoch_seconds=time.time())
    if not isinstance(raw, dict):
        raise StatePatchError(
            "closure_state_not_object",
            "mission.closure_state must be an object or null",
            detail={"failing_path": "mission.closure_state"},
        )

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
            detail={
                "failing_path": "mission.closure_state",
                "repair_targets": ["repair_closure_dimension_row"],
            },
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
            raise StatePatchError(
                f"{key}_not_boolean",
                f"mission.closure_state.{key} must be a boolean",
                detail={"failing_path": f"mission.closure_state.{key}"},
            )
        updates[key] = val

    if "dimensions" in raw:
        dims = raw["dimensions"]
        if not isinstance(dims, list):
            raise StatePatchError(
                "closure_dimensions_not_array",
                "mission.closure_state.dimensions must be an array",
                detail={"failing_path": "mission.closure_state.dimensions"},
            )
        by_id: dict[str, ClosureDimension] = {d.dimension_id: d for d in current.dimensions}
        next_order: list[str] = [d.dimension_id for d in current.dimensions]
        for index, row in enumerate(dims):
            if not isinstance(row, dict):
                raise StatePatchError(
                    "closure_dimension_not_object",
                    "mission.closure_state.dimensions rows must be objects",
                    detail={"failing_path": f"mission.closure_state.dimensions[{index}]"},
                )
            dim_id_raw = row.get("dimension_id")
            dim_id = str(dim_id_raw).strip() if dim_id_raw is not None else ""
            if not dim_id:
                raise StatePatchError(
                    "closure_dimension_missing_id",
                    "mission.closure_state.dimensions rows require dimension_id",
                    detail={
                        "failing_path": f"mission.closure_state.dimensions[{index}].dimension_id",
                        "repair_targets": ["repair_closure_dimension_row"],
                        "repair_hint": "Patch only the failing mission.closure_state.dimensions row and include dimension_id, title, and status.",
                    },
                )
            merged, validation_errors = _merge_closure_dimension_row(by_id.get(dim_id), row)
            if merged is None:
                raise StatePatchError(
                    "closure_dimension_validation_failed",
                    f"mission.closure_state.dimensions[{dim_id}] failed validation",
                    detail={
                        "failing_path": f"mission.closure_state.dimensions[{dim_id}]",
                        "validation_errors": validation_errors or [],
                        "repair_targets": ["repair_closure_dimension_row"],
                        "repair_hint": "Patch only the failing mission.closure_state.dimensions row and include dimension_id, title, and status.",
                    },
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
                detail={"failing_path": "mission.closure_state.opaque_payload"},
            )

    updates["updated_at_epoch_seconds"] = time.time()
    return current.model_copy(update=updates)
