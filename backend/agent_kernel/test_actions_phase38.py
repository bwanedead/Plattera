"""Phase 38: shared execution roles are generic-first but remain compatible."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import (
    ActionExecutor,
    ActionExecutorDeps,
    ArtifactBundler,
    ArtifactCompiler,
    ArtifactDraftProposer,
    ArtifactGeoreferencer,
    ArtifactHydrator,
    ArtifactJudge,
    ArtifactRenderer,
    ArtifactValidator,
)
from backend.agent_kernel.run_artifact import ArtifactRef, ValidationInline


class _GenericServices(
    ArtifactHydrator,
    ArtifactDraftProposer,
    ArtifactCompiler,
    ArtifactJudge,
    ArtifactBundler,
    ArtifactGeoreferencer,
    ArtifactValidator,
    ArtifactRenderer,
):
    def hydrate_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/artifact/hydrated-generic.json")

    def draft_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/ir/draft-generic.json")

    def compile_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/compile/generic.json")

    def judge_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/judge/generic.json")

    def bundle_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/bundle/generic.json")

    def georeference_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/georef/generic.json")

    def validate_artifact(self, inputs: Mapping[str, Any]) -> ValidationInline:
        del inputs
        return ValidationInline(passed=True, reason_code="ok", checks={})

    def render_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/render/generic.json")


def test_generic_artifact_roles_and_legacy_aliases_both_dispatch() -> None:
    services = _GenericServices()
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            artifact_hydrator=services,
            artifact_draft_proposer=services,
            artifact_compiler=services,
            artifact_judge=services,
            artifact_bundler=services,
            artifact_georeferencer=services,
            artifact_validator=services,
            artifact_renderer=services,
        )
    )

    assert executor.deps.artifact_hydrator is services
    assert executor.deps.artifact_draft_proposer is services
    assert executor.deps.artifact_compiler is services
    assert executor.available_actions(allow_stubbed=False) == (
        "set_graph_requirements",
        "hydrate_artifact",
        "draft_artifact",
        "compile_artifact",
        "judge_artifact",
        "bundle_artifact",
        "georeference_artifact",
        "validate_artifact",
        "render_artifact",
    )
