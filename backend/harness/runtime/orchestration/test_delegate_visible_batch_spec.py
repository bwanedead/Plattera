"""Visible delegate_subtask batching spec alignment tests."""

from __future__ import annotations

from domains.mapping.transcript_edit.execution.action_batch_policy import (
    TRANSCRIPT_EDIT_VISUAL_DELEGATE_MAX_BATCH,
    build_transcript_edit_action_batch_policy,
)
from harness.runtime.composition import ComposedTurnInput
from harness.runtime.orchestration.subtasks.batch_policy import DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.runner.runner import _with_delegate_subtask_tool


def _composed_with_handlers() -> ComposedTurnInput:
    return ComposedTurnInput(
        blocks=(),
        surface_payloads={"transcript_edit": {"tool_specs": []}},
        tool_handlers={"hydrate_artifact_refs": lambda request: request},
    )


def _delegate_batching(composed: ComposedTurnInput) -> dict:
    payload = composed.surface_payloads["harness_delegate_subtask"]
    spec = payload["tool_specs"][0]
    assert spec["tool_id"] == DELEGATE_SUBTASK_ACTION_TYPE
    batching = spec.get("batching")
    assert isinstance(batching, dict)
    return batching


def _delegate_input_shape(composed: ComposedTurnInput) -> dict:
    payload = composed.surface_payloads["harness_delegate_subtask"]
    spec = payload["tool_specs"][0]
    input_shape = spec.get("input_shape")
    assert isinstance(input_shape, dict)
    return input_shape


def test_default_visible_delegate_spec_cap_is_four() -> None:
    composed = _with_delegate_subtask_tool(
        _composed_with_handlers(),
        model_caller=lambda *args, **kwargs: {},
        model_name="model-a",
        opaque_run_context={},
    )
    batching = _delegate_batching(composed)
    assert batching["max_calls_per_batch"] == DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH
    assert batching["can_run_parallel"] is True
    input_shape = _delegate_input_shape(composed)
    assert "target_entity_id" in input_shape
    assert "audit/UI linkage" in input_shape["target_entity_id"]


def test_transcript_edit_visible_delegate_spec_cap_is_fifteen() -> None:
    composed = _with_delegate_subtask_tool(
        _composed_with_handlers(),
        model_caller=lambda *args, **kwargs: {},
        model_name="model-a",
        opaque_run_context={"action_batch_policy": build_transcript_edit_action_batch_policy()},
    )
    batching = _delegate_batching(composed)
    assert batching["max_calls_per_batch"] == TRANSCRIPT_EDIT_VISUAL_DELEGATE_MAX_BATCH
