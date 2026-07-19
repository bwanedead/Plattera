"""BR-021 integration: admission, prompt projection, and contact acknowledgement."""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import patch

import pytest

from domains.mapping.deed_to_ir.execution.draft_result_views import build_save_ir_artifact_view
from domains.mapping.deed_to_ir.execution.mapping_result_views import (
    SCHEMA_SUBMIT_IR_FOR_MAPPING,
    build_submit_ir_for_mapping_view,
)
from domains.mapping.deed_to_ir.execution.result_view_common import build_working_head_continuity_key
from domains.mapping.transcript_edit.execution.result_views import build_hydrate_artifact_refs_view
from harness.execution.agent_result_view import MAX_AGENT_RESULT_VIEW_CHARS, build_agent_result_view
from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionRefusal,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_closure_state, new_mission_state, new_resolution_state
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.result_delivery import (
    MAX_LATEST_ACTION_RESULTS_CHARS,
    MAX_RESULT_CONTACTS,
    admit_pending_result_delivery,
    measure_compact_json_chars,
    project_latest_action_results,
)
from harness.runtime.memory.resume_snapshot import (
    build_kernel_resume_snapshot,
    parse_kernel_resume_snapshot,
)
from harness.runtime.orchestration.action_sequence import ActionPlanAction
from harness.runtime.orchestration.action_sequence_hooks import (
    _consume_sequence_step_result,
    _execute_parallel_delegate_sequence,
    _execute_sequence_items,
)
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.delegate_batch_execution import DelegateParallelOutcome
from harness.runtime.orchestration.delegate_wave_trace import DelegateWaveTiming
from harness.runtime.orchestration.trace_collector import KernelTraceCollector
from harness.runtime.orchestration.llm_prompt_builder import (
    build_choose_action_prompt_document,
    build_compaction_prompt_document,
    build_repair_prompt_document,
    build_resume_prompt_document,
    build_state_repair_prompt_document,
    build_turn_recovery_prompt_document,
)
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.llm_turn_lifecycle import LlmTurnPreChooseActionParticipant
from harness.runtime.orchestration.result_delivery_hooks import (
    admit_recorded_execution_result,
    acknowledge_prompt_result_delivery_contact,
    build_result_delivery_contact_metadata,
    make_result_delivery_contact_id,
)
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.tool_batch_policy import ToolBatchPolicy


def _pad_outputs(chars: int) -> dict[str, Any]:
    base = {"pad": ""}
    overhead = measure_compact_json_chars(base)
    return {"pad": "x" * (chars - overhead)}


def _dispatch(
    *,
    action_id: str = "tool_a",
    executed: bool = True,
    outputs: dict[str, Any] | None = None,
    artifact_refs: tuple[str, ...] = (),
    view=None,
    refusal: ExecutionRefusal | None = None,
) -> ActionDispatchResult:
    return ActionDispatchResult(
        action_id=action_id,
        executed=executed,
        outputs=dict(outputs or {}),
        artifact_refs=artifact_refs,
        agent_result_view=view,
        refusal=refusal,
    )


def _step(
    *,
    result: ActionDispatchResult | None,
    execution_state: ExecutionState = ExecutionState.EXECUTED,
    session_id: str = "s",
    idempotency_key: str = "ik",
) -> ExecutionStepResult:
    record = None
    if result is not None:
        record = SessionExecutionRecord(
            session_id=session_id,
            run_id="r",
            request=ExecutionStepRequest(
                session_id=session_id,
                action_id=result.action_id,
                inputs={},
                idempotency_key=idempotency_key,
            ),
            result=result,
        )
    return ExecutionStepResult(
        session_id=session_id,
        idempotency_key=idempotency_key,
        execution_state=execution_state,
        dashboard=ExecutionDashboard(
            latest_refs=ExecutionLatestRefs(refs={}),
            budgets_remaining={},
            last_refusal=result.refusal if result is not None else None,
        ),
        refusal=result.refusal if result is not None else None,
        record=record,
    )


def _composed() -> ComposedTurnInput:
    return ComposedTurnInput(
        blocks=(TurnBlock(content="block"),),
        surface_payloads={},
        tool_handlers={"noop": lambda x: x},
    )


def _context(lm: LoopMemoryState | None = None) -> OrchestratorContext:
    loop_memory = lm or LoopMemoryState()
    if loop_memory.iterations <= 0:
        loop_memory.iterations = 3
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-prd",
        loop_memory=loop_memory,
        request_id_prefix="req-prd",
        opaque_run_context={},
        prompt_event_observer=None,
        raw_llm_io_observer=None,
    )


