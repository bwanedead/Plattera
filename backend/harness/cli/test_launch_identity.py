"""Tests for CLI launch-context identity merge."""

from __future__ import annotations

import os

from harness.cli.launch_identity import merge_cli_launch_identity


def test_merge_injects_run_id_and_workspace_when_absent(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", "deed-to-ir-live-r00000001")
    merged, err = merge_cli_launch_identity({"dossier_id": "d1"})
    assert err is None
    assert merged["run_id"] == "deed-to-ir-live-r00000001"
    assert merged["workspace_id"] == "deed-to-ir-live-r00000001"
    assert merged["dossier_id"] == "d1"


def test_merge_preserves_matching_explicit_run_id(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", "deed-to-ir-live-r00000001")
    merged, err = merge_cli_launch_identity(
        {"run_id": "deed-to-ir-live-r00000001", "workspace_id": "custom-ws"}
    )
    assert err is None
    assert merged["run_id"] == "deed-to-ir-live-r00000001"
    assert merged["workspace_id"] == "custom-ws"


def test_merge_refuses_run_id_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", "deed-to-ir-live-r00000001")
    _, err = merge_cli_launch_identity({"run_id": "other-run-id"})
    assert err == "launch_run_id_cli_mismatch"


def test_merge_noop_without_cli_env(monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_CLI_RUN_ID", raising=False)
    merged, err = merge_cli_launch_identity({"run_id": "explicit-only"})
    assert err is None
    assert merged["run_id"] == "explicit-only"
