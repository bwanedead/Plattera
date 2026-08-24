"""Explicit prompt-mode specs for the harness-owned orchestration builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .choose_action_instruction import CHOOSE_ACTION_INSTRUCTION
from .compaction_instruction import COMPACTION_INSTRUCTION
from .repair_instruction import REPAIR_INSTRUCTION, STATE_REPAIR_INSTRUCTION
from .resume_instruction import RESUME_INSTRUCTION
from .turn_recovery_instruction import TURN_RECOVERY_INSTRUCTION

if TYPE_CHECKING:
    from .result_delivery_hooks import ResultDeliveryContactMetadata

PromptMode = Literal["full_choose_action", "state_repair", "repair", "compaction", "resume", "turn_recovery"]


@dataclass(frozen=True)
class PromptModeSpec:
    mode: PromptMode
    instruction_text: str
    include_doctrine_blocks: bool
    include_surface_packet_blocks: bool
    include_surface_payloads: bool
    include_tool_ids: bool
    include_compact_tool_contracts: bool
    run_context_fields: tuple[str, ...]
    structured_state_fields: tuple[str, ...]
    mode_packet_key: str | None
    call_phase: str


@dataclass(frozen=True)
class PromptBuildDocument:
    mode: PromptMode
    call_phase: str
    instruction_text: str
    prompt_body: dict[str, Any]
    prompt_text: str
    prompt_budget: dict[str, Any] | None = None
    # Internal only — never serialized into prompt_text / prompt_body / model input.
    result_delivery_contact: ResultDeliveryContactMetadata | None = None


_FULL_RUN_CONTEXT_FIELDS = (
    "iteration",
    "launch_context",
    "state_patch_feedback",
    "contract_feedback",
    "hitl_state",
    "pending_hitl_requests",
    "answered_hitl_responses",
    "domain_runtime_projection",
    "projection",
)
_STATE_REPAIR_RUN_CONTEXT_FIELDS = (
    "iteration",
    "session_id",
    "request_id_prefix",
    "launch_context",
    "latest_refs",
    "active_item_id",
    "state_patch_feedback",
    "contract_feedback",
    "operator_progress_message",
    "hitl_state",
    "pending_hitl_requests",
    "answered_hitl_responses",
    "domain_runtime_projection",
    "projection",
)
_FULL_STRUCTURED_STATE_FIELDS = (
    "compacted_continuity_summary",
    "recent_continuity_journal_entries",
    "recent_turn_timeline",
    "agent_requested_hydration",
    "pinned_refs",
    "pinned_refs_hydration",
    "stable_context",
    "latest_action_results",
    "prompt_observability_summary",
)
_STATE_REPAIR_STRUCTURED_STATE_FIELDS = (
    "compacted_continuity_summary",
    "recent_continuity_journal_entries",
    "recent_turn_timeline",
    "agent_requested_hydration",
    "pinned_refs",
    "pinned_refs_hydration",
    "stable_context",
    "latest_action_results",
    "prompt_observability_summary",
)
_RESUME_RUN_CONTEXT_FIELDS = (
    "iteration",
    "launch_context",
    "state_patch_feedback",
    "hitl_state",
    "pending_hitl_requests",
    "answered_hitl_responses",
    "domain_runtime_projection",
    "projection",
)
_RESUME_STRUCTURED_STATE_FIELDS = (
    "compacted_continuity_summary",
    "recent_continuity_journal_entries",
    "recent_turn_timeline",
    "agent_requested_hydration",
    "pinned_refs",
    "pinned_refs_hydration",
    "stable_context",
    "latest_action_results",
    "prompt_observability_summary",
)
_TURN_RECOVERY_RUN_CONTEXT_FIELDS = (
    "iteration",
    "state_patch_feedback",
    "turn_recovery",
    "hitl_state",
    "pending_hitl_requests",
    "answered_hitl_responses",
    "projection",
)
_TURN_RECOVERY_STRUCTURED_STATE_FIELDS = (
    "recent_turn_timeline",
    "agent_requested_hydration",
    "pinned_refs",
    "pinned_refs_hydration",
    "stable_context",
    "latest_action_results",
    "prompt_observability_summary",
)

_PROMPT_MODE_SPECS: dict[PromptMode, PromptModeSpec] = {
    "full_choose_action": PromptModeSpec(
        mode="full_choose_action",
        instruction_text=CHOOSE_ACTION_INSTRUCTION,
        include_doctrine_blocks=True,
        include_surface_packet_blocks=True,
        include_surface_payloads=True,
        include_tool_ids=True,
        include_compact_tool_contracts=False,
        run_context_fields=_FULL_RUN_CONTEXT_FIELDS,
        structured_state_fields=_FULL_STRUCTURED_STATE_FIELDS,
        mode_packet_key=None,
        call_phase="choose_action",
    ),
    "state_repair": PromptModeSpec(
        mode="state_repair",
        instruction_text=STATE_REPAIR_INSTRUCTION,
        include_doctrine_blocks=True,
        include_surface_packet_blocks=True,
        include_surface_payloads=True,
        include_tool_ids=True,
        include_compact_tool_contracts=False,
        run_context_fields=_STATE_REPAIR_RUN_CONTEXT_FIELDS,
        structured_state_fields=_STATE_REPAIR_STRUCTURED_STATE_FIELDS,
        mode_packet_key=None,
        call_phase="choose_action_state_repair",
    ),
    "repair": PromptModeSpec(
        mode="repair",
        instruction_text=REPAIR_INSTRUCTION,
        include_doctrine_blocks=False,
        include_surface_packet_blocks=False,
        include_surface_payloads=False,
        include_tool_ids=True,
        include_compact_tool_contracts=False,
        run_context_fields=(),
        structured_state_fields=(),
        mode_packet_key="repair_context",
        call_phase="choose_action_repair",
    ),
    "compaction": PromptModeSpec(
        mode="compaction",
        instruction_text=COMPACTION_INSTRUCTION,
        include_doctrine_blocks=False,
        include_surface_packet_blocks=False,
        include_surface_payloads=False,
        include_tool_ids=False,
        include_compact_tool_contracts=False,
        run_context_fields=(),
        structured_state_fields=(),
        mode_packet_key="compaction_context",
        call_phase="continuity_compaction",
    ),
    "resume": PromptModeSpec(
        mode="resume",
        instruction_text=RESUME_INSTRUCTION,
        include_doctrine_blocks=True,
        include_surface_packet_blocks=True,
        include_surface_payloads=True,
        include_tool_ids=True,
        include_compact_tool_contracts=False,
        run_context_fields=_RESUME_RUN_CONTEXT_FIELDS,
        structured_state_fields=_RESUME_STRUCTURED_STATE_FIELDS,
        mode_packet_key=None,
        call_phase="choose_action_resume",
    ),
    "turn_recovery": PromptModeSpec(
        mode="turn_recovery",
        instruction_text=TURN_RECOVERY_INSTRUCTION,
        include_doctrine_blocks=False,
        include_surface_packet_blocks=False,
        include_surface_payloads=False,
        include_tool_ids=True,
        include_compact_tool_contracts=True,
        run_context_fields=_TURN_RECOVERY_RUN_CONTEXT_FIELDS,
        structured_state_fields=_TURN_RECOVERY_STRUCTURED_STATE_FIELDS,
        mode_packet_key=None,
        call_phase="choose_action_turn_recovery",
    ),
}


def require_prompt_mode_spec(mode: PromptMode) -> PromptModeSpec:
    return _PROMPT_MODE_SPECS[mode]
