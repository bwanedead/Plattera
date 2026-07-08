"""Tests for deed-to-IR upstream_corrections final-package lane."""

from __future__ import annotations

import json
import tempfile

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.final_package_preview_projection import (
    render_final_package_preview_timeline_lines,
    render_upstream_corrections_timeline_lines,
)
from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output
from tooling.mapping.deed_to_ir.publish_gate_feedback import render_publish_output_summary_timeline_lines
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _prepare_mapping,
    _valid_rows,
)


def _sample_upstream_correction(**overrides: object) -> dict:
    row = {
        "correction_id": "example_call_distance_transcript_correction",
        "title": "Example call distance correction",
        "target_entity_id": "example_call2_distance",
        "target_entity_type": "resolution_unit",
        "upstream_value": "410 feet",
        "corrected_value": "438 feet",
        "posture": "confirmed_from_source",
        "resolution_used_by_ir": True,
        "recommended_action": "transcript_amendment",
        "basis_refs": [
            "transcript_edit:resolution_state:example",
            "feature_graph:ir:example",
        ],
        "rationale": "Final IR and mapping rely on the corrected distance.",
    }
    row.update(overrides)
    return row


def test_preview_accepts_valid_upstream_corrections(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction()],
        )

        assert result["executed"] is True
        outputs = result["outputs"]
        assert outputs["upstream_correction_count"] == 1
        assert outputs["upstream_correction_summaries"][0]["correction_id"] == (
            "example_call_distance_transcript_correction"
        )


def test_publish_from_preview_preserves_upstream_corrections(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction()],
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]

        published = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref=preview_ref,
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
        )

        assert published["executed"] is True
        assert published["outputs"]["upstream_correction_count"] == 1
        summaries = published["outputs"]["upstream_correction_summaries"]
        assert summaries[0]["posture"] == "confirmed_from_source"
        assert summaries[0]["recommended_action"] == "transcript_amendment"


def test_hydrating_output_returns_bounded_upstream_corrections(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction(rationale="secret rationale text")],
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]
        published = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref=preview_ref,
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
        )
        output_ref = published["outputs"]["output_revision_ref"]

        hydrated = hydrate_artifact_refs(
            dossier_id="d-preview",
            ref_ids=[output_ref],
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        row = hydrated["outputs"]["results"][0]
        assert row["upstream_correction_count"] == 1
        assert row["upstream_correction_summaries"][0]["correction_id"] == (
            "example_call_distance_transcript_correction"
        )
        assert row["upstream_corrections"][0]["rationale"] == "secret rationale text"
        dumped = json.dumps(row)
        assert "410 feet" not in dumped or "upstream_corrections" in dumped


def test_invalid_upstream_correction_is_field_level_retryable(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction(posture="not_a_posture")],
        )

        assert result["executed"] is False
        outputs = result["outputs"]
        assert outputs["validation_errors"]
        assert any("upstream_corrections[0].posture" in err["path"] for err in outputs["validation_errors"])
        assert result["refusal"]["retryable"] is True


def test_duplicate_correction_id_rejected(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        row = _sample_upstream_correction()

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[row, dict(row)],
        )

        assert result["executed"] is False
        assert any(
            err.get("code") == "correction_id_not_unique"
            for err in result["outputs"]["validation_errors"]
        )


def test_unknown_extra_fields_rejected(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction(extra_field="nope")],
        )

        assert result["executed"] is False
        assert any(
            err.get("code") == "extra_forbidden"
            for err in result["outputs"]["validation_errors"]
        )


def test_missing_basis_refs_rejected(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction(basis_refs=[])],
        )

        assert result["executed"] is False
        assert any(
            "upstream_corrections[0].basis_refs" in err["path"]
            for err in result["outputs"]["validation_errors"]
        )


def test_missing_rationale_rejected(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        row = _sample_upstream_correction()
        del row["rationale"]

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[row],
        )

        assert result["executed"] is False
        assert any(
            "upstream_corrections[0].rationale" in err["path"]
            for err in result["outputs"]["validation_errors"]
        )


