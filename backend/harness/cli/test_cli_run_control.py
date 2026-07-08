"""Tests for human-editable run_control.json sidecar."""

from __future__ import annotations

import json
from pathlib import Path

from harness.cli.start import start_run, build_stub_argv
from harness.cli.status import status_run
from harness.runtime.control import CONTROL_SCHEMA_VERSION, RunControlRequest
from harness.runtime.run_control_sidecar import (
    DEFAULT_RUN_CONTROL_STATE,
    build_sidecar_aware_run_control_reader,
    read_run_control_sidecar,
    run_control_path,
    write_initial_run_control_sidecar,
)
from harness.runtime.run_control_watchdog import write_emergency_stop_terminal_artifacts


def test_write_initial_run_control_sidecar_creates_defaults(tmp_path) -> None:
    path = write_initial_run_control_sidecar(tmp_path)
    assert path.is_file()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc == DEFAULT_RUN_CONTROL_STATE


def test_malformed_run_control_sidecar_reports_parse_error(tmp_path) -> None:
    path = run_control_path(tmp_path)
    path.write_text("{not json", encoding="utf-8")
    state, err = read_run_control_sidecar(path)
    assert state is None
    assert err == "run_control_sidecar_unreadable"


def test_sidecar_reader_honors_stop(tmp_path) -> None:
    sidecar = run_control_path(tmp_path)
    sidecar.write_text(
        json.dumps({**DEFAULT_RUN_CONTROL_STATE, "stop": True, "message": "manual stop"}),
        encoding="utf-8",
    )
    reader = build_sidecar_aware_run_control_reader(
        cli_command_path=tmp_path / "control.json",
        sidecar_path=sidecar,
    )
    req = reader()
    assert isinstance(req, RunControlRequest)
    assert req.command == "stop"
    assert req.requested_by == "run_control_sidecar"
    assert req.reason == "manual stop"
    assert reader() is None


def test_sidecar_reader_honors_pause(tmp_path) -> None:
    sidecar = run_control_path(tmp_path)
    sidecar.write_text(json.dumps({**DEFAULT_RUN_CONTROL_STATE, "pause": True}), encoding="utf-8")
    reader = build_sidecar_aware_run_control_reader(
        cli_command_path=tmp_path / "control.json",
        sidecar_path=sidecar,
    )
    req = reader()
    assert req is not None
    assert req.command == "pause"
    assert req.schema_version == CONTROL_SCHEMA_VERSION


def test_emergency_stop_terminal_artifacts_not_resumable_without_checkpoint(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    done_file = run_dir / "done.json"
    result_file = run_dir / "result.json"
    monkeypatch.setenv("HARNESS_CLI_WATCHDOG_WORKER_PID", "1234")
    write_emergency_stop_terminal_artifacts(
        run_dir=run_dir,
        done_file=done_file,
        result_file=result_file,
    )
    done = json.loads(done_file.read_text(encoding="utf-8"))
    assert done["reason_code"] == "emergency_stop_requested"
    assert done["resumable"] is False
    assert done.get("operator_interrupted") is True


def test_emergency_stop_skips_terminal_write_when_artifacts_exist(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    done_file = run_dir / "done.json"
    result_file = run_dir / "result.json"
    done_file.write_text('{"status":"completed","reason_code":"done"}', encoding="utf-8")
    result_file.write_text('{"status":"completed","reason_code":"done"}', encoding="utf-8")
    monkeypatch.setenv("HARNESS_CLI_WATCHDOG_WORKER_PID", "1234")
    triggered = write_emergency_stop_terminal_artifacts(
        run_dir=run_dir,
        done_file=done_file,
        result_file=result_file,
    )
    assert triggered.get("terminal_write_skipped") is True
    assert json.loads(done_file.read_text(encoding="utf-8"))["reason_code"] == "done"


def test_watchdog_loop_exits_when_worker_already_dead(tmp_path, monkeypatch) -> None:
    from harness.runtime.run_control_watchdog import run_watchdog_loop

    sidecar = run_control_path(tmp_path)
    sidecar.write_text(json.dumps({**DEFAULT_RUN_CONTROL_STATE, "emergency_stop": True}), encoding="utf-8")
    exit_code = run_watchdog_loop(
        run_dir=tmp_path,
        worker_pid=999999999,
        done_file=tmp_path / "done.json",
        result_file=tmp_path / "result.json",
        poll_interval_seconds=0.05,
    )
    assert exit_code == 0
    assert not (tmp_path / "done.json").is_file()


def test_emergency_stop_terminal_artifacts_resumable_when_checkpoint_exists(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "kernel_resume.json").write_text("{}", encoding="utf-8")
    done_file = run_dir / "done.json"
    result_file = run_dir / "result.json"
    monkeypatch.setenv("HARNESS_CLI_WATCHDOG_WORKER_PID", "1234")
    write_emergency_stop_terminal_artifacts(
        run_dir=run_dir,
        done_file=done_file,
        result_file=result_file,
    )
    done = json.loads(done_file.read_text(encoding="utf-8"))
    result = json.loads(result_file.read_text(encoding="utf-8"))
    assert done["reason_code"] == "emergency_stop_requested"
    assert done["terminal_class"] == "stopped"
    assert done["resumable"] is True
    assert done.get("operator_interrupted") is True
    assert result["reason_code"] == "emergency_stop_requested"
    assert (run_dir / "emergency_stop_triggered.json").is_file()


def test_start_run_creates_run_control_sidecar(tmp_path, monkeypatch) -> None:
    import harness.cli.run_state as rs

    run_id = "run-control-start-test"
    run_path = tmp_path / run_id
    monkeypatch.setattr(rs, "allocate_run_directory", lambda **kwargs: run_path)
    monkeypatch.setattr(
        "harness.cli.start.subprocess.Popen",
        lambda *args, **kwargs: type("P", (), {"pid": 4321})(),
    )
    monkeypatch.setattr("harness.cli.start.spawn_run_control_watchdog", lambda **kwargs: None)
    out = start_run(
        run_id=run_id,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
        run_dir=run_path,
    )
    assert "run_control_file" in out
    assert Path(out["run_control_file"]).is_file()
    assert out["run_control_state"]["present"] is True


def test_status_reports_run_control_state(tmp_path, monkeypatch) -> None:
    import harness.cli.run_state as rs

    run_id = "run-control-status-test"
    run_path = tmp_path / run_id
    st = rs.new_run_state(
        run_id=run_id,
        pid=1,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
        run_dir=run_path,
    )
    run_path.mkdir(parents=True, exist_ok=True)
    rs.write_state(st)
    monkeypatch.setattr(rs, "run_dir", lambda _rid: run_path)
    monkeypatch.setattr("harness.cli.status.run_dir", lambda _rid: run_path)
    monkeypatch.setattr("harness.cli.status.read_state", lambda _rid: st)
    sidecar = write_initial_run_control_sidecar(st.paths.run_dir)
    sidecar.write_text(
        json.dumps({**DEFAULT_RUN_CONTROL_STATE, "emergency_stop": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr("harness.cli.status.is_pid_alive", lambda _pid: True)
    out = status_run(run_id=run_id)
    assert out["run_control_file"].endswith("run_control.json")
    assert out["run_control_state"]["emergency_stop"] is True
    assert out["emergency_stop_requested"] is True
