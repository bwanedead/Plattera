from __future__ import annotations

import json

from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.composition.contracts import ComposedTurnInput
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document
from harness.runtime.orchestration.prompt_budget import build_prompt_budget_report

LONG_TAIL = "late-run tail prose " * 200


def _synthetic_late_run_context() -> tuple[OrchestratorContext, SharedStateProjection]:
    loop_memory = LoopMemoryState()
    loop_memory.iterations = 12
    cont = loop_memory.continuity
    cont.latest_refs = {
        "final": "artifact://final",
        "working": "artifact://working",
        **{f"old_image_{index}": f"image://stale-{index}" for index in range(20)},
    }
    cont.kernel_step_result_records = [
        {
            "kernel_turn_index": turn,
            "action_type": "read_artifact",
            "execution_state": "completed",
            "outputs_for_continuity": {"text": LONG_TAIL},
            "artifact_refs": [f"artifact://turn-{turn}"],
        }
        for turn in range(1, 12)
    ]
    resolution = new_resolution_state(
        items=[
            {
                "item_id": f"closed-{index}",
                "title": f"Closed {index}",
                "kind": "claim",
                "status": "closed",
                "determined_value": f"v-{index}",
                "summary": LONG_TAIL,
                "verification_basis": LONG_TAIL,
                "evidence_refs": [f"artifact://evidence-{index}"],
                "covered_units": [
                    {
                        "unit_id": f"closed-{index}-unit",
                        "status": "closed",
                        "determined_value": f"u-{index}",
                        "verification_basis": LONG_TAIL,
                    }
                ],
            }
            for index in range(8)
        ]
    )
    mission = new_mission_state(
        mission_id="m-late",
        loop_family="orchestration_kernel",
        resolution_state=resolution,
    )
    context = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-late",
        loop_memory=loop_memory,
        request_id_prefix="req-late",
    )
    projection = SharedStateProjection(
        mission_state=mission,
        resolution_state=resolution,
        latest_refs=dict(cont.latest_refs),
    )
    return context, projection


def test_late_run_prompt_smaller_than_uncompacted_baseline() -> None:
    context, projection = _synthetic_late_run_context()
    doc = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(blocks=()),
        opaque_launch_context={},
        context=context,
        projection=projection,
        journal_verbatim_keep_n=2,
    )
    assert doc.prompt_budget is not None
    projected_resolution = doc.prompt_body["run_context"]["projection"]["resolution_state"]
    assert LONG_TAIL not in json.dumps(projected_resolution)

    cont = context.loop_memory.continuity
    baseline_body = {
        "run_context": {
            "latest_refs": dict(cont.latest_refs),
            "projection": {
                "resolution_state": {
                    "items": [
                        {
                            "item_id": f"closed-{index}",
                            "summary": LONG_TAIL,
                            "verification_basis": LONG_TAIL,
                            "evidence_refs": [f"artifact://evidence-{index}"],
                        }
                        for index in range(8)
                    ]
                }
            },
        },
        "structured_state": {
            # Uncompacted baseline: raw continuity result records (not a live prompt lane).
            "recent_kernel_step_result_records": list(cont.kernel_step_result_records),
        },
    }
    baseline = build_prompt_budget_report(
        instruction_text=doc.instruction_text,
        prompt_body=baseline_body,
    )
    assert doc.prompt_budget["buckets"]["total_prompt_chars"] < baseline["buckets"]["total_prompt_chars"]
    assert doc.prompt_budget["buckets"]["resolution_state"] < baseline["buckets"]["resolution_state"]
