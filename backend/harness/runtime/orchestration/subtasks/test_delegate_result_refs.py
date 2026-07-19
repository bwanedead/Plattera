"""Tests for delegate result refs (M13)."""

from __future__ import annotations

import json
from typing import Any

from harness.audit.delegate_subtask_timeline import render_delegate_subtask_section
from harness.execution.contracts import ExecutionStepRequest
from harness.runtime.memory.loop_state import LoopMemoryState
from harness.runtime.memory.resume_snapshot import build_kernel_resume_snapshot, parse_kernel_resume_snapshot
from harness.runtime.orchestration.action_batch import build_batch_item_result_row
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.delegate_result_hydration import (
    install_delegate_result_hydration,
    wrap_hydrate_handler_with_delegate_results,
)
from harness.runtime.orchestration.subtasks.delegate_result_refs import (
    build_delegate_result_record,
    build_delegate_result_ref_id,
    hydrate_delegate_result_refs,
    register_delegate_result_record,
    validate_stored_delegate_result_record,
)
from harness.execution.executor import ExecutionExecutor
from harness.execution.session import ExecutionSessionManager


def _sample_outputs(*, status: str = "completed", result: dict | None = None) -> dict:
    return {
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "subtask_id": "read_bearing",
        "profile": "transcript_edit.visual_source_observation",
        "status": status,
        "input_refs": ["image:derived:abc123"],
        "result": result
        or {
            "source_visible_text": "N. 4° 00' W., 1638 feet distant,",
            "task_response": "Observed bearing line.",
        },
        "subtask_trace": {
            "model": "gpt-5.4",
            "prompt_char_count": 4151,
            "image_attachment_count": 1,
            "hydration_seconds": 0.12,
            "prompt_build_seconds": 0.01,
            "model_call_seconds": 18.42,
            "output_normalize_seconds": 0.01,
            "wall_seconds": 18.56,
            "total_seconds": 18.56,
            "started_at_epoch_seconds": 1_700_000_000.0,
            "finished_at_epoch_seconds": 1_700_000_018.56,
            "retry_count": 0,
            "image_refs": [
                {
                    "ref_id": "image:derived:abc123",
                    "width_height": [800, 600],
                    "size_bytes": 42_000,
                    "mime_type": "image/png",
                    "b64": "must strip",
                }
            ],
            "raw_prompt_text": "must strip",
            "b64": "must strip",
        },
    }


def test_delegate_ref_id_uses_alias() -> None:
    ref = build_delegate_result_ref_id(
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=3,
    )
    assert ref == "subtask:turn8:read_parcel1_bearing"


def test_duplicate_aliases_get_unique_refs() -> None:
    first = build_delegate_result_ref_id(
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=1,
        duplicate_index=1,
    )
    second = build_delegate_result_ref_id(
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=2,
        duplicate_index=2,
    )
    assert first == "subtask:turn8:read_parcel1_bearing"
    assert second == "subtask:turn8:read_parcel1_bearing:2"


def test_missing_alias_falls_back_to_action_index() -> None:
    ref = build_delegate_result_ref_id(
        turn_index=8,
        alias="",
        action_index=3,
    )
    assert ref == "subtask:turn8:action3"


def test_no_alias_record_survives_resume_and_hydrates() -> None:
    ref_id = build_delegate_result_ref_id(turn_index=8, alias="", action_index=3)
    record = build_delegate_result_record(
        ref_id=ref_id,
        turn_index=8,
        alias="",
        action_index=3,
        action_inputs={
            "profile": "p",
            "task": "Read bearing",
            "context_refs": ["image:derived:a"],
        },
        outputs=_sample_outputs(),
    )
    assert record["alias"] == "action3"

    loop_memory = LoopMemoryState()
    register_delegate_result_record(loop_memory.continuity, record)

    from harness.execution.contracts import ExecutionSessionStartRequest

    executor = ExecutionExecutor()
    session_manager = ExecutionSessionManager(executor=executor)
    session_manager.start_session(
        ExecutionSessionStartRequest(run_id="run", session_id="sess")
    )
    snapshot = build_kernel_resume_snapshot(
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id="sess",
        next_iteration=9,
    )
    restored, start, err = parse_kernel_resume_snapshot(snapshot)
    assert err is None
    assert start == 9
    assert len(restored.continuity.delegate_subtask_results) == 1
    restored_record = restored.continuity.delegate_subtask_results[0]
    assert restored_record["alias"] == "action3"
    assert restored_record["ref_id"] == "subtask:turn8:action3"

    results, errors = hydrate_delegate_result_refs(
        restored.continuity.delegate_subtask_results,
        ["subtask:turn8:action3"],
    )
    assert not errors
    assert results[0]["ref_id"] == "subtask:turn8:action3"