def _projection(*, latest_refs: dict[str, Any] | None = None) -> SharedStateProjection:
    resolution_state = new_resolution_state(
        items=[{"item_id": "item-1", "title": "t", "kind": "review", "status": "open"}],
        updated_at_epoch_seconds=1.0,
    )
    mission_state = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        objective="o",
        resolution_state=resolution_state,
        closure_state=new_closure_state(overall_status="open", updated_at_epoch_seconds=1.0),
        updated_at_epoch_seconds=1.0,
    )
    return SharedStateProjection(
        mission_state=mission_state,
        resolution_state=resolution_state,
        latest_refs=dict(latest_refs or {}),
        active_item_id="item-1",
    )


def _valid_plan_json() -> str:
    return json.dumps(
        {
            "action_type": "noop",
            "action_inputs": {},
            "idempotency_key": "ik-1",
            "skip_execution": True,
            "wait_for_human": False,
            "complete_run": False,
            "rationale": "t",
            "state_patch": None,
            "continuity_journal_entry": {"llm_continuity_turn": True},
        }
    )


# --- Hook unit helpers -------------------------------------------------------


def test_make_contact_id_stable_and_bounded() -> None:
    a = make_result_delivery_contact_id(
        request_id_prefix="req-prd",
        iteration=3,
        prompt_mode="full_choose_action",
    )
    b = make_result_delivery_contact_id(
        request_id_prefix="req-prd",
        iteration=3,
        prompt_mode="full_choose_action",
    )
    c = make_result_delivery_contact_id(
        request_id_prefix="req-prd",
        iteration=4,
        prompt_mode="full_choose_action",
    )
    assert a == b
    assert a != c
    assert "full_choose_action" in a
    assert len(a) <= 128


def test_make_contact_id_digests_oversized_prefix() -> None:
    import hashlib

    huge = "p" * 200
    raw_identity = f"{huge}|1|resume|orchestration_kernel_choose_action"
    cid = make_result_delivery_contact_id(
        request_id_prefix=huge,
        iteration=1,
        prompt_mode="resume",
    )
    assert cid.startswith("sha256:")
    assert len(cid) <= 128
    assert huge[:24] not in cid
    assert cid == f"sha256:{hashlib.sha256(raw_identity.encode('utf-8')).hexdigest()}"
    assert cid == make_result_delivery_contact_id(
        request_id_prefix=huge,
        iteration=1,
        prompt_mode="resume",
    )


def test_admit_recorded_execution_result_skips_absent_record() -> None:
    deliveries: list[dict[str, Any]] = []
    admit_recorded_execution_result(
        deliveries,
        step_result=_step(result=None),
        source_turn_index=1,
        action_index=1,
        action_alias="a",
    )
    assert deliveries == []


def test_admit_recorded_execution_result_logs_rejection(caplog: pytest.LogCaptureFixture) -> None:
    deliveries: list[dict[str, Any]] = []
    outcome = type("O", (), {"status": "rejected", "reason_code": "pending_result_delivery_invalid_row", "delivery_id": "x"})()
    with patch(
        "harness.runtime.orchestration.result_delivery_hooks.admit_pending_result_delivery",
        return_value=outcome,
    ):
        with caplog.at_level(logging.WARNING):
            admit_recorded_execution_result(
                deliveries,
                step_result=_step(result=_dispatch(outputs={"ok": True})),
                source_turn_index=2,
                action_index=1,
                action_alias="alias",
            )
    assert any("pending_result_delivery_admission_rejected" in r.message for r in caplog.records)
    assert deliveries == []


# --- Admission via action sequence -------------------------------------------


class _AdmitSession(ExecutionSessionManager):
    def __init__(self, *, behavior: str = "ok") -> None:
        super().__init__()
        self.behavior = behavior
        self.requests: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.requests.append(request)
        if self.behavior == "raise" and request.action_id == "boom":
            raise RuntimeError("dispatch boom")
        if request.action_id == "fail_once":
            result = _dispatch(
                action_id=request.action_id,
                executed=False,
                refusal=ExecutionRefusal(reason_code="retryable_fail", retryable=True),
            )
            state = ExecutionState.REFUSED
        elif request.action_id == "dedupe_me":
            result = _dispatch(action_id=request.action_id, outputs={"cached": True})
            state = ExecutionState.DEDUPED
        else:
            result = _dispatch(
                action_id=request.action_id,
                outputs={"ok": True},
                artifact_refs=(f"artifact://{request.action_id}",),
            )
            state = ExecutionState.EXECUTED
        return _step(
            result=result,
            execution_state=state,
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
        )


