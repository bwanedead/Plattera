"""Tests for durable CLI run-state extra merging."""

from __future__ import annotations

import harness.cli.run_state as rs


def test_merge_state_extra_preserves_existing_keys(isolated_harness_root) -> None:
    run_id = "merge-extra-1"
    st = rs.new_run_state(
        run_id=run_id,
        pid=1,
        loop_kind="harness_cli",
        mode="stub",
        spawn_argv=["python", "-m", "harness.cli.stub_worker"],
        extra={"model": "gpt-5.4-mini"},
    )
    rs.write_state(st)

    lineage = {
        "schema_version": "upstream_run_lineage.v1",
        "upstream_runs": [
            {
                "run_id": "practice-row-live-20260619-76",
                "domain_id": "transcript_edit",
                "relation": "input_handoff",
                "handoff_refs": ["transcript_edit:output"],
            }
        ],
    }
    merged = rs.merge_state_extra(run_id, {"upstream_run_lineage": lineage})
    assert merged is not None
    assert merged.extra["model"] == "gpt-5.4-mini"
    assert merged.extra["upstream_run_lineage"] == lineage

    loaded = rs.read_state(run_id)
    assert loaded is not None
    assert loaded.extra["model"] == "gpt-5.4-mini"
    assert loaded.extra["upstream_run_lineage"] == lineage


def test_start_post_spawn_write_preserves_child_merged_extra(isolated_harness_root, monkeypatch) -> None:
    """Simulate child writing upstream_run_lineage before parent pid/status update."""
    run_id = "merge-extra-start-race"
    st = rs.new_run_state(
        run_id=run_id,
        pid=0,
        loop_kind="deed_to_ir",
        mode="live",
        spawn_argv=["python", "-m", "harness.runtime.runner.entrypoint"],
        status="spawning",
        extra={"model": "gpt-5.4-mini"},
    )
    rs.write_state(st)

    lineage = {
        "schema_version": "upstream_run_lineage.v1",
        "upstream_runs": [
            {
                "run_id": "practice-row-live-20260619-76",
                "domain_id": "transcript_edit",
                "relation": "input_handoff",
                "handoff_refs": ["transcript_edit:output"],
            }
        ],
    }
    rs.merge_state_extra(run_id, {"upstream_run_lineage": lineage})

    stale_parent = st
    fresh = rs.read_state(run_id)
    assert fresh is not None
    fresh.pid = 4242
    fresh.status = "started"
    rs.write_state(fresh)

    loaded = rs.read_state(run_id)
    assert loaded is not None
    assert loaded.pid == 4242
    assert loaded.status == "started"
    assert loaded.extra["model"] == "gpt-5.4-mini"
    assert loaded.extra["upstream_run_lineage"] == lineage

    stale_parent.pid = 4242
    stale_parent.status = "started"
    rs.write_state(stale_parent)
    lost = rs.read_state(run_id)
    assert lost is not None
    assert "upstream_run_lineage" not in lost.extra