def test_validate_stored_record_normalizes_legacy_empty_alias() -> None:
    normalized = validate_stored_delegate_result_record(
        {
            "ref_id": "subtask:turn8:action3",
            "kind": "delegate_subtask_result",
            "turn_index": 8,
            "alias": "",
            "action_index": 3,
            "status": "completed",
            "result": {"source_visible_text": "N. 4° 00' W."},
        }
    )
    assert normalized is not None
    assert normalized["alias"] == "action3"


def test_install_delegate_result_hydration_refreshes_records_provider() -> None:
    first_record = build_delegate_result_record(
        ref_id="subtask:turn1:first",
        turn_index=1,
        alias="first",
        action_index=1,
        action_inputs={"profile": "p", "task": "t", "context_refs": ["image:derived:a"]},
        outputs=_sample_outputs(result={"source_visible_text": "first-run"}),
    )
    second_record = build_delegate_result_record(
        ref_id="subtask:turn2:second",
        turn_index=2,
        alias="second",
        action_index=1,
        action_inputs={"profile": "p", "task": "t", "context_refs": ["image:derived:b"]},
        outputs=_sample_outputs(result={"source_visible_text": "second-run"}),
    )

    def base_handler(_request: ExecutionStepRequest) -> dict[str, Any]:
        return {"executed": True, "outputs": {"results": [], "errors": []}}

    executor = ExecutionExecutor()
    executor.register("hydrate_artifact_refs", base_handler)

    install_delegate_result_hydration(executor, lambda: [first_record])
    install_delegate_result_hydration(executor, lambda: [second_record])

    handler = executor.handlers["hydrate_artifact_refs"]
    result = handler(
        ExecutionStepRequest(
            session_id="s",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": ["subtask:turn2:second"]},
        )
    )
    outputs = result["outputs"]
    assert outputs["hydrated_count"] == 1
    assert outputs["results"][0]["ref_id"] == "subtask:turn2:second"
    assert outputs["results"][0]["result"]["source_visible_text"] == "second-run"

    stale = handler(
        ExecutionStepRequest(
            session_id="s",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": ["subtask:turn1:first"]},
        )
    )
    stale_errors = stale["outputs"]["errors"]
    assert stale_errors[0]["code"] == "ref_not_found"


def test_record_stores_bounded_fields_and_strips_binary() -> None:
    record = build_delegate_result_record(
        ref_id="subtask:turn8:read_parcel1_bearing",
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=3,
        action_inputs={
            "profile": "transcript_edit.visual_source_observation",
            "task": "Read the exact visible bearing",
            "target_entity_id": "p1_bearing",
            "context_refs": ["image:derived:abc123"],
        },
        outputs=_sample_outputs(),
    )
    assert record["ref_id"] == "subtask:turn8:read_parcel1_bearing"
    assert record["profile"] == "transcript_edit.visual_source_observation"
    assert record["target_entity_id"] == "p1_bearing"
    assert record["context_refs"] == ["image:derived:abc123"]
    assert record["status"] == "completed"
    assert "source_visible_text" in record["result"]
    trace = record.get("subtask_trace") or {}
    assert trace.get("model") == "gpt-5.4"
    assert trace.get("wall_seconds") == 18.56
    assert trace.get("model_call_seconds") == 18.42
    assert trace.get("total_seconds") == 18.56
    image_refs = trace.get("image_refs")
    assert isinstance(image_refs, list) and image_refs
    assert image_refs[0].get("ref_id") == "image:derived:abc123"
    assert "b64" not in image_refs[0]
    assert "raw_prompt_text" not in trace
    assert "b64" not in trace


def test_hydrate_delegate_ref_returns_payload_without_rerun() -> None:
    record = build_delegate_result_record(
        ref_id="subtask:turn8:read_parcel1_bearing",
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=3,
        action_inputs={
            "profile": "p",
            "task": "t",
            "context_refs": ["image:derived:abc123"],
        },
        outputs=_sample_outputs(),
    )
    results, errors = hydrate_delegate_result_refs([record], ["subtask:turn8:read_parcel1_bearing"])
    assert not errors
    assert len(results) == 1
    payload = results[0]
    assert payload["kind"] == "delegate_subtask_result"
    assert payload["result"]["source_visible_text"].startswith("N. 4")


def test_hydrate_unknown_delegate_ref_fails_softly() -> None:
    results, errors = hydrate_delegate_result_refs([], ["subtask:turn8:missing"])
    assert not results
    assert errors[0]["code"] == "ref_not_found"


