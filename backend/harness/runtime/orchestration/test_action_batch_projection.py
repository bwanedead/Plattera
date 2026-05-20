"""Prompt projection tests for recent_action_sequence_result."""

from __future__ import annotations

from harness.runtime.composition import ComposedTurnInput
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import OrchestratorContext
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document
from harness.execution.session import ExecutionSessionManager


def test_prompt_includes_recent_batch_result() -> None:
    lm = LoopMemoryState()
    lm.continuity.recent_action_sequence_result = {
        "batch_id": "req:iter:2:batch",
        "source_turn_index": 2,
        "items": [
            {
                "alias": "p1",
                "action_type": "transform_artifact",
                "execution_state": "executed",
                "artifact_refs": ["image:derived:p1"],
            },
        ],
    }
    ctx = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="s",
        loop_memory=lm,
        request_id_prefix="req",
    )
    doc = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(blocks=(), surface_payloads={}),
        opaque_launch_context={},
        context=ctx,
        projection=None,
        journal_verbatim_keep_n=2,
    )
    lane = doc.prompt_body["structured_state"].get("recent_action_sequence_result")
    assert lane is not None
    assert lane["items"][0]["alias"] == "p1"


def test_prompt_omits_batch_lane_when_absent() -> None:
    lm = LoopMemoryState()
    ctx = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="s",
        loop_memory=lm,
        request_id_prefix="req",
    )
    doc = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(blocks=(), surface_payloads={}),
        opaque_launch_context={},
        context=ctx,
        projection=None,
        journal_verbatim_keep_n=2,
    )
    assert "recent_action_sequence_result" not in doc.prompt_body.get("structured_state", {})
