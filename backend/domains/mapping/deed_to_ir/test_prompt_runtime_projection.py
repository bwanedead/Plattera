"""Tests for deed-to-IR prompt runtime projection seam."""

from __future__ import annotations

from domains.mapping.deed_to_ir.manifest import build_deed_to_ir_manifest
from domains.mapping.deed_to_ir.state.prompt_runtime_projection import (
    PROJECTION_SCHEMA,
    build_prompt_runtime_projection,
)
from tooling.mapping.deed_to_ir.mapping_lineage import (
    build_current_mapping_lineage,
    write_current_mapping_lineage,
)


CURRENT_MAPPING = "feature_graph:mapping:mapping_current_abc"
CURRENT_IR = "feature_graph:ir:graph__ws_run_v2"
SUPERSEDED_MAPPING = "feature_graph:mapping:mapping_old_xyz"


def test_manifest_declares_prompt_runtime_projection_module() -> None:
    manifest = build_deed_to_ir_manifest()
    assert (
        manifest.projection_module_ref
        == "domains.mapping.deed_to_ir.state.prompt_runtime_projection"
    )


def test_prompt_runtime_projection_classifies_historical_work_items(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    dossier_id = "dossier-prompt-proj"
    transcription_id = "draft_legal_text_image"
    run_id = "deed-to-ir-live-r-test"
    lineage = build_current_mapping_lineage(
        mapping_artifact_ref=CURRENT_MAPPING,
        source_ir_artifact_ref=CURRENT_IR,
        compile_gap_count=0,
        judge_gap_count=0,
    )
    write_current_mapping_lineage(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=None,
        run_id=run_id,
        lineage=lineage,
    )
    projected = build_prompt_runtime_projection(
        launch_context={
            "dossier_id": dossier_id,
            "transcription_id": transcription_id,
            "run_id": run_id,
        },
        resolution_items=[
            {
                "item_id": "stale_mapping_review",
                "status": "open",
                "evidence_refs": [SUPERSEDED_MAPPING],
            },
            {
                "item_id": "current_preview",
                "status": "open",
                "evidence_refs": [CURRENT_MAPPING],
            },
            {
                "item_id": "no_lineage_refs",
                "status": "blocked",
                "evidence_refs": ["image:derived:abc"],
            },
        ],
    )
    assert projected is not None
    assert projected["schema"] == PROJECTION_SCHEMA
    assert projected["active_handoff_context"]["mapping_artifact_ref"] == CURRENT_MAPPING
    assert projected["hot_artifact_refs"] == [CURRENT_MAPPING, CURRENT_IR]
    hist_ids = {row["item_id"] for row in projected["historical_lineage_context"]["items"]}
    assert hist_ids == {"stale_mapping_review"}
    cur_ids = {row["item_id"] for row in projected["current_lineage_work_items"]}
    assert cur_ids == {"current_preview"}
    # Unreferenced / non-lineage items remain outside both lanes (unchanged).
    assert "no_lineage_refs" not in hist_ids
    assert "no_lineage_refs" not in cur_ids


def test_prompt_runtime_projection_without_lineage_returns_none() -> None:
    assert (
        build_prompt_runtime_projection(
            launch_context={"dossier_id": "missing"},
            resolution_items=[
                {"item_id": "x", "evidence_refs": [SUPERSEDED_MAPPING]},
            ],
        )
        is None
    )
