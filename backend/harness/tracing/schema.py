from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TRACE_VERSION = "trace.v1"

LoopFamily = str
CompletenessStatus = Literal["complete", "partial"]
EventKind = Literal[
    "request_start",
    "iteration",
    "mode_segment",
    "mission_transition",
    "model_proposal",
    "tool_execution",
    "retrieval_evidence",
    "blocker_transition",
    "verification",
    "hitl_escalation",
    "terminal_outcome",
]
ActorKind = Literal["model", "kernel", "tool", "harness", "human"]
EventStatus = Literal["started", "completed", "refused", "waiting", "failed", "running", "unknown"]
TimestampSource = Literal["source", "derived_sequence"]


class SourceOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=128)
    ref: str = Field(min_length=1, max_length=1024)
    local_id: str | None = Field(default=None, max_length=256)
    sequence_index: int = Field(ge=0)


class TerminalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terminal_class: str = Field(min_length=1, max_length=128)
    terminal_reason_code: str | None = Field(default=None, max_length=256)
    success: bool | None = None
    terminal_metadata: dict[str, Any] = Field(default_factory=dict)


class CanonicalTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128)
    event_index: int = Field(ge=0)
    timestamp_epoch_seconds: int = Field(ge=0)
    event_kind: EventKind
    phase: str | None = Field(default=None, max_length=128)
    iteration_index: int | None = Field(default=None, ge=0)
    actor: ActorKind
    status: EventStatus
    reason_code: str | None = Field(default=None, max_length=256)
    refs_delta: dict[str, Any]
    payload: dict[str, Any]
    source_origin: SourceOrigin


class RawTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_epoch_seconds: int | None = Field(default=None, ge=0)
    event_kind: EventKind
    phase: str | None = Field(default=None, max_length=128)
    iteration_index: int | None = Field(default=None, ge=0)
    actor: ActorKind
    status: EventStatus
    reason_code: str | None = Field(default=None, max_length=256)
    refs_delta: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_origin: SourceOrigin | None = None


class MissionTransitionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prior_mode: str = Field(min_length=1, max_length=128)
    next_mode: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=256)
    status: str = Field(min_length=1, max_length=32)
    order_anchor: int = Field(ge=0)
    timestamp_epoch_seconds: int = Field(ge=0)
    resume_note_for_prior_mode: str | None = Field(default=None, max_length=256)
    handed_forward_artifact_refs: list[str] = Field(default_factory=list, max_length=24)


class CanonicalTraceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=256)
    request_id: str | None = Field(default=None, max_length=256)
    loop_family: LoopFamily
    request_metadata: dict[str, Any]
    start_context_summary: dict[str, Any]
    started_at_epoch_seconds: int = Field(ge=0)
    events: list[CanonicalTraceEvent]
    terminal: TerminalSnapshot
    mission_id: str | None = Field(default=None, max_length=128)
    executed_mode: str | None = Field(default=None, max_length=128)
    active_mode: str | None = Field(default=None, max_length=128)
    mode_history: list[str] = Field(default_factory=list, max_length=32)
    transition_events: list[MissionTransitionEvent] = Field(default_factory=list, max_length=32)
    resume_context_summary: dict[str, Any] = Field(default_factory=dict)
    completeness_status: CompletenessStatus
    missing_components: list[str]
    normalization_warnings: list[str]
    trace_version: str = Field(min_length=1, max_length=64)