def _policies(*, stop_batch_on_failure: bool = False) -> dict[str, ToolBatchPolicy]:
    # continues_after_item_failure is derived from side_effect_class membership.
    fail_class = "workspace_write" if stop_batch_on_failure else "read_only"
    return {
        "hydrate_artifact_refs": ToolBatchPolicy(
            tool_id="hydrate_artifact_refs",
            allowed=True,
            max_calls_per_batch=4,
            side_effect_class="read_only",
        ),
        "fail_once": ToolBatchPolicy(
            tool_id="fail_once",
            allowed=True,
            max_calls_per_batch=2,
            side_effect_class=fail_class,
        ),
        "boom": ToolBatchPolicy(
            tool_id="boom",
            allowed=True,
            max_calls_per_batch=2,
            side_effect_class=fail_class,
        ),
        "dedupe_me": ToolBatchPolicy(
            tool_id="dedupe_me",
            allowed=True,
            max_calls_per_batch=2,
            side_effect_class="read_only",
        ),
        DELEGATE_SUBTASK_ACTION_TYPE: ToolBatchPolicy(
            tool_id=DELEGATE_SUBTASK_ACTION_TYPE,
            allowed=True,
            max_calls_per_batch=4,
            side_effect_class="read_only",
            can_run_parallel=True,
        ),
    }


def test_admission_executed_single_action() -> None:
    sm = _AdmitSession()
    lm = LoopMemoryState()
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=(ActionPlanAction("a1", "hydrate_artifact_refs", {}),),
        iteration=5,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=False,
    )
    assert sequence_result["items"][0]["execution_state"] == "executed"
    assert len(lm.continuity.pending_result_deliveries) == 1
    row = lm.continuity.pending_result_deliveries[0]
    assert row["action_index"] == 1
    assert row["action_alias"] == "a1"
    assert row["source_turn_index"] == 5
    assert row["representation"] == {"ok": True}


def test_admission_recorded_refusal() -> None:
    sm = _AdmitSession()
    lm = LoopMemoryState()
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=(ActionPlanAction("bad", "fail_once", {}),),
        iteration=2,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=False,
    )
    assert sequence_result["items"][0]["execution_state"] == "retryable_error"
    assert len(lm.continuity.pending_result_deliveries) == 1
    assert lm.continuity.pending_result_deliveries[0]["execution_state"] == "refused"


def test_admission_deduplicated_cached_result() -> None:
    sm = _AdmitSession()
    lm = LoopMemoryState()
    _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=(ActionPlanAction("d1", "dedupe_me", {}),),
        iteration=1,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=False,
    )
    assert len(lm.continuity.pending_result_deliveries) == 1
    assert lm.continuity.pending_result_deliveries[0]["execution_state"] == "deduped"


def test_admission_dispatch_exception_and_skipped_do_not_admit() -> None:
    sm = _AdmitSession(behavior="raise")
    lm = LoopMemoryState()
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=(
            ActionPlanAction("x", "boom", {}),
            ActionPlanAction("y", "hydrate_artifact_refs", {}),
        ),
        iteration=1,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(stop_batch_on_failure=True),
        multi_action=True,
    )
    by_alias = {row["alias"]: row for row in sequence_result["items"]}
    assert by_alias["x"]["execution_state"] == "retryable_error"
    assert by_alias["y"]["execution_state"] == "skipped_due_to_prior_batch_failure"
    assert lm.continuity.pending_result_deliveries == []


def test_admission_stable_one_based_indices_after_prior_failure() -> None:
    sm = _AdmitSession()
    lm = LoopMemoryState()
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=(
            ActionPlanAction("bad", "fail_once", {}),
            ActionPlanAction("ok", "hydrate_artifact_refs", {}),
        ),
        iteration=7,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(stop_batch_on_failure=False),
        multi_action=True,
    )
    assert [row["alias"] for row in sequence_result["items"]] == ["bad", "ok"]
    deliveries = lm.continuity.pending_result_deliveries
    assert [d["action_index"] for d in deliveries] == [1, 2]
    assert [d["action_alias"] for d in deliveries] == ["bad", "ok"]


def test_admission_sequential_multi_action() -> None:
    sm = _AdmitSession()
    lm = LoopMemoryState()
    _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=(
            ActionPlanAction("h1", "hydrate_artifact_refs", {}),
            ActionPlanAction("h2", "hydrate_artifact_refs", {}),
        ),
        iteration=3,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=True,
    )
    assert len(lm.continuity.pending_result_deliveries) == 2
    assert [d["action_index"] for d in lm.continuity.pending_result_deliveries] == [1, 2]


