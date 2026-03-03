from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranscriptEditLoopState:
    latest_refs: dict[str, Any] = field(default_factory=dict)
    current_transcript_ref: str | None = None
    iterations: int = 0
    invalid_plan_strikes: int = 0
    no_progress_streak: int = 0
    previous_finding_signature: str | None = None
    applied_non_normalization: bool = False
    applied_requires_review: bool = False
    span_seeds_ref: str | None = None
    sticky_range_selection: int | None = None
    last_reason: str = "tx_agent_not_started"
    applied_any_edits: bool = False
    used_human_feedback: bool = False
    decision_ledger: dict[str, Any] = field(default_factory=dict)
    pending_feedback_prompt_id: str | None = None
