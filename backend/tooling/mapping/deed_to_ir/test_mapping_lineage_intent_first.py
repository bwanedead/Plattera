"""Tests for current mapping lineage persistence and intent-first prepare."""

from __future__ import annotations

import tempfile
from pathlib import Path

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.mapping_lineage import (
    read_current_mapping_lineage,
)
from tooling.mapping.deed_to_ir.test_correction_posture import (
    _PRACTICE_CORRECT_DISTANCE,
    _resolution_snapshot,
    _source_repair_graph,
)
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _valid_rows,
)


def _compact_dispositions() -> dict:
    return {
        "scope_dispositions": [
            {"scope_id": "parcel_1", "status": "handoffable"},
            {"scope_id": "parcel_2", "status": "blocked"},
        ],
        "closure_dispositions": [
            {
                "dimension_id": dimension_id,
                "status": "partial" if dimension_id.endswith("scoped_completion") else "closed",
            }
            for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
        ],
    }


def _submit_with_lineage(tmp: str, *, leg2_distance: float, monkeypatch):
    _patch_deed_root(monkeypatch, tmp)
    from tooling.mapping.deed_to_ir.test_final_package_preview import _services

    ctx = _context()
    persistence = _services(tmp)
    saved = save_ir_artifact(
        dossier_id="d-preview",
        feature_graph=_source_repair_graph(leg2_distance=leg2_distance).model_dump(mode="json"),
        artifact_id="ir_source_repair",
        draft_workspace_id=ctx["workspace_id"],
        draft_run_id=ctx["run_id"],
        transcription_id=ctx["transcription_id"],
        persistence=persistence,
    )
    assert saved["executed"] is True
    ir_ref = saved["outputs"]["ir_artifact_ref"]
    submitted = submit_ir_for_mapping(
        dossier_id="d-preview",
        ir_artifact_ref=ir_ref,
        persistence=persistence,
        resolution_state_snapshot=_resolution_snapshot(),
        transcription_id=ctx["transcription_id"],
        workspace_id=ctx["workspace_id"],
        run_id=ctx["run_id"],
    )
    assert submitted["executed"] is True
    mapping_ref = submitted["outputs"]["mapping_artifact_ref"]
    return persistence, ir_ref, mapping_ref, submitted, ctx


