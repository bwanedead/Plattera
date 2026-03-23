from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest


def test_kernel_session_start_request_no_longer_exposes_policy_id() -> None:
    assert "policy_id" not in KernelSessionStartRequest.model_fields

    request = KernelSessionStartRequest(
        request_id="req-001",
        goal=KernelGoal(requires_global_placement=False, objective="test"),
        budgets=KernelBudgets(
            max_steps=1,
            max_wall_time_seconds=1,
            max_retrieval_calls=0,
            max_semantic_calls=0,
            max_patch_calls=0,
        ),
    )

    assert request.dossier_id is None
    assert request.source_entry_ref is None
