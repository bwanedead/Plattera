"""Feature-graph claimability policy owned by product composition."""

from __future__ import annotations

from dataclasses import dataclass

from agent_kernel.claimability import ClaimabilityPolicy
from agent_kernel.harness_action_ids import ActionType, canonical_action_id
from agent_kernel.run_artifact import RunArtifact


@dataclass(frozen=True)
class FeatureGraphClaimabilityPolicy(ClaimabilityPolicy):
    """Current feature-graph closure doctrine, isolated from shared core."""

    def evaluate(self, run_artifact: RunArtifact) -> tuple[bool, list[str]]:
        missing: list[str] = []
        if run_artifact.ir_artifact_ref is None:
            missing.append("has_ir")
        if run_artifact.compile_artifact_ref is None:
            missing.append("has_compile")
        if run_artifact.judge_artifact_ref is None:
            missing.append("has_judge")
        if run_artifact.requires_global_placement:
            if run_artifact.georeference_artifact_ref is None:
                missing.append("has_georef")
            if not _latest_validation_passed(run_artifact):
                missing.append("validation_passed")
        if run_artifact.render_required and run_artifact.render_artifact_ref is None:
            missing.append("has_render")
        return len(missing) == 0, missing


def _latest_validation_passed(run_artifact: RunArtifact) -> bool:
    for step in reversed(run_artifact.steps):
        if canonical_action_id(step.action) != ActionType.VALIDATE_ARTIFACT.value:
            continue
        if step.validation_result is None:
            return False
        return bool(step.validation_result.passed)
    return False
