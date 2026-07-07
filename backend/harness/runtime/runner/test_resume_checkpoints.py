"""Per-turn resume checkpoint persistence tests."""

from __future__ import annotations

import json

from harness.cli.resume_paths import kernel_resume_path, turn_checkpoint_path
from harness.cli.test_cli_fork_resume import _minimal_valid_snapshot
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.runner import runner as runner_module


def test_resume_checkpoint_writer_persists_latest_and_turn_file(monkeypatch, tmp_path) -> None:
    run_id = "turn-checkpoint-writer-test"
    run_path = tmp_path / "cli_runs" / "by_loop_kind" / "deed_to_ir" / run_id
    run_path.mkdir(parents=True)
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", run_id)
    monkeypatch.setattr(
        "harness.cli.run_state.run_dir",
        lambda _run_id: run_path,
    )

    writer = runner_module._build_resume_checkpoint_writer()
    assert writer is not None
    snapshot = _minimal_valid_snapshot(next_iteration=19)
    writer(snapshot)

    latest = kernel_resume_path(run_path)
    assert latest.is_file()
    turn = turn_checkpoint_path(run_dir=run_path, from_turn=18)
    assert turn.is_file()
    doc = json.loads(turn.read_text(encoding="utf-8"))
    _, _, err = parse_kernel_resume_snapshot(doc)
    assert err is None
