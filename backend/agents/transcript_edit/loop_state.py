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
    last_progress_reason: str = "not_evaluated"
    previous_finding_signature: str | None = None
    previous_blocking_signature: str | None = None
    previous_blocking_unresolved_count: int | None = None
    previous_signal_counter: int = 0
    pending_reaudit_after_apply: bool = False
    apply_reaudit_baseline_blocking_count: int | None = None
    last_focus_key: str | None = None
    focus_stagnation_streak: int = 0
    applied_non_normalization: bool = False
    applied_requires_review: bool = False
    span_seeds_ref: str | None = None
    latest_feedback: dict[str, Any] | None = None
    last_reason: str = "tx_agent_not_started"
    applied_any_edits: bool = False
    used_human_feedback: bool = False
    decision_ledger: dict[str, Any] = field(default_factory=dict)
    pending_feedback_prompt_id: str | None = None
    pending_feedback_prompt: dict[str, Any] | None = None
    continuity_log: list[dict[str, Any]] = field(default_factory=list)
    evidence_repeat_guard: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_signal_counter: int = 0
    llm_call_seq: int = 0
