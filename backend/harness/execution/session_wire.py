"""Serialize / deserialize ``ExecutionSession`` for kernel resume (mechanical only)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import ActionDispatchResult, SessionExecutionRecord
from .run_artifact import RunArtifact
from .session import ExecutionSession
from .wire_codec import (
    action_dispatch_result_from_wire,
    action_dispatch_result_to_wire,
    execution_step_request_from_wire,
    execution_step_request_to_wire,
)


def session_execution_record_to_wire(rec: SessionExecutionRecord) -> dict[str, Any]:
    return {
        "session_id": rec.session_id,
        "run_id": rec.run_id,
        "request": execution_step_request_to_wire(rec.request),
        "result": action_dispatch_result_to_wire(rec.result),
    }


def session_execution_record_from_wire(raw: object) -> SessionExecutionRecord | None:
    if not isinstance(raw, Mapping):
        return None
    req = execution_step_request_from_wire(raw.get("request"))
    res = action_dispatch_result_from_wire(raw.get("result"))
    if req is None or res is None:
        return None
    sid = str(raw.get("session_id") or "").strip()
    rid = str(raw.get("run_id") or "").strip()
    if not sid or not rid:
        return None
    return SessionExecutionRecord(session_id=sid, run_id=rid, request=req, result=res)


def execution_session_to_wire(session: ExecutionSession) -> dict[str, Any]:
    keys = sorted(str(k) for k in session.completed_idempotency_keys if str(k).strip())
    last_by_key: dict[str, dict[str, Any]] = {}
    for key, res in session.last_result_by_key.items():
        k = str(key or "").strip()
        if k:
            last_by_key[k] = action_dispatch_result_to_wire(res)
    records = [session_execution_record_to_wire(r) for r in session.records]
    return {
        "session_id": session.session_id,
        "run_id": session.run_id,
        "run_artifact": session.run_artifact.to_dict(),
        "completed_idempotency_keys": keys,
        "last_dispatch_by_key": last_by_key,
        "session_records": records,
    }


def execution_session_from_wire(raw: object) -> tuple[ExecutionSession | None, str | None]:
    if not isinstance(raw, Mapping):
        return None, "execution_session_not_object"
    sid = str(raw.get("session_id") or "").strip()
    rid = str(raw.get("run_id") or "").strip()
    if not sid or not rid:
        return None, "execution_session_missing_ids"
    art_raw = raw.get("run_artifact")
    if not isinstance(art_raw, Mapping):
        return None, "execution_session_run_artifact_invalid"
    try:
        artifact = RunArtifact.from_dict(art_raw)
    except Exception:
        return None, "execution_session_run_artifact_parse_failed"

    keys_in: object = raw.get("completed_idempotency_keys")
    if not isinstance(keys_in, list):
        return None, "execution_session_completed_keys_not_array"
    completed: set[str] = {str(k).strip() for k in keys_in if str(k).strip()}

    last_raw = raw.get("last_dispatch_by_key")
    if not isinstance(last_raw, Mapping):
        return None, "execution_session_last_dispatch_not_object"
    last_by_key: dict[str, ActionDispatchResult] = {}
    for key, val in last_raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        parsed = action_dispatch_result_from_wire(val)
        if parsed is None:
            return None, "execution_session_last_dispatch_entry_invalid"
        last_by_key[k] = parsed

    recs_raw = raw.get("session_records")
    if not isinstance(recs_raw, list):
        return None, "execution_session_records_not_array"
    records: list[SessionExecutionRecord] = []
    for row in recs_raw:
        rec = session_execution_record_from_wire(row)
        if rec is None:
            return None, "execution_session_record_invalid"
        records.append(rec)

    session = ExecutionSession(session_id=sid, run_id=rid, run_artifact=artifact)
    session.completed_idempotency_keys = completed
    session.last_result_by_key = last_by_key
    session.records = records
    return session, None
