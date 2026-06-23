"""CLI command resolution tests for namespaced and ambiguous runs."""

from __future__ import annotations

import json
from pathlib import Path

from harness.cli import run_state as rs
from harness.cli.answer import answer_run
from harness.cli.message import inject_user_message
from harness.cli.pause import pause_run
from harness.cli.resume import classify_resumability
from harness.cli.start import build_stub_argv
from harness.cli.status import status_run
from harness.cli.stop import stop_run
from harness.cli.watch import watch_run
from harness.cli.run_layout import BY_LOOP_KIND_DIRNAME


def _write_namespaced_run(root: Path, *, collection: str, run_id: str) -> rs.HarnessCliRunState:
    st = rs.new_run_state(
        run_id=run_id,
        pid=1234,
        loop_kind=collection,
        mode="stub",
        spawn_argv=build_stub_argv(),
    )
    Path(st.paths.run_dir).mkdir(parents=True, exist_ok=True)
    rs.write_state(st)
    return st


def _write_legacy_run(root: Path, *, run_id: str) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "pid": 1,
                "loop_kind": "transcript_edit",
                "run_collection": "transcript_edit",
                "mode": "live",
                "paths": {
                    "run_dir": str(run_dir),
                    "state_file": str(run_dir / "state.json"),
                    "done_file": str(run_dir / "done.json"),
                    "result_file": str(run_dir / "result.json"),
                    "stdout_log": str(run_dir / "stdout.log"),
                    "stderr_log": str(run_dir / "stderr.log"),
                },
                "spawn_argv": [],
                "created_at_epoch_seconds": 0.0,
                "status": "started",
                "extra": {},
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_every_cli_command_resolves_namespaced_run(isolated_harness_root, monkeypatch) -> None:
    st = _write_namespaced_run(
        isolated_harness_root / "cli_runs",
        collection="deed_to_ir",
        run_id="deed-cli-1",
    )
    from harness.cli import _control_request as cr_mod

    monkeypatch.setattr(cr_mod, "is_pid_alive", lambda _pid: True)

    status = status_run(run_id="deed-cli-1")
    assert status["state"] == "ok"
    assert status["run_collection"] == "deed_to_ir"
    assert status["paths"]["run_dir"].replace("\\", "/").endswith("by_loop_kind/deed_to_ir/deed-cli-1")

    pause = pause_run(run_id="deed-cli-1")
    assert pause["status"] == "requested"

    stop = stop_run(run_id="deed-cli-1")
    assert stop["status"] == "requested"

    watch = watch_run(run_id="deed-cli-1", timeout_seconds=1, poll_interval=0.01)
    assert watch.get("reason") != "missing_run_state"

    message = inject_user_message(
        run_id="deed-cli-1",
        text="hello",
        source="tester",
        loop_kind=None,
        metadata=None,
    )
    assert message["status"] == "injected"

    answer = answer_run(
        run_id="deed-cli-1",
        prompt_id="p1",
        choice="yes",
        note=None,
        loop_kind="deed_to_ir",
    )
    assert answer.get("status") != "error"

    cls = classify_resumability("deed-cli-1")
    assert cls["reason_code"] != "missing_state"


def test_resume_uses_namespaced_checkpoint(isolated_harness_root) -> None:
    st = _write_namespaced_run(
        isolated_harness_root / "cli_runs",
        collection="deed_to_ir",
        run_id="deed-resume-1",
    )
    ckpt = Path(st.paths.run_dir) / "kernel_resume.json"
    ckpt.write_text("{}", encoding="utf-8")
    cls = classify_resumability("deed-resume-1")
    assert cls["checkpoint_path"] == str(ckpt.resolve())


def test_ambiguous_run_id_refused_by_cli_commands(isolated_harness_root) -> None:
    root = isolated_harness_root / "cli_runs"
    root.mkdir(parents=True, exist_ok=True)
    run_id = "ambiguous-run"
    _write_legacy_run(root, run_id=run_id)
    namespaced = root / BY_LOOP_KIND_DIRNAME / "deed_to_ir" / run_id
    namespaced.mkdir(parents=True)
    (namespaced / "state.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

    assert status_run(run_id=run_id)["reason_code"] == "run_id_ambiguous"
    assert pause_run(run_id=run_id)["reason_code"] == "run_id_ambiguous"
    assert stop_run(run_id=run_id)["reason_code"] == "run_id_ambiguous"
    assert watch_run(run_id=run_id, timeout_seconds=1, poll_interval=0.01)["reason"] == "run_id_ambiguous"
    assert inject_user_message(
        run_id=run_id,
        text="x",
        source="tester",
        loop_kind=None,
        metadata=None,
    )["reason"] == "run_id_ambiguous"
    assert classify_resumability(run_id)["reason_code"] == "run_id_ambiguous"
