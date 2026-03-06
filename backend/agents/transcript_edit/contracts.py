from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field


class TranscriptEditAgentRunRequest(BaseModel):
    dossier_id: Optional[str] = None
    transcription_id: Optional[str] = None
    trigger: Optional[str] = None
    source_transcript_ref: Optional[str] = None
    source_text: Optional[str] = None
    source_image_refs: list[str] = Field(default_factory=list, max_length=5)
    model: str = "gpt-5.2"
    max_iterations: int = Field(default=4, ge=1, le=30)
    min_iterations_before_complete: int = Field(default=3, ge=1, le=10)
    mode: str = Field(default="audit_then_repair_then_promote")
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