def test_admission_parallel_delegate_path() -> None:
    sm = _AdmitSession()
    lm = LoopMemoryState()
    actions = (
        ActionPlanAction("d1", DELEGATE_SUBTASK_ACTION_TYPE, {"profile_id": "p"}),
        ActionPlanAction("d2", DELEGATE_SUBTASK_ACTION_TYPE, {"profile_id": "p"}),
    )

    def _fake_parallel(**_kwargs: Any):
        outcomes = []
        for item, req in [
            (actions[0], ExecutionStepRequest(
                session_id="s",
                action_id=DELEGATE_SUBTASK_ACTION_TYPE,
                inputs={},
                idempotency_key="ik1",
            )),
            (actions[1], ExecutionStepRequest(
                session_id="s",
                action_id=DELEGATE_SUBTASK_ACTION_TYPE,
                inputs={},
                idempotency_key="ik2",
            )),
        ]:
            del item
            outcomes.append(
                DelegateParallelOutcome(
                    normalized_request=req,
                    dispatch_result=_dispatch(
                        action_id=DELEGATE_SUBTASK_ACTION_TYPE,
                        outputs={"subtask": True},
                    ),
                )
            )
        timing = DelegateWaveTiming(
            wall_elapsed_seconds=0.01,
            started_at_epoch_seconds=1.0,
            finished_at_epoch_seconds=1.01,
        )
        return outcomes, timing

    with patch(
        "harness.runtime.orchestration.action_sequence_hooks.execute_delegate_batch_parallel",
        side_effect=_fake_parallel,
    ):
        with patch(
            "harness.runtime.orchestration.action_sequence_hooks.record_delegate_dispatch",
            side_effect=lambda **kwargs: _step(
                result=kwargs["dispatch_result"],
                execution_state=ExecutionState.EXECUTED,
                session_id=kwargs["session_id"],
                idempotency_key=(kwargs["request"].idempotency_key if kwargs.get("request") else "ik"),
            ),
        ):
            _execute_parallel_delegate_sequence(
                loop_memory=lm,
                session_manager=sm,
                session_id="s",
                actions=actions,
                iteration=9,
                request_id_prefix="req",
                run_id="r",
                sequence_id="seq",
            )
    assert [d["action_index"] for d in lm.continuity.pending_result_deliveries] == [1, 2]
    assert [d["action_alias"] for d in lm.continuity.pending_result_deliveries] == ["d1", "d2"]


def test_admission_does_not_mutate_sequence_result_semantics() -> None:
    sm = _AdmitSession()
    lm = LoopMemoryState()
    sequence_result, _ = _execute_sequence_items(
        loop_memory=lm,
        session_manager=sm,
        session_id="s",
        actions=(ActionPlanAction("a1", "hydrate_artifact_refs", {}),),
        iteration=1,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_policies(),
        multi_action=False,
    )
    item = sequence_result["items"][0]
    assert item["execution_state"] == "executed"
    assert "outputs" in item or "outputs_excerpt" in item or item.get("artifact_refs") is not None
    # Delivery is separate carriage; sequence row is unchanged by projection.
    assert "continuity_key" not in item
    assert "representation_kind" not in item


# --- Prompt projection -------------------------------------------------------


def _seed_delivery(lm: LoopMemoryState, *, artifact_refs: tuple[str, ...] = ()) -> None:
    admit_pending_result_delivery(
        lm.continuity.pending_result_deliveries,
        result=_dispatch(outputs={"seed": True}, artifact_refs=artifact_refs),
        source_turn_index=1,
        action_index=1,
        action_alias="seed",
        execution_state="executed",
    )


@pytest.mark.parametrize(
    "builder",
    [
        build_choose_action_prompt_document,
        build_state_repair_prompt_document,
        build_resume_prompt_document,
        build_turn_recovery_prompt_document,
    ],
)
def test_semantic_prompt_modes_expose_latest_action_results(builder) -> None:
    lm = LoopMemoryState()
    lm.iterations = 4
    _seed_delivery(lm)
    doc = builder(
        composed_input=_composed(),
        opaque_launch_context={},
        context=_context(lm),
        projection=_projection(),
        journal_verbatim_keep_n=3,
    )
    structured = doc.prompt_body["structured_state"]
    assert "latest_action_results" in structured
    assert structured["latest_action_results"]
    assert "continuity_key" not in json.dumps(doc.prompt_body)
    assert "result_delivery_contact" not in doc.prompt_text
    assert "result_delivery_contact" not in json.dumps(doc.prompt_body)
    assert doc.result_delivery_contact is not None
    assert doc.prompt_budget is not None
    assert doc.prompt_budget["buckets"]["latest_action_results"] > 0


def test_semantic_prompt_omits_lane_when_empty() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=3,
    )
    structured = doc.prompt_body.get("structured_state") or {}
    assert "latest_action_results" not in structured
    assert doc.result_delivery_contact is None


