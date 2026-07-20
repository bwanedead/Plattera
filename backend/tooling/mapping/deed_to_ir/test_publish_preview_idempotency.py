"""Deterministic tests for idempotent preview-based deed-to-IR publication (D2IR-BR-012)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _prepare_mapping,
    _valid_rows,
)
from tooling.mapping.deed_to_ir.test_output_persistence import (
    _prepare_mapping as _prepare_direct_mapping,
    _publish_context,
    _patch_deed_root as _patch_direct_deed_root,
)


def _output_dir(tmp: str, *, transcription_id: str, workspace_id: str) -> Path:
    return (
        Path(tmp)
        / "artifacts"
        / "deed_to_ir"
        / "d-preview"
        / transcription_id
        / workspace_id
        / "output"
    )


def _prepare_and_get_preview(tmp: str, monkeypatch, *, note_id: str = "preview_note"):
    persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
    ctx = _context()
    _patch_deed_root(monkeypatch, tmp)
    rows = _valid_rows()
    rows["notes"] = [
        {
            "note_id": note_id,
            "summary": f"Example preview note ({note_id}).",
            "basis_refs": [],
        }
    ]
    prepared = prepare_deed_to_ir_final_package(
        dossier_id="d-preview",
        mapping_artifact_ref=mapping_ref,
        expected_ir_artifact_ref=ir_ref,
        persistence=persistence,
        **ctx,
        **rows,
    )
    assert prepared["executed"] is True
    preview_ref = prepared["outputs"]["final_package_preview_revision_ref"]
    return persistence, ir_ref, mapping_ref, ctx, preview_ref


def _publish_preview(persistence, preview_ref: str, ctx: dict) -> dict:
    return publish_deed_to_ir_output(
        dossier_id="d-preview",
        final_package_preview_ref=preview_ref,
        persistence=persistence,
        transcription_id=ctx["transcription_id"],
        workspace_id=ctx["workspace_id"],
        run_id=ctx["run_id"],
        transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
        resolution_state_ref=ctx["resolution_state_ref"],
    )


def _normal_output_fields(outputs: dict) -> dict:
    """Comparable success fields excluding idempotent_replay."""
    return {key: value for key, value in outputs.items() if key != "idempotent_replay"}


def test_first_preview_publication_creates_revision_1(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        first = _publish_preview(persistence, preview_ref, ctx)
        assert first["executed"] is True
        assert first["outputs"]["output_revision_ref"] == "deed_to_ir:output:rev:0001"
        assert first["outputs"]["final_package_preview_ref"] == preview_ref
        assert first["artifact_refs"].count(preview_ref) == 1
        assert "idempotent_replay" not in first["outputs"]

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        latest = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
        assert latest["revision_digits"] == "0001"
        assert latest["final_package_preview_ref"] == preview_ref
        assert (output_dir / "rev_0001.json").is_file()
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]


def test_repeat_same_preview_replays_revision_1_without_duplicate(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        first = _publish_preview(persistence, preview_ref, ctx)
        assert first["executed"] is True

        mark_calls = {"n": 0}
        original = FeatureGraphPersistenceService.mark_final_artifacts

        def _counting_mark(self, **kwargs):
            mark_calls["n"] += 1
            return original(self, **kwargs)

        monkeypatch.setattr(
            FeatureGraphPersistenceService,
            "mark_final_artifacts",
            _counting_mark,
        )

        second = _publish_preview(persistence, preview_ref, ctx)
        assert second["executed"] is True
        assert second["outputs"]["output_revision_ref"] == "deed_to_ir:output:rev:0001"
        assert second["outputs"]["idempotent_replay"] is True
        assert second["outputs"]["final_package_preview_ref"] == preview_ref
        assert first["artifact_refs"].count(preview_ref) == 1
        assert second["artifact_refs"].count(preview_ref) == 1
        assert mark_calls["n"] == 0

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]
        assert _normal_output_fields(first["outputs"]) == _normal_output_fields(second["outputs"])


def test_serialized_same_preview_calls_cannot_allocate_separate_revisions(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        results = [
            _publish_preview(persistence, preview_ref, ctx),
            _publish_preview(persistence, preview_ref, ctx),
            _publish_preview(persistence, preview_ref, ctx),
        ]
        assert all(row["executed"] for row in results)
        refs = [row["outputs"]["output_revision_ref"] for row in results]
        assert refs == [
            "deed_to_ir:output:rev:0001",
            "deed_to_ir:output:rev:0001",
            "deed_to_ir:output:rev:0001",
        ]
        assert results[0]["outputs"].get("idempotent_replay") is None
        assert results[1]["outputs"]["idempotent_replay"] is True
        assert results[2]["outputs"]["idempotent_replay"] is True

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        assert len(list(output_dir.glob("rev_*.json"))) == 1


def test_different_preview_creates_next_revision(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref = _prepare_mapping(tmp)
        ctx = _context()
        _patch_deed_root(monkeypatch, tmp)

        first_prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **_valid_rows(),
        )
        first_preview = first_prepared["outputs"]["final_package_preview_revision_ref"]
        first = _publish_preview(persistence, first_preview, ctx)
        assert first["outputs"]["output_revision_ref"] == "deed_to_ir:output:rev:0001"

        second_rows = _valid_rows()
        second_rows["notes"] = [
            {
                "note_id": "second_preview_note",
                "summary": "Second immutable preview.",
                "basis_refs": [],
            }
        ]
        second_prepared = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=mapping_ref,
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            **ctx,
            **second_rows,
        )
        second_preview = second_prepared["outputs"]["final_package_preview_revision_ref"]
        assert second_preview != first_preview

        second = _publish_preview(persistence, second_preview, ctx)
        assert second["executed"] is True
        assert second["outputs"]["output_revision_ref"] == "deed_to_ir:output:rev:0002"
        assert "idempotent_replay" not in second["outputs"]
        assert second["outputs"]["final_package_preview_ref"] == second_preview

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        latest = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
        assert latest["revision_digits"] == "0002"
        assert latest["final_package_preview_ref"] == second_preview
        assert len(list(output_dir.glob("rev_*.json"))) == 2


def test_legacy_pointer_without_preview_ref_remains_readable(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        first = _publish_preview(persistence, preview_ref, ctx)
        assert first["executed"] is True

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        latest_path = output_dir / "latest.json"
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        latest.pop("final_package_preview_ref", None)
        latest_path.write_text(json.dumps(latest), encoding="utf-8")

        # Legacy pointer still points at a readable revision.
        from tooling.mapping.deed_to_ir.output_persistence import load_published_output

        loaded = load_published_output(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        assert isinstance(loaded, dict)
        assert loaded.get("selected_artifacts")

        # Same preview publishes normally (no matching preview field) → next revision.
        second = _publish_preview(persistence, preview_ref, ctx)
        assert second["executed"] is True
        assert second["outputs"]["output_revision_ref"] == "deed_to_ir:output:rev:0002"
        assert "idempotent_replay" not in second["outputs"]


def test_direct_legacy_publication_omits_preview_ref_on_pointer(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, mapping_ref = _prepare_direct_mapping(tmp)
        ctx = _publish_context()
        _patch_direct_deed_root(monkeypatch, tmp)
        result = publish_deed_to_ir_output(
            dossier_id="d-pub",
            mapping_artifact_ref=mapping_ref,
            scope_results=[{"scope_id": "parcel_1", "status": "handoffable"}],
            **ctx,
            persistence=persistence,
        )
        assert result["executed"] is True
        assert "final_package_preview_ref" not in result["outputs"]
        assert not any(
            str(ref).startswith("deed_to_ir:final_package_preview")
            for ref in result.get("artifact_refs") or []
        )

        latest_path = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-pub"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "output"
            / "latest.json"
        )
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        assert "final_package_preview_ref" not in latest
        assert latest["revision_digits"] == "0001"


def test_matching_pointer_missing_revision_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        first = _publish_preview(persistence, preview_ref, ctx)
        assert first["executed"] is True

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        (output_dir / "rev_0001.json").unlink()

        refused = _publish_preview(persistence, preview_ref, ctx)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "published_preview_replay_state_invalid"
        assert list(output_dir.glob("rev_*.json")) == []


def test_matching_pointer_invalid_revision_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        first = _publish_preview(persistence, preview_ref, ctx)
        assert first["executed"] is True

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        (output_dir / "rev_0001.json").write_text('{"not": "a published output"}', encoding="utf-8")

        refused = _publish_preview(persistence, preview_ref, ctx)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "published_preview_replay_state_invalid"
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]


def test_matching_pointer_mapping_ir_conflict_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        first = _publish_preview(persistence, preview_ref, ctx)
        assert first["executed"] is True

        output_dir = _output_dir(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
        )
        rev_path = output_dir / "rev_0001.json"
        payload = json.loads(rev_path.read_text(encoding="utf-8"))
        payload["selected_artifacts"]["mapping_artifact_ref"] = "feature_graph:mapping:conflicted"
        payload["selected_artifacts"]["ir_artifact_ref"] = "feature_graph:ir:conflicted"
        rev_path.write_text(json.dumps(payload), encoding="utf-8")

        refused = _publish_preview(persistence, preview_ref, ctx)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "published_preview_replay_state_invalid"
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]


def _corrupt_latest_pointer(
    tmp: str,
    *,
    transcription_id: str,
    workspace_id: str,
    mutate,
) -> Path:
    output_dir = _output_dir(
        tmp,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    )
    latest_path = output_dir / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    mutate(latest)
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    return output_dir


def test_matching_pointer_missing_revision_ref_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        assert _publish_preview(persistence, preview_ref, ctx)["executed"] is True

        output_dir = _corrupt_latest_pointer(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            mutate=lambda latest: latest.pop("revision_ref", None),
        )
        refused = _publish_preview(persistence, preview_ref, ctx)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "published_preview_replay_state_invalid"
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]


def test_matching_pointer_revision_ref_disagrees_with_digits_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        assert _publish_preview(persistence, preview_ref, ctx)["executed"] is True

        def _mutate(latest: dict) -> None:
            latest["revision_ref"] = "deed_to_ir:output:rev:0002"

        output_dir = _corrupt_latest_pointer(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            mutate=_mutate,
        )
        refused = _publish_preview(persistence, preview_ref, ctx)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "published_preview_replay_state_invalid"
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]


def test_matching_pointer_incorrect_output_ref_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        assert _publish_preview(persistence, preview_ref, ctx)["executed"] is True

        def _mutate(latest: dict) -> None:
            latest["output_ref"] = "deed_to_ir:not_output"

        output_dir = _corrupt_latest_pointer(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            mutate=_mutate,
        )
        refused = _publish_preview(persistence, preview_ref, ctx)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "published_preview_replay_state_invalid"
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]


def test_matching_pointer_invalid_revision_digits_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, ctx, preview_ref = _prepare_and_get_preview(tmp, monkeypatch)
        assert _publish_preview(persistence, preview_ref, ctx)["executed"] is True

        def _mutate(latest: dict) -> None:
            latest["revision_digits"] = "1"
            latest["revision_ref"] = "deed_to_ir:output:rev:0001"

        output_dir = _corrupt_latest_pointer(
            tmp,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            mutate=_mutate,
        )
        refused = _publish_preview(persistence, preview_ref, ctx)
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "published_preview_replay_state_invalid"
        assert refused["refusal"]["reason_code"] != "invalid_scope_path"
        assert list(output_dir.glob("rev_*.json")) == [output_dir / "rev_0001.json"]
