"""Harness tests for opaque domain prompt runtime projection seam."""

from __future__ import annotations

import sys
import types

from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_closure_state, new_mission_state, new_resolution_state
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document


def _composed() -> ComposedTurnInput:
    return ComposedTurnInput(
        blocks=(
            TurnBlock(
                content="stable doctrine",
                metadata={
                    "harness.prompt_block": {
                        "layer": "harness_trunk",
                        "block_id": "harness_trunk",
                    }
                },
            ),
        ),
        surface_payloads={},
        tool_handlers={"noop": lambda payload: payload},
    )


def test_choose_action_includes_opaque_domain_runtime_projection(monkeypatch) -> None:
    """Harness transports domain projection without interpreting deed fields."""

    def _fake_builder(*, launch_context, resolution_items):
        assert launch_context.get("dossier_id") == "d1"
        assert any(i.get("item_id") == "old" for i in resolution_items)
        return {
            "schema": "test.projection.v1",
            "active_handoff_context": {
                "mapping_artifact_ref": "feature_graph:mapping:current",
                "source_ir_artifact_ref": "feature_graph:ir:current",
                "lineage_status": "current",
                "selected_for_next_preview": True,
            },
            "historical_lineage_context": {
                "note": "historical only",
                "items": [{"item_id": "old", "lineage_epoch": "historical"}],
            },
            "hot_artifact_refs": [
                "feature_graph:mapping:current",
                "feature_graph:ir:current",
            ],
        }

    fake_mod = types.ModuleType("harness_test_domain_prompt_projection")
    fake_mod.build_prompt_runtime_projection = _fake_builder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "harness_test_domain_prompt_projection", fake_mod)

    resolution_state = new_resolution_state(
        items=[
            {
                "item_id": "old",
                "title": "Old mapping",
                "kind": "mapping_scope",
                "status": "open",
                "evidence_refs": ["feature_graph:mapping:old"],
            }
        ],
        updated_at_epoch_seconds=42.0,
    )
    mission_state = new_mission_state(
        mission_id="mission-1",
        loop_family="orchestration_kernel",
        objective="Verify projection seam.",
        resolution_state=resolution_state,
        closure_state=new_closure_state(
            overall_status="in_review",
            updated_at_epoch_seconds=42.0,
        ),
        updated_at_epoch_seconds=42.0,
    )
    loop_memory = LoopMemoryState()
    loop_memory.iterations = 2
    loop_memory.continuity.latest_refs = {
        "feature_graph:mapping:current": "feature_graph:mapping:current",
        "feature_graph:mapping:old": "feature_graph:mapping:old",
        "feature_graph:ir:current": "feature_graph:ir:current",
    }
    loop_memory.continuity.resolution_state = resolution_state
    context = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-proj",
        loop_memory=loop_memory,
        request_id_prefix="req-proj",
        opaque_run_context={},
        prompt_event_observer=None,
        raw_llm_io_observer=None,
    )
    projection = SharedStateProjection(
        mission_state=mission_state,
        resolution_state=resolution_state,
        latest_refs=dict(loop_memory.continuity.latest_refs),
        active_item_id=None,
    )
    doc = build_choose_action_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={
            "run_id": "r-1",
            "dossier_id": "d1",
            "domain_prompt_runtime_projection_module": "harness_test_domain_prompt_projection",
        },
        context=context,
        projection=projection,
        journal_verbatim_keep_n=3,
    )
    run_context = doc.prompt_body["run_context"]
    assert "domain_runtime_projection" in run_context
    projected = run_context["domain_runtime_projection"]
    assert projected["schema"] == "test.projection.v1"
    assert projected["historical_lineage_context"]["items"][0]["item_id"] == "old"
    assert "active_handoff_context" in projected
    assert "domain_prompt_runtime_projection_module" not in run_context["launch_context"]
