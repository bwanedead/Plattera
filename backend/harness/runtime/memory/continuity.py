from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...mission_state import MissionState, ResolutionState, new_mission_state, new_resolution_state


def _default_mission_state() -> MissionState:
    return new_mission_state(
        mission_id="unknown_mission",
        # Canonical loop_family for orchestration-kernel runs (wire + trace vocabulary).
        loop_family="orchestration_kernel",
        resolution_state=new_resolution_state(),
    )


@dataclass
class OrchestrationContinuity:
    """Hydrated mission understanding and refs carried iteration-to-iteration.

    Values are updated from each ``SharedStateProjection`` sync and step
    execution; this is continuity carriage for the orchestrator, not the
    authoritative mission-state store.
    """

    latest_refs: dict[str, Any] = field(default_factory=dict)
    mission_state: MissionState = field(default_factory=_default_mission_state)
    resolution_state: ResolutionState = field(default_factory=new_resolution_state)
    active_item_id: str | None = None
    # Mechanical outcome of the last state_patch attempt (for prompt + traces; not semantic work).
    state_patch_feedback: dict[str, Any] = field(default_factory=dict)
    # Append-only LLM-authored journal rows: {kernel_turn_index, author_payload}; full history kept for resume.
    continuity_journal_entries: list[dict[str, Any]] = field(default_factory=list)
    # LLM-authored text from a dedicated compaction call; injected into prompts instead of older journal rows.
    compacted_continuity_summary: str | None = None
    # Latest LLM-authored short operator-facing status line.
    operator_progress_message: str | None = None
    # Mechanical per-turn execution facts for compaction prompts (host does not interpret).
    kernel_step_records: list[dict[str, Any]] = field(default_factory=list)
    # Bounded mechanical tool-dispatch outcomes for prompt memory (not raw artifacts; host does not interpret meaning).
    kernel_step_result_records: list[dict[str, Any]] = field(default_factory=list)
    # Mechanical frontier: rows with ``kernel_turn_index <=`` this were already sent in a successful compaction payload.
    kernel_compaction_covered_through_turn_index: int = 0
    # Advisory sequencing debt: unit keys ("item_id//unit_id") that transitioned to
    # earned/closed with a determined_value before any claim-local evidence_locators
    # existed.  Maps key → iteration when debt was first recorded.  Cleared only
    # when the unit is materially re-evaluated (determined_value or verification_basis
    # changed, or status reopened) — adding locators alone does NOT clear this debt
    # (that produces ``posthoc_recheck_needed_debt`` instead).
    earned_before_local_evidence_debt: dict[str, int] = field(default_factory=dict)
    # Advisory post-hoc debt: subset of earned_before_local_evidence_debt entries for
    # which a later patch attached locators without re-evaluating the claim.
    # Maps key → iteration when the post-hoc locator was first added.
    # Cleared when a subsequent patch materially re-evaluates the unit: changes
    # determined_value, updates verification_basis, or reopens the status.
    posthoc_recheck_needed_debt: dict[str, int] = field(default_factory=dict)
    # Append-only HITL exchange ledger: durable mechanical history of every
    # human-in-the-loop interaction (outbound request, inbound response,
    # consumption status).  Separate from ``LoopMemoryState.hitl`` (transport
    # queue) — the ledger preserves history that survives consumption.
    # Bounded by ``runtime/hitl/exchange_ledger.clamp_ledger`` (drops only old
    # consumed entries).  See ``runtime/hitl/exchange_ledger.py``.
    hitl_exchange_ledger: list[dict[str, Any]] = field(default_factory=list)
    # Cumulative count of agent-declared ``hitl_consumed_prompt_ids`` entries
    # that did not match any ledger exchange (drift signal; never cleared).
    hitl_consumed_unknown_prompt_count: int = 0
    # Append-only user-message ledger: durable mechanical history of every
    # user-initiated message injected into the run (via CLI/UI/API).  Each
    # entry preserves exact user-authored text plus consumption status
    # (pending/consumed/deferred).  Separate from the HITL exchange ledger:
    # HITL is agent-initiated, user messages are user-initiated.  See
    # ``runtime/user_messages/ledger.py``.
    user_message_ledger: list[dict[str, Any]] = field(default_factory=list)
    # Cumulative count of agent-declared ``user_message_consumed_ids`` entries
    # that did not match any ledger row (drift signal; never cleared).
    user_message_consumed_unknown_count: int = 0