def test_publish_from_preview_rejects_upstream_correction_mutation(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]

        result = publish_deed_to_ir_output(
            dossier_id="d-preview",
            final_package_preview_ref=preview_ref,
            upstream_corrections=[_sample_upstream_correction()],
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
        )

        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "final_package_preview_row_mutation_forbidden"


def test_timeline_renders_compact_upstream_corrections() -> None:
    lines = render_upstream_corrections_timeline_lines(
        upstream_correction_count=1,
        upstream_correction_summaries=[
            {
                "correction_id": "example_call_distance_transcript_correction",
                "posture": "confirmed_from_source",
                "recommended_action": "transcript_amendment",
                "target_entity_id": "example_call2_distance",
                "resolution_used_by_ir": True,
            }
        ],
        indent="  ",
    )
    body = "\n".join(lines)
    assert "upstream_corrections: 1" in body
    assert "example_call_distance_transcript_correction" in body
    assert "posture=confirmed_from_source" in body
    assert "action=transcript_amendment" in body
    assert "target=example_call2_distance" in body
    assert "used_by_ir=true" in body
    assert "410 feet" not in body


def test_preview_timeline_includes_upstream_corrections(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction()],
        )
        lines = render_final_package_preview_timeline_lines(result["outputs"])
        body = "\n".join(lines)
        assert "upstream_corrections: 1" in body


def test_publish_output_timeline_includes_upstream_corrections() -> None:
    outputs = {
        "output_ref": "deed_to_ir:output",
        "output_revision_ref": "deed_to_ir:output:rev:0001",
        "upstream_correction_count": 1,
        "upstream_correction_summaries": [
            {
                "correction_id": "example_call_distance_transcript_correction",
                "posture": "confirmed_from_source",
                "recommended_action": "transcript_amendment",
                "target_entity_id": "example_call2_distance",
                "resolution_used_by_ir": True,
            }
        ],
        "final_output_summary": {"ready_for_completion_candidate": True},
    }
    lines = render_publish_output_summary_timeline_lines(outputs)
    body = "\n".join(lines)
    assert "upstream_corrections: 1" in body


def test_hydrating_preview_returns_bounded_upstream_corrections(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction()],
        )
        preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]
        hydrated = hydrate_artifact_refs(
            dossier_id="d-preview",
            ref_ids=[preview_ref],
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        row = hydrated["outputs"]["results"][0]
        assert row["upstream_correction_count"] == 1
        assert row["upstream_correction_summaries"][0]["correction_id"] == (
            "example_call_distance_transcript_correction"
        )


def test_direct_publish_accepts_upstream_corrections(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        rows = _valid_rows()

        published = publish_deed_to_ir_output(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
            resolution_state_ref=ctx["resolution_state_ref"],
            upstream_corrections=[_sample_upstream_correction()],
            **rows,
        )

        assert published["executed"] is True
        assert published["outputs"]["upstream_correction_count"] == 1


def _validation_messages(result: dict) -> list[str]:
    return [str(err.get("message") or "") for err in result["outputs"]["validation_errors"]]


def test_malformed_upstream_correction_summary_extra_returns_hint(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        row = _sample_upstream_correction()
        row.pop("rationale", None)
        row["summary"] = "wrong field"
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[row],
        )
    assert result["executed"] is False
    messages = " ".join(_validation_messages(result))
    assert "summary is not a field" in messages


def test_malformed_upstream_correction_inherited_value_extra_returns_hint(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        row = _sample_upstream_correction()
        row.pop("upstream_value", None)
        row["inherited_value"] = "618 feet"
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[row],
        )
    messages = " ".join(_validation_messages(result))
    assert "Use upstream_value" in messages


def test_malformed_upstream_correction_posture_confirmed_returns_hint(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
            upstream_corrections=[_sample_upstream_correction(posture="confirmed")],
        )
    messages = " ".join(_validation_messages(result))
    assert "confirmed_from_source" in messages
