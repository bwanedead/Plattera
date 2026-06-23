"""Tests for upstream run lineage timeline projection."""

from __future__ import annotations

import json
from pathlib import Path

from harness.audit.upstream_run_lineage_timeline import render_upstream_runs_section
from harness.cli.run_layout import BY_LOOP_KIND_DIRNAME


def _lineage() -> dict:
    return {
        "schema_version": "upstream_run_lineage.v1",
        "upstream_runs": [
            {
                "run_id": "practice-row-live-20260619-76",
                "domain_id": "transcript_edit",
                "relation": "input_handoff",
                "handoff_refs": [
                    "transcript_edit:output",
                    "transcript_edit:resolution_state:practice-row-live-20260619-76",
                ],
            }
        ],
    }


def _write_legacy_run(cli_runs_root: Path, run_id: str) -> Path:
    run_dir = cli_runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
    return run_dir


def test_timeline_renders_identity_and_refs_without_local_upstream_timeline(tmp_path: Path) -> None:
    cli_runs_root = tmp_path / "cli_runs"
    downstream = cli_runs_root / "downstream-run" / "audit" / "human" / "timeline.md"
    downstream.parent.mkdir(parents=True)

    lines = render_upstream_runs_section(
        _lineage(),
        downstream_timeline_path=downstream,
        resolve_upstream_timeline_path=lambda _run_id: None,
    )
    body = "\n".join(lines)
    assert "## Upstream Runs" in body
    assert "practice-row-live-20260619-76" in body
    assert "transcript_edit:output" in body
    assert "open upstream timeline" not in body


def test_timeline_renders_local_upstream_link_when_timeline_exists_legacy(tmp_path: Path) -> None:
    cli_runs_root = tmp_path / "cli_runs"
    upstream_dir = _write_legacy_run(cli_runs_root, "practice-row-live-20260619-76")
    upstream_timeline = upstream_dir / "audit" / "human" / "timeline.md"
    upstream_timeline.parent.mkdir(parents=True)
    upstream_timeline.write_text("# upstream", encoding="utf-8")

    downstream = cli_runs_root / "downstream-run" / "audit" / "human" / "timeline.md"
    downstream.parent.mkdir(parents=True)

    def _resolve(run_id: str) -> Path | None:
        candidate = cli_runs_root / run_id / "audit" / "human" / "timeline.md"
        return candidate if candidate.is_file() else None

    lines = render_upstream_runs_section(
        _lineage(),
        downstream_timeline_path=downstream,
        resolve_upstream_timeline_path=_resolve,
    )
    body = "\n".join(lines)
    assert "[open upstream timeline]" in body
    assert "practice-row-live-20260619-76/audit/human/timeline.md" in body.replace("\\", "/")


def test_timeline_renders_local_upstream_link_when_timeline_exists_namespaced(tmp_path: Path) -> None:
    cli_runs_root = tmp_path / "cli_runs"
    upstream_dir = (
        cli_runs_root
        / BY_LOOP_KIND_DIRNAME
        / "transcript_edit"
        / "practice-row-live-20260619-76"
    )
    upstream_dir.mkdir(parents=True)
    (upstream_dir / "state.json").write_text(
        json.dumps({"run_id": "practice-row-live-20260619-76"}),
        encoding="utf-8",
    )
    upstream_timeline = upstream_dir / "audit" / "human" / "timeline.md"
    upstream_timeline.parent.mkdir(parents=True)
    upstream_timeline.write_text("# upstream", encoding="utf-8")

    downstream = (
        cli_runs_root
        / BY_LOOP_KIND_DIRNAME
        / "deed_to_ir"
        / "downstream-run"
        / "audit"
        / "human"
        / "timeline.md"
    )
    downstream.parent.mkdir(parents=True)

    from harness.cli.run_layout import resolve_run_human_timeline_path
    import harness.cli.run_layout as layout_mod

    original = layout_mod.cli_runs_root
    layout_mod.cli_runs_root = lambda: cli_runs_root
    try:
        lines = render_upstream_runs_section(
            _lineage(),
            downstream_timeline_path=downstream,
            resolve_upstream_timeline_path=resolve_run_human_timeline_path,
        )
    finally:
        layout_mod.cli_runs_root = original

    body = "\n".join(lines)
    assert "[open upstream timeline]" in body
    assert "transcript_edit/practice-row-live-20260619-76/audit/human/timeline.md" in body.replace(
        "\\", "/"
    )
