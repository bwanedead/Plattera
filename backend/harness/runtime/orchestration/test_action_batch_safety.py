"""Safety and durability tests for action sequences (no b64 leak, resume, audit)."""

from __future__ import annotations

from harness.execution.contracts import ExecutionSessionStartRequest
from harness.execution.executor import ExecutionExecutor
from harness.execution.session import ExecutionSessionManager
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import (
    build_kernel_resume_snapshot,
    parse_kernel_resume_snapshot,
)
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.orchestration.action_batch import (
    build_action_batch_result_record,
    build_batch_item_result_row,
)
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.action_sequence import (
    ActionPlanAction,
    action_plan_with_canonical_actions,
    build_sequence_tool_request_summary,
    build_sequence_tool_result_summary,
    project_sequence_item_row,
    validate_stored_action_sequence_result,
)
from harness.runtime.orchestration.contracts import OrchestratorContext
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document
from harness.runtime.composition import ComposedTurnInput


def test_batch_item_row_never_stores_raw_b64() -> None:
    row = build_batch_item_result_row(
        alias="c1",
        action_type="transform_artifact",
        execution_state="executed",
        image_evidence=[
            {"ref_id": "image:derived:x", "b64": "aGVsbG8=", "media_type": "image/png"},
        ],
    )
    assert "image_evidence" not in row
    assert "b64" not in str(row)
    assert row.get("image_evidence_summary") == {
        "count": 1,
        "ref_ids": ["image:derived:x"],
        "media_types": ["image/png"],
    }


def test_prompt_projection_omits_b64_from_legacy_stored_rows() -> None:
    lm = LoopMemoryState()
    lm.continuity.recent_action_sequence_result = {
        "batch_id": "req:iter:1:batch",
        "source_turn_index": 1,
        "items": [
            {
                "alias": "c1",
                "action_type": "transform_artifact",
                "execution_state": "executed",
                "image_evidence": [
                    {"ref_id": "image:derived:x", "b64": "SECRET", "media_type": "image/png"},
                ],
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
    text = str(doc.prompt_body)
    assert "SECRET" not in text
    assert "b64" not in text
    lane = doc.prompt_body["structured_state"]["recent_action_sequence_result"]
    assert lane["items"][0].get("image_evidence_summary", {}).get("count") == 1


def test_validate_stored_action_sequence_result_strips_b64() -> None:
    out = validate_stored_action_sequence_result({
        "batch_id": "b-1",
        "source_turn_index": 2,
        "items": [
            {
                "alias": "a",
                "action_type": "transform_artifact",
                "execution_state": "executed",
                "image_evidence": [{"ref_id": "r", "b64": "x", "media_type": "image/jpeg"}],
            },
        ],
    })
    assert out is not None
    assert "b64" not in str(out)
    assert "image_evidence" not in out["items"][0]


def test_roundtrip_recent_action_sequence_result_in_resume_snapshot() -> None:
    executor = ExecutionExecutor()
    sm = ExecutionSessionManager(executor=executor)
    sm.start_session(ExecutionSessionStartRequest(run_id="run-batch", session_id="sess-batch"))
    lm = LoopMemoryState()
    lm.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    lm.continuity.resolution_state = new_resolution_state()
    lm.continuity.recent_action_sequence_result = {
        "batch_id": "req:iter:5:batch",
        "source_turn_index": 5,
        "items": [
            build_batch_item_result_row(
                alias="p1",
                action_type="transform_artifact",
                execution_state="executed",
                artifact_refs=["image:derived:p1"],
                image_evidence=[
                    {"ref_id": "image:derived:p1", "b64": "bytes", "media_type": "image/png"},
                ],
            ),
        ],
    }

    snap = build_kernel_resume_snapshot(
        loop_memory=lm, session_manager=sm, session_id="sess-batch", next_iteration=6,
    )
    mem2, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    rec = mem2.continuity.recent_action_sequence_result
    assert rec is not None
    assert rec["batch_id"] == "req:iter:5:batch"
    assert rec["items"][0]["alias"] == "p1"
    assert "b64" not in str(rec)


def test_homogeneous_delegate_sequence_result_retains_up_to_fifteen_items() -> None:
    items = [
        build_batch_item_result_row(
            alias=f"read_{index}",
            action_type=DELEGATE_SUBTASK_ACTION_TYPE,
            execution_state="executed",
            outputs={
                "status": "completed",
                "profile": "harness.observation",
                "result": {"reading": "A"},
            },
        )
        for index in range(12)
    ]
    record = build_action_batch_result_record(
        batch_id="req:iter:9:batch",
        items=items,
        source_turn_index=9,
    )
    assert len(record["items"]) == 12

    mixed_items = [
        build_batch_item_result_row(
            alias="hydrate",
            action_type="hydrate_artifact_refs",
            execution_state="executed",
        ),
        *items[:3],
    ]
    mixed_record = build_action_batch_result_record(
        batch_id="req:iter:10:batch",
        items=mixed_items,
        source_turn_index=10,
    )
    assert len(mixed_record["items"]) == 4


def test_sequence_audit_summaries_cover_all_items() -> None:
    plan = action_plan_with_canonical_actions(
        actions=(
            ActionPlanAction("a", "noop", {"x": 1}),
            ActionPlanAction("b", "noop", {"y": 2}),
        ),
        rationale="batch",
        idempotency_key="idem-batch",
    )
    req = build_sequence_tool_request_summary(plan)
    assert len(req["actions"]) == 2
    result = build_sequence_tool_result_summary({
        "batch_id": "b-1",
        "source_turn_index": 1,
        "items": [
            project_sequence_item_row({
                "alias": "a", "action_type": "noop", "execution_state": "executed",
            }),
            project_sequence_item_row({
                "alias": "b", "action_type": "noop", "execution_state": "retryable_error",
                "error": {"reason_code": "x", "retryable": True},
            }),
        ],
    })
    assert result is not None
    assert len(result["items"]) == 2
    assert result["items"][1]["execution_state"] == "retryable_error"
