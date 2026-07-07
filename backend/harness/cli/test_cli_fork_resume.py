"""CLI fork-resume operator tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.cli import fork_resume as cli_fork
from harness.cli import run_state as rs
from harness.cli.resume_paths import turn_checkpoint_path
from harness.cli.start import build_stub_argv
from harness.mission_state import new_mission_state, new_resolution_state


def _minimal_valid_snapshot(*, next_iteration: int = 15) -> dict:
    resolution = new_resolution_state()
    mission = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        resolution_state=resolution,
    )
    return {
        "schema_version": "kernel_resume.v1",
        "next_iteration": next_iteration,
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


def _write_source_run(*, run_id: str, run_path: Path, with_turn: int | None = None) -> rs.HarnessCliRunState:
    st = rs.new_run_state(
        run_id=run_id,
        pid=999999,
        loop_kind="deed_to_ir",
        mode="stub",
        spawn_argv=build_stub_argv(),
        run_dir=run_path,
    )
    run_path.mkdir(parents=True, exist_ok=True)
    rs.write_state(st)
    if with_turn is not None:
        ckpt = turn_checkpoint_path(run_dir=run_path, from_turn=with_turn)
        ckpt.parent.mkdir(parents=True, exist_ok=True)
        ckpt.write_text(json.dumps(_minimal_valid_snapshot(next_iteration=with_turn + 1)), encoding="utf-8")
    return st


def test_fork_refuses_when_turn_checkpoint_missing(tmp_path, monkeypatch) -> None:
    run_id = "fork-missing-turn-test"
    run_path = tmp_path / run_id
    source_state = _write_source_run(run_id=run_id, run_path=run_path)
    monkeypatch.setattr(cli_fork, "run_dir", lambda _run_id: run_path)
    monkeypatch.setattr(cli_fork, "read_state", lambda _run_id: source_state)

    result = cli_fork.fork_run_from_turn(run_id=run_id, from_turn=14)
    assert result["status"] == "refused"
    assert result["reason_code"] == "turn_checkpoint_missing"
    assert result.get("resume_latest_command") is None


def test_fork_creates_child_run_with_lineage(tmp_path, monkeypatch) -> None:
    source_id = "fork-source-test"
    source_path = tmp_path / source_id
    source_state = _write_source_run(run_id=source_id, run_path=source_path, with_turn=14)
    monkeypatch.setattr(cli_fork, "run_dir", lambda run_id: source_path if run_id == source_id else tmp_path / run_id)
    monkeypatch.setattr(cli_fork, "read_state", lambda run_id: source_state if run_id == source_id else None)

    child_id = "deed-to-ir-live-r00009999"
    child_path = tmp_path / child_id

    class _Allocated:
        run_id = child_id
        run_dir = child_path
        human_timeline_path = child_path / "audit" / "human" / "timeline.md"

    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=_Allocated()):
        with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
            popen.return_value.pid = 4242
            result = cli_fork.fork_run_from_turn(run_id=source_id, from_turn=14)

    assert result["status"] == "forked"
    assert result["run_id"] == child_id
    assert result["source_run_id"] == source_id
    assert result["from_turn"] == 14
    lineage = result["fork_lineage"]
    assert lineage["forked_from_run_id"] == source_id
    assert lineage["forked_from_turn"] == 14

    child_state = rs.HarnessCliRunState.from_json_dict(
        json.loads((child_path / "state.json").read_text(encoding="utf-8"))
    )
    assert child_state.extra.get("fork_lineage") == lineage
    assert source_state.status != "forked"

    popen.assert_called_once()
    env = popen.call_args.kwargs["env"]
    assert "turn_0014.json" in env["HARNESS_CLI_RESUME_FILE"]


def test_fork_refuses_checkpoint_turn_mismatch(tmp_path, monkeypatch) -> None:
    run_id = "fork-turn-mismatch-test"
    run_path = tmp_path / run_id
    source_state = _write_source_run(run_id=run_id, run_path=run_path, with_turn=14)
    ckpt = turn_checkpoint_path(run_dir=run_path, from_turn=14)
    ckpt.write_text(json.dumps(_minimal_valid_snapshot(next_iteration=16)), encoding="utf-8")
    monkeypatch.setattr(cli_fork, "run_dir", lambda _run_id: run_path)
    monkeypatch.setattr(cli_fork, "read_state", lambda _run_id: source_state)

    result = cli_fork.fork_run_from_turn(run_id=run_id, from_turn=14)
    assert result["status"] == "refused"
    assert result["reason_code"] == "checkpoint_turn_mismatch"
    assert result["expected_next_iteration"] == 15


def test_fork_strips_embedded_launch_context_identity(tmp_path, monkeypatch) -> None:
    source_id = "fork-launch-context-test"
    source_path = tmp_path / source_id
    launch = {"run_id": source_id, "workspace_id": "parent-ws", "dossier_id": "d1"}
    spawn_argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    source_state = rs.new_run_state(
        run_id=source_id,
        pid=999999,
        loop_kind="deed_to_ir",
        mode="live",
        spawn_argv=spawn_argv,
        run_dir=source_path,
    )
    source_path.mkdir(parents=True, exist_ok=True)
    rs.write_state(source_state)
    ckpt = turn_checkpoint_path(run_dir=source_path, from_turn=14)
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    ckpt.write_text(json.dumps(_minimal_valid_snapshot(next_iteration=15)), encoding="utf-8")

    monkeypatch.setattr(cli_fork, "run_dir", lambda run_id: source_path if run_id == source_id else tmp_path / run_id)
    monkeypatch.setattr(cli_fork, "read_state", lambda run_id: source_state if run_id == source_id else None)

    child_id = "deed-to-ir-live-r00008888"
    child_path = tmp_path / child_id

    class _Allocated:
        run_id = child_id
        run_dir = child_path
        human_timeline_path = child_path / "audit" / "human" / "timeline.md"

    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=_Allocated()):
        with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
            popen.return_value.pid = 5151
            result = cli_fork.fork_run_from_turn(run_id=source_id, from_turn=14)

    assert result["status"] == "forked"
    child_state = rs.HarnessCliRunState.from_json_dict(
        json.loads((child_path / "state.json").read_text(encoding="utf-8"))
    )
    launch_arg = child_state.spawn_argv[-1]
    doc = json.loads(launch_arg)
    assert "run_id" not in doc
    assert "workspace_id" not in doc
    assert doc["dossier_id"] == "d1"
