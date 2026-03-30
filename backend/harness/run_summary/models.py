"""Pydantic models for the derived run-summary inspection envelope."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..mission_state import MissionState
from ..terminal_taxonomy import TerminalClass

RUN_SUMMARY_ENVELOPE_VERSION = "run_summary.v1"
LoopFamily = str


class RequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str | None = Field(default=None, max_length=240)
    mode: str | None = Field(default=None, max_length=64)
    trigger: str | None = Field(default=None, max_length=64)


class LatestRefsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_refs: bool
    total_count: int = Field(ge=0)
    ref_keys: list[str] = Field(default_factory=list, max_length=16)


class BlockerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_count: int | None = Field(default=None, ge=0)
    active_blocker_id: str | None = Field(default=None, max_length=128)
    waiting_human: bool
    answered_unintegrated_count: int | None = Field(default=None, ge=0)
    source: Literal["registry", "derived", "sparse"]


class VerificationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, max_length=64)
    last_verification_kind: str | None = Field(default=None, max_length=64)


class WaitingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waiting: bool
    waiting_kind: str | None = Field(default=None, max_length=64)
    resumable: bool
    owner_kind: str | None = Field(default=None, max_length=64)


class NormalizedTerminalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terminal: bool
    terminal_class: TerminalClass | None = None
    reason_code: str | None = Field(default=None, max_length=256)


class ContinuitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int | None = Field(default=None, ge=0)
    last_phase: str | None = Field(default=None, max_length=128)
    last_reason_code: str | None = Field(default=None, max_length=256)
    has_recent_activity: bool


class MissionModeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_mode: str | None = Field(default=None, max_length=64)
    mode_history: list[str] = Field(default_factory=list, max_length=32)
    latest_transition_reason: str | None = Field(default=None, max_length=256)
    resume_context_summary: dict[str, Any] = Field(default_factory=dict)


class PromptObservabilitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_event_count: int = Field(default=0, ge=0)
    last_prompt_event_id: str | None = Field(default=None, max_length=128)
    last_prompt_event_surface: str | None = Field(default=None, max_length=64)


class SharedRunSummaryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=256)
    request_id: str | None = Field(default=None, max_length=256)
    loop_family: LoopFamily
    request_summary: RequestSummary
    latest_refs_summary: LatestRefsSummary
    blocker_summary: BlockerSummary
    verification_summary: VerificationSummary
    waiting_summary: WaitingSummary
    terminal_summary: NormalizedTerminalSummary
    continuity_summary: ContinuitySummary
    mission_state: MissionState
    mission_mode_summary: MissionModeSummary = Field(default_factory=MissionModeSummary)
    prompt_observability_summary: PromptObservabilitySummary = Field(default_factory=PromptObservabilitySummary)
    envelope_version: str = Field(min_length=1, max_length=64)
