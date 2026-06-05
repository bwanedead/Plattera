"""Harness-native one-step session execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any
from uuid import uuid4

from .contracts import (
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionPersistence,
    ExecutionRefusal,
    ExecutionSessionStartRequest,
    ExecutionSessionStartResult,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from .executor import ExecutionExecutor
from .run_artifact import ActionHistoryEntry, RunArtifact


@dataclass
class ExecutionSession:
    session_id: str
    run_id: str
    run_artifact: RunArtifact = field(default_factory=lambda: RunArtifact(run_id="unknown_run", session_id="unknown_session"))
    completed_idempotency_keys: set[str] = field(default_factory=set)
    records: list[SessionExecutionRecord] = field(default_factory=list)
    last_result_by_key: dict[str, ActionDispatchResult] = field(default_factory=dict)

    def is_duplicate(self, idempotency_key: str) -> bool:
        key = str(idempotency_key or "").strip()
        return bool(key and key in self.completed_idempotency_keys)

    def record(self, *, request: ExecutionStepRequest, result: ActionDispatchResult) -> SessionExecutionRecord:
        key = str(request.idempotency_key or "").strip()
        if key:
            self.completed_idempotency_keys.add(key)
            self.last_result_by_key[key] = result
        record = SessionExecutionRecord(
            session_id=self.session_id,
            run_id=self.run_id,
            request=request,
            result=result,
        )
        self.records.append(record)
        entry = ActionHistoryEntry(
            sequence_index=len(self.run_artifact.action_history) + 1,
            action_id=result.action_id,
            idempotency_key=key,
            executed=bool(result.executed),
            reason_codes=result.reason_codes,
            artifact_refs=result.artifact_refs,
            timestamp_epoch_seconds=time(),
            refusal=result.refusal,
        )
        self.run_artifact.append_history_entry(entry)
        if result.artifact_refs:
            self.run_artifact.merge_latest_refs({ref: ref for ref in result.artifact_refs})
        if not result.executed and result.refusal is not None:
            self.run_artifact.status = "refused"
            self.run_artifact.reason_code = result.refusal.reason_code
        return record


@dataclass
class ExecutionSessionManager:
    executor: ExecutionExecutor = field(default_factory=ExecutionExecutor)
    persistence: ExecutionPersistence | None = None
    sessions: dict[str, ExecutionSession] = field(default_factory=dict)

    def hydrate_session(self, session: ExecutionSession) -> None:
        """Register a fully-built session (e.g. from a resume snapshot). Does not create a new ``RunArtifact``."""
        sid = str(session.session_id or "").strip()
        if not sid:
            raise ValueError("execution_session_id_required")
        self.sessions[sid] = session
        self._persist(session)

    def start_session(self, request: ExecutionSessionStartRequest) -> ExecutionSessionStartResult:
        session_id = str(request.session_id or "").strip() or f"exec-{uuid4().hex}"
        run_id = str(request.run_id or "").strip() or session_id
        artifact = RunArtifact(run_id=run_id, session_id=session_id)
        artifact.merge_latest_refs(request.initial_latest_refs)
        session = ExecutionSession(session_id=session_id, run_id=run_id, run_artifact=artifact)
        self.sessions[session_id] = session
        run_artifact_ref = None
        if self.persistence is not None:
            run_artifact_ref = self.persistence.save_run_artifact(session.run_artifact)
            self.persistence.save_session(session)
        return ExecutionSessionStartResult(
            session_id=session_id,
            run_id=run_id,
            run_artifact_ref=run_artifact_ref,
            dashboard=_build_dashboard(session),
        )

    def preflight_step(
        self,
        request: ExecutionStepRequest,
    ) -> tuple[ExecutionStepRequest | None, ExecutionStepResult | None]:
        """Normalize and apply session/idempotency checks without executing the handler."""

        session = self._get_session(str(request.session_id or "").strip())
        if session is None:
            refusal = ExecutionRefusal(reason_code="session_not_found", retryable=False)
            return None, ExecutionStepResult(
                session_id=str(request.session_id or ""),
                idempotency_key=str(request.idempotency_key or ""),
                execution_state=ExecutionState.REFUSED,
                dashboard=ExecutionDashboard(last_refusal=refusal),
                refusal=refusal,
            )

        normalized_request = _normalize_step_request(request, session=session)
        deduped = _dedupe_step_if_needed(session, normalized_request)
        if deduped is not None:
            return None, deduped
        return normalized_request, None

    def record_dispatch_result(
        self,
        request: ExecutionStepRequest,
        dispatch_result: ActionDispatchResult,
    ) -> ExecutionStepResult:
        """Persist a pre-executed dispatch result using the same semantics as ``step``."""

        session = self._get_session(str(request.session_id or "").strip())
        if session is None:
            refusal = ExecutionRefusal(reason_code="session_not_found", retryable=False)
            return ExecutionStepResult(
                session_id=str(request.session_id or ""),
                idempotency_key=str(request.idempotency_key or ""),
                execution_state=ExecutionState.REFUSED,
                dashboard=ExecutionDashboard(last_refusal=refusal),
                refusal=refusal,
            )

        normalized_request = _normalize_step_request(request, session=session)
        deduped = _dedupe_step_if_needed(session, normalized_request)
        if deduped is not None:
            return deduped

        record = session.record(request=normalized_request, result=dispatch_result)
        self._persist(session)
        state = ExecutionState.EXECUTED if dispatch_result.executed else ExecutionState.REFUSED
        return ExecutionStepResult(
            session_id=session.session_id,
            idempotency_key=normalized_request.idempotency_key,
            execution_state=state,
            dashboard=_build_dashboard(session, last_refusal=dispatch_result.refusal),
            refusal=dispatch_result.refusal,
            record=record,
        )

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:
        normalized_request, deduped = self.preflight_step(request)
        if deduped is not None:
            return deduped
        assert normalized_request is not None
        dispatch_result = self.executor.execute(normalized_request)
        return self.record_dispatch_result(normalized_request, dispatch_result)

    def _get_session(self, session_id: str) -> ExecutionSession | None:
        if session_id in self.sessions:
            return self.sessions[session_id]
        return None

    def _persist(self, session: ExecutionSession) -> None:
        if self.persistence is None:
            return
        self.persistence.save_run_artifact(session.run_artifact)
        self.persistence.save_session(session)


def new_execution_session(*, session_id: str, run_id: str, run_artifact: RunArtifact | None = None) -> ExecutionSession:
    artifact = run_artifact or RunArtifact(run_id=run_id, session_id=session_id)
    return ExecutionSession(session_id=session_id, run_id=run_id, run_artifact=artifact)


def _normalize_step_request(
    request: ExecutionStepRequest,
    *,
    session: ExecutionSession,
) -> ExecutionStepRequest:
    return ExecutionStepRequest(
        session_id=session.session_id,
        action_id=request.action_id,
        inputs=dict(request.inputs),
        idempotency_key=str(request.idempotency_key or "").strip(),
        run_id=request.run_id or session.run_id,
    )


def _dedupe_step_if_needed(
    session: ExecutionSession,
    normalized_request: ExecutionStepRequest,
) -> ExecutionStepResult | None:
    key = normalized_request.idempotency_key
    if not key or not session.is_duplicate(key):
        return None
    cached = session.last_result_by_key.get(key)
    if cached is not None:
        return ExecutionStepResult(
            session_id=session.session_id,
            idempotency_key=key,
            execution_state=ExecutionState.DEDUPED,
            dashboard=_build_dashboard(session),
            record=_record_for_key(session, key),
        )
    refusal = ExecutionRefusal(reason_code="duplicate_idempotency_key", retryable=False)
    return ExecutionStepResult(
        session_id=session.session_id,
        idempotency_key=key,
        execution_state=ExecutionState.REFUSED,
        dashboard=_build_dashboard(session, last_refusal=refusal),
        refusal=refusal,
    )


def _build_dashboard(
    session: ExecutionSession,
    *,
    last_refusal: ExecutionRefusal | None = None,
) -> ExecutionDashboard:
    return ExecutionDashboard(
        latest_refs=ExecutionLatestRefs(refs=dict(session.run_artifact.latest_refs)),
        budgets_remaining={},
        last_refusal=last_refusal,
    )


def _record_for_key(session: ExecutionSession, idempotency_key: str) -> SessionExecutionRecord | None:
    for record in reversed(session.records):
        if record.request.idempotency_key == idempotency_key:
            return record
    return None
