"""Phase 32: provider registration seam — domain actions are not harness enum members."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import (
    ActionExecutor,
    ActionExecutorDeps,
    RegisteredProviderAction,
)
from backend.agent_kernel.run_artifact import ArtifactRef


def _fake_domain_ping(_inputs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_ref": {"artifact_path": "artifacts/fake_pack/ping-001.json"},
        "reason_codes": ["fake_ping_completed"],
    }


def test_fake_pack_action_registers_and_executes_with_generic_envelope() -> None:
    """Non-core provider id dispatches through provider_actions with artifact ref output."""
    action_id = "fake_pack__ping"
    deps = ActionExecutorDeps(
        provider_actions={
            action_id: RegisteredProviderAction(
                output_key="fake_artifact_ref",
                reason_code="fake_ping_completed",
                missing_reason="missing_fake_ping_handler",
                handler=_fake_domain_ping,
            )
        }
    )
    executor = ActionExecutor(deps=deps)
    assert action_id in executor.available_actions()
    step = executor.execute("step-fake-1", action_id, {})
    assert step.action == action_id
    assert step.outputs.get("fake_artifact_ref") == ArtifactRef(
        artifact_path="artifacts/fake_pack/ping-001.json"
    ).model_dump(mode="json")
    assert "fake_ping_completed" in step.reason_codes
