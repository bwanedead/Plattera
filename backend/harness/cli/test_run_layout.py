"""Tests for CLI run layout discovery and allocation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.cli.run_layout import (
    BY_LOOP_KIND_DIRNAME,
    RunLayoutError,
    allocate_run_directory,
    find_run_directory_candidates,
    normalize_run_collection,
    resolve_run_directory,
    resolve_run_human_timeline_path,
)
from harness.cli import run_state as rs


def _write_run(root: Path, *, run_id: str, collection: str | None = None) -> Path:
    if collection is None:
        run_dir = root / run_id
    else:
        run_dir = root / BY_LOOP_KIND_DIRNAME / collection / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    return run_dir


@pytest.fixture
def cli_root(tmp_path, monkeypatch):
    root = tmp_path / "cli_runs"
    root.mkdir()
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: root)
    return root


def test_normalize_run_collection_from_loop_kind() -> None:
    assert normalize_run_collection("transcript_edit") == "transcript_edit"
    assert normalize_run_collection("deed_to_ir") == "deed_to_ir"


def test_new_runs_use_namespaced_directories(isolated_harness_root) -> None:
    st = rs.new_run_state(
        run_id="te-live-1",
        pid=1,
        loop_kind="transcript_edit",
        mode="live",
        spawn_argv=["python", "-m", "x"],
    )
    rs.write_state(st)
    assert "by_loop_kind" in st.paths.run_dir.replace("\\", "/")
    assert st.paths.run_dir.replace("\\", "/").endswith("by_loop_kind/transcript_edit/te-live-1")
    assert st.run_collection == "transcript_edit"


def test_transcript_and_deed_runs_use_separate_directories(isolated_harness_root) -> None:
    te = rs.new_run_state(
        run_id="te-1",
        pid=1,
        loop_kind="transcript_edit",
        mode="live",
        spawn_argv=["python", "-m", "x"],
    )
    deed = rs.new_run_state(
        run_id="deed-1",
        pid=2,
        loop_kind="deed_to_ir",
        mode="live",
        spawn_argv=["python", "-m", "x"],
    )
    rs.write_state(te)
    rs.write_state(deed)
    assert "transcript_edit" in te.paths.run_dir
    assert "deed_to_ir" in deed.paths.run_dir
    assert te.paths.run_dir != deed.paths.run_dir


def test_legacy_flat_run_remains_discoverable(cli_root: Path) -> None:
    legacy = _write_run(cli_root, run_id="practice-row-live-20260619-76")
    resolved = resolve_run_directory("practice-row-live-20260619-76")
    assert resolved.path == legacy
    assert resolved.layout == "legacy_flat"


def test_namespaced_run_discoverable(cli_root: Path) -> None:
    namespaced = _write_run(cli_root, run_id="deed-live-01", collection="deed_to_ir")
    resolved = resolve_run_directory("deed-live-01")
    assert resolved.path == namespaced
    assert resolved.layout == "by_loop_kind"
    assert resolved.run_collection == "deed_to_ir"


def test_duplicate_run_id_ambiguity_refused(cli_root: Path) -> None:
    _write_run(cli_root, run_id="dup-run")
    _write_run(cli_root, run_id="dup-run", collection="deed_to_ir")
    with pytest.raises(RunLayoutError) as exc:
        resolve_run_directory("dup-run")
    assert exc.value.code == "run_id_ambiguous"


def test_allocate_rejects_existing_global_run_id(cli_root: Path) -> None:
    _write_run(cli_root, run_id="existing-run")
    with pytest.raises(RunLayoutError) as exc:
        allocate_run_directory(run_id="existing-run", run_collection="deed_to_ir")
    assert exc.value.code == "run_id_already_exists"


def test_resolve_human_timeline_across_layouts(cli_root: Path) -> None:
    legacy = _write_run(cli_root, run_id="legacy-up")
    timeline = legacy / "audit" / "human" / "timeline.md"
    timeline.parent.mkdir(parents=True)
    timeline.write_text("# legacy", encoding="utf-8")
    assert resolve_run_human_timeline_path("legacy-up") == timeline

    namespaced = _write_run(cli_root, run_id="ns-up", collection="transcript_edit")
    ns_timeline = namespaced / "audit" / "human" / "timeline.md"
    ns_timeline.parent.mkdir(parents=True)
    ns_timeline.write_text("# namespaced", encoding="utf-8")
    assert resolve_run_human_timeline_path("ns-up") == ns_timeline


def test_find_candidates_prefers_legacy_then_collections(cli_root: Path) -> None:
    _write_run(cli_root, run_id="only-legacy")
    matches = find_run_directory_candidates("only-legacy")
    assert len(matches) == 1
    assert matches[0].layout == "legacy_flat"