def test_repair_and_compaction_omit_latest_action_results() -> None:
    repair = build_repair_prompt_document(
        available_tool_ids=("noop",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="bad_json",
        parse_error_detail="x",
        previous_response_text="{}",
    )
    assert "latest_action_results" not in json.dumps(repair.prompt_body)
    assert repair.result_delivery_contact is None

    compaction = build_compaction_prompt_document(
        prior_compacted_continuity_summary=None,
        journal_entries_to_fold=[],
        kernel_step_records_to_fold=[],
        kernel_step_result_records_to_fold=[],
        target_compacted_summary_chars=100,
    )
    assert "latest_action_results" not in json.dumps(compaction.prompt_body)
    assert compaction.result_delivery_contact is None


def test_prompt_builder_alone_does_not_acknowledge() -> None:
    lm = LoopMemoryState()
    lm.iterations = 2
    _seed_delivery(lm)
    before = list(lm.continuity.pending_result_deliveries[0].get("successful_content_contact_ids") or [])
    build_choose_action_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={},
        context=_context(lm),
        projection=_projection(),
        journal_verbatim_keep_n=3,
    )
    after = list(lm.continuity.pending_result_deliveries[0].get("successful_content_contact_ids") or [])
    assert after == before


def test_lane_budget_projection_receipt_skips_content_contact() -> None:
    """Oversized production projection → real receipt → ack must not contact lane-budget IDs."""
    lm = LoopMemoryState()
    lm.iterations = 3
    for i in range(32):
        admit_pending_result_delivery(
            lm.continuity.pending_result_deliveries,
            result=_dispatch(
                action_id=f"tool_{i}",
                outputs=_pad_outputs(min(4000, MAX_AGENT_RESULT_VIEW_CHARS)),
            ),
            source_turn_index=1,
            action_index=i + 1,
            action_alias=f"a{i}",
            execution_state="executed",
        )
    doc = build_choose_action_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={},
        context=_context(lm),
        projection=_projection(),
        journal_verbatim_keep_n=3,
    )
    assert "latest_action_results" in (doc.prompt_body.get("structured_state") or {})
    assert measure_compact_json_chars(
        doc.prompt_body["structured_state"]["latest_action_results"]
    ) <= MAX_LATEST_ACTION_RESULTS_CHARS
    assert doc.result_delivery_contact is not None
    receipt = doc.result_delivery_contact.contact_receipt
    assert receipt.lane_budget_delivery_ids
    lane_budget_ids = set(receipt.lane_budget_delivery_ids)
    content_ids = set(receipt.content_exposed_delivery_ids)

    acknowledge_prompt_result_delivery_contact(
        lm.continuity.pending_result_deliveries,
        metadata=doc.result_delivery_contact,
    )
    by_id = {row["delivery_id"]: row for row in lm.continuity.pending_result_deliveries}
    for did in lane_budget_ids:
        assert by_id[did].get("successful_content_contact_ids") in (None, [])
    for did in content_ids:
        assert by_id[did].get("successful_content_contact_ids") == [
            doc.result_delivery_contact.contact_id
        ]


# --- Contact acknowledgement -------------------------------------------------


def test_successful_model_response_acknowledges() -> None:
    lm = LoopMemoryState()
    lm.iterations = 3
    _seed_delivery(lm)
    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=lambda *_a, **_k: _valid_plan_json(),
        model_name="fake",
        opaque_launch_context={},
    )
    adapter.choose_action(_context(lm), _projection())
    contacts = lm.continuity.pending_result_deliveries[0]["successful_content_contact_ids"]
    assert len(contacts) == 1
    assert contacts[0] == make_result_delivery_contact_id(
        request_id_prefix="req-prd",
        iteration=3,
        prompt_mode="full_choose_action",
    )


def test_malformed_response_acknowledges_once() -> None:
    lm = LoopMemoryState()
    lm.iterations = 3
    _seed_delivery(lm)
    calls = {"n": 0}

    def caller(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not-json"
        return _valid_plan_json()

    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=caller,
        model_name="fake",
        opaque_launch_context={},
    )
    adapter.choose_action(_context(lm), _projection())
    contacts = lm.continuity.pending_result_deliveries[0]["successful_content_contact_ids"]
    assert len(contacts) == 1


def test_model_caller_exception_does_not_acknowledge() -> None:
    lm = LoopMemoryState()
    lm.iterations = 3
    _seed_delivery(lm)

    def caller(*_a, **_k):
        raise RuntimeError("provider down")

    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=caller,
        model_name="fake",
        opaque_launch_context={},
    )
    with pytest.raises(RuntimeError):
        adapter.choose_action(_context(lm), _projection())
    assert lm.continuity.pending_result_deliveries[0].get("successful_content_contact_ids") == []


def test_compaction_preflight_does_not_acknowledge() -> None:
    lm = LoopMemoryState()
    lm.iterations = 3
    _seed_delivery(lm)
    participant = LlmTurnPreChooseActionParticipant(
        composed_input=_composed(),
        text_model_caller=lambda *_a, **_k: "{}",
        model_name="fake",
        opaque_launch_context={},
        continuity_compaction_prompt_char_threshold=10_000_000,
        continuity_compaction_trigger_fraction=2.0,
        continuity_compaction_max_prompt_chars=10_000_000,
        continuity_journal_verbatim_keep_n=5,
    )
    # Size probe builds the semantic prompt but must not ack pending deliveries.
    participant.before_choose_action(
        _context(lm),
        _projection(),
        tracer=KernelTraceCollector(session_id="s", request_id="req-prd", run_id="r-prd"),
    )
    assert lm.continuity.pending_result_deliveries[0].get("successful_content_contact_ids") == []


