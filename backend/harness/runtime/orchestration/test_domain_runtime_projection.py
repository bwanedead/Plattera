"""Harness tests for sealed opaque domain prompt runtime projection seam."""

from __future__ import annotations

import logging
import sys
import types
from dataclasses import dataclass

from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_closure_state, new_mission_state, new_resolution_state
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document
from harness.runtime.runner.runner import _with_domain_policy_context


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


@dataclass(frozen=True)
class _FakeManifest:
    domain_id: str = "deed_to_ir"
    prompt_runtime_projection_module_ref: str = "harness_test_domain_prompt_projection"
    projection_module_ref: str = "should.not.be.used.for.prompt"
    closure_policy: object | None = None
    work_graph_policy: object | None = None


@dataclass(frozen=True)
class _FakeAdapter:
    manifest: _FakeManifest = _FakeManifest()

    def build_turn_surface(self, launch_context):
        raise AssertionError("not used")


def test_runner_seals_prompt_hook_from_manifest_not_launch_override() -> None:
    sealed = _with_domain_policy_context(
        {
            "dossier_id": "d1",
            "domain_prompt_runtime_projection_module": "evil.untrusted.module",
        },
        _FakeAdapter(),
    )
    assert sealed["domain_prompt_runtime_projection_module"] == (
        "harness_test_domain_prompt_projection"
    )


def test_choose_action_demotes_cold_refs_and_orders_domain_projection(monkeypatch) -> None:
    """Superseded mapping leaves exact_refs; domain projection precedes work graph."""

    def _fake_builder(*, launch_context, resolution_items):
        del launch_context, resolution_items
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
                "items": [
                    {
                        "item_id": "old",
                        "lineage_epoch": "historical",
                        "tied_artifact_refs": ["feature_graph:mapping:old"],
                    }
                ],
            },
            "hot_artifact_refs": [
                "feature_graph:mapping:current",
                "feature_graph:ir:current",
            ],
            "cold_artifact_refs": ["feature_graph:mapping:old"],
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
            # Sealed by runner in production; tests inject the trusted path directly.
            "domain_prompt_runtime_projection_module": "harness_test_domain_prompt_projection",
        },
        context=context,
        projection=projection,
        journal_verbatim_keep_n=3,
    )
    run_context = doc.prompt_body["run_context"]
    keys = list(run_context.keys())
    assert keys.index("domain_runtime_projection") < keys.index("projection")

    projected = run_context["domain_runtime_projection"]
    assert projected["historical_lineage_context"]["items"][0]["item_id"] == "old"
    assert "feature_graph:mapping:old" in projected["cold_artifact_refs"]

    exact = ((run_context["projection"].get("latest_refs") or {}).get("exact_refs") or {})
    assert "feature_graph:mapping:current" in exact
    assert "feature_graph:mapping:old" not in exact
    assert "feature_graph:ir:current" in exact


def test_configured_hook_failure_emits_warning(monkeypatch, caplog) -> None:
    def _boom(*, launch_context, resolution_items):
        del launch_context, resolution_items
        raise RuntimeError("projection_boom")

    fake_mod = types.ModuleType("harness_test_domain_prompt_projection_boom")
    fake_mod.build_prompt_runtime_projection = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "harness_test_domain_prompt_projection_boom", fake_mod)

    loop_memory = LoopMemoryState()
    context = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-boom",
        loop_memory=loop_memory,
        request_id_prefix="req-boom",
        opaque_run_context={},
        prompt_event_observer=None,
        raw_llm_io_observer=None,
    )
    with caplog.at_level(logging.WARNING):
        doc = build_choose_action_prompt_document(
            composed_input=_composed(),
            opaque_launch_context={
                "run_id": "r-boom",
                "domain_prompt_runtime_projection_module": (
                    "harness_test_domain_prompt_projection_boom"
                ),
            },
            context=context,
            projection=None,
            journal_verbatim_keep_n=3,
        )
    assert "domain_runtime_projection" not in doc.prompt_body.get("run_context", {})
    assert any("domain_prompt_runtime_projection_failed" in r.message for r in caplog.records)
