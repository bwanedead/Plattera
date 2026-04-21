"""CLI resume operator tests: classification guards and re-spawn plumbing."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness.cli import run_state as rs
from harness.cli import resume as cli_resume
from harness.cli.resume import classify_resumability, resume_run
from harness.cli.start import build_stub_argv, start_run
from harness.cli.status import status_run
from harness.mission_state import new_mission_state, new_resolution_state


@pytest.fixture
def isolated_harness_root(tmp_path, monkeypatch):
    root = tmp_path / "harness_art"
    root.mkdir()
    monkeypatch.setattr(rs, "harness_cli_artifacts_root", lambda: root)
    return root


def _minimal_valid_snapshot() -> dict:
    resolution = new_resolution_state()
    mission = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        resolution_state=resolution,
    )
    return {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 2,
        "continuity": {
            "latest_refs": {"foo": "bar"},
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


def _write_dead_run(run_id: str, *, with_checkpoint: bool, dead_pid: int = 999999) -> rs.HarnessCliRunState:
    st = rs.new_run_state(
        run_id=run_id,
        pid=dead_pid,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=build_stub_argv(),
    )
    Path(st.paths.run_dir).mkdir(parents=True, exist_ok=True)
    rs.write_state(st)
    if with_checkpoint:
        ckpt = Path(st.paths.run_dir) / "kernel_resume.json"
        ckpt.write_text(json.dumps(_minimal_valid_snapshot()), encoding="utf-8")
    return st


def _write_result(run_id: str, payload: dict) -> None:
    st = rs.read_state(run_id)
    assert st is not None
    Path(st.paths.result_file).write_text(json.dumps(payload), encoding="utf-8")


def test_classify_missing_state(isolated_harness_root):
    res = classify_resumability("nope-run")
    assert res["resumability"] == "missing_state"


def test_classify_terminal_done_refuses(isolated_harness_root):
    rid = "done-run"
    _write_dead_run(rid, with_checkpoint=True)
    Path(rs.read_state(rid).paths.done_file).write_text(
        json.dumps({"status": "ok"}), encoding="utf-8"
    )
    res = classify_resumability(rid)
    assert res["resumability"] == "terminal_done"


def test_classify_failed_model_call_result_with_checkpoint_is_resumable(isolated_harness_root):
    rid = "failed-resumable-run"
    _write_dead_run(rid, with_checkpoint=True)
    _write_result(
        rid,
        {
            "status": "failed",
            "reason_code": "model_call_failed",
            "terminal_class": "failed",
        },
    )
    res = classify_resumability(rid)
    assert res["resumability"] in {"resumable", "failed_resumable"}
    assert res["reason_code"] == "model_call_failed"
    assert res["resume_command"].endswith(rid)


def test_classify_completed_result_still_refuses(isolated_harness_root):
    rid = "completed-result-run"
    _write_dead_run(rid, with_checkpoint=True)
    _write_result(
        rid,
        {
            "status": "completed",
            "reason_code": "complete_run",
            "terminal_class": "completed",
        },
    )
    res = classify_resumability(rid)
    assert res["resumability"] == "terminal_result"
    assert res["reason_code"] == "complete_run"


def test_classify_completed_result_ignores_resumable_true(isolated_harness_root):
    rid = "completed-result-resumable-flag"
    _write_dead_run(rid, with_checkpoint=True)
    _write_result(
        rid,
        {
            "status": "completed",
            "reason_code": "complete_run",
            "terminal_class": "completed",
            "resumable": True,
        },
    )
    res = classify_resumability(rid)
    assert res["resumability"] == "terminal_result"
    assert res["reason_code"] == "complete_run"


def test_classify_generic_failed_result_still_refuses(isolated_harness_root):
    rid = "generic-failed-run"
    _write_dead_run(rid, with_checkpoint=True)
    _write_result(
        rid,
        {
            "status": "failed",
            "reason_code": "invalid_model_action_json",
            "terminal_class": "failed",
        },
    )
    res = classify_resumability(rid)
    assert res["resumability"] == "terminal_result"
    assert res["reason_code"] == "invalid_model_action_json"


def test_classify_no_checkpoint(isolated_harness_root):
    rid = "no-ckpt"
    _write_dead_run(rid, with_checkpoint=False)
    res = classify_resumability(rid)
    assert res["resumability"] == "no_checkpoint"


def test_classify_process_alive_refuses(isolated_harness_root, monkeypatch):
    rid = "alive-run"
    _write_dead_run(rid, with_checkpoint=True, dead_pid=1234)
    monkeypatch.setattr(cli_resume, "is_pid_alive", lambda _pid: True)
    res = classify_resumability(rid)
    assert res["resumability"] == "process_alive"


def test_classify_checkpoint_invalid(isolated_harness_root):
    rid = "bad-ckpt"
    st = _write_dead_run(rid, with_checkpoint=False)
    ckpt = Path(st.paths.run_dir) / "kernel_resume.json"
    # Valid JSON object but fails schema validation (no schema_version).
    ckpt.write_text(json.dumps({"not": "a snapshot"}), encoding="utf-8")
    res = classify_resumability(rid)
    assert res["resumability"] == "checkpoint_invalid"


def test_classify_checkpoint_unreadable(isolated_harness_root):
    rid = "unreadable-ckpt"
    st = _write_dead_run(rid, with_checkpoint=False)
    ckpt = Path(st.paths.run_dir) / "kernel_resume.json"
    ckpt.write_text("this is not json", encoding="utf-8")
    res = classify_resumability(rid)
    assert res["resumability"] == "checkpoint_unreadable"


def test_classify_resumable_happy_path(isolated_harness_root):
    rid = "ok-run"
    _write_dead_run(rid, with_checkpoint=True)
    res = classify_resumability(rid)
    assert res["resumability"] == "resumable"
    assert res["resume_command"].endswith(rid)
    assert res["checkpoint_path"].endswith("kernel_resume.json")


def test_resume_run_refuses_when_not_resumable(isolated_harness_root):
    rid = "refused-run"
    _write_dead_run(rid, with_checkpoint=False)
    out = resume_run(run_id=rid)
    assert out["status"] == "refused"
    assert out["reason_code"] == "no_checkpoint"


def test_resume_run_respawns_with_env(isolated_harness_root, monkeypatch):
    rid = "respawn-run"
    _write_dead_run(rid, with_checkpoint=True)

    captured: dict = {}

    class _FakeProc:
        pid = 54321

    def fake_popen(argv, *, cwd, stdin, stdout, stderr, env, close_fds, **kw):
        captured["argv"] = list(argv)
        captured["env"] = dict(env)
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    out = resume_run(run_id=rid)
    assert out["status"] == "resumed"
    assert out["pid"] == 54321
    assert "HARNESS_CLI_RESUME_FILE" in captured["env"]
    assert captured["env"]["HARNESS_CLI_RESUME_FILE"].endswith("kernel_resume.json")
    assert captured["env"]["HARNESS_CLI_RUN_ID"] == rid

    # State record reflects resume lineage.
    st = rs.read_state(rid)
    assert st is not None
    assert st.status == "resumed"
    assert st.pid == 54321
    assert isinstance(st.extra.get("resume_events"), list)
    assert len(st.extra["resume_events"]) == 1


def test_resume_run_accepts_failed_resumable_classification(isolated_harness_root, monkeypatch):
    rid = "failed-respawn-run"
    _write_dead_run(rid, with_checkpoint=True)
    _write_result(
        rid,
        {
            "status": "failed",
            "reason_code": "model_call_failed",
            "terminal_class": "failed",
        },
    )

    class _FakeProc:
        pid = 60001

    def fake_popen(argv, *, cwd, stdin, stdout, stderr, env, close_fds, **kw):
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    out = resume_run(run_id=rid)
    assert out["status"] == "resumed"
    assert out["pid"] == 60001


def test_resume_preserves_model_override_env(isolated_harness_root, monkeypatch):
    rid = "resume-model-env"
    st = _write_dead_run(rid, with_checkpoint=True)
    st.extra = {"model": "gpt-5.4-mini"}
    rs.write_state(st)

    captured: dict = {}

    class _FakeProc:
        pid = 65432

    def fake_popen(argv, *, cwd, stdin, stdout, stderr, env, close_fds, **kw):
        captured["env"] = dict(env)
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    out = resume_run(run_id=rid)
    assert out["status"] == "resumed"
    assert captured["env"]["HARNESS_CLI_MODEL"] == "gpt-5.4-mini"


def test_status_reports_interrupted_resumable(isolated_harness_root, isolated_dossiers_artifacts_shim):
    rid = "interrupted-ok"
    _write_dead_run(rid, with_checkpoint=True)
    out = status_run(run_id=rid)
    assert out["state"] == "ok"
    interrupted = out.get("interrupted")
    assert interrupted is not None
    assert interrupted["kind"] == "interrupted_resumable"
    assert interrupted["resume_command"].endswith(rid)


def test_status_reports_interrupted_no_checkpoint(isolated_harness_root, isolated_dossiers_artifacts_shim):
    rid = "interrupted-bad"
    _write_dead_run(rid, with_checkpoint=False)
    out = status_run(run_id=rid)
    interrupted = out.get("interrupted")
    assert interrupted is not None
    assert interrupted["kind"] == "interrupted_no_checkpoint"


@pytest.fixture
def isolated_dossiers_artifacts_shim(tmp_path, monkeypatch):
    import config.paths as paths_mod

    root = tmp_path / "dossiers_art"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "dossiers_artifacts_root", lambda: root)
    return root
