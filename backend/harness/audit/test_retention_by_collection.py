"""Per-collection retention queue tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from harness.audit.retention import cleanup_old_cli_runs, purge_all_cli_runs
from harness.cli.run_layout import BY_LOOP_KIND_DIRNAME, list_run_dirs_in_bucket, iter_retention_buckets


def _make_run_dir(root: Path, run_id: str, *, pinned: bool = False, age: float = 0.0) -> Path:
    d = root / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    (d / "retention.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "pinned": pinned,
                "created_at_epoch_seconds": time.time() - age,
                "cleanup_policy_version": "v2",
            }
        ),
        encoding="utf-8",
    )
    return d


def _make_namespaced_run(
    root: Path,
    *,
    collection: str,
    run_id: str,
    pinned: bool = False,
    age: float = 0.0,
) -> Path:
    d = root / BY_LOOP_KIND_DIRNAME / collection / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    (d / "retention.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "pinned": pinned,
                "created_at_epoch_seconds": time.time() - age,
                "cleanup_policy_version": "v2",
            }
        ),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def cli_root(tmp_path, monkeypatch):
    root = tmp_path / "cli_runs"
    root.mkdir()
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: root)
    return root


def test_five_plus_five_runs_coexist(cli_root: Path) -> None:
    for i, run_id in enumerate(["te1", "te2", "te3", "te4", "te5"]):
        _make_namespaced_run(cli_root, collection="transcript_edit", run_id=run_id, age=(50 - i))
    for i, run_id in enumerate(["deed1", "deed2", "deed3", "deed4", "deed5"]):
        _make_namespaced_run(cli_root, collection="deed_to_ir", run_id=run_id, age=(50 - i))

    deleted = cleanup_old_cli_runs(keep_n=5)
    assert deleted == []

    te_bucket = cli_root / BY_LOOP_KIND_DIRNAME / "transcript_edit"
    deed_bucket = cli_root / BY_LOOP_KIND_DIRNAME / "deed_to_ir"
    assert len(list_run_dirs_in_bucket(te_bucket, legacy_flat=False)) == 5
    assert len(list_run_dirs_in_bucket(deed_bucket, legacy_flat=False)) == 5


def test_sixth_deed_run_removes_only_oldest_deed(cli_root: Path) -> None:
    for i, run_id in enumerate(["te1", "te2", "te3", "te4", "te5"]):
        _make_namespaced_run(cli_root, collection="transcript_edit", run_id=run_id, age=(70 - i * 10))
    deed_ids = ["deed1", "deed2", "deed3", "deed4", "deed5", "deed6"]
    for i, run_id in enumerate(deed_ids):
        _make_namespaced_run(cli_root, collection="deed_to_ir", run_id=run_id, age=(70 - i * 10))

    deleted = cleanup_old_cli_runs(keep_n=5)
    assert deleted == ["deed1"]

    te_bucket = cli_root / BY_LOOP_KIND_DIRNAME / "transcript_edit"
    deed_bucket = cli_root / BY_LOOP_KIND_DIRNAME / "deed_to_ir"
    assert {d.name for d in list_run_dirs_in_bucket(te_bucket, legacy_flat=False)} == {
        "te1",
        "te2",
        "te3",
        "te4",
        "te5",
    }
    assert {d.name for d in list_run_dirs_in_bucket(deed_bucket, legacy_flat=False)} == {
        "deed2",
        "deed3",
        "deed4",
        "deed5",
        "deed6",
    }


def test_pinned_runs_survive_in_each_bucket(cli_root: Path) -> None:
    _make_namespaced_run(cli_root, collection="deed_to_ir", run_id="deed-pinned", pinned=True, age=1000)
    for i, run_id in enumerate(["deed2", "deed3", "deed4", "deed5", "deed6", "deed7"]):
        _make_namespaced_run(cli_root, collection="deed_to_ir", run_id=run_id, age=(70 - i * 10))

    deleted = cleanup_old_cli_runs(keep_n=5)
    assert "deed-pinned" not in deleted
    assert (cli_root / BY_LOOP_KIND_DIRNAME / "deed_to_ir" / "deed-pinned").exists()


def test_collection_directories_never_deleted_as_runs(cli_root: Path) -> None:
    _make_namespaced_run(cli_root, collection="transcript_edit", run_id="te-only")
    purge_all_cli_runs()
    assert (cli_root / BY_LOOP_KIND_DIRNAME).exists()
    assert (cli_root / BY_LOOP_KIND_DIRNAME / "transcript_edit").exists()
    buckets = iter_retention_buckets(cli_root)
    for _bucket_id, bucket_root, legacy_flat in buckets:
        assert list_run_dirs_in_bucket(bucket_root, legacy_flat=legacy_flat) == []


def test_legacy_flat_bucket_retains_latest_five_independently(cli_root: Path) -> None:
    for i, run_id in enumerate(["legacy1", "legacy2", "legacy3", "legacy4", "legacy5", "legacy6"]):
        _make_run_dir(cli_root, run_id, age=(70 - i * 10))

    deleted = cleanup_old_cli_runs(keep_n=5)
    assert deleted == ["legacy1"]
    remaining = {d.name for d in list_run_dirs_in_bucket(cli_root, legacy_flat=True)}
    assert remaining == {"legacy2", "legacy3", "legacy4", "legacy5", "legacy6"}
