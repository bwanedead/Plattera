"""Unit tests for generic CLI workspace-reference discovery."""

from __future__ import annotations

import json
from pathlib import Path

from harness.cli.workspace_refs import discover_run_workspace_ids


def test_default_workspace_is_run_id(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(json.dumps({"run_id": "run-a"}), encoding="utf-8")
    refs, err = discover_run_workspace_ids(run_id="run-a", run_dir=run_dir)
    assert err is None
    assert refs == frozenset({"run-a"})


def test_launch_and_lineage_workspace_agree(tmp_path: Path) -> None:
    run_dir = tmp_path / "child"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "run_id": "child",
                "spawn_argv": [
                    "py",
                    "-m",
                    "x",
                    "--launch-context-json",
                    json.dumps({"workspace_id": "source-ws"}),
                ],
                "extra": {
                    "fork_lineage": {
                        "workspace_mode": "continue",
                        "source_workspace_id": "source-ws",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    refs, err = discover_run_workspace_ids(run_id="child", run_dir=run_dir)
    assert err is None
    assert refs == frozenset({"source-ws"})


def test_duplicate_launch_context_is_uncertain(tmp_path: Path) -> None:
    run_dir = tmp_path / "dup"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "run_id": "dup",
                "spawn_argv": [
                    "py",
                    "-m",
                    "x",
                    "--launch-context-json",
                    "{}",
                    "--launch-context-json",
                    "{}",
                ],
            }
        ),
        encoding="utf-8",
    )
    refs, err = discover_run_workspace_ids(run_id="dup", run_dir=run_dir)
    assert refs is None
    assert err == "workspace_refs_uncertain"


def test_present_non_list_spawn_argv_is_uncertain(tmp_path: Path) -> None:
    for index, value in enumerate((None, "", 0, {})):
        run_dir = tmp_path / f"falsey-{index}"
        run_dir.mkdir()
        (run_dir / "state.json").write_text(
            json.dumps({"run_id": f"falsey-{index}", "spawn_argv": value}),
            encoding="utf-8",
        )
        refs, err = discover_run_workspace_ids(run_id=f"falsey-{index}", run_dir=run_dir)
        assert refs is None
        assert err == "workspace_refs_uncertain"


def test_tuple_spawn_argv_is_uncertain() -> None:
    from harness.cli.workspace_refs import _explicit_workspace_ids

    _launch, _lineage, err = _explicit_workspace_ids(
        {"spawn_argv": ()},
        source_run_id="run-a",
    )
    assert err == "workspace_refs_uncertain"


def test_empty_list_spawn_argv_defaults_to_run_id(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty-argv"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        json.dumps({"run_id": "empty-argv", "spawn_argv": []}),
        encoding="utf-8",
    )
    refs, err = discover_run_workspace_ids(run_id="empty-argv", run_dir=run_dir)
    assert err is None
    assert refs == frozenset({"empty-argv"})


def test_conflicting_launch_and_lineage_is_uncertain(tmp_path: Path) -> None:
    run_dir = tmp_path / "conflict"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "run_id": "conflict",
                "spawn_argv": [
                    "py",
                    "-m",
                    "x",
                    "--launch-context-json",
                    json.dumps({"workspace_id": "ws-a"}),
                ],
                "extra": {"fork_lineage": {"source_workspace_id": "ws-b"}},
            }
        ),
        encoding="utf-8",
    )
    refs, err = discover_run_workspace_ids(run_id="conflict", run_dir=run_dir)
    assert refs is None
    assert err == "workspace_refs_uncertain"
