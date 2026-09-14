"""Retention must delete referenced workspace IDs only after the last safe ref."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from harness.audit.retention import cleanup_old_cli_runs, purge_all_cli_runs


def _write_state(
    run_dir: Path,
    run_id: str,
    *,
    workspace_id: str | None = None,
    lineage_workspace: str | None = None,
    spawn_argv: list | None = None,
) -> None:
    launch = {"run_id": run_id}
    if workspace_id is not None:
        launch["workspace_id"] = workspace_id
    argv = spawn_argv or [
        "python",
        "-m",
        "x",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    extra = {}
    if lineage_workspace is not None:
        extra["fork_lineage"] = {
            "workspace_mode": "continue",
            "source_workspace_id": lineage_workspace,
        }
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "pid": 0,
                "status": "failed",
                "spawn_argv": argv,
                "extra": extra,
            }
        ),
        encoding="utf-8",
    )


def _make_run(
    root: Path,
    run_id: str,
    *,
    pinned: bool = False,
    age: float = 0.0,
    workspace_id: str | None = None,
    lineage_workspace: str | None = None,
    spawn_argv: list | None = None,
) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_state(
        run_dir,
        run_id,
        workspace_id=workspace_id,
        lineage_workspace=lineage_workspace,
        spawn_argv=spawn_argv,
    )
    (run_dir / "retention.json").write_text(
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
    return run_dir


def _te_workspace(te_root: Path, workspace_id: str) -> Path:
    path = te_root / "dossier1" / "tx1" / workspace_id
    path.mkdir(parents=True, exist_ok=True)
    (path / "draft.json").write_text("{}", encoding="utf-8")
    return path


@pytest.fixture
def roots(tmp_path, monkeypatch):
    cli_root = tmp_path / "cli_runs"
    cli_root.mkdir()
    te_root = tmp_path / "transcript_edit"
    te_root.mkdir()
    dossier_root = tmp_path / "transcript_edit_dossier"
    dossier_root.mkdir()
    import harness.cli.run_layout as layout_mod
    import config.paths as paths_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: cli_root)
    monkeypatch.setattr(paths_mod, "dossiers_transcript_edit_artifacts_root", lambda dossier_id=None: te_root)
    monkeypatch.setattr(
        paths_mod,
        "dossiers_transcript_edit_dossier_artifacts_root",
        lambda dossier_id=None: dossier_root,
    )
    return cli_root, te_root, dossier_root


def test_ordinary_retention_deletes_default_workspace_after_last_ref(roots) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "old-run", age=50)
    _make_run(cli_root, "new-run", age=1)
    old_ws = _te_workspace(te_root, "old-run")
    new_ws = _te_workspace(te_root, "new-run")

    deleted = cleanup_old_cli_runs(keep_n=1)
    assert deleted == ["old-run"]
    assert not old_ws.exists()
    assert new_ws.exists()


def test_pinned_run_keeps_shared_workspace(roots) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "source-run", age=50, workspace_id="shared-ws")
    _make_run(
        cli_root,
        "pinned-child",
        pinned=True,
        age=40,
        workspace_id="shared-ws",
        lineage_workspace="shared-ws",
    )
    ws = _te_workspace(te_root, "shared-ws")

    deleted = cleanup_old_cli_runs(keep_n=0)
    assert deleted == ["source-run"]
    assert (cli_root / "pinned-child").exists()
    assert ws.exists()


def test_source_retirement_keeps_workspace_for_surviving_child(roots) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "source-run", age=50, workspace_id="source-run")
    _make_run(
        cli_root,
        "child-run",
        age=1,
        workspace_id="source-run",
        lineage_workspace="source-run",
    )
    ws = _te_workspace(te_root, "source-run")
    child_named = _te_workspace(te_root, "child-run")

    deleted = cleanup_old_cli_runs(keep_n=1)
    assert deleted == ["source-run"]
    assert ws.exists()
    assert child_named.exists()


def test_active_or_unknown_child_preserves_workspace(roots, monkeypatch) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "source-run", age=50, workspace_id="shared-ws")
    _make_run(
        cli_root,
        "live-child",
        age=40,
        workspace_id="shared-ws",
        lineage_workspace="shared-ws",
    )
    ws = _te_workspace(te_root, "shared-ws")

    monkeypatch.setattr(
        "harness.audit.retention_workspace_cleanup.assess_run_quiescence",
        lambda run_id: "run_not_quiescent" if run_id == "live-child" else None,
    )
    deleted = cleanup_old_cli_runs(keep_n=0)
    assert "source-run" in deleted
    assert ws.exists()

    _make_run(cli_root, "source-run-2", age=50, workspace_id="unknown-ws")
    _make_run(
        cli_root,
        "mystery-child",
        age=40,
        workspace_id="unknown-ws",
        lineage_workspace="unknown-ws",
    )
    ws2 = _te_workspace(te_root, "unknown-ws")
    monkeypatch.setattr(
        "harness.audit.retention_workspace_cleanup.assess_run_quiescence",
        lambda run_id: "run_activity_unknown" if run_id == "mystery-child" else None,
    )
    cleanup_old_cli_runs(keep_n=0)
    assert ws2.exists()


def test_final_reference_retirement_deletes_actual_workspace_id(roots) -> None:
    cli_root, te_root, dossier_root = roots
    _make_run(
        cli_root,
        "last-child",
        workspace_id="original-ws",
        lineage_workspace="original-ws",
    )
    leaf = _te_workspace(te_root, "original-ws")
    dossier_ws = dossier_root / "dossier1" / "original-ws"
    dossier_ws.mkdir(parents=True)
    (dossier_ws / "out.json").write_text("{}", encoding="utf-8")
    child_named = _te_workspace(te_root, "last-child")

    deleted = cleanup_old_cli_runs(keep_n=0)
    assert deleted == ["last-child"]
    assert not leaf.exists()
    assert not dossier_ws.exists()
    assert child_named.exists()


def test_continuation_of_continuation_keeps_original_workspace(roots) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "source-run", age=90, workspace_id="original-ws")
    _make_run(
        cli_root,
        "mid-child",
        age=50,
        workspace_id="original-ws",
        lineage_workspace="original-ws",
    )
    _make_run(
        cli_root,
        "grand-child",
        age=1,
        workspace_id="original-ws",
        lineage_workspace="original-ws",
    )
    ws = _te_workspace(te_root, "original-ws")

    deleted = cleanup_old_cli_runs(keep_n=1)
    assert set(deleted) == {"source-run", "mid-child"}
    assert (cli_root / "grand-child").exists()
    assert ws.exists()


def test_purge_all_failed_run_delete_keeps_run_and_workspace(roots, monkeypatch) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "ok-run", workspace_id="ok-ws")
    _make_run(cli_root, "stuck-run", workspace_id="stuck-ws")
    ok_ws = _te_workspace(te_root, "ok-ws")
    stuck_ws = _te_workspace(te_root, "stuck-ws")
    stuck_bytes = (stuck_ws / "draft.json").read_bytes()

    def _delete(path: Path) -> bool:
        if path.name == "stuck-run":
            return False
        import shutil

        shutil.rmtree(path)
        return True

    monkeypatch.setattr("harness.audit.retention._delete_run_dir", _delete)
    purged = purge_all_cli_runs()
    assert set(purged) == {"ok-run"}
    assert (cli_root / "stuck-run").exists()
    assert not (cli_root / "ok-run").exists()
    assert not ok_ws.exists()
    assert stuck_ws.exists()
    assert (stuck_ws / "draft.json").read_bytes() == stuck_bytes


def test_falsey_spawn_argv_skips_all_workspace_cleanup(roots) -> None:
    cli_root, te_root, _dossier_root = roots
    for index, value in enumerate((None, "", 0, {})):
        run_id = f"falsey-run-{index}"
        run_dir = _make_run(cli_root, run_id, age=50)
        (run_dir / "state.json").write_text(
            json.dumps({"run_id": run_id, "pid": 0, "spawn_argv": value}),
            encoding="utf-8",
        )
        ws = _te_workspace(te_root, run_id)
        marker = ws / "draft.json"
        before = marker.read_bytes()
        deleted = cleanup_old_cli_runs(keep_n=0)
        assert run_id in deleted
        assert ws.exists()
        assert marker.read_bytes() == before


def test_unrecognized_or_exception_activity_skips_workspace_delete(roots, monkeypatch) -> None:
    cli_root, te_root, _dossier_root = roots
    for index, quiet in enumerate(("", 0, True, "mystery", [], {})):
        run_id = f"coerced-{index}"
        _make_run(cli_root, run_id, age=50)
        ws = _te_workspace(te_root, run_id)
        before = (ws / "draft.json").read_bytes()
        monkeypatch.setattr(
            "harness.audit.retention_workspace_cleanup.assess_run_quiescence",
            lambda _rid, value=quiet: value,
        )
        deleted = cleanup_old_cli_runs(keep_n=0)
        assert deleted == [run_id]
        assert ws.exists()
        assert (ws / "draft.json").read_bytes() == before

    _make_run(cli_root, "boom-run", age=50)
    boom_ws = _te_workspace(te_root, "boom-run")
    boom_bytes = (boom_ws / "draft.json").read_bytes()

    def _boom(_rid: str):
        raise RuntimeError("activity")

    monkeypatch.setattr(
        "harness.audit.retention_workspace_cleanup.assess_run_quiescence",
        _boom,
    )
    deleted = cleanup_old_cli_runs(keep_n=0)
    assert deleted == ["boom-run"]
    assert boom_ws.exists()
    assert (boom_ws / "draft.json").read_bytes() == boom_bytes


def test_incomplete_activity_index_skips_workspace_delete(roots, monkeypatch) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "partial-run", age=50)
    ws = _te_workspace(te_root, "partial-run")
    before = (ws / "draft.json").read_bytes()

    def _partial(run_ids, *, required_run_ids=None):
        del run_ids, required_run_ids
        return {}

    monkeypatch.setattr("harness.audit.retention.assess_run_activity", _partial)
    deleted = cleanup_old_cli_runs(keep_n=0)
    assert deleted == ["partial-run"]
    assert ws.exists()
    assert (ws / "draft.json").read_bytes() == before


def test_ordinary_retention_skips_workspace_when_refs_uncertain(roots) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(
        cli_root,
        "bad-ref",
        age=50,
        spawn_argv=[
            "python",
            "-m",
            "x",
            "--launch-context-json",
            "{}",
            "--launch-context-json",
            "{}",
        ],
    )
    _make_run(cli_root, "kept-run", age=1)
    ws = _te_workspace(te_root, "bad-ref")

    deleted = cleanup_old_cli_runs(keep_n=1)
    assert deleted == ["bad-ref"]
    assert ws.exists()


def test_purge_all_skips_workspace_when_active_or_uncertain(roots, monkeypatch) -> None:
    cli_root, te_root, _dossier_root = roots
    _make_run(cli_root, "live-run", workspace_id="live-ws")
    ws = _te_workspace(te_root, "live-ws")
    monkeypatch.setattr(
        "harness.audit.retention_workspace_cleanup.assess_run_quiescence",
        lambda _rid: "run_not_quiescent",
    )
    purged = purge_all_cli_runs()
    assert purged == ["live-run"]
    assert not (cli_root / "live-run").exists()
    assert ws.exists()

    _make_run(
        cli_root,
        "bad-ref",
        spawn_argv=[
            "python",
            "-m",
            "x",
            "--launch-context-json",
            "{}",
            "--launch-context-json",
            "{}",
        ],
    )
    bad_ws = _te_workspace(te_root, "bad-ref")
    monkeypatch.setattr(
        "harness.audit.retention_workspace_cleanup.assess_run_quiescence",
        lambda _rid: None,
    )
    purged = purge_all_cli_runs()
    assert "bad-ref" in purged
    assert bad_ws.exists()
