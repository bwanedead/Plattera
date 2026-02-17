"""Tests for the minimal deterministic kernel CLI."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.cli import run_cli
from backend.agent_kernel.models import KernelResult


def test_cli_accepts_request_file_and_prints_kernel_result_json(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "request_id": "req-cli-001",
                "goal": {
                    "requires_global_placement": False,
                    "objective": "cli smoke test",
                },
                "budgets": {
                    "max_steps": 10,
                    "max_wall_time_seconds": 60,
                    "max_retrieval_calls": 2,
                    "max_semantic_calls": 2,
                    "max_patch_calls": 2,
                },
                "initial_ir_ref": "artifacts/ir/cli-input.json",
            }
        ),
        encoding="utf-8",
    )

    stdout = StringIO()
    exit_code = run_cli([str(request_path)], stdout=stdout)
    payload = json.loads(stdout.getvalue())
    result = KernelResult.model_validate(payload)

    assert exit_code == 0
    assert result.request_id == "req-cli-001"
    assert result.steps_executed >= 1
