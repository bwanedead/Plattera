"""Deterministic claimability gate evaluation for DECLARE_DONE."""

from __future__ import annotations

from .run_artifact import RunArtifact

GATE_HAS_IR = "has_ir"
GATE_HAS_COMPILE = "has_compile"
GATE_HAS_JUDGE = "has_judge"
GATE_HAS_GEOREF = "has_georef"
GATE_VALIDATION_PASSED = "validation_passed"


def evaluate_claimability(
    *,
    run_artifact: RunArtifact,
    requires_global_placement: bool,
) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if run_artifact.ir_artifact_ref is None:
        missing.append(GATE_HAS_IR)
    if run_artifact.compile_artifact_ref is None:
        missing.append(GATE_HAS_COMPILE)
    if run_artifact.judge_artifact_ref is None:
        missing.append(GATE_HAS_JUDGE)
    if requires_global_placement:
        georef_ready = run_artifact.georeference_artifact_ref is not None
        if not georef_ready:
            missing.append(GATE_HAS_GEOREF)
        if not _latest_validation_passed(run_artifact):
            missing.append(GATE_VALIDATION_PASSED)
    return len(missing) == 0, missing


def _latest_validation_passed(run_artifact: RunArtifact) -> bool:
    for step in reversed(run_artifact.steps):
        if step.action.value != "validate":
            continue
        if step.validation_result is None:
            return False
        return bool(step.validation_result.passed)
    return False
