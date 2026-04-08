from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from harness.audit.retention import (
    cleanup_old_cli_runs,
    purge_all_cli_runs,
    write_run_retention_json,
    _is_pinned,
    _is_safe_run_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_dir(root: Path, run_id: str, *, pinned: bool = False, age: float = 0.0) -> Path:
    d = root / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    ret = d / "retention.json"
    ret.write_text(
        json.dumps({
            "run_id": run_id,
            "pinned": pinned,
            "created_at_epoch_seconds": time.time() - age,
            "cleanup_policy_version": "v1",
        }),
        encoding="utf-8",
    )
    return d


# ---------------------------------------------------------------------------
# _is_pinned
# ---------------------------------------------------------------------------


def test_is_pinned_returns_true_when_pinned(tmp_path: Path) -> None:
    d = _make_run_dir(tmp_path, "r1", pinned=True)
    assert _is_pinned(d) is True


def test_is_pinned_returns_false_when_not_pinned(tmp_path: Path) -> None:
    d = _make_run_dir(tmp_path, "r1", pinned=False)
    assert _is_pinned(d) is False


def test_is_pinned_returns_false_when_no_retention_json(tmp_path: Path) -> None:
    d = tmp_path / "r1"
    d.mkdir()
    assert _is_pinned(d) is False


# ---------------------------------------------------------------------------
# _is_safe_run_dir
# ---------------------------------------------------------------------------


def test_is_safe_run_dir_direct_child_is_safe(tmp_path: Path) -> None:
    d = tmp_path / "r1"
    d.mkdir()
    assert _is_safe_run_dir(d, tmp_path) is True


def test_is_safe_run_dir_nested_is_not_safe(tmp_path: Path) -> None:
    d = tmp_path / "a" / "b"
    d.mkdir(parents=True)
    assert _is_safe_run_dir(d, tmp_path) is False


# ---------------------------------------------------------------------------
# purge_all_cli_runs
# ---------------------------------------------------------------------------


def test_purge_all_cli_runs_removes_all_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "cli_runs"
    root.mkdir()
    for run_id in ["r1", "r2", "r3"]:
        _make_run_dir(root, run_id)

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    purged = purge_all_cli_runs()

    assert set(purged) == {"r1", "r2", "r3"}
    assert list(root.iterdir()) == []


def test_purge_all_cli_runs_removes_pinned_too(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "cli_runs"
    root.mkdir()
    _make_run_dir(root, "pinned-run", pinned=True)
    _make_run_dir(root, "normal-run", pinned=False)

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    purged = purge_all_cli_runs()

    assert set(purged) == {"pinned-run", "normal-run"}
    assert list(root.iterdir()) == []


def test_purge_all_cli_runs_cleans_linked_transcript_edit_workspaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "cli_runs"
    root.mkdir()
    _make_run_dir(root, "run-abc")

    # Simulate transcript_edit layout: transcript_edit/<dossier>/<tx>/run-abc/
    te_root = tmp_path / "transcript_edit"
    workspace = te_root / "dossier1" / "tx1" / "run-abc"
    workspace.mkdir(parents=True)
    (workspace / "draft.json").write_text("{}", encoding="utf-8")

    # Unrelated workspace that must NOT be deleted
    unrelated = te_root / "dossier1" / "tx1" / "other-run"
    unrelated.mkdir(parents=True)

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    import config.paths as paths_mod
    monkeypatch.setattr(paths_mod, "dossiers_transcript_edit_artifacts_root", lambda dossier_id=None: te_root)

    purged = purge_all_cli_runs()

    assert purged == ["run-abc"]
    assert not workspace.exists()
    assert unrelated.exists()


def test_purge_all_cli_runs_noop_when_root_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "does_not_exist"

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    purged = purge_all_cli_runs()
    assert purged == []


def test_purge_all_cli_runs_noop_when_root_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "cli_runs"
    root.mkdir()

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    purged = purge_all_cli_runs()
    assert purged == []


# ---------------------------------------------------------------------------
# cleanup_old_cli_runs – uses monkeypatched cli_runs_root
# ---------------------------------------------------------------------------


def test_cleanup_keeps_latest_4_unpinned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "cli_runs"
    root.mkdir()

    # Manually create 7 run dirs (age: 70s oldest → 10s newest)
    for i, run_id in enumerate(["r1", "r2", "r3", "r4", "r5", "r6", "r7"]):
        _make_run_dir(root, run_id, pinned=False, age=(70 - i * 10))

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    deleted = cleanup_old_cli_runs(keep_n=4)

    assert len(deleted) == 3
    # Oldest 3 (r1, r2, r3) deleted; latest 4 (r4–r7) remain
    remaining = {d.name for d in root.iterdir() if d.is_dir()}
    assert remaining == {"r4", "r5", "r6", "r7"}


def test_cleanup_does_not_delete_pinned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "cli_runs"
    root.mkdir()
    for i, run_id in enumerate(["r1", "r2", "r3", "r4", "r5"]):
        pinned = run_id == "r1"  # r1 is oldest but pinned
        _make_run_dir(root, run_id, pinned=pinned, age=(50 - i * 10))

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    deleted = cleanup_old_cli_runs(keep_n=4)

    # 5 dirs: 4 unpinned (r2-r5) + 1 pinned (r1). keep_n=4 unpinned → delete 0 unpinned
    assert deleted == []
    assert (root / "r1").exists()


def test_cleanup_noop_when_cli_runs_root_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "does_not_exist"

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: root)

    deleted = cleanup_old_cli_runs(keep_n=4)
    assert deleted == []


# ---------------------------------------------------------------------------
# write_run_retention_json
# ---------------------------------------------------------------------------


def test_write_run_retention_json_writes_correct_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "run-abc"
    run_dir.mkdir()

    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: tmp_path)

    write_run_retention_json("run-abc")

    ret = json.loads((run_dir / "retention.json").read_text())
    assert ret["run_id"] == "run-abc"
    assert ret["pinned"] is False
    assert ret["cleanup_policy_version"] == "v1"
    assert isinstance(ret["created_at_epoch_seconds"], float)
