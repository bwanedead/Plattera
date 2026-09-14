"""Tests for fork spawn-argv launch-context identity stripping."""

from __future__ import annotations

import json

from harness.cli.fork_spawn_argv import (
    parse_embedded_launch_context,
    parse_embedded_launch_context_strict,
    replace_embedded_launch_context,
    replace_unique_embedded_launch_context,
    strip_launch_context_identity_for_fork,
)
from harness.cli.fork_workspace import (
    prepare_continue_spawn_argv,
    prepare_isolated_spawn_argv,
)


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
        "muse-spark-1.3-contributor",
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


def test_isolated_prepare_strips_run_and_workspace() -> None:
    launch = {"run_id": "parent-run", "workspace_id": "parent-ws", "dossier_id": "d1"}
    argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    prepared = prepare_isolated_spawn_argv(argv)
    doc = json.loads(prepared[4])
    assert "run_id" not in doc
    assert "workspace_id" not in doc
    assert doc["dossier_id"] == "d1"


def test_continue_prepare_keeps_explicit_workspace_and_drops_run_id() -> None:
    launch = {"run_id": "parent-run", "workspace_id": "parent-ws", "dossier_id": "d1"}
    argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    prepared, workspace_id, err = prepare_continue_spawn_argv(
        spawn_argv=argv,
        source_run_id="parent-run",
    )
    assert err is None
    assert workspace_id == "parent-ws"
    assert prepared is not None
    doc = json.loads(prepared[4])
    assert "run_id" not in doc
    assert doc["workspace_id"] == "parent-ws"
    assert doc["dossier_id"] == "d1"


def test_continue_prepare_missing_workspace_uses_source_run_id() -> None:
    launch = {"run_id": "parent-run", "dossier_id": "d1"}
    argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    prepared, workspace_id, err = prepare_continue_spawn_argv(
        spawn_argv=argv,
        source_run_id="parent-run",
    )
    assert err is None
    assert workspace_id == "parent-run"
    assert prepared is not None
    doc = json.loads(prepared[4])
    assert doc["workspace_id"] == "parent-run"
    assert "run_id" not in doc


def test_continue_prepare_injects_workspace_when_launch_flag_absent() -> None:
    argv = ["python", "-m", "harness.cli.stub_worker"]
    prepared, workspace_id, err = prepare_continue_spawn_argv(
        spawn_argv=argv,
        source_run_id="parent-run",
    )
    assert err is None
    assert workspace_id == "parent-run"
    assert prepared is not None
    doc, parse_err = parse_embedded_launch_context(prepared)
    assert parse_err is None
    assert doc == {"workspace_id": "parent-run"}


def test_continue_prepare_refuses_malformed_and_non_object_launch_context() -> None:
    bad = ["python", "-m", "x", "--launch-context-json", "{not-json"]
    argv, ws, err = prepare_continue_spawn_argv(spawn_argv=bad, source_run_id="parent-run")
    assert argv is None and ws is None
    assert err == "launch_context_malformed"

    listed = ["python", "-m", "x", "--launch-context-json", "[1]"]
    argv, ws, err = prepare_continue_spawn_argv(spawn_argv=listed, source_run_id="parent-run")
    assert argv is None and ws is None
    assert err == "launch_context_not_object"


def test_continue_prepare_refuses_blank_unsafe_and_mismatched_identity() -> None:
    blank = {
        "run_id": "parent-run",
        "workspace_id": "  padded  ",
    }
    argv = ["py", "-m", "x", "--launch-context-json", json.dumps(blank)]
    _, _, err = prepare_continue_spawn_argv(spawn_argv=argv, source_run_id="parent-run")
    assert err == "workspace_id_invalid"

    numbered = {"run_id": "parent-run", "workspace_id": 12}
    argv = ["py", "-m", "x", "--launch-context-json", json.dumps(numbered)]
    _, _, err = prepare_continue_spawn_argv(spawn_argv=argv, source_run_id="parent-run")
    assert err == "workspace_id_invalid"

    unsafe = {"run_id": "parent-run", "workspace_id": "../escape"}
    argv = ["py", "-m", "x", "--launch-context-json", json.dumps(unsafe)]
    _, _, err = prepare_continue_spawn_argv(spawn_argv=argv, source_run_id="parent-run")
    assert err == "workspace_id_unsafe"

    mismatch = {"run_id": "other-run", "workspace_id": "parent-ws"}
    argv = ["py", "-m", "x", "--launch-context-json", json.dumps(mismatch)]
    _, _, err = prepare_continue_spawn_argv(spawn_argv=argv, source_run_id="parent-run")
    assert err == "launch_run_id_source_mismatch"


def test_replace_embedded_launch_context_round_trip() -> None:
    argv = ["py", "-m", "x", "--launch-context-json", '{"a":1}']
    out = replace_embedded_launch_context(argv, {"workspace_id": "ws-1"})
    assert json.loads(out[-1]) == {"workspace_id": "ws-1"}


def test_strict_parse_accepts_zero_or_one_occurrence() -> None:
    absent, err = parse_embedded_launch_context_strict(["python", "-m", "x"])
    assert absent is None and err is None
    split = ["python", "-m", "x", "--launch-context-json", '{"workspace_id":"ws"}']
    doc, err = parse_embedded_launch_context_strict(split)
    assert err is None and doc == {"workspace_id": "ws"}
    equals = ['python', '-m', 'x', '--launch-context-json={"workspace_id":"ws"}']
    doc, err = parse_embedded_launch_context_strict(equals)
    assert err is None and doc == {"workspace_id": "ws"}


def test_strict_parse_refuses_duplicate_and_dangling_flags() -> None:
    split_dup = [
        "py",
        "-m",
        "x",
        "--launch-context-json",
        "{}",
        "--launch-context-json",
        "{}",
    ]
    _, err = parse_embedded_launch_context_strict(split_dup)
    assert err == "launch_context_duplicate"

    equals_dup = [
        "py",
        "-m",
        "x",
        "--launch-context-json={}",
        "--launch-context-json={}",
    ]
    _, err = parse_embedded_launch_context_strict(equals_dup)
    assert err == "launch_context_duplicate"

    mixed = [
        "py",
        "-m",
        "x",
        "--launch-context-json",
        "{}",
        "--launch-context-json={}",
    ]
    _, err = parse_embedded_launch_context_strict(mixed)
    assert err == "launch_context_duplicate"

    dangling = ["py", "-m", "x", "--launch-context-json"]
    _, err = parse_embedded_launch_context_strict(dangling)
    assert err == "launch_context_dangling"

    option_value = ["py", "-m", "x", "--launch-context-json", "--loop-kind"]
    _, err = parse_embedded_launch_context_strict(option_value)
    assert err == "launch_context_dangling"

    _, err = parse_embedded_launch_context_strict(["py", "-m", "x", 12])
    assert err == "launch_context_value_invalid"


def test_unique_replace_leaves_exactly_one_canonical_flag() -> None:
    argv = ["py", "-m", "x", "--launch-context-json={}", "--keep"]
    out, err = replace_unique_embedded_launch_context(argv, {"workspace_id": "ws-1"})
    assert err is None
    assert out is not None
    assert out.count("--launch-context-json") == 1
    assert not any(
        type(item) is str and item.startswith("--launch-context-json=") for item in out
    )
    assert json.loads(out[-1]) == {"workspace_id": "ws-1"}
    assert "--keep" in out
