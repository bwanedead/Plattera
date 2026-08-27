"""Tests for resume snapshot plain/gzip storage transport."""

from __future__ import annotations

import json

from harness.cli.resume_paths import (
    resolve_existing_turn_checkpoint,
    turn_checkpoint_canonical_path,
    turn_checkpoint_legacy_path,
)
from harness.runtime.memory.resume_snapshot_storage import (
    RESUME_SNAPSHOT_GZIP_INVALID,
    RESUME_SNAPSHOT_JSON_INVALID,
    RESUME_SNAPSHOT_PATH_UNREADABLE,
    RESUME_SNAPSHOT_ROOT_NOT_OBJECT,
    dumps_compact_checkpoint_bytes,
    gzip_compress_deterministic,
    load_kernel_resume_snapshot_from_path,
    write_gzip_json_atomic,
    write_plain_json_atomic,
)


def test_load_plain_roundtrip(tmp_path) -> None:
    path = tmp_path / "kernel_resume.json"
    doc = {"schema_version": "kernel_resume.v1", "next_iteration": 2}
    write_plain_json_atomic(path, text=json.dumps(doc, indent=2, sort_keys=True))
    loaded, err = load_kernel_resume_snapshot_from_path(path)
    assert err is None
    assert loaded == doc


def test_load_gzip_never_treats_corrupt_bytes_as_plain_json(tmp_path) -> None:
    path = tmp_path / "turn_0001.json.gz"
    # Valid JSON bytes, but not gzip — must refuse as gzip invalid, not parse as JSON.
    path.write_bytes(b'{"schema_version":"kernel_resume.v1","next_iteration":2}')
    loaded, err = load_kernel_resume_snapshot_from_path(path)
    assert loaded is None
    assert err == RESUME_SNAPSHOT_GZIP_INVALID


def test_load_gzip_invalid_json_inside_archive(tmp_path) -> None:
    path = tmp_path / "turn_0001.json.gz"
    path.write_bytes(gzip_compress_deterministic(b"not-json"))
    loaded, err = load_kernel_resume_snapshot_from_path(path)
    assert loaded is None
    assert err == RESUME_SNAPSHOT_JSON_INVALID


def test_load_gzip_root_not_object(tmp_path) -> None:
    path = tmp_path / "turn_0001.json.gz"
    path.write_bytes(gzip_compress_deterministic(b"[1,2,3]"))
    loaded, err = load_kernel_resume_snapshot_from_path(path)
    assert loaded is None
    assert err == RESUME_SNAPSHOT_ROOT_NOT_OBJECT


def test_load_missing_path(tmp_path) -> None:
    loaded, err = load_kernel_resume_snapshot_from_path(tmp_path / "missing.json")
    assert loaded is None
    assert err == RESUME_SNAPSHOT_PATH_UNREADABLE


def test_resolve_existing_turn_checkpoint_canonical_first(tmp_path) -> None:
    run_dir = tmp_path / "run"
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=3)
    legacy = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=3)
    write_gzip_json_atomic(canonical, snapshot={"next_iteration": 4})
    write_plain_json_atomic(legacy, text='{"next_iteration": 99}')
    selected = resolve_existing_turn_checkpoint(run_dir=run_dir, from_turn=3)
    assert selected == canonical


def test_resolve_existing_falls_back_to_legacy_when_canonical_absent(tmp_path) -> None:
    run_dir = tmp_path / "run"
    legacy = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=3)
    write_plain_json_atomic(legacy, text='{"next_iteration": 4}')
    selected = resolve_existing_turn_checkpoint(run_dir=run_dir, from_turn=3)
    assert selected == legacy


def test_resolve_existing_returns_none_when_both_missing(tmp_path) -> None:
    assert resolve_existing_turn_checkpoint(run_dir=tmp_path / "run", from_turn=3) is None


def test_compact_encoding_is_sorted_and_separators(tmp_path) -> None:
    raw = dumps_compact_checkpoint_bytes({"b": 1, "a": 2})
    assert raw == b'{"a":2,"b":1}'
