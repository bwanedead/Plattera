"""Phase 33: provider-owned step projection — shared session stays mission-agnostic."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import ActionExecutor, ActionExecutorDeps, ProviderStepResultProjector
from backend.agent_kernel import session as kernel_session_module
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact, StepRecord
from backend.agents.transcript_edit.execution_action_ids import TX_AUDIT_TRANSCRIPT
from backend.agents.transcript_edit.provider_step_projections import build_transcript_edit_provider_step_projectors


def test_session_py_has_no_transcript_action_id_branches() -> None:
    """Core session module must not embed transcript-specific action constants or tx_* branches."""
    text = Path(kernel_session_module.__file__).read_text(encoding="utf-8")
    assert "TX_AUDIT_TRANSCRIPT" not in text
    assert "tx_audit_transcript" not in text


def test_fake_provider_projector_routes_opaque_keys_without_session_semantics() -> None:
    """Session dispatches by action id only; meaning lives in the projector callable."""
    action_id = "fake_domain__widget_write"

    def _project_widget(run_artifact: RunArtifact, step: StepRecord) -> None:
        from backend.agent_kernel.ref_coercion import extract_output_ref, put_artifact_ref

        put_artifact_ref(
            run_artifact,
            "opaque_slot_for_tests",
            extract_output_ref(step.outputs, "totally_nonstandard_output_key"),
        )

    deps = ActionExecutorDeps(
        provider_step_projectors={action_id: _project_widget},
    )
    executor = ActionExecutor(deps=deps)
    step = StepRecord(
        step_id="w1",
        action=action_id,
        outputs={"totally_nonstandard_output_key": {"artifact_path": "artifacts/fake/widget.json"}},
        reason_codes=["ok"],
    )
    run_artifact = RunArtifact(run_id="run-f", request_id="req-f")
    kernel_session_module._update_latest_refs(run_artifact, step, action_executor=executor)
    assert run_artifact.artifact_refs["opaque_slot_for_tests"] == ArtifactRef(artifact_path="artifacts/fake/widget.json")


def test_transcript_edit_projection_via_registered_projectors_updates_artifact_refs() -> None:
    """Transcript-edit semantics live in the pack; session only invokes ``provider_step_projectors``."""
    projectors: dict[str, ProviderStepResultProjector] = build_transcript_edit_provider_step_projectors()
    deps = ActionExecutorDeps(provider_step_projectors=projectors)
    executor = ActionExecutor(deps=deps)
    step = StepRecord(
        step_id="tx1",
        action=TX_AUDIT_TRANSCRIPT,
        outputs={"tx_validator_report_ref": {"artifact_path": "artifacts/tx/audit-99.json"}},
        reason_codes=["tx_audit_completed"],
    )
    run_artifact = RunArtifact(run_id="run-tx", request_id="req-tx")
    kernel_session_module._update_latest_refs(run_artifact, step, action_executor=executor)
    assert run_artifact.artifact_refs["tx_validator_report_ref"].artifact_path == "artifacts/tx/audit-99.json"
