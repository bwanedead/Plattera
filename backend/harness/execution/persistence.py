"""Generic persistence for execution sessions and run artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ActionDispatchResult,
    ExecutionRefusal,
    ExecutionStepRequest,
    SessionExecutionRecord,
)
from .run_artifact import RunArtifact
from .session import ExecutionSession, new_execution_session
from .wire_codec import action_dispatch_result_from_wire, action_dispatch_result_to_wire


class JsonFileExecutionPersistence:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save_run_artifact(self, run_artifact: RunArtifact) -> str:
        path = self._root / "runs" / f"{run_artifact.run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run_artifact.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return str(path)

    def load_run_artifact(self, run_artifact_ref: str) -> RunArtifact:
        payload = json.loads(Path(run_artifact_ref).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("run_artifact_payload_not_object")
        return RunArtifact.from_dict(payload)

    def save_session(self, session: ExecutionSession) -> str:
        path = self._root / "sessions" / f"{session.session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_session_payload(session), indent=2, sort_keys=True), encoding="utf-8")
        return str(path)

    def load_session(self, session_ref: str) -> ExecutionSession:
        payload = json.loads(Path(session_ref).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("session_payload_not_object")
        run_artifact_payload = payload.get("run_artifact")
        run_artifact = RunArtifact.from_dict(run_artifact_payload) if isinstance(run_artifact_payload, dict) else None
        session = new_execution_session(
            session_id=str(payload.get("session_id") or "unknown_session"),
            run_id=str(payload.get("run_id") or "unknown_run"),
            run_artifact=run_artifact,
        )
        session.records = [
            _record_from_payload(row)
            for row in list(payload.get("records") or [])
            if isinstance(row, Mapping)
        ]
        session.completed_idempotency_keys = {
            str(item) for item in list(payload.get("completed_idempotency_keys") or []) if str(item).strip()
        }
        for record in session.records:
            key = str(record.request.idempotency_key or "").strip()
            if key:
                session.completed_idempotency_keys.add(key)
                session.last_result_by_key[key] = record.result
        return session


def _session_payload(session: ExecutionSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "run_id": session.run_id,
        "completed_idempotency_keys": sorted(session.completed_idempotency_keys),
        "run_artifact": session.run_artifact.to_dict(),
        "records": [_record_to_payload(record) for record in session.records],
    }


def _record_to_payload(record: SessionExecutionRecord) -> dict[str, Any]:
    return {
        "session_id": record.session_id,
        "run_id": record.run_id,
        "request": asdict(record.request),
        "result": _result_to_payload(record.result),
    }


def _result_to_payload(result: ActionDispatchResult) -> dict[str, Any]:
    # Canonical view/omission encoding via the shared wire helper; preserve
    # image_evidence write behavior that the wire codec intentionally omits.
    payload = action_dispatch_result_to_wire(result)
    payload["image_evidence"] = [dict(item) for item in result.image_evidence]
    return payload


def _record_from_payload(payload: Mapping[str, Any]) -> SessionExecutionRecord:
    request_payload = payload.get("request") if isinstance(payload.get("request"), Mapping) else {}
    result_payload = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    return SessionExecutionRecord(
        session_id=str(payload.get("session_id") or "unknown_session"),
        run_id=str(payload.get("run_id") or "unknown_run"),
        request=_request_from_payload(request_payload),
        result=_result_from_payload(result_payload),
    )


def _request_from_payload(payload: Mapping[str, Any]) -> ExecutionStepRequest:
    return ExecutionStepRequest(
        session_id=str(payload.get("session_id") or "unknown_session"),
        action_id=str(payload.get("action_id") or ""),
        inputs=dict(payload.get("inputs") or {}),
        idempotency_key=str(payload.get("idempotency_key") or ""),
        run_id=str(payload.get("run_id")) if payload.get("run_id") is not None else None,
    )


def _result_from_payload(payload: Mapping[str, Any]) -> ActionDispatchResult:
    # Prefer the canonical wire codec so view/omission share one interpretation.
    # image_evidence remains intentionally unrestored on load (pre-existing behavior).
    parsed = action_dispatch_result_from_wire(payload)
    if parsed is not None:
        return parsed
    refusal_payload = payload.get("refusal")
    refusal = _refusal_from_payload(refusal_payload) if isinstance(refusal_payload, Mapping) else None
    outputs = payload.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    return ActionDispatchResult(
        action_id=str(payload.get("action_id") or ""),
        executed=bool(payload.get("executed", False)),
        reason_codes=tuple(str(item) for item in list(payload.get("reason_codes") or []) if str(item).strip()),
        outputs=dict(outputs),
        refusal=refusal,
        artifact_refs=tuple(str(item) for item in list(payload.get("artifact_refs") or []) if str(item).strip()),
        idempotency_key=str(payload.get("idempotency_key") or ""),
    )


def _refusal_from_payload(payload: Mapping[str, Any]) -> ExecutionRefusal:
    return ExecutionRefusal(
        reason_code=str(payload.get("reason_code") or "refused"),
        retryable=bool(payload.get("retryable", False)),
        blocked_by_budget=bool(payload.get("blocked_by_budget", False)),
        blocked_by_invariant=bool(payload.get("blocked_by_invariant", False)),
        missing_inputs=tuple(str(item) for item in list(payload.get("missing_inputs") or []) if str(item).strip()),
    )
