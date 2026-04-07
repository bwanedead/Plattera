"""Minimal generic contracts for the harness execution layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from .action_ids import ActionId


@dataclass(frozen=True)
class ExecutionStepRequest:
    session_id: str
    action_id: ActionId
    inputs: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    run_id: str | None = None


@dataclass(frozen=True)
class ExecutionRefusal:
    reason_code: str
    retryable: bool = False
    blocked_by_budget: bool = False
    blocked_by_invariant: bool = False
    missing_inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionDispatchResult:
    action_id: ActionId
    executed: bool
    reason_codes: tuple[str, ...] = ()
    outputs: dict[str, Any] = field(default_factory=dict)
    refusal: ExecutionRefusal | None = None
    artifact_refs: tuple[str, ...] = ()
    idempotency_key: str = ""
    # Mechanical side channel for model-visible image evidence (base64 payloads).
    # NOT included in continuity text records to avoid token bloat.
    image_evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExecutionLatestRefs:
    refs: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        del mode
        return dict(self.refs)


@dataclass(frozen=True)
class ExecutionDashboard:
    latest_refs: ExecutionLatestRefs = field(default_factory=ExecutionLatestRefs)
    budgets_remaining: dict[str, int] = field(default_factory=dict)
    last_refusal: ExecutionRefusal | None = None


class ExecutionState(str, Enum):
    EXECUTED = "executed"
    REFUSED = "refused"
    DEDUPED = "deduped"


@dataclass(frozen=True)
class SessionExecutionRecord:
    session_id: str
    run_id: str
    request: ExecutionStepRequest
    result: ActionDispatchResult


@dataclass(frozen=True)
class ExecutionStepResult:
    session_id: str
    idempotency_key: str
    execution_state: ExecutionState
    dashboard: ExecutionDashboard
    refusal: ExecutionRefusal | None = None
    record: SessionExecutionRecord | None = None


@dataclass(frozen=True)
class ExecutionSessionStartRequest:
    run_id: str
    session_id: str | None = None
    initial_latest_refs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionSessionStartResult:
    session_id: str
    run_id: str
    run_artifact_ref: str | None
    dashboard: ExecutionDashboard
    refusal: ExecutionRefusal | None = None


@runtime_checkable
class ActionDispatchHandler(Protocol):
    def __call__(self, request: ExecutionStepRequest) -> ActionDispatchResult | Mapping[str, Any]: ...


@runtime_checkable
class ExecutionPersistence(Protocol):
    def save_run_artifact(self, run_artifact: Any) -> str | None: ...

    def load_run_artifact(self, run_artifact_ref: str) -> Any: ...

    def save_session(self, session: Any) -> str | None: ...

    def load_session(self, session_ref: str) -> Any: ...
