from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Literal

from pydantic import BaseModel, Field, field_validator


class TranscriptEditAgentRunRequest(BaseModel):
    """Canonical request model for the harness-facing transcript-edit agent loop.

    Compatibility note:
    - ``resume_pending_feedback_*`` fields are migration-bridge inputs only.
    - Registry-first resumability (``resume_blocker_registry``) is the canonical
      waiting/resume authority surface.
    """

    mission_objective: str = Field(
        default="",
        description="Human-readable mission objective threaded to all LLM call surfaces.",
    )
    dossier_id: Optional[str] = None
    transcription_id: Optional[str] = None
    trigger: Optional[str] = None
    source_transcript_ref: Optional[str] = None
    source_text: Optional[str] = None
    resume_working_transcript_ref: Optional[str] = Field(
        default=None,
        description=(
            "Latest successfully edited transcript artifact path from a prior iteration or run. "
            "When set, the loop audits/applies against this file before falling back to source_transcript_ref. "
            "Session boundaries: set from snapshot tx_edited_transcript_ref on resume."
        ),
    )
    original_seed_transcript_ref: Optional[str] = Field(
        default=None,
        description=(
            "Immutable original import path for lineage (first transcript uploaded). "
            "When resume_working_transcript_ref is set, keep source_transcript_ref as this seed while "
            "working edits use the resume_working path."
        ),
    )
    source_image_refs: list[str] = Field(default_factory=list, max_length=5)
    model: str = "gpt-5.2"
    max_iterations: int = Field(default=4, ge=1, le=30)
    min_iterations_before_complete: int = Field(default=3, ge=1, le=10)
    mode: str = Field(default="audit_then_repair_then_promote")
    validation_mode: str = Field(default="off")
    auto_promote: bool = True
    edit_plan: Optional[dict[str, Any]] = None
    candidate_refs: list[str] = Field(default_factory=list, max_length=10)
    candidate_texts: list[str] = Field(default_factory=list, max_length=10)
    max_candidates_for_orient: int = Field(default=3, ge=1, le=10)
    max_total_hydrated_bytes_for_orient: int = Field(default=120000, ge=2000, le=2000000)
    max_bytes_per_candidate_for_orient: int | None = Field(default=40000, ge=500, le=500000)
    orient_hydration_selection_strategy: str = Field(default="first_middle_last")
    max_invalid_plan_attempts: int = Field(default=2, ge=1, le=5)
    max_no_progress_iterations: int = Field(default=2, ge=1, le=5)
    hitl_enabled: bool = True
    hitl_wait_timeout_seconds: int = Field(default=120, ge=10, le=900)
    hitl_poll_interval_seconds: int = Field(default=2, ge=1, le=30)
    resume_pending_feedback_prompt_id: Optional[str] = Field(
        default=None,
        description=(
            "Compatibility bridge input only. Canonical waiting/resume ownership "
            "is registry-first via resume_blocker_registry."
        ),
    )
    resume_pending_feedback_decision_key: Optional[str] = Field(
        default=None,
        description=(
            "Compatibility bridge input only. Canonical waiting/resume ownership "
            "is registry-first via resume_blocker_registry."
        ),
    )
    resume_pending_feedback_prompt: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Compatibility bridge payload only. Canonical waiting/resume ownership "
            "is registry-first via resume_blocker_registry."
        ),
    )
    resume_blocker_registry: dict[str, Any] | None = None
    run_standalone_edit_planner: bool = Field(
        default=False,
        description=(
            "When true, the repair loop also calls the standalone edit planner (propose_plan) once per "
            "iteration with the same slim execution_context as the resolver. Off by default to avoid "
            "doubling LLM cost."
        ),
    )


class EmergentBlockerUpdateProposal(BaseModel):
    operation: Literal["add", "update", "resolve", "supersede"]
    blocker_id: str | None = None
    blocker_kind: str | None = None
    title: str | None = None
    blocking_class: Literal["mapping_blocking", "closure_blocking", "source_blocking", "quality_only"] | None = None
    reason: str | None = None
    evidence_summary: str | None = None
    candidate_values: list[str] = Field(default_factory=list, max_length=10)
    resolution_condition: str | None = None
    next_valid_actions: list[str] = Field(default_factory=list, max_length=10)
    source_completeness_impact: str | None = None
    scope_status: Literal["in_target", "outside_target", "unknown"] | None = None
    supersedes_blocker_id: str | None = None
    linked_ticket_id: str | None = None
    legacy_decision_key: str | None = None
    duplicate_rationale: str | None = None

    @field_validator("blocker_kind")
    @classmethod
    def _normalize_blocker_kind(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None

    @field_validator("source_completeness_impact")
    @classmethod
    def _normalize_source_impact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None

    @field_validator("next_valid_actions", mode="before")
    @classmethod
    def _normalize_actions(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for row in value:
            text = str(row).strip().lower()
            if not text:
                continue
            if text in out:
                continue
            out.append(text)
        return out


@dataclass(frozen=True)
class TranscriptEditAgentRunResult:
    run_artifact_ref: Optional[str]
    session_id: str
    iterations: int
    status: str
    reason_code: str
    latest_refs: dict[str, Any]
    review_required: bool
    runtime_hitl_state: dict[str, Any] | None = None
    handoff_posture: dict[str, Any] | None = None