def test_wrap_hydrate_handler_partitions_subtask_refs() -> None:
    record = build_delegate_result_record(
        ref_id="subtask:turn8:read_parcel1_bearing",
        turn_index=8,
        alias="read_parcel1_bearing",
        action_index=1,
        action_inputs={"profile": "p", "task": "t", "context_refs": ["image:derived:a"]},
        outputs=_sample_outputs(),
    )

    def base_handler(request: ExecutionStepRequest) -> dict:
        ref_ids = list(request.inputs.get("ref_ids") or [])
        return {
            "executed": True,
            "outputs": {
                "results": [{"ref_id": ref_ids[0], "kind": "image", "text": "ok"}],
                "errors": [],
                "hydrated_count": 1,
            },
        }

    wrapped = wrap_hydrate_handler_with_delegate_results(base_handler, lambda: [record])
    result = wrapped(
        ExecutionStepRequest(
            session_id="s",
            action_id="hydrate_artifact_refs",
            inputs={
                "ref_ids": [
                    "subtask:turn8:read_parcel1_bearing",
                    "image:derived:other",
                ]
            },
        )
    )
    outputs = result["outputs"]
    assert outputs["hydrated_count"] == 2
    kinds = {row.get("kind") for row in outputs["results"]}
    assert "delegate_subtask_result" in kinds
    assert "image" in kinds


def test_timeline_renders_delegate_ref() -> None:
    lines = render_delegate_subtask_section(
        alias="read_parcel1_bearing",
        inputs={
            "profile": "transcript_edit.visual_source_observation",
            "task": "Read bearing",
            "target_entity_id": "p1_bearing",
            "context_refs": ["image:derived:abc123"],
        },
        item={
            "alias": "read_parcel1_bearing",
            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
            "execution_state": "executed",
            "delegate_result_ref": "subtask:turn8:read_parcel1_bearing",
            "delegate_subtask": {
                "subtask_id": "read_parcel1_bearing",
                "profile": "transcript_edit.visual_source_observation",
                "status": "completed",
                "target_entity_id": "p1_bearing",
                "input_refs": ["image:derived:abc123"],
                "result": {"source_visible_text": "N. 4° 00' W."},
            },
        },
    )
    assert any("subtask:turn8:read_parcel1_bearing" in line for line in lines)
    assert any("target_entity_id: `p1_bearing`" in line for line in lines)


def test_resume_snapshot_preserves_delegate_results() -> None:
    loop_memory = LoopMemoryState()
    register_delegate_result_record(
        loop_memory.continuity,
        build_delegate_result_record(
            ref_id="subtask:turn8:read_parcel1_bearing",
            turn_index=8,
            alias="read_parcel1_bearing",
            action_index=1,
            action_inputs={"profile": "p", "task": "t", "context_refs": ["image:derived:a"]},
            outputs=_sample_outputs(),
        ),
    )
    from harness.execution.contracts import ExecutionSessionStartRequest

    executor = ExecutionExecutor()
    session_manager = ExecutionSessionManager(executor=executor)
    session_manager.start_session(
        ExecutionSessionStartRequest(run_id="run", session_id="sess")
    )
    snapshot = build_kernel_resume_snapshot(
        loop_memory=loop_memory,
        session_manager=session_manager,
        session_id="sess",
        next_iteration=9,
    )
    restored, start, err = parse_kernel_resume_snapshot(snapshot)
    assert err is None
    assert start == 9
    assert len(restored.continuity.delegate_subtask_results) == 1
    ref = restored.continuity.delegate_subtask_results[0]["ref_id"]
    results, errors = hydrate_delegate_result_refs(
        restored.continuity.delegate_subtask_results,
        [ref],
    )
    assert not errors
    assert results[0]["ref_id"] == ref


def test_size_caps_truncate_long_task_and_result() -> None:
    long_task = "x" * 5000
    long_value = "y" * 5000
    record = build_delegate_result_record(
        ref_id="subtask:turn1:big",
        turn_index=1,
        alias="big",
        action_index=1,
        action_inputs={
            "profile": "p",
            "task": long_task,
            "context_refs": ["image:derived:a"],
        },
        outputs=_sample_outputs(result={"source_visible_text": long_value}),
    )
    assert len(record["task"]) <= 400
    serialized = json.dumps(record["result"], default=str)
    assert len(serialized) <= 2400


def test_validate_stored_delegate_result_record_rejects_invalid() -> None:
    assert validate_stored_delegate_result_record({"ref_id": "not-subtask"}) is None


def test_batch_row_includes_delegate_result_ref() -> None:
    row = build_batch_item_result_row(
        alias="read_bearing",
        action_type=DELEGATE_SUBTASK_ACTION_TYPE,
        execution_state="executed",
        outputs=_sample_outputs(),
        delegate_result_ref="subtask:turn8:read_bearing",
    )
    assert row["delegate_result_ref"] == "subtask:turn8:read_bearing"
