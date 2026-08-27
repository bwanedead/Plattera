"""Per-turn resume checkpoint persistence tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from harness.cli.resume_paths import (
    kernel_resume_path,
    turn_checkpoint_canonical_path,
    turn_checkpoint_legacy_path,
)
from harness.cli.test_cli_fork_resume import _minimal_valid_snapshot
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.memory.resume_snapshot_storage import (
    dumps_compact_checkpoint_bytes,
    gzip_compress_deterministic,
    load_kernel_resume_snapshot_from_path,
    write_gzip_json_atomic,
)
from harness.runtime.runner import runner as runner_module


def test_resume_checkpoint_writer_persists_latest_plain_and_turn_gzip(monkeypatch, tmp_path) -> None:
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
    assert latest.suffix == ".json"
    assert not latest.name.endswith(".gz")
    latest_doc = json.loads(latest.read_text(encoding="utf-8"))
    _, _, latest_err = parse_kernel_resume_snapshot(latest_doc)
    assert latest_err is None

    turn = turn_checkpoint_canonical_path(run_dir=run_path, from_turn=18)
    assert turn.is_file()
    assert turn.name.endswith(".json.gz")
    legacy = turn_checkpoint_legacy_path(run_dir=run_path, from_turn=18)
    assert not legacy.exists()

    loaded, err = load_kernel_resume_snapshot_from_path(turn)
    assert err is None
    assert loaded == snapshot
    _, _, parse_err = parse_kernel_resume_snapshot(loaded)
    assert parse_err is None


def test_compressed_checkpoint_round_trips_exact_json_document(tmp_path) -> None:
    snapshot = _minimal_valid_snapshot(next_iteration=5)
    path = tmp_path / "turn_0004.json.gz"
    write_gzip_json_atomic(path, snapshot=snapshot)
    loaded, err = load_kernel_resume_snapshot_from_path(path)
    assert err is None
    assert loaded == dict(snapshot)
    # Round-trip equals the compact JSON document bytes after decompress.
    raw = dumps_compact_checkpoint_bytes(snapshot)
    assert gzip_compress_deterministic(raw) == path.read_bytes()


def test_gzip_output_is_deterministic_for_identical_snapshots(tmp_path) -> None:
    snapshot = _minimal_valid_snapshot(next_iteration=3)
    a = tmp_path / "a.json.gz"
    b = tmp_path / "b.json.gz"
    write_gzip_json_atomic(a, snapshot=snapshot)
    write_gzip_json_atomic(b, snapshot=snapshot)
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes() == gzip_compress_deterministic(dumps_compact_checkpoint_bytes(snapshot))


def test_historical_write_failure_leaves_latest_intact(monkeypatch, tmp_path) -> None:
    run_id = "turn-checkpoint-latest-intact"
    run_path = tmp_path / "cli_runs" / "by_loop_kind" / "deed_to_ir" / run_id
    run_path.mkdir(parents=True)
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", run_id)
    monkeypatch.setattr("harness.cli.run_state.run_dir", lambda _run_id: run_path)

    snapshot = _minimal_valid_snapshot(next_iteration=19)

    with patch(
        "harness.runtime.memory.resume_snapshot_storage.write_gzip_json_atomic",
        side_effect=OSError("simulated gzip write failure"),
    ):
        writer = runner_module._build_resume_checkpoint_writer()
        assert writer is not None
        writer(snapshot)

    latest = kernel_resume_path(run_path)
    assert latest.is_file()
    assert json.loads(latest.read_text(encoding="utf-8"))["next_iteration"] == 19
    assert not turn_checkpoint_canonical_path(run_dir=run_path, from_turn=18).exists()
    assert not turn_checkpoint_legacy_path(run_dir=run_path, from_turn=18).exists()


def test_atomic_write_failure_leaves_no_partial_canonical_checkpoint(tmp_path) -> None:
    path = tmp_path / "turn_0001.json.gz"
    snapshot = _minimal_valid_snapshot(next_iteration=2)

    real_replace = __import__("os").replace

    def _fail_replace(src, dst, *args, **kwargs):
        if str(dst).endswith(".json.gz") or str(dst) == str(path):
            raise OSError("simulated replace failure")
        return real_replace(src, dst, *args, **kwargs)

    with patch("os.replace", side_effect=_fail_replace):
        try:
            write_gzip_json_atomic(path, snapshot=snapshot)
        except OSError:
            pass

    assert not path.exists()
    leftovers = list(tmp_path.glob(".tmp_resume_*"))
    assert leftovers == []
