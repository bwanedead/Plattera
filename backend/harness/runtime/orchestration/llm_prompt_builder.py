"""Harness-owned prompt builder entrypoints for orchestration modes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..composition import ComposedTurnInput
from .contracts import OrchestratorContext, SharedStateProjection
from .prompt_modes import PromptBuildDocument, PromptMode
from .prompt_packet_builder import (
    build_compaction_prompt_document as _build_compaction_prompt_document,
    build_repair_prompt_document as _build_repair_prompt_document,
    build_turn_prompt_document as _build_turn_prompt_document,
    prompt_visible_launch_context,
)
from .prompt_utils import jsonable  # re-exported: callers import jsonable from here


def build_choose_action_prompt_document(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
) -> PromptBuildDocument:
    return _build_turn_prompt_document(
        mode="full_choose_action",
        composed_input=composed_input,
        opaque_launch_context=opaque_launch_context,
        context=context,
        projection=projection,
        journal_verbatim_keep_n=journal_verbatim_keep_n,
    )


def build_resume_prompt_document(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
) -> PromptBuildDocument:
    return _build_turn_prompt_document(
        mode="resume",
        composed_input=composed_input,
        opaque_launch_context=opaque_launch_context,
        context=context,
        projection=projection,
        journal_verbatim_keep_n=journal_verbatim_keep_n,
    )


def build_state_repair_prompt_document(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
) -> PromptBuildDocument:
    return _build_turn_prompt_document(
        mode="state_repair",
        composed_input=composed_input,
        opaque_launch_context=opaque_launch_context,
        context=context,
        projection=projection,
        journal_verbatim_keep_n=journal_verbatim_keep_n,
    )


def build_choose_action_prompt(
    *,
    composed_input: ComposedTurnInput,
    opaque_launch_context: Mapping[str, Any],
    context: OrchestratorContext,
    projection: SharedStateProjection | None,
    journal_verbatim_keep_n: int,
    mode: PromptMode = "full_choose_action",
) -> str:
    if mode == "resume":
        builder = build_resume_prompt_document
    elif mode == "state_repair":
        builder = build_state_repair_prompt_document
    else:
        builder = build_choose_action_prompt_document
    return builder(
        composed_input=composed_input,
        opaque_launch_context=opaque_launch_context,
        context=context,
        projection=projection,
        journal_verbatim_keep_n=journal_verbatim_keep_n,
    ).prompt_text


def build_repair_prompt_document(
    *,
    available_tool_ids: tuple[str, ...],
    prior_prompt_mode: str,
    parse_reason_code: str,
    parse_error_detail: str,
    previous_response_text: str,
    previous_response_object: dict[str, Any] | None = None,
    repair_targets: list[str] | None = None,
    repair_hints: list[str] | None = None,
) -> PromptBuildDocument:
    return _build_repair_prompt_document(
        available_tool_ids=available_tool_ids,
        prior_prompt_mode=prior_prompt_mode,
        parse_reason_code=parse_reason_code,
        parse_error_detail=parse_error_detail,
        previous_response_text=previous_response_text,
        previous_response_object=previous_response_object,
        repair_targets=repair_targets,
        repair_hints=repair_hints,
    )


def build_compaction_prompt_document(
    *,
    prior_compacted_continuity_summary: str | None,
    journal_entries_to_fold: list[dict[str, Any]],
    kernel_step_records_to_fold: list[dict[str, Any]],
    kernel_step_result_records_to_fold: list[dict[str, Any]],
    target_compacted_summary_chars: int,
) -> PromptBuildDocument:
    return _build_compaction_prompt_document(
        prior_compacted_continuity_summary=prior_compacted_continuity_summary,
        journal_entries_to_fold=journal_entries_to_fold,
        kernel_step_records_to_fold=kernel_step_records_to_fold,
        kernel_step_result_records_to_fold=kernel_step_result_records_to_fold,
        target_compacted_summary_chars=target_compacted_summary_chars,
    )
