"""Continue-mode fork-resume gates (mocked spawn, temporary roots)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from harness.cli import fork_resume as cli_fork
from harness.cli import run_state as rs
from harness.cli.fork_workspace import parse_workspace_mode
from harness.cli.test_cli_fork_resume import _write_turn_checkpoint


def _launch_argv(*, run_id: str, workspace_id: str | None, extra: dict | None = None) -> list[str]:
    launch: dict = {"run_id": run_id, "dossier_id": "d1"}
    if extra:
        launch.update(extra)
    if workspace_id is not None:
        launch["workspace_id"] = workspace_id
    return [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]


def _write_terminal(run_path: Path, payload: dict) -> None:
    (run_path / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_path / "done.json").write_text(json.dumps(payload), encoding="utf-8")


def _failed_payload() -> dict:
    return {
        "status": "failed",
        "reason_code": "model_call_failed",
        "terminal_class": "failed",
    }


def _source(
    *,
    tmp_path: Path,
    run_id: str,
    spawn_argv: list[str] | None = None,
    turns: tuple[int, ...] = (17,),
    pid: int = 0,
    terminal: dict | None = None,
) -> tuple[rs.HarnessCliRunState, Path]:
    run_path = tmp_path / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    st = rs.new_run_state(
        run_id=run_id,
        pid=pid,
        loop_kind="transcript_edit",
        mode="live",
        spawn_argv=spawn_argv or _launch_argv(run_id=run_id, workspace_id="source-ws"),
        run_dir=run_path,
    )
    rs.write_state(st)
    for turn in turns:
        _write_turn_checkpoint(run_path=run_path, turn=turn, format="gzip")
    payload = _failed_payload() if terminal is None else terminal
    if payload:
        _write_terminal(run_path, payload)
    return st, run_path


def _patch_layout(monkeypatch, *, source_id: str, source_state: rs.HarnessCliRunState, source_path: Path, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli_fork,
        "run_dir",
        lambda run_id: source_path if run_id == source_id else tmp_path / run_id,
    )
    monkeypatch.setattr(
        cli_fork,
        "read_state",
        lambda run_id: source_state if run_id == source_id else None,
    )
    monkeypatch.setattr("harness.cli.fork_continue_eligibility.assess_run_quiescence", lambda _rid: None)
    scan_root = tmp_path / "cli_runs_root"
    scan_root.mkdir(exist_ok=True)
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: scan_root)


def _allocated(tmp_path: Path, child_id: str):
    child_path = tmp_path / child_id

    class _Allocated:
        run_id = child_id
        run_dir = child_path
        human_timeline_path = child_path / "audit" / "human" / "timeline.md"

    return _Allocated(), child_path


def test_parse_workspace_mode_defaults_isolated_and_refuses_unknown() -> None:
    mode, err = parse_workspace_mode(None)
    assert mode == "isolated" and err is None
    mode, err = parse_workspace_mode("isolated")
    assert mode == "isolated" and err is None
    mode, err = parse_workspace_mode("continue")
    assert mode == "continue" and err is None
    mode, err = parse_workspace_mode("CONTINUE")
    assert mode is None and err == "workspace_mode_invalid"


def test_default_fork_is_isolated(tmp_path, monkeypatch) -> None:
    source_id = "fork-default-isolated"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id, terminal={})
    # isolated must still work without terminal artifacts
    (source_path / "result.json").unlink(missing_ok=True)
    (source_path / "done.json").unlink(missing_ok=True)
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    allocated, child_path = _allocated(tmp_path, "child-isolated")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated):
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 11
                result = cli_fork.fork_run_from_turn(run_id=source_id, from_turn=17)
    assert result["status"] == "forked"
    assert result["workspace_mode"] == "isolated"
    assert result["fork_lineage"]["workspace_mode"] == "isolated"
    doc = json.loads(rs.HarnessCliRunState.from_json_dict(
        json.loads((child_path / "state.json").read_text(encoding="utf-8"))
    ).spawn_argv[-1])
    assert "run_id" not in doc
    assert "workspace_id" not in doc


def test_explicit_isolated_strips_source_identity(tmp_path, monkeypatch) -> None:
    source_id = "fork-explicit-isolated"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id, terminal={})
    (source_path / "result.json").unlink(missing_ok=True)
    (source_path / "done.json").unlink(missing_ok=True)
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    allocated, child_path = _allocated(tmp_path, "child-explicit-isolated")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated):
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 12
                result = cli_fork.fork_run_from_turn(
                    run_id=source_id,
                    from_turn=17,
                    workspace_mode="isolated",
                )
    assert result["status"] == "forked"
    doc = json.loads(
        rs.HarnessCliRunState.from_json_dict(
            json.loads((child_path / "state.json").read_text(encoding="utf-8"))
        ).spawn_argv[-1]
    )
    assert "run_id" not in doc
    assert "workspace_id" not in doc


def test_continue_preserves_explicit_workspace_and_new_run_id(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-ws"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id, turns=(14, 17))
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    allocated, child_path = _allocated(tmp_path, "child-continue")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated) as alloc:
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 13
                result = cli_fork.fork_run_from_turn(
                    run_id=source_id,
                    from_turn=17,
                    workspace_mode="continue",
                )
    alloc.assert_called_once()
    assert result["status"] == "forked"
    assert result["run_id"] == "child-continue"
    assert result["run_id"] != source_id
    lineage = result["fork_lineage"]
    assert lineage["workspace_mode"] == "continue"
    assert lineage["source_workspace_id"] == "source-ws"
    child_state = rs.HarnessCliRunState.from_json_dict(
        json.loads((child_path / "state.json").read_text(encoding="utf-8"))
    )
    doc = json.loads(child_state.spawn_argv[-1])
    assert "run_id" not in doc
    assert doc["workspace_id"] == "source-ws"
    env = popen.call_args.kwargs["env"]
    assert env["HARNESS_CLI_RUN_ID"] == "child-continue"


def test_continue_missing_workspace_uses_source_run_id(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-default-ws"
    source_state, source_path = _source(
        tmp_path=tmp_path,
        run_id=source_id,
        spawn_argv=_launch_argv(run_id=source_id, workspace_id=None),
    )
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    allocated, child_path = _allocated(tmp_path, "child-default-ws")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated):
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 14
                result = cli_fork.fork_run_from_turn(
                    run_id=source_id,
                    from_turn=17,
                    workspace_mode="continue",
                )
    assert result["fork_lineage"]["source_workspace_id"] == source_id
    doc = json.loads(
        rs.HarnessCliRunState.from_json_dict(
            json.loads((child_path / "state.json").read_text(encoding="utf-8"))
        ).spawn_argv[-1]
    )
    assert doc["workspace_id"] == source_id


def test_continuation_of_continuation_keeps_original_workspace(tmp_path, monkeypatch) -> None:
    source_id = "intermediate-child"
    argv = _launch_argv(run_id="should-not-matter", workspace_id="original-ws")
    # Continuation children store workspace only.
    argv[-1] = json.dumps({"workspace_id": "original-ws", "dossier_id": "d1"}, separators=(",", ":"))
    source_state, source_path = _source(
        tmp_path=tmp_path,
        run_id=source_id,
        spawn_argv=argv,
    )
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    allocated, child_path = _allocated(tmp_path, "grandchild")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated):
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 15
                result = cli_fork.fork_run_from_turn(
                    run_id=source_id,
                    from_turn=17,
                    workspace_mode="continue",
                )
    assert result["fork_lineage"]["source_workspace_id"] == "original-ws"
    doc = json.loads(
        rs.HarnessCliRunState.from_json_dict(
            json.loads((child_path / "state.json").read_text(encoding="utf-8"))
        ).spawn_argv[-1]
    )
    assert doc["workspace_id"] == "original-ws"
    assert "run_id" not in doc
    assert doc["workspace_id"] != source_id


def test_continue_earlier_than_latest_refuses_before_allocate(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-old-turn"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id, turns=(14, 17))
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=14,
                workspace_mode="continue",
            )
    assert result["status"] == "refused"
    assert result["reason_code"] == "continue_checkpoint_not_latest"
    alloc.assert_not_called()
    popen.assert_not_called()


def test_continue_active_and_unknown_activity_refuse(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-active"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    monkeypatch.setattr(cli_fork, "run_dir", lambda _rid: source_path)
    monkeypatch.setattr(cli_fork, "read_state", lambda _rid: source_state)
    scan_root = tmp_path / "cli_runs_root"
    scan_root.mkdir()
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: scan_root)
    monkeypatch.setattr(
        "harness.cli.fork_continue_eligibility.assess_run_quiescence",
        lambda _rid: "run_not_quiescent",
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
    assert result["reason_code"] == "run_not_quiescent"
    alloc.assert_not_called()
    popen.assert_not_called()

    monkeypatch.setattr(
        "harness.cli.fork_continue_eligibility.assess_run_quiescence",
        lambda _rid: "run_activity_unknown",
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        result = cli_fork.fork_run_from_turn(
            run_id=source_id,
            from_turn=17,
            workspace_mode="continue",
        )
    assert result["reason_code"] == "run_activity_unknown"
    alloc.assert_not_called()


def test_continue_refuses_completed_hitl_and_operator_stopped(tmp_path, monkeypatch) -> None:
    cases = [
        (
            {"status": "completed", "reason_code": "complete_run", "terminal_class": "completed"},
            "continue_completed",
        ),
        (
            {"status": "paused", "reason_code": "wait_for_human", "terminal_class": "paused", "wait_for_human": True},
            "continue_waiting_hitl",
        ),
        (
            {"status": "stopped", "reason_code": "stopped_by_operator", "terminal_class": "stopped"},
            "continue_operator_resumable",
        ),
        (
            {"status": "paused", "reason_code": "paused_by_operator", "terminal_class": "paused"},
            "continue_operator_resumable",
        ),
    ]
    for payload, expected in cases:
        source_id = f"fork-continue-{expected}"
        source_state, source_path = _source(
            tmp_path=tmp_path,
            run_id=source_id,
            terminal=payload,
        )
        _patch_layout(
            monkeypatch,
            source_id=source_id,
            source_state=source_state,
            source_path=source_path,
            tmp_path=tmp_path,
        )
        with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
        assert result["status"] == "refused"
        assert result["reason_code"] == expected
        alloc.assert_not_called()


def test_continue_refuses_malformed_launch_and_unsafe_workspace(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-bad-json"
    source_state, source_path = _source(
        tmp_path=tmp_path,
        run_id=source_id,
        spawn_argv=["python", "-m", "x", "--launch-context-json", "{nope"],
    )
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        result = cli_fork.fork_run_from_turn(
            run_id=source_id,
            from_turn=17,
            workspace_mode="continue",
        )
    assert result["reason_code"] == "launch_context_malformed"
    alloc.assert_not_called()

    source_id = "fork-continue-list-ctx"
    source_state, source_path = _source(
        tmp_path=tmp_path,
        run_id=source_id,
        spawn_argv=["python", "-m", "x", "--launch-context-json", "[1]"],
    )
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        result = cli_fork.fork_run_from_turn(
            run_id=source_id,
            from_turn=17,
            workspace_mode="continue",
        )
    assert result["reason_code"] == "launch_context_not_object"
    alloc.assert_not_called()

    cases = [
        (
            "fork-continue-blank-ws",
            _launch_argv(run_id="fork-continue-blank-ws", workspace_id="  padded  "),
            "workspace_id_invalid",
        ),
        (
            "fork-continue-num-ws",
            ["python", "-m", "x", "--launch-context-json", json.dumps({"run_id": "fork-continue-num-ws", "workspace_id": 12})],
            "workspace_id_invalid",
        ),
        (
            "fork-continue-unsafe-ws",
            _launch_argv(run_id="fork-continue-unsafe-ws", workspace_id="../escape"),
            "workspace_id_unsafe",
        ),
        (
            "fork-continue-mismatch",
            _launch_argv(run_id="other-run", workspace_id="source-ws"),
            "launch_run_id_source_mismatch",
        ),
    ]
    for source_id, argv, expected in cases:
        source_state, source_path = _source(
            tmp_path=tmp_path,
            run_id=source_id,
            spawn_argv=argv,
        )
        _patch_layout(
            monkeypatch,
            source_id=source_id,
            source_state=source_state,
            source_path=source_path,
            tmp_path=tmp_path,
        )
        with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
        assert result["reason_code"] == expected
        alloc.assert_not_called()


def test_continue_refuses_malformed_terminal_result(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-bad-result"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    (source_path / "result.json").write_text("{nope", encoding="utf-8")
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
    assert result["status"] == "refused"
    assert result["reason_code"] == "continue_result_malformed"
    alloc.assert_not_called()
    popen.assert_not_called()


def test_continue_quiescence_change_before_spawn_does_not_launch(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-race"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    monkeypatch.setattr(cli_fork, "run_dir", lambda _rid: source_path)
    monkeypatch.setattr(cli_fork, "read_state", lambda _rid: source_state)
    scan_root = tmp_path / "cli_runs_root"
    scan_root.mkdir()
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: scan_root)
    calls = iter([None, "run_not_quiescent"])

    def _quiet(_rid: str) -> str | None:
        return next(calls)

    monkeypatch.setattr("harness.cli.fork_continue_eligibility.assess_run_quiescence", _quiet)
    allocated, _child_path = _allocated(tmp_path, "child-aborted")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated) as alloc:
        with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
    assert result["status"] == "refused"
    assert result["reason_code"] == "run_not_quiescent"
    alloc.assert_called_once()
    popen.assert_not_called()
    assert not (scan_root / "workspace_claims" / "source-ws.json").exists()


def _plant_continue_occupant(
    scan_root: Path,
    *,
    run_id: str,
    workspace_id: str,
    status: str,
    pid: object = 0,
    terminal: bool = False,
) -> Path:
    run_path = scan_root / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id,
        "pid": pid,
        "status": status,
        "loop_kind": "transcript_edit",
        "mode": "live",
        "spawn_argv": [
            "python",
            "-m",
            "x",
            "--launch-context-json",
            json.dumps({"workspace_id": workspace_id}, separators=(",", ":")),
        ],
        "extra": {
            "fork_lineage": {
                "workspace_mode": "continue",
                "source_workspace_id": workspace_id,
            }
        },
        "paths": {},
    }
    (run_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    if terminal:
        payload = {
            "status": "failed",
            "reason_code": "model_call_failed",
            "terminal_class": "failed",
        }
        (run_path / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        (run_path / "done.json").write_text(json.dumps(payload), encoding="utf-8")
    return run_path


def test_continue_refuses_duplicate_launch_context(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-dup-ctx"
    argv = [
        "python",
        "-m",
        "x",
        "--launch-context-json",
        json.dumps({"run_id": source_id, "workspace_id": "source-ws"}),
        "--launch-context-json",
        json.dumps({"run_id": source_id, "workspace_id": "other-ws"}),
    ]
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id, spawn_argv=argv)
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        result = cli_fork.fork_run_from_turn(
            run_id=source_id,
            from_turn=17,
            workspace_mode="continue",
        )
    assert result["reason_code"] == "launch_context_duplicate"
    alloc.assert_not_called()


def test_continue_refuses_divergent_result_and_done(tmp_path, monkeypatch) -> None:
    cases = [
        {
            "done": {
                "status": "completed",
                "reason_code": "complete_run",
                "terminal_class": "completed",
            }
        },
        {
            "done": {
                "status": "paused",
                "reason_code": "wait_for_human",
                "terminal_class": "paused",
                "wait_for_human": True,
            }
        },
        {
            "done": {
                "status": "stopped",
                "reason_code": "stopped_by_operator",
                "terminal_class": "stopped",
            }
        },
        {
            "done": {
                "status": "failed",
                "reason_code": "model_call_failed",
                "terminal_class": "exhausted",
            }
        },
        {
            "done": {
                "status": "error",
                "reason_code": "model_call_failed",
                "terminal_class": "failed",
            }
        },
        {
            "done": {
                "status": "failed",
                "reason_code": "recoverable_turn_failure_budget_exhausted",
                "terminal_class": "failed",
            }
        },
        {
            "done": {
                "status": "failed",
                "reason_code": "model_call_failed",
                "terminal_class": "failed",
                "wait_for_human": True,
            }
        },
    ]
    for index, case in enumerate(cases):
        source_id = f"fork-continue-conflict-{index}"
        source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
        (source_path / "done.json").write_text(json.dumps(case["done"]), encoding="utf-8")
        _patch_layout(
            monkeypatch,
            source_id=source_id,
            source_state=source_state,
            source_path=source_path,
            tmp_path=tmp_path,
        )
        with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
        assert result["reason_code"] == "continue_terminal_conflict"
        alloc.assert_not_called()


def test_continue_refuses_malformed_terminal_coordinates(tmp_path, monkeypatch) -> None:
    cases = [
        {
            "status": "failed",
            "reason_code": "model_call_failed",
            "terminal_class": 1,
        },
        {
            "status": True,
            "reason_code": "model_call_failed",
            "terminal_class": "failed",
        },
        {
            "status": "failed",
            "reason_code": {},
            "terminal_class": "failed",
        },
        {
            "status": "failed",
            "reason_code": "model_call_failed",
            "terminal_class": "",
        },
        {
            "status": "failed",
            "reason_code": "  ",
            "terminal_class": "failed",
        },
        {
            "status": "failed",
            "reason_code": "model_call_failed",
            "terminal_class": "failed",
            "wait_for_human": 1,
        },
        {
            "status": "failed",
            "reason_code": "model_call_failed",
            "terminal_class": "failed",
            "wait_for_human": "true",
        },
    ]
    for index, payload in enumerate(cases):
        source_id = f"fork-continue-bad-coord-{index}"
        source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id, terminal={})
        (source_path / "result.json").write_text(json.dumps(payload), encoding="utf-8")
        (source_path / "done.json").write_text(json.dumps(payload), encoding="utf-8")
        _patch_layout(
            monkeypatch,
            source_id=source_id,
            source_state=source_state,
            source_path=source_path,
            tmp_path=tmp_path,
        )
        with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
        assert result["reason_code"] == "continue_result_malformed", payload
        alloc.assert_not_called()


def test_continue_refuses_malformed_done_when_result_exists(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-bad-done"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    (source_path / "done.json").write_text("[1]", encoding="utf-8")
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        result = cli_fork.fork_run_from_turn(
            run_id=source_id,
            from_turn=17,
            workspace_mode="continue",
        )
    assert result["reason_code"] == "continue_result_malformed"
    alloc.assert_not_called()


def test_continue_workspace_in_use_and_unknown_occupant(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-ws-busy"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    scan_root = tmp_path / "cli_runs_root"
    _plant_continue_occupant(
        scan_root,
        run_id="active-child",
        workspace_id="source-ws",
        status="forked",
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        result = cli_fork.fork_run_from_turn(
            run_id=source_id,
            from_turn=17,
            workspace_mode="continue",
        )
    assert result["reason_code"] == "continue_workspace_in_use"
    alloc.assert_not_called()

    source_id = "fork-continue-ws-unknown"
    source_state, source_path = _source(
        tmp_path=tmp_path,
        run_id=source_id,
        spawn_argv=_launch_argv(run_id=source_id, workspace_id="unknown-ws"),
    )
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    scan_root = tmp_path / "cli_runs_root"
    _plant_continue_occupant(
        scan_root,
        run_id="mystery-child",
        workspace_id="unknown-ws",
        status="forked",
        pid="bad",
    )
    with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
        result = cli_fork.fork_run_from_turn(
            run_id=source_id,
            from_turn=17,
            workspace_mode="continue",
        )
    assert result["reason_code"] == "run_activity_unknown"
    alloc.assert_not_called()


def test_aborted_child_does_not_block_and_terminal_child_can_continue(
    tmp_path, monkeypatch
) -> None:
    source_id = "fork-continue-after-abort"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    scan_root = tmp_path / "cli_runs_root"
    _plant_continue_occupant(
        scan_root,
        run_id="aborted-child",
        workspace_id="source-ws",
        status="fork_aborted",
    )
    allocated, _child_path = _allocated(tmp_path, "next-child")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated):
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 77
                result = cli_fork.fork_run_from_turn(
                    run_id=source_id,
                    from_turn=17,
                    workspace_mode="continue",
                )
    assert result["status"] == "forked"

    source_id = "terminal-continue-child"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    scan_root = tmp_path / "cli_runs_root"
    _plant_continue_occupant(
        scan_root,
        run_id="prior-terminal-child",
        workspace_id="source-ws",
        status="forked",
        terminal=True,
    )
    allocated, _child_path = _allocated(tmp_path, "from-terminal")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated):
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 78
                result = cli_fork.fork_run_from_turn(
                    run_id=source_id,
                    from_turn=17,
                    workspace_mode="continue",
                )
    assert result["status"] == "forked"


def test_malformed_claim_refuses_before_allocate(tmp_path, monkeypatch) -> None:
    cases = [
        "{nope",
        {
            "workspace_id": "other-ws",
            "owner_run_id": "owner-1",
            "status": "claimed",
        },
        {
            "workspace_id": "source-ws",
            "owner_run_id": "",
            "status": "claimed",
        },
        {
            "workspace_id": "source-ws",
            "owner_run_id": "../x",
            "status": "claimed",
        },
        {
            "workspace_id": "source-ws",
            "owner_run_id": "owner-1",
            "status": "held",
        },
        {
            "workspace_id": "source-ws",
            "owner_run_id": "owner-1",
            "status": "claimed",
            "note": "extra",
        },
        {
            "workspace_id": "source-ws",
            "owner_run_id": 12,
            "status": "claimed",
        },
    ]
    for index, payload in enumerate(cases):
        source_id = f"fork-continue-bad-claim-{index}"
        source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
        _patch_layout(
            monkeypatch,
            source_id=source_id,
            source_state=source_state,
            source_path=source_path,
            tmp_path=tmp_path,
        )
        scan_root = tmp_path / "cli_runs_root"
        claim = scan_root / "workspace_claims" / "source-ws.json"
        claim.parent.mkdir(parents=True, exist_ok=True)
        if type(payload) is str:
            claim.write_text(payload, encoding="utf-8")
        else:
            claim.write_text(json.dumps(payload), encoding="utf-8")
        before = claim.read_bytes()
        with patch("harness.cli.fork_resume.allocate_automatic_run_id") as alloc:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
        assert result["reason_code"] == "run_activity_unknown", payload
        alloc.assert_not_called()
        assert claim.read_bytes() == before


def test_continue_rechecks_full_eligibility_before_spawn(tmp_path, monkeypatch) -> None:
    source_id = "fork-continue-gate-race"
    source_state, source_path = _source(tmp_path=tmp_path, run_id=source_id)
    _patch_layout(
        monkeypatch,
        source_id=source_id,
        source_state=source_state,
        source_path=source_path,
        tmp_path=tmp_path,
    )
    from harness.cli.fork_continue_eligibility import continue_pre_allocate_refusal

    calls = {"n": 0}
    original = continue_pre_allocate_refusal

    def _gate(**kwargs):
        if calls["n"] == 1:
            completed = {
                "status": "completed",
                "reason_code": "complete_run",
                "terminal_class": "completed",
            }
            (source_path / "result.json").write_text(json.dumps(completed), encoding="utf-8")
            (source_path / "done.json").write_text(json.dumps(completed), encoding="utf-8")
        calls["n"] += 1
        return original(**kwargs)

    monkeypatch.setattr("harness.cli.fork_resume.continue_pre_allocate_refusal", _gate)
    allocated, _child_path = _allocated(tmp_path, "child-gate-aborted")
    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=allocated) as alloc:
        with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
            result = cli_fork.fork_run_from_turn(
                run_id=source_id,
                from_turn=17,
                workspace_mode="continue",
            )
    assert result["status"] == "refused"
    assert result["reason_code"] == "continue_completed"
    alloc.assert_called_once()
    popen.assert_not_called()
    assert not (tmp_path / "cli_runs_root" / "workspace_claims" / "source-ws.json").exists()
