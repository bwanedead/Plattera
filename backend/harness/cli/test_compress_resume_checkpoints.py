"""Tests for validation-first legacy resume-checkpoint compression."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any

import pytest

from harness.cli.resume_checkpoint_compress import (
    REASON_CANONICAL_CONFLICT,
    REASON_CANONICAL_SYMLINK,
    REASON_CHECKPOINT_TURN_MISMATCH,
    REASON_DELETE_FAILED,
    REASON_PATH_IS_SYMLINK,
    REASON_RUN_NOT_QUIESCENT,
    REASON_STAGING_CLEANUP_FAILED,
    REASON_VERIFICATION_FAILED,
    REASON_WRITE_FAILED,
    compress_run_legacy_checkpoints,
    estimate_canonical_bytes,
)
from harness.cli.resume_paths import (
    TURN_CHECKPOINTS_DIRNAME,
    kernel_resume_path,
    turn_checkpoint_canonical_path,
    turn_checkpoint_legacy_path,
)
from harness.cli.run_layout import BY_LOOP_KIND_DIRNAME, allocate_run_directory
from harness.cli import run_state as rs
from harness.cli.start import build_stub_argv
from harness.cli.test_cli_fork_resume import _minimal_valid_snapshot
from harness.runtime.memory.resume_snapshot_storage import (
    RESUME_SNAPSHOT_GZIP_INVALID,
    RESUME_SNAPSHOT_JSON_INVALID,
    load_kernel_resume_snapshot_from_path,
    write_gzip_json_atomic,
    write_plain_json_atomic,
)


def _seed_run(
    isolated_harness_root: Path,
    *,
    run_id: str,
    collection: str = "deed_to_ir",
    pid: int = 999999999,
) -> Path:
    run_dir = allocate_run_directory(run_id=run_id, run_collection=collection)
    st = rs.new_run_state(
        run_id=run_id,
        pid=pid,
        loop_kind=collection,
        mode="stub",
        spawn_argv=build_stub_argv(),
        run_dir=run_dir,
        run_collection=collection,
    )
    rs.write_state(st)
    return run_dir


def _write_legacy(run_dir: Path, turn: int, snapshot: dict[str, Any] | None = None) -> Path:
    snap = snapshot if snapshot is not None else _minimal_valid_snapshot(next_iteration=turn + 1)
    path = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=turn)
    text = json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True)
    write_plain_json_atomic(path, text=text)
    return path


def _write_canonical(run_dir: Path, turn: int, snapshot: dict[str, Any] | None = None) -> Path:
    snap = snapshot if snapshot is not None else _minimal_valid_snapshot(next_iteration=turn + 1)
    path = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=turn)
    write_gzip_json_atomic(path, snapshot=snap)
    return path


def _gzip_bytes_for(snapshot: dict[str, Any]) -> bytes:
    from harness.runtime.memory.resume_snapshot_storage import (
        dumps_compact_checkpoint_bytes,
        gzip_compress_deterministic,
    )

    return gzip_compress_deterministic(dumps_compact_checkpoint_bytes(snapshot))


def test_dry_run_writes_nothing(isolated_harness_root) -> None:
    run_id = "compress-dry-run"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 12)
    before = legacy.read_bytes()
    kernel = kernel_resume_path(run_dir)
    kernel.write_text('{"keep":true}', encoding="utf-8")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=False)
    assert result["status"] == "planned"
    assert result["apply"] is False
    assert result["legacy_checkpoint_count"] == 1
    assert result["checkpoints"][0]["status"] == "would_migrate"
    assert result["migrated_count"] == 0
    assert legacy.read_bytes() == before
    assert not turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=12).exists()
    assert kernel.read_text(encoding="utf-8") == '{"keep":true}'


def test_successful_atomic_migration_and_round_trip(isolated_harness_root) -> None:
    run_id = "compress-migrate-ok"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=5)
    legacy = _write_legacy(run_dir, 4, snap)
    legacy_size = legacy.stat().st_size
    expected_canon = estimate_canonical_bytes(snap)

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["status"] == "applied"
    assert result["migrated_count"] == 1
    assert result["bytes_reclaimed"] == legacy_size - expected_canon
    assert result["legacy_bytes_removed"] == legacy_size
    assert result["legacy_bytes"] == legacy_size
    assert result["canonical_bytes"] == expected_canon
    assert result["checkpoints"][0]["status"] == "migrated"

    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=4)
    assert canonical.is_file()
    assert not legacy.exists()
    loaded, err = load_kernel_resume_snapshot_from_path(canonical)
    assert err is None
    assert loaded == snap


def test_legacy_deleted_only_after_verified_canonical(isolated_harness_root) -> None:
    run_id = "compress-verify-order"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=3)
    legacy = _write_legacy(run_dir, 2, snap)
    calls: list[str] = []

    def _write(path: Path, snapshot: dict[str, Any]) -> None:
        calls.append("write")
        write_gzip_json_atomic(path, snapshot=snapshot)

    def _load(path: Path | str):
        calls.append(f"load:{Path(path).name}")
        return load_kernel_resume_snapshot_from_path(path)

    def _delete(path: Path) -> None:
        calls.append("delete")
        path.unlink()

    result = compress_run_legacy_checkpoints(
        run_id=run_id,
        apply=True,
        write_gzip_fn=_write,
        load_fn=_load,
        delete_fn=_delete,
    )
    assert result["migrated_count"] == 1
    assert not legacy.exists()
    # load legacy → write unique staging → load staging → delete legacy (promote is hard-link)
    assert calls[0].startswith("load:turn_0002.json")
    assert "write" in calls
    write_i = calls.index("write")
    delete_i = calls.index("delete")
    assert any("staging.json.gz" in c for c in calls[write_i:delete_i])
    assert delete_i > write_i
    assert turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=2).is_file()
    assert not list((run_dir / TURN_CHECKPOINTS_DIRNAME).glob("*.staging.json.gz"))


def test_existing_equal_canonical_removes_legacy(isolated_harness_root) -> None:
    run_id = "compress-equal-both"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=8)
    legacy = _write_legacy(run_dir, 7, snap)
    _write_canonical(run_dir, 7, snap)
    legacy_size = legacy.stat().st_size

    planned = compress_run_legacy_checkpoints(run_id=run_id, apply=False)
    assert planned["checkpoints"][0]["status"] == "would_remove_equivalent"

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["status"] == "applied"
    assert result["equivalent_legacy_removed_count"] == 1
    assert result["bytes_reclaimed"] == legacy_size
    assert result["legacy_bytes_removed"] == legacy_size
    assert not legacy.exists()
    assert turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=7).is_file()


def test_existing_conflicting_canonical_untouched(isolated_harness_root) -> None:
    run_id = "compress-conflict"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy_snap = _minimal_valid_snapshot(next_iteration=8)
    other = _minimal_valid_snapshot(next_iteration=8)
    other["continuity"] = dict(other["continuity"])
    other["continuity"]["latest_refs"] = {"different": "body"}
    legacy = _write_legacy(run_dir, 7, legacy_snap)
    canonical = _write_canonical(run_dir, 7, other)
    legacy_bytes = legacy.read_bytes()
    canonical_bytes = canonical.read_bytes()

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["status"] == "partial"
    assert result["checkpoints"][0]["status"] == "skipped"
    assert result["checkpoints"][0]["reason_code"] == REASON_CANONICAL_CONFLICT
    assert legacy.read_bytes() == legacy_bytes
    assert canonical.read_bytes() == canonical_bytes


def test_corrupt_legacy_skipped(isolated_harness_root) -> None:
    run_id = "compress-corrupt-legacy"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=1)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("not-json", encoding="utf-8")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["checkpoints"][0]["status"] == "skipped"
    assert result["checkpoints"][0]["reason_code"] == RESUME_SNAPSHOT_JSON_INVALID
    assert legacy.exists()


def test_corrupt_canonical_with_legacy_untouched(isolated_harness_root) -> None:
    run_id = "compress-corrupt-canonical"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 1)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    canonical.write_bytes(b"not-gzip")
    legacy_bytes = legacy.read_bytes()

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["checkpoints"][0]["status"] == "skipped"
    assert result["checkpoints"][0]["reason_code"] == RESUME_SNAPSHOT_GZIP_INVALID
    assert legacy.read_bytes() == legacy_bytes
    assert canonical.read_bytes() == b"not-gzip"


def test_turn_next_iteration_mismatch_skipped(isolated_harness_root) -> None:
    run_id = "compress-turn-mismatch"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 10, _minimal_valid_snapshot(next_iteration=99))

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["checkpoints"][0]["reason_code"] == REASON_CHECKPOINT_TURN_MISMATCH
    assert legacy.exists()
    assert not turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=10).exists()


def test_symlink_legacy_refused(isolated_harness_root) -> None:
    run_id = "compress-symlink"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    real = run_dir / "real_payload.json"
    real.write_text(json.dumps(_minimal_valid_snapshot(next_iteration=2)), encoding="utf-8")
    link = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=1)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(real, link)
    except OSError:
        pytest.skip("symlinks unavailable on this host")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["checkpoints"][0]["status"] == "skipped"
    assert result["checkpoints"][0]["reason_code"] == REASON_PATH_IS_SYMLINK
    assert link.is_symlink()


def test_canonical_symlink_emits_canonical_path_is_symlink(isolated_harness_root) -> None:
    run_id = "compress-canonical-symlink"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=2)
    legacy = _write_legacy(run_dir, 1, snap)
    target = run_dir / "canonical_target.json.gz"
    write_gzip_json_atomic(target, snapshot=snap)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    try:
        os.symlink(target, canonical)
    except OSError:
        pytest.skip("symlinks unavailable on this host")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["checkpoints"][0]["status"] == "skipped"
    assert result["checkpoints"][0]["reason_code"] == REASON_CANONICAL_SYMLINK
    assert legacy.exists()
    assert canonical.is_symlink()


def test_unrecognized_filenames_ignored(isolated_harness_root) -> None:
    run_id = "compress-ignore-names"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    ckpt = run_dir / TURN_CHECKPOINTS_DIRNAME
    ckpt.mkdir(parents=True, exist_ok=True)
    (ckpt / "turn_12.json").write_text("{}", encoding="utf-8")
    (ckpt / "turn_0001.json.bak").write_text("{}", encoding="utf-8")
    (ckpt / "notes.txt").write_text("x", encoding="utf-8")
    _write_legacy(run_dir, 3)

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=False)
    assert result["legacy_checkpoint_count"] == 1
    assert result["checkpoints"][0]["turn"] == 3


def test_simulated_compressed_write_failure_leaves_legacy(isolated_harness_root) -> None:
    run_id = "compress-write-fail"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 1)

    def _boom(path: Path, snapshot: dict[str, Any]) -> None:
        raise OSError("simulated write failure")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True, write_gzip_fn=_boom)
    assert result["checkpoints"][0]["reason_code"] == REASON_WRITE_FAILED
    assert legacy.exists()
    assert not turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1).exists()


def test_simulated_verification_failure_leaves_canonical_absent(isolated_harness_root) -> None:
    run_id = "compress-verify-fail"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=2)
    legacy = _write_legacy(run_dir, 1, snap)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)

    def _load(path: Path | str):
        p = Path(path)
        if ".json.gz" in p.name:
            bad = dict(snap)
            bad["next_iteration"] = 999
            return bad, None
        return load_kernel_resume_snapshot_from_path(p)

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True, load_fn=_load)
    assert result["checkpoints"][0]["reason_code"] == REASON_VERIFICATION_FAILED
    assert legacy.exists()
    assert not canonical.exists()
    assert not list((run_dir / TURN_CHECKPOINTS_DIRNAME).glob("*.staging.json.gz"))


def test_simulated_staging_cleanup_failure_reports_path(isolated_harness_root) -> None:
    run_id = "compress-staging-cleanup-fail"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=2)
    legacy = _write_legacy(run_dir, 1, snap)
    from harness.cli.resume_checkpoint_compress import REASON_STAGING_CLEANUP_FAILED

    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    fixed_staging = canonical.with_name("turn_0001.fixedtoken.staging.json.gz")

    def _load(path: Path | str):
        p = Path(path)
        if ".json.gz" in p.name:
            bad = dict(snap)
            bad["next_iteration"] = 999
            return bad, None
        return load_kernel_resume_snapshot_from_path(p)

    def _delete(path: Path) -> None:
        if ".staging.json.gz" in path.name:
            raise OSError("simulated staging cleanup failure")
        path.unlink()

    result = compress_run_legacy_checkpoints(
        run_id=run_id,
        apply=True,
        load_fn=_load,
        delete_fn=_delete,
        staging_path_fn=lambda _canonical: fixed_staging,
    )
    row = result["checkpoints"][0]
    assert row["reason_code"] == REASON_STAGING_CLEANUP_FAILED
    assert row["staging_path"] == str(fixed_staging)
    assert legacy.exists()
    assert not canonical.exists()
    assert fixed_staging.exists()


def test_simulated_legacy_deletion_failure_keeps_both(isolated_harness_root) -> None:
    run_id = "compress-delete-fail"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 1)

    def _delete_fail(path: Path) -> None:
        raise OSError("simulated delete failure")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True, delete_fn=_delete_fail)
    assert result["checkpoints"][0]["reason_code"] == REASON_DELETE_FAILED
    assert legacy.exists()
    assert turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1).exists()


def test_interrupted_both_formats_replay_safe(isolated_harness_root) -> None:
    run_id = "compress-interrupted-both"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=4)
    legacy = _write_legacy(run_dir, 3, snap)
    _write_canonical(run_dir, 3, snap)

    # First apply removes equivalent legacy; second apply finds no legacy work.
    first = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert first["equivalent_legacy_removed_count"] == 1
    assert not legacy.exists()

    second = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert second["legacy_checkpoint_count"] == 0
    assert second["migrated_count"] == 0
    assert second["equivalent_legacy_removed_count"] == 0
    assert second["status"] == "applied"


def test_idempotent_replay_after_migration(isolated_harness_root) -> None:
    run_id = "compress-idempotent"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    _write_legacy(run_dir, 6)
    first = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert first["migrated_count"] == 1
    second = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert second["legacy_checkpoint_count"] == 0
    assert second["checkpoints"] == []
    assert turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=6).is_file()


def test_run_layout_collection_discovery(isolated_harness_root) -> None:
    run_id = "compress-collection-row"
    collection = "transcript_edit_right_of_way"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id, collection=collection)
    assert BY_LOOP_KIND_DIRNAME in run_dir.parts
    assert collection in run_dir.parts
    _write_legacy(run_dir, 2)

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=False)
    assert result["status"] == "planned"
    assert result["run_collection"] == collection
    assert Path(result["run_dir"]) == run_dir
    assert result["legacy_checkpoint_count"] == 1


def test_conflicting_canonical_remains_untouched_on_replay(isolated_harness_root) -> None:
    run_id = "compress-conflict-replay"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    a = _minimal_valid_snapshot(next_iteration=2)
    b = _minimal_valid_snapshot(next_iteration=2)
    b["continuity"] = dict(b["continuity"])
    b["continuity"]["latest_refs"] = {"x": "y"}
    legacy = _write_legacy(run_dir, 1, a)
    canonical = _write_canonical(run_dir, 1, b)
    before_l = legacy.read_bytes()
    before_c = canonical.read_bytes()

    for _ in range(2):
        result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
        assert result["checkpoints"][0]["reason_code"] == REASON_CANONICAL_CONFLICT
        assert legacy.read_bytes() == before_l
        assert canonical.read_bytes() == before_c


def test_mixed_run_byte_totals_include_all_recognized_rows(isolated_harness_root) -> None:
    run_id = "compress-mixed-totals"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)

    ok_snap = _minimal_valid_snapshot(next_iteration=2)
    ok_legacy = _write_legacy(run_dir, 1, ok_snap)

    corrupt = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=2)
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_text("not-json", encoding="utf-8")

    conflict_legacy_snap = _minimal_valid_snapshot(next_iteration=4)
    conflict_canon_snap = _minimal_valid_snapshot(next_iteration=4)
    conflict_canon_snap["continuity"] = dict(conflict_canon_snap["continuity"])
    conflict_canon_snap["continuity"]["latest_refs"] = {"other": "body"}
    conflict_legacy = _write_legacy(run_dir, 3, conflict_legacy_snap)
    conflict_canon = _write_canonical(run_dir, 3, conflict_canon_snap)

    delete_fail_legacy = _write_legacy(run_dir, 4)

    def _delete(path: Path) -> None:
        if path.name == "turn_0004.json":
            raise OSError("simulated delete failure")
        path.unlink()

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True, delete_fn=_delete)
    assert result["status"] == "partial"
    assert result["legacy_checkpoint_count"] == 4
    assert result["migrated_count"] == 1
    assert result["skipped_count"] == 3

    by_turn = {row["turn"]: row for row in result["checkpoints"]}
    assert by_turn[1]["status"] == "migrated"
    assert by_turn[2]["status"] == "skipped"
    assert by_turn[2]["reason_code"] == RESUME_SNAPSHOT_JSON_INVALID
    assert by_turn[3]["reason_code"] == REASON_CANONICAL_CONFLICT
    assert by_turn[4]["reason_code"] == REASON_DELETE_FAILED

    expected_legacy = (
        by_turn[1]["legacy_bytes"]
        + by_turn[2]["legacy_bytes"]
        + by_turn[3]["legacy_bytes"]
        + by_turn[4]["legacy_bytes"]
    )
    expected_canonical = (
        by_turn[1]["canonical_bytes"]
        + by_turn[2]["canonical_bytes"]
        + by_turn[3]["canonical_bytes"]
        + by_turn[4]["canonical_bytes"]
    )
    assert result["legacy_bytes"] == expected_legacy
    assert result["canonical_bytes"] == expected_canonical
    assert by_turn[2]["legacy_bytes"] == corrupt.stat().st_size
    assert by_turn[3]["legacy_bytes"] == conflict_legacy.stat().st_size
    assert by_turn[3]["canonical_bytes"] == conflict_canon.stat().st_size
    assert by_turn[4]["legacy_bytes"] == delete_fail_legacy.stat().st_size
    assert by_turn[4]["canonical_bytes"] == turn_checkpoint_canonical_path(
        run_dir=run_dir, from_turn=4
    ).stat().st_size

    migrated_canon = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    assert not ok_legacy.exists()
    assert migrated_canon.is_file()
    assert result["bytes_reclaimed"] == by_turn[1]["legacy_bytes"] - by_turn[1]["canonical_bytes"]
    assert result["legacy_bytes_removed"] == by_turn[1]["legacy_bytes"]
    assert by_turn[4]["legacy_bytes"] > 0  # delete failure contributes 0 reclaimed
    assert result["bytes_reclaimed"] == by_turn[1]["legacy_bytes"] - by_turn[1]["canonical_bytes"]


def test_nan_legacy_skipped_without_aborting_other_rows(isolated_harness_root) -> None:
    from harness.cli.resume_checkpoint_compress import REASON_CANONICAL_JSON_NOT_SERIALIZABLE

    run_id = "compress-nan-continue"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)

    nan_snap = _minimal_valid_snapshot(next_iteration=2)
    nan_snap["legacy_probe"] = float("nan")
    nan_path = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=1)
    nan_path.parent.mkdir(parents=True, exist_ok=True)
    nan_path.write_text(json.dumps(nan_snap, allow_nan=True), encoding="utf-8")

    ok_legacy = _write_legacy(run_dir, 2)

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["status"] == "partial"
    by_turn = {row["turn"]: row for row in result["checkpoints"]}
    assert by_turn[1]["status"] == "skipped"
    assert by_turn[1]["reason_code"] == REASON_CANONICAL_JSON_NOT_SERIALIZABLE
    assert nan_path.exists()
    assert not turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1).exists()
    assert by_turn[2]["status"] == "migrated"
    assert not ok_legacy.exists()
    assert turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=2).is_file()


def test_apply_refuses_active_run_without_mutation(isolated_harness_root, monkeypatch) -> None:
    from harness.cli.resume_checkpoint_compress import REASON_RUN_NOT_QUIESCENT

    run_id = "compress-active-run"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id, pid=4242)
    legacy = _write_legacy(run_dir, 1)
    before = legacy.read_bytes()
    monkeypatch.setattr(
        "harness.cli.run_quiescence.is_pid_alive",
        lambda pid: pid == 4242,
    )

    writes: list[Path] = []

    def _write(path: Path, snapshot: dict[str, Any]) -> None:
        writes.append(path)
        write_gzip_json_atomic(path, snapshot=snapshot)

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True, write_gzip_fn=_write)
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_NOT_QUIESCENT
    assert result["migrated_count"] == 0
    assert writes == []
    assert legacy.read_bytes() == before
    assert not turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1).exists()
    assert not list((run_dir / TURN_CHECKPOINTS_DIRNAME).glob("*.staging.json.gz"))

    planned = compress_run_legacy_checkpoints(run_id=run_id, apply=False)
    assert planned["status"] == "planned"
    assert planned["checkpoints"][0]["status"] == "would_migrate"


def test_apply_refuses_activity_unknown_without_mutation(isolated_harness_root) -> None:
    from harness.cli.resume_checkpoint_compress import REASON_RUN_ACTIVITY_UNKNOWN

    run_id = "compress-activity-unknown"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 1)
    before = legacy.read_bytes()
    (run_dir / "state.json").write_text("{not-json", encoding="utf-8")

    writes: list[Path] = []

    def _write(path: Path, snapshot: dict[str, Any]) -> None:
        writes.append(path)
        raise AssertionError("write must not run")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True, write_gzip_fn=_write)
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_ACTIVITY_UNKNOWN
    assert writes == []
    assert legacy.read_bytes() == before
    assert not turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1).exists()


def test_canonical_race_after_discovery_does_not_overwrite(isolated_harness_root) -> None:
    run_id = "compress-canonical-race"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy_snap = _minimal_valid_snapshot(next_iteration=2)
    rival = _minimal_valid_snapshot(next_iteration=2)
    rival["continuity"] = dict(rival["continuity"])
    rival["continuity"]["latest_refs"] = {"rival": "bytes"}
    legacy = _write_legacy(run_dir, 1, legacy_snap)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)

    def _load(path: Path | str):
        p = Path(path)
        if ".staging.json.gz" in p.name:
            # Simulate another writer creating canonical after our initial absence check.
            write_gzip_json_atomic(canonical, snapshot=rival)
            return load_kernel_resume_snapshot_from_path(p)
        return load_kernel_resume_snapshot_from_path(p)

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True, load_fn=_load)
    assert result["checkpoints"][0]["reason_code"] == REASON_CANONICAL_CONFLICT
    assert legacy.exists()
    assert canonical.read_bytes() == _gzip_bytes_for(rival)
    assert not list((run_dir / TURN_CHECKPOINTS_DIRNAME).glob("*.staging.json.gz"))


def test_foreign_staging_identity_is_not_deleted(isolated_harness_root) -> None:
    run_id = "compress-foreign-staging"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    _write_legacy(run_dir, 1)
    ckpt = run_dir / TURN_CHECKPOINTS_DIRNAME
    foreign = ckpt / "turn_0001.foreigntoken.staging.json.gz"
    foreign.write_bytes(b"foreign-staging-bytes")

    result = compress_run_legacy_checkpoints(run_id=run_id, apply=True)
    assert result["migrated_count"] == 1
    assert foreign.read_bytes() == b"foreign-staging-bytes"


def test_broken_staging_symlink_cleanup_failure(isolated_harness_root) -> None:
    run_id = "compress-broken-staging-symlink"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=2)
    legacy = _write_legacy(run_dir, 1, snap)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    fixed_staging = canonical.with_name("turn_0001.brokensym.staging.json.gz")

    def _load(path: Path | str):
        p = Path(path)
        if ".json.gz" in p.name:
            bad = dict(snap)
            bad["next_iteration"] = 999
            return bad, None
        return load_kernel_resume_snapshot_from_path(p)

    def _delete(path: Path) -> None:
        if path == fixed_staging:
            if path.exists() and not path.is_symlink():
                path.unlink()
            if not path.is_symlink():
                try:
                    os.symlink("missing-staging-target", path)
                except OSError:
                    pytest.skip("symlinks unavailable on this host")
            raise OSError("simulated broken-symlink cleanup failure")
        path.unlink()

    result = compress_run_legacy_checkpoints(
        run_id=run_id,
        apply=True,
        load_fn=_load,
        delete_fn=_delete,
        staging_path_fn=lambda _c: fixed_staging,
    )
    row = result["checkpoints"][0]
    assert row["reason_code"] == REASON_STAGING_CLEANUP_FAILED
    assert row["staging_path"] == str(fixed_staging)
    assert legacy.exists()
    assert not canonical.exists()
    assert os.path.lexists(fixed_staging)


def test_partial_write_cleanup_failure_reports_staging_path(isolated_harness_root) -> None:
    run_id = "compress-partial-write-cleanup-fail"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 1)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    fixed_staging = canonical.with_name("turn_0001.partial.staging.json.gz")

    def _write(path: Path, snapshot: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"partial-gzip")
        raise OSError("simulated write failure after partial staging")

    def _delete(path: Path) -> None:
        if path == fixed_staging:
            raise OSError("simulated staging cleanup failure")
        path.unlink()

    result = compress_run_legacy_checkpoints(
        run_id=run_id,
        apply=True,
        write_gzip_fn=_write,
        delete_fn=_delete,
        staging_path_fn=lambda _c: fixed_staging,
    )
    row = result["checkpoints"][0]
    assert row["reason_code"] == REASON_STAGING_CLEANUP_FAILED
    assert row["staging_path"] == str(fixed_staging)
    assert legacy.exists()
    assert not canonical.exists()
    assert fixed_staging.exists()


def test_quiescence_recheck_before_promotion_aborts(isolated_harness_root) -> None:
    run_id = "compress-quiescence-pre-promote"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 1)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        # Initial apply gate passes; recheck before promotion fails.
        if calls["n"] >= 2:
            return REASON_RUN_NOT_QUIESCENT
        return None

    result = compress_run_legacy_checkpoints(
        run_id=run_id,
        apply=True,
        quiescence_fn=_quiescence,
    )
    assert result["checkpoints"][0]["reason_code"] == REASON_RUN_NOT_QUIESCENT
    assert legacy.exists()
    assert not canonical.exists()
    assert not list((run_dir / TURN_CHECKPOINTS_DIRNAME).glob("*.staging.json.gz"))


def test_quiescence_recheck_before_delete_retains_both(isolated_harness_root) -> None:
    run_id = "compress-quiescence-pre-delete"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    legacy = _write_legacy(run_dir, 1)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        # Apply gate + pre-promotion pass; post-promotion pre-delete fails.
        if calls["n"] >= 3:
            return REASON_RUN_NOT_QUIESCENT
        return None

    result = compress_run_legacy_checkpoints(
        run_id=run_id,
        apply=True,
        quiescence_fn=_quiescence,
    )
    assert result["checkpoints"][0]["reason_code"] == REASON_RUN_NOT_QUIESCENT
    assert legacy.exists()
    assert canonical.is_file()
    assert not list((run_dir / TURN_CHECKPOINTS_DIRNAME).glob("*.staging.json.gz"))


def test_quiescence_seam_extracted_to_shared_module() -> None:
    from harness.cli.run_quiescence import assess_run_quiescence as shared

    from harness.cli import resume_checkpoint_compress as mod

    assert shared is mod.assess_run_quiescence
    import harness.cli.resume_checkpoint_compress as source_mod

    assert "def assess_run_quiescence" not in inspect.getsource(source_mod)


def test_lexists_cleanup_failure_without_symlinks(isolated_harness_root, monkeypatch) -> None:
    """Broken-symlink cleanup semantics via mocked lexists (no host symlink required)."""
    run_id = "compress-lexists-mock-cleanup"
    run_dir = _seed_run(isolated_harness_root, run_id=run_id)
    snap = _minimal_valid_snapshot(next_iteration=2)
    legacy = _write_legacy(run_dir, 1, snap)
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=1)
    fixed_staging = canonical.with_name("turn_0001.mocklex.staging.json.gz")
    remaining = {str(fixed_staging): True}

    real_lexists = os.path.lexists

    def _lexists(path: str | os.PathLike[str]) -> bool:
        key = str(path)
        if key in remaining:
            return True
        return real_lexists(path)

    def _load(path: Path | str):
        p = Path(path)
        if ".json.gz" in p.name:
            bad = dict(snap)
            bad["next_iteration"] = 999
            return bad, None
        return load_kernel_resume_snapshot_from_path(p)

    def _delete(path: Path) -> None:
        if path == fixed_staging:
            raise OSError("simulated cleanup failure")
        path.unlink()

    monkeypatch.setattr("harness.cli.resume_checkpoint_migrate.os.path.lexists", _lexists)

    result = compress_run_legacy_checkpoints(
        run_id=run_id,
        apply=True,
        load_fn=_load,
        delete_fn=_delete,
        staging_path_fn=lambda _c: fixed_staging,
    )
    row = result["checkpoints"][0]
    assert row["reason_code"] == REASON_STAGING_CLEANUP_FAILED
    assert row["staging_path"] == str(fixed_staging)
    assert legacy.exists()
    assert not canonical.exists()
    assert remaining[str(fixed_staging)] is True
