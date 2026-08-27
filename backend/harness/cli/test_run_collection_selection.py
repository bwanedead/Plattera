"""CLI --run-collection selection and persistence tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.cli import fork_resume as cli_fork
from harness.cli import run_state as rs
from harness.cli import start as cli_start
from harness.cli.resume_paths import turn_checkpoint_legacy_path
from harness.cli.run_layout import BY_LOOP_KIND_DIRNAME, RunLayoutError, normalize_run_collection
from harness.cli.start import build_stub_argv
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.memory.resume_snapshot_storage import write_plain_json_atomic


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


def test_normalize_run_collection_refuses_blank_and_unsafe() -> None:
    with pytest.raises(RunLayoutError) as empty:
        normalize_run_collection("")
    assert empty.value.code == "run_collection_empty"
    with pytest.raises(RunLayoutError) as blank:
        normalize_run_collection("   ")
    assert blank.value.code == "run_collection_empty"
    with pytest.raises(RunLayoutError) as unsafe:
        normalize_run_collection("bad/name")
    assert unsafe.value.code == "run_collection_unsafe"


def test_new_run_state_defaults_collection_from_loop_kind(isolated_harness_root) -> None:
    st = rs.new_run_state(
        run_id="default-collection-1",
        pid=1,
        loop_kind="transcript_edit",
        mode="stub",
        spawn_argv=["python", "-m", "x"],
    )
    assert st.run_collection == "transcript_edit"
    assert st.paths.run_dir.replace("\\", "/").endswith(
        "by_loop_kind/transcript_edit/default-collection-1"
    )


def test_new_run_state_accepts_explicit_collection_divergent_from_loop_kind(
    isolated_harness_root,
) -> None:
    st = rs.new_run_state(
        run_id="row-1",
        pid=1,
        loop_kind="transcript_edit",
        mode="stub",
        spawn_argv=["python", "-m", "x"],
        run_collection="transcript_edit_right_of_way",
    )
    assert st.loop_kind == "transcript_edit"
    assert st.run_collection == "transcript_edit_right_of_way"
    assert st.paths.run_dir.replace("\\", "/").endswith(
        "by_loop_kind/transcript_edit_right_of_way/row-1"
    )


def test_new_run_state_refuses_blank_explicit_collection(isolated_harness_root) -> None:
    with pytest.raises(RunLayoutError) as exc:
        rs.new_run_state(
            run_id="bad-collection",
            pid=1,
            loop_kind="transcript_edit",
            mode="stub",
            spawn_argv=["python", "-m", "x"],
            run_collection=" ",
        )
    assert exc.value.code == "run_collection_empty"


def test_resolve_run_id_auto_allocates_under_collection(isolated_harness_root) -> None:
    run_id, run_dir = cli_start._resolve_run_id(
        explicit_run_id=None,
        run_collection="transcript_edit_curve_station_chain",
    )
    assert run_id.startswith("transcript-edit-curve-station-chain-live-r")
    assert run_dir is not None
    assert "transcript_edit_curve_station_chain" in str(run_dir).replace("\\", "/")


def test_resolve_run_id_explicit_id_skips_allocation(isolated_harness_root) -> None:
    run_id, run_dir = cli_start._resolve_run_id(
        explicit_run_id="explicit-row-9",
        run_collection="transcript_edit_right_of_way",
    )
    assert run_id == "explicit-row-9"
    assert run_dir is None


def test_start_main_default_collection_from_loop_kind(isolated_harness_root, monkeypatch) -> None:
    captured: dict = {}

    def fake_start_run(**kwargs):
        captured.update(kwargs)
        return {
            "run_id": kwargs["run_id"],
            "status": "started",
            "run_collection": kwargs.get("run_collection"),
            "loop_kind": kwargs["loop_kind"],
        }

    monkeypatch.setattr(cli_start, "start_run", fake_start_run)
    monkeypatch.setattr(
        "sys.argv",
        ["harness.cli.start", "--run-id", "start-default-1", "--loop-kind", "transcript_edit", "--stub"],
    )
    cli_start.main()
    assert captured["loop_kind"] == "transcript_edit"
    assert captured["run_collection"] == "transcript_edit"


def test_start_main_explicit_collection(isolated_harness_root, monkeypatch) -> None:
    captured: dict = {}

    def fake_start_run(**kwargs):
        captured.update(kwargs)
        return {
            "run_id": kwargs["run_id"],
            "status": "started",
            "run_collection": kwargs.get("run_collection"),
            "loop_kind": kwargs["loop_kind"],
        }

    monkeypatch.setattr(cli_start, "start_run", fake_start_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "harness.cli.start",
            "--run-id",
            "start-row-1",
            "--loop-kind",
            "transcript_edit",
            "--run-collection",
            "transcript_edit_right_of_way",
            "--stub",
        ],
    )
    cli_start.main()
    assert captured["loop_kind"] == "transcript_edit"
    assert captured["run_collection"] == "transcript_edit_right_of_way"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("", "run_collection_empty"),
        ("   ", "run_collection_empty"),
        ("bad/name", "run_collection_unsafe"),
        ("has space", "run_collection_unsafe"),
    ],
)
def test_start_main_refuses_invalid_explicit_collection(
    isolated_harness_root, monkeypatch, capsys, value, code
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "harness.cli.start",
            "--run-id",
            "bad-col-1",
            "--loop-kind",
            "transcript_edit",
            "--run-collection",
            value,
            "--stub",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli_start.main()
    assert exc.value.code == 2
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload == {"status": "error", "error": code}


def test_fork_preserves_source_collection_divergent_from_loop_kind(tmp_path, monkeypatch) -> None:
    source_id = "fork-src-row"
    source_path = tmp_path / source_id
    source_state = rs.new_run_state(
        run_id=source_id,
        pid=999999,
        loop_kind="transcript_edit",
        mode="stub",
        spawn_argv=build_stub_argv(),
        run_dir=source_path,
        run_collection="transcript_edit_right_of_way",
    )
    source_path.mkdir(parents=True, exist_ok=True)
    rs.write_state(source_state)
    ckpt = turn_checkpoint_legacy_path(run_dir=source_path, from_turn=14)
    write_plain_json_atomic(
        ckpt,
        text=json.dumps(_minimal_valid_snapshot(next_iteration=15), ensure_ascii=False, indent=2, sort_keys=True),
    )

    monkeypatch.setattr(
        cli_fork, "run_dir", lambda run_id: source_path if run_id == source_id else tmp_path / run_id
    )
    monkeypatch.setattr(
        cli_fork, "read_state", lambda run_id: source_state if run_id == source_id else None
    )

    child_id = "fork-child-row"
    child_path = tmp_path / BY_LOOP_KIND_DIRNAME / "transcript_edit_right_of_way" / child_id

    class _Allocated:
        run_id = child_id
        run_dir = child_path
        run_collection = "transcript_edit_right_of_way"
        human_timeline_path = child_path / "audit" / "human" / "timeline.md"

    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=_Allocated()) as alloc:
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 4242
                result = cli_fork.fork_run_from_turn(run_id=source_id, from_turn=14)

    alloc.assert_called_once_with(run_collection="transcript_edit_right_of_way")
    assert result["status"] == "forked"
    assert result["run_collection"] == "transcript_edit_right_of_way"
    assert result["loop_kind"] == "transcript_edit"
    child_state = rs.HarnessCliRunState.from_json_dict(
        json.loads((child_path / "state.json").read_text(encoding="utf-8"))
    )
    assert child_state.run_collection == "transcript_edit_right_of_way"
    assert child_state.loop_kind == "transcript_edit"