def test_replay_same_contact_id_is_noop() -> None:
    lm = LoopMemoryState()
    lm.iterations = 3
    _seed_delivery(lm)
    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=lambda *_a, **_k: _valid_plan_json(),
        model_name="fake",
        opaque_launch_context={},
    )
    ctx = _context(lm)
    adapter.choose_action(ctx, _projection())
    first = list(lm.continuity.pending_result_deliveries[0]["successful_content_contact_ids"])
    # Re-ack same contact id without advancing iteration.
    doc = build_choose_action_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={},
        context=ctx,
        projection=_projection(),
        journal_verbatim_keep_n=3,
    )
    acknowledge_prompt_result_delivery_contact(
        lm.continuity.pending_result_deliveries,
        metadata=doc.result_delivery_contact,
    )
    assert lm.continuity.pending_result_deliveries[0]["successful_content_contact_ids"] == first


def test_two_distinct_contacts_retire_non_hot() -> None:
    lm = LoopMemoryState()
    lm.iterations = 3
    _seed_delivery(lm, artifact_refs=())
    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=lambda *_a, **_k: _valid_plan_json(),
        model_name="fake",
        opaque_launch_context={},
    )
    adapter.choose_action(_context(lm), _projection())
    assert len(lm.continuity.pending_result_deliveries) == 1
    lm.iterations = 4
    adapter.choose_action(_context(lm), _projection())
    assert lm.continuity.pending_result_deliveries == []


def test_hot_ref_retains_after_two_contacts() -> None:
    lm = LoopMemoryState()
    lm.iterations = 3
    hot = "artifact://hot-head"
    _seed_delivery(lm, artifact_refs=(hot,))
    lm.continuity.latest_refs = {"working": hot}
    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=lambda *_a, **_k: _valid_plan_json(),
        model_name="fake",
        opaque_launch_context={},
    )
    proj = _projection(latest_refs={"working": hot})
    adapter.choose_action(_context(lm), proj)
    lm.iterations = 4
    adapter.choose_action(_context(lm), proj)
    assert len(lm.continuity.pending_result_deliveries) == 1
    assert len(lm.continuity.pending_result_deliveries[0]["successful_content_contact_ids"]) == 2


def test_eighth_contact_retires_hot_delivery() -> None:
    deliveries: list[dict[str, Any]] = []
    admit_pending_result_delivery(
        deliveries,
        result=_dispatch(outputs={"ok": True}, artifact_refs=("artifact://hot",)),
        source_turn_index=1,
        action_index=1,
        action_alias="seed",
        execution_state="executed",
    )
    projection = project_latest_action_results(deliveries)
    for i in range(MAX_RESULT_CONTACTS):
        meta = build_result_delivery_contact_metadata(
            request_id_prefix="req",
            iteration=i + 1,
            prompt_mode="full_choose_action",
            contact_receipt=projection.contact_receipt,
            active_attention_refs=("artifact://hot",),
        )
        acknowledge_prompt_result_delivery_contact(deliveries, metadata=meta)
    assert deliveries == []


# --- Lifecycle / production-shaped views ------------------------------------


def test_same_continuity_key_supersedes_via_hooks() -> None:
    deliveries: list[dict[str, Any]] = []
    view1, _ = build_agent_result_view(
        schema_id="t.v1", payload={"n": 1}, continuity_key="map:current"
    )
    view2, _ = build_agent_result_view(
        schema_id="t.v1", payload={"n": 2}, continuity_key="map:current"
    )
    big = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    admit_recorded_execution_result(
        deliveries,
        step_result=_step(result=_dispatch(outputs=big, view=view1)),
        source_turn_index=1,
        action_index=1,
        action_alias="old",
    )
    admit_recorded_execution_result(
        deliveries,
        step_result=_step(result=_dispatch(outputs=big, view=view2)),
        source_turn_index=2,
        action_index=1,
        action_alias="new",
    )
    assert len(deliveries) == 1
    assert deliveries[0]["action_alias"] == "new"


def test_keyless_results_coexist() -> None:
    deliveries: list[dict[str, Any]] = []
    admit_recorded_execution_result(
        deliveries,
        step_result=_step(result=_dispatch(action_id="a", outputs={"a": 1})),
        source_turn_index=1,
        action_index=1,
        action_alias="a",
    )
    admit_recorded_execution_result(
        deliveries,
        step_result=_step(result=_dispatch(action_id="b", outputs={"b": 1})),
        source_turn_index=1,
        action_index=2,
        action_alias="b",
    )
    assert len(deliveries) == 2


