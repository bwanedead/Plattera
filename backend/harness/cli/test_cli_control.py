"""CLI pause/stop operator tests: guards, control.json shape, status + resume integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness.cli import run_state as rs
from harness.cli import resume as cli_resume
from harness.cli.pause import pause_run
from harness.cli.resume import resume_run
from harness.cli.start import build_stub_argv
from harness.cli.status import status_run
from harness.cli.stop import stop_run
from harness.runtime.control import (
    CONTROL_FILENAME,
    CONTROL_SCHEMA_VERSION,
    read_run_control_request,
    write_run_control_request,
)


@pytest.fixture
def isolated_dossiers_artifacts_shim(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_art"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "dossiers_artifacts_root", lambda: root)
    return root


def _write_run(run_id: str, *, pid: int, alive: bool, monkeypatch) -> rs.HarnessCliRunState:
    st = rs.new_run_state(
        run_id=run_id,
        pid=pid,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
    )
    Path(st.paths.run_dir).mkdir(parents=True, exist_ok=True)
    rs.write_state(st)
    # Force the alive probe deterministically in tests.
    from harness.cli import _control_request as cr_mod
    from harness.cli import status as status_mod
    from harness.cli import resume as resume_mod
    monkeypatch.setattr(cr_mod, "is_pid_alive", lambda _pid: alive)
    monkeypatch.setattr(status_mod, "is_pid_alive", lambda _pid: alive)
    monkeypatch.setattr(resume_mod, "is_pid_alive", lambda _pid: alive)
    return st


def test_control_contract_roundtrip(tmp_path):
    target = tmp_path / "control.json"
    req = write_run_control_request(target, command="pause", reason="coffee")
    assert target.is_file()
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["schema_version"] == CONTROL_SCHEMA_VERSION
    assert raw["command"] == "pause"
    assert raw["reason"] == "coffee"
    loaded = read_run_control_request(target)
    assert loaded is not None
    assert loaded.command == "pause"
    assert loaded.request_id == req.request_id


def test_control_contract_rejects_unknown_command(tmp_path):
    with pytest.raises(ValueError):
        write_run_control_request(tmp_path / "control.json", command="explode")


def test_control_contract_missing_file_returns_none(tmp_path):
    assert read_run_control_request(tmp_path / "missing.json") is None


def test_control_contract_malformed_file_returns_none(tmp_path):
    target = tmp_path / "control.json"
    target.write_text("not json at all", encoding="utf-8")
    assert read_run_control_request(target) is None


def test_control_contract_invalid_schema_returns_none(tmp_path):
    target = tmp_path / "control.json"
    target.write_text(json.dumps({"command": "pause", "schema_version": 99}), encoding="utf-8")
    assert read_run_control_request(target) is None


def test_pause_refuses_missing_run(isolated_harness_root):
    out = pause_run(run_id="not-a-run")
    assert out["status"] == "refused"
    assert out["reason_code"] in {"missing_state", "run_id_not_found"}


def test_pause_refuses_completed_run(isolated_harness_root, monkeypatch):
    rid = "already-done"
    st = _write_run(rid, pid=1234, alive=True, monkeypatch=monkeypatch)
    Path(st.paths.done_file).write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    out = pause_run(run_id=rid)
    assert out["status"] == "refused"
    assert out["reason_code"] == "run_has_done_sentinel"


def test_stop_refuses_dead_run_with_checkpoint(isolated_harness_root, monkeypatch):
    rid = "already-interrupted"
    st = _write_run(rid, pid=1234, alive=False, monkeypatch=monkeypatch)
    (Path(st.paths.run_dir) / "kernel_resume.json").write_text("{}", encoding="utf-8")
    out = stop_run(run_id=rid)
    assert out["status"] == "refused"
    assert out["reason_code"] == "run_already_interrupted"


def test_stop_refuses_dead_run_without_checkpoint(isolated_harness_root, monkeypatch):
    rid = "dead-no-ckpt"
    _write_run(rid, pid=1234, alive=False, monkeypatch=monkeypatch)
    out = stop_run(run_id=rid)
    assert out["status"] == "refused"
    assert out["reason_code"] == "run_not_alive_no_checkpoint"


def test_pause_writes_control_json(isolated_harness_root, monkeypatch):
    rid = "live-pause"
    _write_run(rid, pid=1234, alive=True, monkeypatch=monkeypatch)
    out = pause_run(run_id=rid, reason="operator break")
    assert out["status"] == "requested"
    assert out["command"] == "pause"
    assert out["control_file"].endswith(CONTROL_FILENAME)
    req = read_run_control_request(rs.run_dir(rid) / CONTROL_FILENAME)
    assert req is not None
    assert req.command == "pause"
    assert req.reason == "operator break"


def test_stop_writes_control_json(isolated_harness_root, monkeypatch):
    rid = "live-stop"
    _write_run(rid, pid=5678, alive=True, monkeypatch=monkeypatch)
    out = stop_run(run_id=rid)
    assert out["status"] == "requested"
    req = read_run_control_request(rs.run_dir(rid) / CONTROL_FILENAME)
    assert req is not None
    assert req.command == "stop"


def test_status_reports_pending_control_for_live_run(
    isolated_harness_root, isolated_dossiers_artifacts_shim, monkeypatch
):
    rid = "live-pending"
    _write_run(rid, pid=9001, alive=True, monkeypatch=monkeypatch)
    pause_run(run_id=rid, reason="sync pause")
    out = status_run(run_id=rid)
    ctl = out.get("control")
    assert ctl is not None
    assert ctl["command"] == "pause"
    assert ctl["status"] == "pending"
    assert ctl["reason"] == "sync pause"


@pytest.mark.parametrize(
    ("terminal_class", "reason_code", "command"),
    [
        ("paused", "paused_by_operator", "pause"),
        ("stopped", "stopped_by_operator", "stop"),
    ],
)
def test_status_reports_operator_interrupted_done_result_as_interrupted(
    isolated_harness_root,
    isolated_dossiers_artifacts_shim,
    monkeypatch,
    terminal_class: str,
    reason_code: str,
    command: str,
):
    rid = f"{terminal_class}-run"
    st = _write_run(rid, pid=9002, alive=False, monkeypatch=monkeypatch)
    Path(st.paths.result_file).write_text(
        json.dumps(
            {
                "status": terminal_class,
                "terminal_class": terminal_class,
                "reason_code": reason_code,
                "resumable": True,
                "interrupted_at_iteration": 3,
                "control_request": {"command": command},
            }
        ),
        encoding="utf-8",
    )
    Path(st.paths.done_file).write_text(
        json.dumps(
            {
                "status": terminal_class,
                "terminal_class": terminal_class,
                "reason_code": reason_code,
                "resumable": True,
                "interrupted_at_iteration": 3,
                "control_request": {"command": command},
            }
        ),
        encoding="utf-8",
    )
    out = status_run(run_id=rid)
    interrupted = out.get("interrupted")
    assert interrupted is not None
    assert interrupted["kind"] == reason_code
    assert interrupted["resumable"] is True
    assert interrupted["interrupted_at_iteration"] == 3


def test_resume_clears_pending_control_before_respawn(isolated_harness_root, monkeypatch):
    rid = "resume-after-pause"
    # Build a dead run with checkpoint and a paused result.
    st = rs.new_run_state(
        run_id=rid,
        pid=1234,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
    )
    Path(st.paths.run_dir).mkdir(parents=True, exist_ok=True)
    rs.write_state(st)
    monkeypatch.setattr(cli_resume, "is_pid_alive", lambda _pid: False)

    # Minimal valid snapshot (reuse the shape from test_cli_resume by writing inline).
    from harness.mission_state import new_mission_state, new_resolution_state
    resolution = new_resolution_state()
    mission = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", resolution_state=resolution)
    snap = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 2,
        "continuity": {
            "latest_refs": {},
            "mission_state": mission.model_dump(mode="json"),
            "resolution_state": resolution.model_dump(mode="json"),
            "active_item_id": None,
            "state_patch_feedback": {},
            "continuity_journal_entries": [],
            "compacted_continuity_summary": None,
            "operator_progress_message": None,
            "kernel_step_records": [],
            "kernel_step_result_records": [],
            "kernel_compaction_covered_through_turn_index": 0,
        },
        "hitl": {
            "hitl_state": "no_prompt",
            "pending_feedback_prompt_id": None,
            "pending_feedback_response": None,
            "pending_hitl_requests": [],
            "answered_hitl_responses": [],
            "blocking_prompt_id": None,
        },
        "telemetry": {
            "llm_contact_count": 0,
            "prompt_event_count": 0,
            "last_prompt_event_id": None,
            "last_prompt_event_surface": None,
        },
        "execution_session": None,
    }
    (Path(st.paths.run_dir) / "kernel_resume.json").write_text(json.dumps(snap), encoding="utf-8")
    Path(st.paths.result_file).write_text(
        json.dumps(
            {
                "status": "paused",
                "terminal_class": "paused",
                "reason_code": "paused_by_operator",
                "resumable": True,
                "interrupted_at_iteration": 2,
                "control_request": {"command": "pause"},
            }
        ),
        encoding="utf-8",
    )
    Path(st.paths.done_file).write_text(
        json.dumps(
            {
                "status": "paused",
                "terminal_class": "paused",
                "reason_code": "paused_by_operator",
                "resumable": True,
                "interrupted_at_iteration": 2,
                "control_request": {"command": "pause"},
            }
        ),
        encoding="utf-8",
    )
    # Drop a stale control request that resume must consume.
    ctl = rs.run_dir(rid) / CONTROL_FILENAME
    write_run_control_request(ctl, command="pause")
    assert ctl.is_file()

    class _FakeProc:
        pid = 77777

    def fake_popen(*args, **kwargs):
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    monkeypatch.setattr("harness.cli.resume.spawn_run_control_watchdog", lambda **kwargs: None)
    out = resume_run(run_id=rid)
    assert out["status"] == "resumed"
    assert not ctl.exists(), "resume must consume the stale control.json"


def test_resume_accepts_paused_and_stopped_reason_codes():
    from harness.cli.resume import _RESULT_RESUMABLE_REASON_CODES
    assert "paused_by_operator" in _RESULT_RESUMABLE_REASON_CODES
    assert "stopped_by_operator" in _RESULT_RESUMABLE_REASON_CODES
