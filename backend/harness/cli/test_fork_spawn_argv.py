"""Tests for fork spawn-argv launch-context identity stripping."""

from __future__ import annotations

import json

from harness.cli.fork_spawn_argv import strip_launch_context_identity_for_fork


def test_strip_removes_run_id_and_workspace_from_separate_flag_arg() -> None:
    launch = {
        "run_id": "parent-run",
        "workspace_id": "parent-ws",
        "dossier_id": "d1",
        "upstream_run_lineage": {"source_run_id": "upstream"},
    }
    argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    stripped = strip_launch_context_identity_for_fork(argv)
    assert stripped[:4] == argv[:4]
    doc = json.loads(stripped[4])
    assert "run_id" not in doc
    assert "workspace_id" not in doc
    assert doc["dossier_id"] == "d1"
    assert doc["upstream_run_lineage"]["source_run_id"] == "upstream"


def test_strip_removes_run_id_from_equals_form_flag() -> None:
    launch = {"run_id": "parent-run", "model": "gpt-5.4"}
    raw = json.dumps(launch, separators=(",", ":"))
    argv = ["python", "-m", "harness.runtime.runner.entrypoint", f"--launch-context-json={raw}"]
    stripped = strip_launch_context_identity_for_fork(argv)
    doc = json.loads(stripped[3].split("=", 1)[1])
    assert "run_id" not in doc
    assert doc["model"] == "gpt-5.4"


def test_strip_preserves_explicit_recorded_models() -> None:
    for model in (
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "muse-spark-1.2-contributor",
    ):
        launch = {"run_id": "parent-run", "model": model, "dossier_id": "d1"}
        raw = json.dumps(launch, separators=(",", ":"))
        argv = ["python", "-m", "harness.runtime.runner.entrypoint", f"--launch-context-json={raw}"]
        stripped = strip_launch_context_identity_for_fork(argv)
        doc = json.loads(stripped[3].split("=", 1)[1])
        assert "run_id" not in doc
        assert doc["model"] == model
        assert doc["dossier_id"] == "d1"


def test_strip_noop_without_launch_context_flag() -> None:
    argv = ["python", "-m", "harness.cli.stub_worker"]
    assert strip_launch_context_identity_for_fork(argv) == argv
