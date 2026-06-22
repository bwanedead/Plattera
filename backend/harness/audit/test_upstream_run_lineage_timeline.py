"""Tests for upstream run lineage timeline projection."""

from __future__ import annotations

from pathlib import Path

from harness.audit.upstream_run_lineage_timeline import render_upstream_runs_section


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


def test_timeline_renders_identity_and_refs_without_local_upstream_timeline(tmp_path: Path) -> None:
    cli_runs_root = tmp_path / "cli_runs"
    downstream = cli_runs_root / "downstream-run" / "audit" / "human" / "timeline.md"
    downstream.parent.mkdir(parents=True)

    lines = render_upstream_runs_section(
        _lineage(),
        cli_runs_root=cli_runs_root,
        downstream_timeline_path=downstream,
    )
    body = "\n".join(lines)
    assert "## Upstream Runs" in body
    assert "practice-row-live-20260619-76" in body
    assert "transcript_edit:output" in body
    assert "open upstream timeline" not in body


def test_timeline_renders_local_upstream_link_when_timeline_exists(tmp_path: Path) -> None:
    cli_runs_root = tmp_path / "cli_runs"
    upstream_timeline = (
        cli_runs_root
        / "practice-row-live-20260619-76"
        / "audit"
        / "human"
        / "timeline.md"
    )
    upstream_timeline.parent.mkdir(parents=True)
    upstream_timeline.write_text("# upstream", encoding="utf-8")

    downstream = cli_runs_root / "downstream-run" / "audit" / "human" / "timeline.md"
    downstream.parent.mkdir(parents=True)

    lines = render_upstream_runs_section(
        _lineage(),
        cli_runs_root=cli_runs_root,
        downstream_timeline_path=downstream,
    )
    body = "\n".join(lines)
    assert "[open upstream timeline]" in body
    assert "practice-row-live-20260619-76/audit/human/timeline.md" in body.replace("\\", "/")
