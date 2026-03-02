from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field


class TranscriptEditAgentRunRequest(BaseModel):
    dossier_id: Optional[str] = None
    source_transcript_ref: Optional[str] = None
    source_text: Optional[str] = None
    source_image_refs: list[str] = Field(default_factory=list, max_length=5)
    model: str = "gpt-5.2"
    max_iterations: int = Field(default=4, ge=1, le=30)
    mode: str = Field(default="audit_then_repair_then_promote")
    auto_promote: bool = True
    edit_plan: Optional[dict[str, Any]] = None
    candidate_texts: list[str] = Field(default_factory=list, max_length=10)
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
