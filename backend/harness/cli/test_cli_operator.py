"""Operator CLI: run-state, start/watch/answer/status plumbing (no real LLM loop)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from harness.cli import run_state as rs
from harness.cli.answer import answer_run
from harness.cli.start import build_module_argv, build_stub_argv, start_run
from harness.cli.status import status_run
from harness.cli.watch import watch_run
from harness.runtime.hitl import watch as hitl_watch
from services.agent_viewer import feedback_store


@pytest.fixture
def isolated_harness_root(tmp_path, monkeypatch):
    root = tmp_path / "harness_art"
    root.mkdir()
    monkeypatch.setattr(rs, "harness_cli_artifacts_root", lambda: root)
    return root


@pytest.fixture
def isolated_dossiers_artifacts(tmp_path, monkeypatch):
    root = tmp_path / "dossiers_art"
    root.mkdir()

    def _root():
        return root

    import config.paths as paths_mod

    monkeypatch.setattr(paths_mod, "dossiers_artifacts_root", _root)
    return root


def test_run_state_round_trip(isolated_harness_root):
    rid = "test-run-1"
    st = rs.new_run_state(
        run_id=rid,
        pid=4242,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=["py", "-m", "x"],
        extra={"k": "v"},
    )
    rs.write_state(st)
    loaded = rs.read_state(rid)
    assert loaded is not None
    assert loaded.run_id == rid
    assert loaded.pid == 4242
    assert loaded.paths.done_file.endswith("done.json")
    assert loaded.extra.get("k") == "v"


def test_build_argv_helpers():
    assert build_stub_argv()[0] == sys.executable
    assert "harness.cli.stub_worker" in build_stub_argv()
    mod = build_module_argv("some.mod", ["a", "b"])
    assert mod[:3] == [sys.executable, "-m", "some.mod"]
    assert mod[3:] == ["a", "b"]


def test_start_spawns_stub_writes_state_and_artifacts(isolated_harness_root):
    rid = "spawn-stub-1"
    out = start_run(
        run_id=rid,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
    )
    assert out["status"] == "started"
    assert out["run_id"] == rid
    assert out["pid"] and out["pid"] > 0
    for key in ("done_file", "result_file", "state_file", "stdout_log"):
        assert key in out
        assert Path(out[key]).is_absolute()

    deadline = time.time() + 15.0
    while time.time() < deadline:
        if Path(out["done_file"]).is_file() and Path(out["result_file"]).is_file():
            break
        time.sleep(0.05)
    assert Path(out["done_file"]).is_file()
    assert Path(out["result_file"]).is_file()

    st = rs.read_state(rid)
    assert st is not None
    assert st.spawn_argv[0] == sys.executable


def test_start_carries_model_override_into_child_metadata(isolated_harness_root):
    rid = "spawn-model-1"
    out = start_run(
        run_id=rid,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
        model="gpt-5.4-mini",
    )
    assert out["status"] == "started"
    assert out["model"] == "gpt-5.4-mini"
    st = rs.read_state(rid)
    assert st is not None
    assert st.spawn_argv[0] == sys.executable
    assert st.extra["model"] == "gpt-5.4-mini"


def test_start_spawn_failure_records_state(isolated_harness_root, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("simulated_spawn_failure")

    monkeypatch.setattr(subprocess, "Popen", boom)
    rid = "spawn-fail-1"
    out = start_run(
        run_id=rid,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
    )
    assert out["status"].startswith("spawn_failed")
    st = rs.read_state(rid)
    assert st is not None
    assert st.status.startswith("spawn_failed")


def test_watch_hitl_event(isolated_harness_root, isolated_dossiers_artifacts):
    rid = "hitl-1"
    st = rs.new_run_state(run_id=rid, pid=1, loop_kind="harness_cli", mode="x", spawn_argv=["x"])
    rs.write_state(st)
    p = hitl_watch.hitl_pending_path(rid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "prompt_id": "p1",
                "message": "choose",
                "choices": ["a", "b"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ev = watch_run(run_id=rid, timeout_seconds=5, poll_interval=0.05)
    assert ev["event"] == "hitl"
    assert ev.get("prompt_id") == "p1"
    assert not p.exists()


def test_watch_loop_done(isolated_harness_root, isolated_dossiers_artifacts, tmp_path):
    rid = "done-1"
    done = tmp_path / "done.json"
    done.write_text(
        json.dumps({"status": "finished", "terminal": "ok", "reason_code": None}, ensure_ascii=False),
        encoding="utf-8",
    )
    st = rs.new_run_state(
        run_id=rid,
        pid=1,
        loop_kind="harness_cli",
        mode="x",
        spawn_argv=["x"],
    )
    st.paths.done_file = str(done.resolve())
    rs.write_state(st)

    ev = watch_run(run_id=rid, timeout_seconds=5, poll_interval=0.05)
    assert ev["event"] == "loop_done"
    assert ev.get("terminal") == "ok"


def test_watch_timeout(isolated_harness_root, isolated_dossiers_artifacts):
    rid = "to-1"
    st = rs.new_run_state(run_id=rid, pid=1, loop_kind="harness_cli", mode="x", spawn_argv=["x"])
    rs.write_state(st)
    ev = watch_run(run_id=rid, timeout_seconds=1, poll_interval=0.05)
    assert ev["event"] == "timeout"
    assert ev.get("timeout_seconds") == 1


def test_watch_missing_state(isolated_dossiers_artifacts):
    ev = watch_run(run_id="nope", timeout_seconds=1, poll_interval=0.05)
    assert ev["event"] == "error"


def test_answer_writes_feedback(isolated_dossiers_artifacts, isolated_harness_root):
    rid = "ans-1"
    st = rs.new_run_state(run_id=rid, pid=1, loop_kind="harness_cli", mode="x", spawn_argv=["x"])
    rs.write_state(st)
    res = answer_run(run_id=rid, prompt_id="p9", choice="yes", note=None, loop_kind=None)
    assert res.get("status") == "injected"
    path = feedback_store.feedback_path(loop_kind="harness_cli", run_id=rid)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert any(e.get("prompt_id") == "p9" for e in data.get("entries", []))


def test_answer_loop_kind_override_without_state(isolated_dossiers_artifacts):
    rid = "ans-2"
    res = answer_run(
        run_id=rid,
        prompt_id="p1",
        choice="c",
        note="n",
        loop_kind="custom_loop",
    )
    assert res["status"] == "injected"


def test_status_missing_and_ok(isolated_harness_root, isolated_dossiers_artifacts):
    miss = status_run(run_id="missing-xyz")
    assert miss["state"] == "missing"

    rid = "stat-1"
    out = start_run(
        run_id=rid,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
    )
    s0 = status_run(run_id=rid)
    assert s0["state"] == "ok"
    assert s0["paths"]["state_file"] == out["state_file"]

    deadline = time.time() + 15.0
    while time.time() < deadline:
        if Path(out["done_file"]).is_file():
            break
        time.sleep(0.05)

    s1 = status_run(run_id=rid)
    assert s1["done_file_exists"] is True
    assert s1["result_file_exists"] is True


def test_cli_start_module_invocation_smoke(isolated_harness_root):
    """``python -m harness.cli.start`` argv path (same interpreter)."""
    rid = "cli-mod-smoke"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli.start",
            "--run-id",
            rid,
            "--stub",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    meta = json.loads(proc.stdout.strip())
    assert meta["run_id"] == rid
    assert meta["status"] == "started"


def test_cli_start_module_invocation_accepts_model_override(isolated_harness_root):
    rid = "cli-model-smoke"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli.start",
            "--run-id",
            rid,
            "--stub",
            "--model",
            "gpt-5.4-mini",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    meta = json.loads(proc.stdout.strip())
    assert meta["run_id"] == rid
    assert meta["status"] == "started"
    assert meta["model"] == "gpt-5.4-mini"