def test_submit_writes_current_mapping_lineage(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        lineage = submitted["outputs"]["current_mapping_lineage"]
        assert lineage["mapping_artifact_ref"] == mapping_ref or lineage["mapping_artifact_ref"] == submitted[
            "outputs"
        ]["mapping_artifact_ref"]
        assert lineage["source_ir_artifact_ref"] == ir_ref
        assert lineage["lineage_current"] is True
        assert lineage["use_for_next_preview"] is True
        assert lineage["stale"] is False

        disk = read_current_mapping_lineage(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["mapping_artifact_ref"] == submitted["outputs"]["mapping_artifact_ref"]
        assert disk["source_ir_artifact_ref"] == ir_ref


def test_save_marks_current_mapping_lineage_stale(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        graph = _source_repair_graph(leg2_distance=520.0).model_dump(mode="json")
        saved = save_ir_artifact(
            dossier_id="d-preview",
            feature_graph=graph,
            base_draft_ref=ir_ref,
            draft_workspace_id=ctx["workspace_id"],
            draft_run_id=ctx["run_id"],
            transcription_id=ctx["transcription_id"],
            persistence=persistence,
        )
        assert saved["executed"] is True
        lineage = saved["outputs"]["current_mapping_lineage"]
        assert lineage["stale"] is True
        assert lineage["use_for_next_preview"] is False
        assert lineage["lineage_current"] is False

        refused = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            reuse_agent_authored_finalization_state=True,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "current_mapping_lineage_stale"


def test_intent_first_prepare_fresh_workspace_no_prior_preview(monkeypatch) -> None:
    """Fresh corrupted-source repair: no prior preview; compact dispositions succeed."""
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        preview_dir = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-preview"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "final_package_preview"
        )
        assert not preview_dir.exists() or not any(preview_dir.glob("rev_*.json"))

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[
                {
                    "target_entity_id": "p1_call2_distance",
                    "posture": "confirmed_from_source",
                    "resolution_used_by_ir": True,
                    "recommended_action": "transcript_amendment",
                    "rationale": (
                        "Targeted source evidence supports 518 feet and the repaired "
                        "mapping is the intended scoped handoff."
                    ),
                }
            ],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert result["executed"] is True
        outputs = result["outputs"]
        assert outputs["finalization_status"] == "preview_ready"
        assert outputs["selected_lineage"]["expected_ir_artifact_ref"] == ir_ref
        assert outputs["selected_lineage"]["mapping_artifact_ref"] == submitted["outputs"][
            "mapping_artifact_ref"
        ]
        summary = outputs["correction_summary"]
        assert summary["active"] is True
        assert summary["rows_created"] == 1
        target = summary["targets"][0]
        assert target["target_entity_id"] == "p1_call2_distance"
        assert "618" in str(target["upstream_value"])
        assert target["selected_ir_value"] == _PRACTICE_CORRECT_DISTANCE
        assert target["resolution_used_by_ir"] is True
        assert outputs["recommended_publish_request"]["final_package_preview_ref"]
        assert any(preview_dir.glob("rev_*.json"))


def test_intent_first_missing_finalization_state_returns_shell(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            reuse_agent_authored_finalization_state=True,
            correction_decisions=[
                {
                    "target_entity_id": "p1_call2_distance",
                    "posture": "confirmed_from_source",
                    "resolution_used_by_ir": True,
                    "recommended_action": "transcript_amendment",
                    "rationale": "Evidence supports 518 feet.",
                }
            ],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "missing_finalization_decisions"
        shell = result["outputs"]["missing_finalization_decisions"]
        assert "scope_dispositions" in shell
        assert "closure_dispositions" in shell
        assert len(shell["closure_dispositions"]) == 4


def test_intent_first_missing_correction_decision_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "correction_decisions_required"


def test_explicit_prepare_still_works(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=submitted["outputs"]["mapping_artifact_ref"],
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            upstream_corrections=[
                {
                    "correction_id": "explicit_p1_call2",
                    "target_entity_id": "p1_call2_distance",
                    "target_entity_type": "resolution_unit",
                    "upstream_value": "618 feet",
                    "corrected_value": "518 feet",
                    "posture": "confirmed_from_source",
                    "resolution_used_by_ir": True,
                    "recommended_action": "transcript_amendment",
                    "basis_refs": ["image:derived:fixture", ir_ref],
                    "rationale": "Explicit path still supported.",
                }
            ],
            **ctx,
            **_valid_rows(),
        )
        assert result["executed"] is True
        assert "finalization_status" not in result["outputs"]


def test_intent_first_refuses_missing_lineage(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _patch_deed_root(monkeypatch, tmp)
        ctx = _context()
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            use_current_mapping_lineage=True,
            reuse_agent_authored_finalization_state=True,
            **ctx,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "current_mapping_lineage_missing"


def test_hydrate_mapping_annotates_current_and_superseded(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref_v0, submitted_v0, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        # Patch IR and remap so v0 mapping is superseded.
        patched = save_ir_artifact(
            dossier_id="d-preview",
            feature_graph=_source_repair_graph(leg2_distance=519.0).model_dump(mode="json"),
            base_draft_ref=ir_ref,
            draft_workspace_id=ctx["workspace_id"],
            draft_run_id=ctx["run_id"],
            transcription_id=ctx["transcription_id"],
            persistence=persistence,
        )
        assert patched["executed"] is True
        remapped = submit_ir_for_mapping(
            dossier_id="d-preview",
            ir_artifact_ref=patched["outputs"]["ir_artifact_ref"],
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert remapped["executed"] is True
        mapping_ref_current = remapped["outputs"]["mapping_artifact_ref"]
        assert mapping_ref_current != mapping_ref_v0

        hydrated = hydrate_artifact_refs(
            dossier_id="d-preview",
            ref_ids=[mapping_ref_v0, mapping_ref_current],
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        by_ref = {row["ref_id"]: row for row in hydrated["outputs"]["results"]}
        stale_row = by_ref[mapping_ref_v0]
        current_row = by_ref[mapping_ref_current]
        assert stale_row["lineage_status"] == "superseded"
        assert stale_row["lineage_current"] is False
        assert stale_row["current_mapping_artifact_ref"] == mapping_ref_current
        assert stale_row["mapping_review"]["lineage_status"] == "superseded"
        assert current_row["lineage_status"] == "current"
        assert current_row["lineage_current"] is True
        assert current_row["mapping_review"]["lineage_status"] == "current"
