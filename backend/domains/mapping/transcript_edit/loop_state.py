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
    apply_reaudit_baseline_blocking_signature: str | None = None
    last_focus_key: str | None = None
    focus_stagnation_streak: int = 0
    applied_non_normalization: bool = False
    applied_requires_review: bool = False
    span_seeds_ref: str | None = None
    latest_feedback: dict[str, Any] | None = None
    last_reason: str = "tx_agent_not_started"
    applied_any_edits: bool = False
    used_human_feedback: bool = False
    # Transcript-edit native store: persistence + mutation. Runtime reads use unified envelope + closure read ledger.
    decision_ledger: dict[str, Any] = field(default_factory=dict)
    convention_context: dict[str, Any] = field(default_factory=dict)
    blocker_registry: dict[str, Any] = field(default_factory=dict)
    pending_feedback_prompt_id: str | None = None
    pending_feedback_prompt: dict[str, Any] | None = None
    pending_feedback_decision_key: str | None = None
    pending_feedback_emitted_iteration: int | None = None
    feedback_received_count: int = 0
    feedback_consumed_count: int = 0
    feedback_stale_count: int = 0
    feedback_superseded_count: int = 0
    feedback_entry_seen_keys: set[str] = field(default_factory=set)
    superseded_feedback_prompt_ids: set[str] = field(default_factory=set)
    hitl_lifecycle_log: list[dict[str, Any]] = field(default_factory=list)
    continuity_log: list[dict[str, Any]] = field(default_factory=list)
    span_context_by_decision_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    image_verification_payload_by_decision_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    visual_evidence_by_decision_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_repeat_guard: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_signal_counter: int = 0
    llm_call_seq: int = 0
    # D2 — edit lineage
    seed_transcript_ref: str | None = None
    edit_lineage_summary: list[dict[str, Any]] = field(default_factory=list)
    # D1 — T0 candidate refs discovered at orient time
    t0_candidate_refs: list[str] = field(default_factory=list)
    # D2 — Investigation summary (scene map) — generated once after orient, reused thereafter
    investigation_summary_ref: str | None = None
    # True once the initial scene survey (orient + summary generation) has completed.
    # Does NOT mean all investigation is done — only that initial recon has happened.
    initial_recon_complete: bool = False
    # Durable harness-emergent rows merged into the unified decision ledger at read time.
    harness_emergent_board_items: list[dict[str, Any]] = field(default_factory=list)
    harness_board_context_notes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Ephemeral: last compact board observability for progress emission (cleared after ticker).
    last_board_observability: dict[str, Any] | None = None
    # LLM-authored startup/orientation (mirror of decision_ledger.llm_startup_understanding).
    llm_startup_understanding: dict[str, Any] | None = None
    # Phase 24: last mechanical audit/inspection snapshot (evidence-only; not authoritative meaning).
    last_audit_evidence_snapshot: dict[str, Any] | None = None
    # Last resolver-applied iteration understanding sidecar (optional).
    llm_iteration_understanding: dict[str, Any] | None = None
