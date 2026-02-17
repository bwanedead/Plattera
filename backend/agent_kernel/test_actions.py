"""Tests for deterministic action executor scaffold."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import (
    ActionExecutor,
    ActionExecutorDeps,
    Bundler,
    Compiler,
    EvidenceRetriever,
    Georeferencer,
    Judge,
    PatchProposer,
    StatusSummarizer,
    Validator,
)
from backend.agent_kernel.models import ActionType
from backend.agent_kernel.run_artifact import ArtifactRef, ValidationInline


class _DeterministicServices(
    EvidenceRetriever,
    Compiler,
    Judge,
    Bundler,
    Georeferencer,
    Validator,
    PatchProposer,
    StatusSummarizer,
):
    def retrieve_evidence(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/retrieval/retrieval-001.json")

    def compile(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/compile/compile-001.json")

    def judge(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/judge/judge-001.json")

    def bundle(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/bundle/bundle-001.json")

    def georeference(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/georef/georef-001.json")

    def validate(self, inputs: Mapping[str, Any]) -> ValidationInline:
        del inputs
        return ValidationInline(passed=True, reason_code="ok", checks={"error_count": 0})

    def propose_patch(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {"patch": "noop"}

    def summarize_status(self, inputs: Mapping[str, Any]) -> str:
        del inputs
        return "stable"


def _build_executor() -> ActionExecutor:
    services = _DeterministicServices()
    deps = ActionExecutorDeps(
        evidence_retriever=services,
        compiler=services,
        judge=services,
        bundler=services,
        georeferencer=services,
        validator=services,
        patch_proposer=services,
        status_summarizer=services,
    )
    return ActionExecutor(deps=deps)


def test_executor_supports_required_deterministic_actions() -> None:
    executor = _build_executor()
    actions = (
        ActionType.SET_GRAPH_REQUIREMENTS,
        ActionType.RETRIEVE_EVIDENCE,
        ActionType.COMPILE,
        ActionType.JUDGE,
        ActionType.BUNDLE,
        ActionType.GEOREFERENCE,
        ActionType.VALIDATE,
    )

    for index, action in enumerate(actions, start=1):
        step = executor.execute(
            step_id=f"step-{index}",
            action=action,
            inputs={
                "graph": {"metadata": {}},
                "global_placement_required": True,
                "updated_ir_artifact_path": "artifacts/ir/ir-001.json",
            },
        )
        assert step.action == action


def test_set_graph_requirements_updates_metadata_and_records_ir_ref() -> None:
    executor = _build_executor()
    original_graph = {"metadata": {"global_placement_required": False}, "nodes": [{"id": "n1"}]}
    step = executor.execute(
        step_id="set-graph",
        action=ActionType.SET_GRAPH_REQUIREMENTS,
        inputs={
            "graph": original_graph,
            "global_placement_required": True,
            "updated_ir_artifact_path": "artifacts/ir/ir-updated-001.json",
        },
    )

    assert step.outputs["graph"]["metadata"]["global_placement_required"] is True
    assert step.outputs["ir_artifact_ref"]["artifact_path"] == "artifacts/ir/ir-updated-001.json"
    assert original_graph["metadata"]["global_placement_required"] is False


def test_validate_returns_inline_validation_result_only() -> None:
    executor = _build_executor()
    step = executor.execute(
        step_id="validate",
        action=ActionType.VALIDATE,
        inputs={"judge_artifact_path": "artifacts/judge/judge-001.json"},
    )

    assert step.validation_result is not None
    assert step.validation_result.passed is True
    assert step.outputs["validation_ref"] == "inline"
    assert "validation_artifact_ref" not in step.outputs


def test_llm_actions_are_stubbed_with_explicit_interfaces() -> None:
    executor = ActionExecutor(deps=ActionExecutorDeps())

    patch_step = executor.execute("patch", ActionType.PROPOSE_PATCH, {"request_id": "req-1"})
    status_step = executor.execute("status", ActionType.SUMMARIZE_STATUS, {"request_id": "req-1"})

    assert patch_step.reason_codes == ["missing_patch_proposer_interface"]
    assert patch_step.outputs_inline["required_interface"] == "PatchProposer"
    assert status_step.reason_codes == ["missing_status_summarizer_interface"]
    assert status_step.outputs_inline["required_interface"] == "StatusSummarizer"


def test_retrieve_evidence_propagates_reason_codes_from_dependency_payload() -> None:
    class _ReasonCodeRetriever(EvidenceRetriever):
        def retrieve_evidence(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
            del inputs
            return {
                "artifact_ref": None,
                "reason_codes": ["semantic_worker_unavailable"],
            }

    executor = ActionExecutor(deps=ActionExecutorDeps(evidence_retriever=_ReasonCodeRetriever()))
    step = executor.execute("retrieve", ActionType.RETRIEVE_EVIDENCE, {"semantic": True})

    assert step.reason_codes == ["semantic_worker_unavailable"]
    assert step.outputs == {}