def test_resume_round_trip_preserves_pending_rows_and_contact_ids() -> None:
    mem = LoopMemoryState()
    admit_pending_result_delivery(
        mem.continuity.pending_result_deliveries,
        result=_dispatch(outputs={"ok": True}),
        source_turn_index=4,
        action_index=1,
        action_alias="review",
        execution_state="executed",
    )
    mem.continuity.pending_result_deliveries[0]["successful_content_contact_ids"] = [
        "req-prd|3|full_choose_action|orchestration_kernel_choose_action"
    ]
    snap = build_kernel_resume_snapshot(
        loop_memory=mem,
        session_manager=ExecutionSessionManager(),
        session_id="s1",
        next_iteration=5,
    )
    restored, _, err = parse_kernel_resume_snapshot(snap)
    assert err is None
    row = restored.continuity.pending_result_deliveries[0]
    assert row["delivery_id"] == "turn:4:action:1:review"
    assert row["successful_content_contact_ids"] == [
        "req-prd|3|full_choose_action|orchestration_kernel_choose_action"
    ]


def test_admission_prompt_ack_with_deed_to_ir_and_transcript_edit_views() -> None:
    scope = {
        "dossier_id": "d1",
        "transcription_id": "t1",
        "workspace_id": "w1",
        "run_id": "r1",
    }
    continuity = build_working_head_continuity_key(**scope)
    current_ref = "feature_graph:ir:v1"
    deed_view, _ = build_save_ir_artifact_view(
        {
            "ir_artifact_ref": current_ref,
            "draft_ir_ref": current_ref,
            "working_draft_ref": current_ref,
            "draft_version": "v2",
            "draft_sequence_index": 2,
            "graph_id": "graph-1",
            "artifact_id": "graph-1_d2",
            "is_draft": True,
            "node_count": 1,
            "edge_count": 0,
            "course_count": 0,
            "compile_gap_count": 0,
            "judge_finding_count": 0,
            "compile_gaps": [],
            "judge_findings": [],
            "draft_repair_items": [],
            "current_draft_ir": {
                "draft_ir_ref": current_ref,
                "working_draft_ref": current_ref,
                "draft_version": "v2",
                "graph_id": "graph-1",
                "node_count": 1,
                "edge_count": 0,
                "compile_gap_count": 0,
                "judge_finding_count": 0,
                "compile_gaps": [],
                "judge_findings": [],
                "draft_repair_items": [],
                "nodes": [{"id": "n1"}],
                "edges": [],
            },
            "world_bbox": (0.0, 0.0, 1.0, 1.0),
        },
        continuity_key=continuity,
    )
    te_view, _ = build_hydrate_artifact_refs_view(
        {
            "hydrated_count": 1,
            "cap_exceeded": False,
            "results": [
                {
                    "ref_id": "t0:raw:draft_1",
                    "kind": "t0_draft",
                    "text": "Exact T0 text",
                    "metadata": {},
                }
            ],
            "errors": [],
        }
    )
    assert deed_view is not None and te_view is not None

    lm = LoopMemoryState()
    lm.iterations = 2
    big = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    admit_recorded_execution_result(
        lm.continuity.pending_result_deliveries,
        step_result=_step(
            result=_dispatch(
                action_id="save_ir_artifact",
                outputs=big,
                view=deed_view,
                artifact_refs=("feature_graph:ir:v1",),
            )
        ),
        source_turn_index=1,
        action_index=1,
        action_alias="save",
    )
    admit_recorded_execution_result(
        lm.continuity.pending_result_deliveries,
        step_result=_step(
            result=_dispatch(
                action_id="hydrate_artifact_refs",
                outputs={"hydrated_count": 1},
                view=te_view,
            )
        ),
        source_turn_index=1,
        action_index=2,
        action_alias="hydrate",
    )
    # Keyed deed head + keyless transcript-edit coexist; no domain branch in harness.
    assert len(lm.continuity.pending_result_deliveries) == 2

    doc = build_choose_action_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={},
        context=_context(lm),
        projection=_projection(),
        journal_verbatim_keep_n=3,
    )
    lane = doc.prompt_body["structured_state"]["latest_action_results"]
    assert lane
    assert "continuity_key" not in json.dumps(lane)
    assert doc.result_delivery_contact is not None

    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=lambda *_a, **_k: _valid_plan_json(),
        model_name="fake",
        opaque_launch_context={},
    )
    adapter.choose_action(_context(lm), _projection())
    assert all(
        len(row.get("successful_content_contact_ids") or []) == 1
        for row in lm.continuity.pending_result_deliveries
    )


