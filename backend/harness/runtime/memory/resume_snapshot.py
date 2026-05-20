"""Mechanical kernel resume snapshot (``kernel_resume.v1``): loop memory + execution session wire.

No semantic inference: validate or reject; restored fields are carried state only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ...execution.executor import ExecutionExecutor
from ...execution.session import ExecutionSessionManager
from ...execution.session_wire import execution_session_from_wire, execution_session_to_wire
from ...mission_state import MissionState, ResolutionState
from ..hitl.transport import HitlTransportPosture
from ..hitl.exchange_ledger import validate_stored_ledger_entry
from ..user_messages.ledger import validate_stored_user_message
from ..orchestration.action_batch import validate_stored_action_batch_result as validate_stored_action_sequence_result
from ..orchestration.hydrate_next import validate_stored_hydrate_next_record
from .continuity import OrchestrationContinuity
from .continuity_journal import (
    clamp_compacted_summary_text,
    clamp_operator_progress_message,
    validate_stored_journal_entry,
    validate_stored_step_record,
)
from .loop_state import LoopMemoryState
from .telemetry import PromptContactTelemetry
from .turn_recovery import TurnRecoveryState

KERNEL_RESUME_SNAPSHOT_VERSION = "kernel_resume.v1"

_VALID_HITL: frozenset[str] = frozenset(
    {"no_prompt", "async_prompts_pending", "waiting", "answered_unintegrated", "consumed"}
)


def build_kernel_resume_snapshot(
    *,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    next_iteration: int,
) -> dict[str, Any]:
    """Produce a JSON-serializable snapshot for persistence (caller writes bytes)."""
    sid = str(session_id or "").strip()
    session = session_manager.sessions.get(sid) if sid else None
    exec_wire: dict[str, Any] | None
    if session is None:
        exec_wire = None
    else:
        exec_wire = execution_session_to_wire(session)

    return {
        "schema_version": KERNEL_RESUME_SNAPSHOT_VERSION,
        "next_iteration": max(1, int(next_iteration)),
        "continuity": {
            "latest_refs": dict(loop_memory.continuity.latest_refs),
            "mission_state": loop_memory.continuity.mission_state.model_dump(mode="json"),
            "resolution_state": loop_memory.continuity.resolution_state.model_dump(mode="json"),
            "active_item_id": loop_memory.continuity.active_item_id,
            "state_patch_feedback": dict(loop_memory.continuity.state_patch_feedback),
            "continuity_journal_entries": list(loop_memory.continuity.continuity_journal_entries),
            "compacted_continuity_summary": loop_memory.continuity.compacted_continuity_summary,
            "operator_progress_message": loop_memory.continuity.operator_progress_message,
            "kernel_step_records": list(loop_memory.continuity.kernel_step_records),
            "kernel_step_result_records": list(loop_memory.continuity.kernel_step_result_records),
            "kernel_compaction_covered_through_turn_index": int(
                loop_memory.continuity.kernel_compaction_covered_through_turn_index
            ),
            "earned_before_local_evidence_debt": dict(
                loop_memory.continuity.earned_before_local_evidence_debt
            ),
            "posthoc_recheck_needed_debt": dict(
                loop_memory.continuity.posthoc_recheck_needed_debt
            ),
            "hitl_exchange_ledger": list(loop_memory.continuity.hitl_exchange_ledger),
            "hitl_consumed_unknown_prompt_count": int(
                loop_memory.continuity.hitl_consumed_unknown_prompt_count
            ),
            "user_message_ledger": list(loop_memory.continuity.user_message_ledger),
            "user_message_consumed_unknown_count": int(
                loop_memory.continuity.user_message_consumed_unknown_count
            ),
            "pending_agent_hydration": (
                dict(loop_memory.continuity.pending_agent_hydration)
                if loop_memory.continuity.pending_agent_hydration is not None
                else None
            ),
            "recent_action_sequence_result": (
                dict(loop_memory.continuity.recent_action_sequence_result)
                if loop_memory.continuity.recent_action_sequence_result is not None
                else None
            ),
        },
        "hitl": {
            "hitl_state": loop_memory.hitl.hitl_state,
            "blocking_prompt_id": loop_memory.hitl.blocking_prompt_id,
            "pending_hitl_requests": list(loop_memory.hitl.pending_hitl_requests),
            "answered_hitl_responses": list(loop_memory.hitl.answered_hitl_responses),
            "pending_feedback_prompt_id": loop_memory.hitl.pending_feedback_prompt_id,
            "pending_feedback_response": loop_memory.hitl.pending_feedback_response,
        },
        "telemetry": {
            "llm_contact_count": int(loop_memory.telemetry.llm_contact_count),
            "prompt_event_count": int(loop_memory.telemetry.prompt_event_count),
            "last_prompt_event_id": loop_memory.telemetry.last_prompt_event_id,
            "last_prompt_event_surface": loop_memory.telemetry.last_prompt_event_surface,
        },
        "turn_recovery": loop_memory.turn_recovery.to_wire(),
        "execution_session": exec_wire,
    }


def parse_kernel_resume_snapshot(payload: Mapping[str, Any]) -> tuple[LoopMemoryState, int, str | None]:
    """Validate snapshot; return ``(loop_memory, next_iteration, error_reason_code)``.

    On failure ``error_reason_code`` is set and ``loop_memory`` / ``next_iteration`` are unusable
    placeholders — callers must branch on the error code (do not partially trust outputs).
    """
    empty = LoopMemoryState()
    if not isinstance(payload, Mapping):
        return empty, 1, "resume_snapshot_not_object"

    ver = str(payload.get("schema_version") or "").strip()
    if ver != KERNEL_RESUME_SNAPSHOT_VERSION:
        return empty, 1, "resume_snapshot_schema_mismatch"

    try:
        next_it = int(payload.get("next_iteration", 1))
    except (TypeError, ValueError):
        return empty, 1, "resume_snapshot_next_iteration_invalid"
    if next_it < 1:
        return empty, 1, "resume_snapshot_next_iteration_invalid"

    cont = payload.get("continuity")
    if not isinstance(cont, Mapping):
        return empty, 1, "resume_snapshot_continuity_invalid"

    try:
        ms = MissionState.model_validate(cont.get("mission_state"))
        rs = ResolutionState.model_validate(cont.get("resolution_state"))
    except ValidationError:
        return empty, 1, "resume_snapshot_mission_resolution_invalid"

    ms = ms.model_copy(update={"resolution_state": rs})

    if "latest_refs" in cont:
        lr_raw = cont.get("latest_refs")
        if not isinstance(lr_raw, Mapping):
            return empty, 1, "resume_snapshot_continuity_latest_refs_invalid"
        latest_refs_out: dict[str, Any] = dict(lr_raw)
    else:
        latest_refs_out = {}

    if "state_patch_feedback" in cont:
        sp_raw = cont.get("state_patch_feedback")
        if not isinstance(sp_raw, Mapping):
            return empty, 1, "resume_snapshot_continuity_state_patch_feedback_invalid"
        state_patch_feedback_out = dict(sp_raw)
    else:
        state_patch_feedback_out = {}

    active_item_id, ai_err = _strict_optional_resume_str_field(
        cont,
        "active_item_id",
        limit=128,
        error_code="resume_snapshot_continuity_active_item_id_invalid",
    )
    if ai_err:
        return empty, 1, ai_err

    journal_entries_out: list[dict[str, Any]] = []
    if "continuity_journal_entries" in cont:
        jraw = cont.get("continuity_journal_entries")
        if jraw is not None:
            if not isinstance(jraw, list):
                return empty, 1, "resume_snapshot_continuity_journal_entries_invalid"
            for row in jraw:
                norm = validate_stored_journal_entry(row)
                if norm is None:
                    return empty, 1, "resume_snapshot_continuity_journal_entries_invalid"
                journal_entries_out.append(norm)

    compacted_summary: str | None = None
    if "compacted_continuity_summary" in cont:
        cs = cont.get("compacted_continuity_summary")
        if cs is not None:
            if not isinstance(cs, str):
                return empty, 1, "resume_snapshot_compacted_continuity_summary_invalid"
            compacted_summary = clamp_compacted_summary_text(cs)

    operator_progress: str | None = None
    if "operator_progress_message" in cont:
        op = cont.get("operator_progress_message")
        if op is not None:
            if not isinstance(op, str):
                return empty, 1, "resume_snapshot_operator_progress_message_invalid"
            operator_progress = clamp_operator_progress_message(op)

    step_records_out: list[dict[str, Any]] = []
    if "kernel_step_records" in cont:
        sraw = cont.get("kernel_step_records")
        if sraw is not None:
            if not isinstance(sraw, list):
                return empty, 1, "resume_snapshot_kernel_step_records_invalid"
            for row in sraw:
                norm = validate_stored_step_record(row)
                if norm is None:
                    return empty, 1, "resume_snapshot_kernel_step_records_invalid"
                step_records_out.append(norm)

    step_result_records_out: list[dict[str, Any]] = []
    if "kernel_step_result_records" in cont:
        rraw = cont.get("kernel_step_result_records")
        if rraw is not None:
            if not isinstance(rraw, list):
                return empty, 1, "resume_snapshot_kernel_step_result_records_invalid"
            for row in rraw:
                norm = validate_stored_step_record(row)
                if norm is None:
                    return empty, 1, "resume_snapshot_kernel_step_result_records_invalid"
                step_result_records_out.append(norm)

    covered_through = 0
    if "kernel_compaction_covered_through_turn_index" in cont:
        cv = cont.get("kernel_compaction_covered_through_turn_index")
        if cv is not None:
            try:
                covered_through = int(cv)
            except (TypeError, ValueError):
                return empty, 1, "resume_snapshot_kernel_compaction_covered_through_invalid"
            if covered_through < 0:
                return empty, 1, "resume_snapshot_kernel_compaction_covered_through_invalid"

    earned_debt_out: dict[str, int] = {}
    if "earned_before_local_evidence_debt" in cont:
        ed_raw = cont.get("earned_before_local_evidence_debt")
        if ed_raw is not None:
            if not isinstance(ed_raw, Mapping):
                return empty, 1, "resume_snapshot_earned_before_local_evidence_debt_invalid"
            for k, v in ed_raw.items():
                if not isinstance(k, str):
                    return empty, 1, "resume_snapshot_earned_before_local_evidence_debt_invalid"
                try:
                    earned_debt_out[k] = int(v)
                except (TypeError, ValueError):
                    return empty, 1, "resume_snapshot_earned_before_local_evidence_debt_invalid"

    posthoc_debt_out: dict[str, int] = {}
    if "posthoc_recheck_needed_debt" in cont:
        ph_raw = cont.get("posthoc_recheck_needed_debt")
        if ph_raw is not None:
            if not isinstance(ph_raw, Mapping):
                return empty, 1, "resume_snapshot_posthoc_recheck_needed_debt_invalid"
            for k, v in ph_raw.items():
                if not isinstance(k, str):
                    return empty, 1, "resume_snapshot_posthoc_recheck_needed_debt_invalid"
                try:
                    posthoc_debt_out[k] = int(v)
                except (TypeError, ValueError):
                    return empty, 1, "resume_snapshot_posthoc_recheck_needed_debt_invalid"

    hitl_exchange_ledger_out: list[dict[str, Any]] = []
    if "hitl_exchange_ledger" in cont:
        led_raw = cont.get("hitl_exchange_ledger")
        if led_raw is not None:
            if not isinstance(led_raw, list):
                return empty, 1, "resume_snapshot_hitl_exchange_ledger_invalid"
            for row in led_raw:
                norm = validate_stored_ledger_entry(row)
                if norm is None:
                    return empty, 1, "resume_snapshot_hitl_exchange_ledger_invalid"
                hitl_exchange_ledger_out.append(norm)

    hitl_consumed_unknown_count = 0
    if "hitl_consumed_unknown_prompt_count" in cont:
        cu_raw = cont.get("hitl_consumed_unknown_prompt_count")
        if cu_raw is not None:
            try:
                hitl_consumed_unknown_count = int(cu_raw)
            except (TypeError, ValueError):
                return empty, 1, "resume_snapshot_hitl_consumed_unknown_prompt_count_invalid"
            if hitl_consumed_unknown_count < 0:
                return empty, 1, "resume_snapshot_hitl_consumed_unknown_prompt_count_invalid"

    user_message_ledger_out: list[dict[str, Any]] = []
    if "user_message_ledger" in cont:
        umled_raw = cont.get("user_message_ledger")
        if umled_raw is not None:
            if not isinstance(umled_raw, list):
                return empty, 1, "resume_snapshot_user_message_ledger_invalid"
            for row in umled_raw:
                norm = validate_stored_user_message(row)
                if norm is None:
                    return empty, 1, "resume_snapshot_user_message_ledger_invalid"
                user_message_ledger_out.append(norm)

    user_message_consumed_unknown_count = 0
    if "user_message_consumed_unknown_count" in cont:
        ucu_raw = cont.get("user_message_consumed_unknown_count")
        if ucu_raw is not None:
            try:
                user_message_consumed_unknown_count = int(ucu_raw)
            except (TypeError, ValueError):
                return empty, 1, "resume_snapshot_user_message_consumed_unknown_count_invalid"
            if user_message_consumed_unknown_count < 0:
                return empty, 1, "resume_snapshot_user_message_consumed_unknown_count_invalid"

    pending_agent_hydration_out: dict[str, Any] | None = None
    if "pending_agent_hydration" in cont:
        pah_raw = cont.get("pending_agent_hydration")
        if pah_raw is not None:
            if not isinstance(pah_raw, Mapping):
                return empty, 1, "resume_snapshot_pending_agent_hydration_invalid"
            normalized_pah = validate_stored_hydrate_next_record(pah_raw)
            if normalized_pah is None:
                return empty, 1, "resume_snapshot_pending_agent_hydration_invalid"
            pending_agent_hydration_out = normalized_pah

    recent_action_sequence_result_out: dict[str, Any] | None = None
    ras_raw = cont.get("recent_action_sequence_result")
    if ras_raw is None:
        ras_raw = cont.get("recent_action_batch_result")
    if ras_raw is not None:
        if not isinstance(ras_raw, Mapping):
            return empty, 1, "resume_snapshot_recent_action_sequence_result_invalid"
        normalized_ras = validate_stored_action_sequence_result(ras_raw)
        if normalized_ras is None:
            return empty, 1, "resume_snapshot_recent_action_sequence_result_invalid"
        recent_action_sequence_result_out = normalized_ras

    continuity = OrchestrationContinuity(
        latest_refs=latest_refs_out,
        mission_state=ms,
        resolution_state=rs,
        active_item_id=active_item_id,
        state_patch_feedback=state_patch_feedback_out,
        continuity_journal_entries=journal_entries_out,
        compacted_continuity_summary=compacted_summary,
        operator_progress_message=operator_progress,
        kernel_step_records=step_records_out,
        kernel_step_result_records=step_result_records_out,
        kernel_compaction_covered_through_turn_index=covered_through,
        earned_before_local_evidence_debt=earned_debt_out,
        posthoc_recheck_needed_debt=posthoc_debt_out,
        hitl_exchange_ledger=hitl_exchange_ledger_out,
        hitl_consumed_unknown_prompt_count=hitl_consumed_unknown_count,
        user_message_ledger=user_message_ledger_out,
        user_message_consumed_unknown_count=user_message_consumed_unknown_count,
        pending_agent_hydration=pending_agent_hydration_out,
        recent_action_sequence_result=recent_action_sequence_result_out,
    )

    hitl_raw = payload.get("hitl")
    if not isinstance(hitl_raw, Mapping):
        return empty, 1, "resume_snapshot_hitl_invalid"
    hs = str(hitl_raw.get("hitl_state") or "no_prompt").strip()
    if hs not in _VALID_HITL:
        return empty, 1, "resume_snapshot_hitl_state_invalid"

    if "pending_feedback_response" in hitl_raw:
        pfr = hitl_raw.get("pending_feedback_response")
        if pfr is not None and not isinstance(pfr, Mapping):
            return empty, 1, "resume_snapshot_hitl_pending_feedback_response_invalid"
        pending_response: dict[str, Any] | None = dict(pfr) if isinstance(pfr, Mapping) else None
    else:
        pending_response = None

    prompt_id, pid_err = _strict_optional_resume_str_field(
        hitl_raw,
        "pending_feedback_prompt_id",
        limit=256,
        error_code="resume_snapshot_hitl_pending_feedback_prompt_id_invalid",
    )
    if pid_err:
        return empty, 1, pid_err

    blocking_id, bid_err = _strict_optional_resume_str_field(
        hitl_raw,
        "blocking_prompt_id",
        limit=256,
        error_code="resume_snapshot_hitl_blocking_prompt_id_invalid",
    )
    if bid_err:
        return empty, 1, bid_err

    pending_req_out: list[dict[str, Any]] = []
    if "pending_hitl_requests" in hitl_raw:
        pr = hitl_raw.get("pending_hitl_requests")
        if pr is not None:
            if not isinstance(pr, list):
                return empty, 1, "resume_snapshot_hitl_pending_requests_invalid"
            for row in pr:
                if not isinstance(row, dict):
                    return empty, 1, "resume_snapshot_hitl_pending_requests_invalid"
                rpid = str(row.get("prompt_id") or "").strip()
                msg = row.get("message")
                if not rpid or not isinstance(msg, str) or not str(msg).strip():
                    return empty, 1, "resume_snapshot_hitl_pending_requests_invalid"
                pending_req_out.append(dict(row))

    answered_out: list[dict[str, Any]] = []
    if "answered_hitl_responses" in hitl_raw:
        ar = hitl_raw.get("answered_hitl_responses")
        if ar is not None:
            if not isinstance(ar, list):
                return empty, 1, "resume_snapshot_hitl_answered_responses_invalid"
            for row in ar:
                if not isinstance(row, dict):
                    return empty, 1, "resume_snapshot_hitl_answered_responses_invalid"
                apid = str(row.get("prompt_id") or "").strip()
                fb = row.get("feedback")
                if not apid or not isinstance(fb, dict):
                    return empty, 1, "resume_snapshot_hitl_answered_responses_invalid"
                answered_out.append({"prompt_id": apid, "feedback": dict(fb)})

    if not answered_out and pending_response is not None and prompt_id:
        answered_out.append({"prompt_id": str(prompt_id), "feedback": dict(pending_response)})

    blk_out: str | None = blocking_id if blocking_id else None
    if blk_out is None and hs == "waiting" and prompt_id:
        blk_out = str(prompt_id).strip() or None

    hitl = HitlTransportPosture(
        hitl_state=hs,  # type: ignore[arg-type]
        blocking_prompt_id=blk_out,
        pending_hitl_requests=pending_req_out,
        answered_hitl_responses=answered_out,
        pending_feedback_prompt_id=prompt_id,
        pending_feedback_response=pending_response,
    )

    tel_raw = payload.get("telemetry")
    if not isinstance(tel_raw, Mapping):
        return empty, 1, "resume_snapshot_telemetry_invalid"

    last_peid, peid_err = _strict_optional_resume_str_field(
        tel_raw,
        "last_prompt_event_id",
        limit=256,
        error_code="resume_snapshot_telemetry_last_prompt_event_id_invalid",
    )
    if peid_err:
        return empty, 1, peid_err
    last_psurf, psurf_err = _strict_optional_resume_str_field(
        tel_raw,
        "last_prompt_event_surface",
        limit=256,
        error_code="resume_snapshot_telemetry_last_prompt_event_surface_invalid",
    )
    if psurf_err:
        return empty, 1, psurf_err

    try:
        telemetry = PromptContactTelemetry(
            llm_contact_count=int(tel_raw.get("llm_contact_count", 0)),
            prompt_event_count=int(tel_raw.get("prompt_event_count", 0)),
            last_prompt_event_id=last_peid,
            last_prompt_event_surface=last_psurf,
        )
    except (TypeError, ValueError):
        return empty, 1, "resume_snapshot_telemetry_invalid"

    memory = LoopMemoryState(
        continuity=continuity,
        telemetry=telemetry,
        hitl=hitl,
        turn_recovery=TurnRecoveryState.from_wire(payload.get("turn_recovery")),
        iterations=0,
    )
    return memory, next_it, None


def merge_launch_latest_refs_with_resume_continuity(
    launch_latest_refs: Mapping[str, Any],
    *,
    initial_loop_memory: LoopMemoryState | None,
) -> dict[str, Any]:
    """For memory-only resume: seed execution ``initial_latest_refs`` from restored continuity, then launch (host) refs.

    Launch keys win on collision so explicit context can still override.
    """
    ctx = dict(launch_latest_refs) if isinstance(launch_latest_refs, Mapping) else {}
    if initial_loop_memory is None:
        return ctx
    return {**dict(initial_loop_memory.continuity.latest_refs), **ctx}


def hydrate_session_manager_from_resume_payload(
    payload: Mapping[str, Any],
    *,
    executor: ExecutionExecutor,
) -> tuple[ExecutionSessionManager | None, str | None]:
    """If ``execution_session`` is present, return a manager sharing ``executor`` with that session loaded.

    When ``execution_session`` is JSON null / absent, returns ``(None, None)`` — caller uses ``start_session``.
    """
    raw = payload.get("execution_session")
    if raw is None:
        return None, None
    if not isinstance(raw, Mapping):
        return None, "resume_snapshot_execution_session_invalid"
    session, err = execution_session_from_wire(raw)
    if err is not None or session is None:
        return None, err or "resume_snapshot_execution_session_invalid"
    mgr = ExecutionSessionManager(executor=executor)
    mgr.hydrate_session(session)
    return mgr, None


def load_kernel_resume_snapshot_from_path(path: Path | str) -> tuple[dict[str, Any] | None, str | None]:
    """Read JSON file; return ``(parsed_dict, error_reason_code)``."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None, "resume_snapshot_path_unreadable"
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None, "resume_snapshot_json_invalid"
    if not isinstance(doc, dict):
        return None, "resume_snapshot_root_not_object"
    return doc, None


def _strict_optional_resume_str_field(
    container: Mapping[str, Any],
    key: str,
    *,
    limit: int,
    error_code: str,
) -> tuple[str | None, str | None]:
    """If ``key`` is absent or null, ``(None, None)``. If present, must be a JSON string (not coerced)."""
    if key not in container:
        return None, None
    val = container.get(key)
    if val is None:
        return None, None
    if not isinstance(val, str):
        return None, error_code
    stripped = val.strip()
    if not stripped:
        return None, None
    return stripped[:limit], None