def test_br024_mapping_view_survives_result_delivery_path() -> None:
    """Production-shaped v2 mapping view through BR-021 pending-result delivery."""
    scope = {
        "dossier_id": "d1",
        "transcription_id": "t1",
        "workspace_id": "w1",
        "run_id": "r1",
    }
    continuity = build_working_head_continuity_key(**scope)
    mapping_ref = "feature_graph:mapping:run40"
    ir_ref = "feature_graph:ir:run40"
    critical_crop = "image:derived:fba6f159e40d4010896245d6525d4acf"
    source_question = (
        "Large unexplained endpoint displacement is a source-sanity trigger, "
        "not automatically a deed defect."
    )
    submit_outputs = {
        "mapping_artifact_ref": mapping_ref,
        "compile_artifact_ref": "feature_graph:compile:c1",
        "graph_id": "graph-run40",
        "compiled_feature_count": 2,
        "current_mapping_lineage": {
            "mapping_artifact_ref": mapping_ref,
            "source_ir_artifact_ref": ir_ref,
            "lineage_current": True,
        },
        "mapping_review": {
            "mapping_artifact_ref": mapping_ref,
            "source_ir_artifact_ref": ir_ref,
            "sanity_review": {
                "endpoint_displacement_candidates": [
                    {
                        "feature_id": "parcel_1_boundary",
                        "endpoint_displacement": 100.8495,
                    }
                ],
                "review_questions": [source_question],
                "recommended_source_evidence_refs": [critical_crop],
                "course_leg_tables": [
                    {
                        "feature_id": "parcel_1_traverse",
                        "courses": [
                            {
                                "leg_index": 2,
                                "distance": 618.0,
                                "source_entity_ids": [
                                    "p1_call2_distance",
                                    "p1_call2_bearing",
                                ],
                                "evidence_refs": [critical_crop],
                            }
                        ],
                    }
                ],
                "feature_metrics": [],
            },
        },
        "active_finalization_session": {
            "status": "pending_decisions",
            "lineage": {
                "mapping_artifact_ref": mapping_ref,
                "source_ir_artifact_ref": ir_ref,
            },
            "requirements": {
                "scope_ids": ["parcel_1"],
                "correction_candidates": [],
                "dependency_candidates": [],
            },
            "decisions": {
                "scope_statuses": {},
                "correction_dispositions": {},
                "dependency_dispositions": {},
                "rationales": {},
            },
        },
    }
    mapping_view, omitted = build_submit_ir_for_mapping_view(
        submit_outputs,
        continuity_key=continuity,
    )
    assert omitted is None and mapping_view is not None
    assert mapping_view.schema_id == SCHEMA_SUBMIT_IR_FOR_MAPPING

    lm = LoopMemoryState()
    lm.iterations = 2
    big = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    admit_recorded_execution_result(
        lm.continuity.pending_result_deliveries,
        step_result=_step(
            result=_dispatch(
                action_id="submit_ir_for_mapping",
                outputs=big,
                view=mapping_view,
                artifact_refs=(mapping_ref,),
            )
        ),
        source_turn_index=1,
        action_index=1,
        action_alias="submit",
    )
    doc = build_choose_action_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={},
        context=_context(lm),
        projection=_projection(),
        journal_verbatim_keep_n=3,
    )
    lane_blob = json.dumps(doc.prompt_body["structured_state"]["latest_action_results"])
    assert SCHEMA_SUBMIT_IR_FOR_MAPPING in lane_blob
    assert "100.8495" in lane_blob
    assert critical_crop in lane_blob
    assert source_question in lane_blob
    assert mapping_ref in lane_blob
    assert "continuity_key" not in lane_blob
    assert doc.result_delivery_contact is not None
    assert doc.result_delivery_contact.contact_receipt.content_exposed_delivery_ids

    adapter = LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=lambda *_a, **_k: _valid_plan_json(),
        model_name="fake",
        opaque_launch_context={},
    )
    adapter.choose_action(_context(lm), _projection())
    assert len(lm.continuity.pending_result_deliveries[0]["successful_content_contact_ids"]) == 1


def test_consume_step_admits_without_rewriting_step_result() -> None:
    lm = LoopMemoryState()
    item = ActionPlanAction("a1", "hydrate_artifact_refs", {})
    step = _step(result=_dispatch(outputs={"kept": True}))
    original_outputs = dict(step.record.result.outputs)
    _consume_sequence_step_result(
        loop_memory=lm,
        item=item,
        step_result=step,
        item_rows=[],
        alias_counts={},
        iteration=1,
        multi_action=False,
        policy=None,
        stop_remaining=False,
        action_index=1,
    )
    assert step.record.result.outputs == original_outputs
    assert lm.continuity.pending_result_deliveries[0]["representation"] == {"kept": True}
