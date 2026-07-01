"""Tests for deed-to-IR upstream source evidence hydration bridge."""

from __future__ import annotations

import json
from pathlib import Path

from domains.mapping.deed_to_ir.test_fixtures.synthetic_transcript_edit_evidence import (
    install_synthetic_transcript_edit_derived_image,
)
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.upstream_source_evidence_hydration import (
    hydrate_upstream_source_evidence_ref,
    transcript_edit_workspace_from_handoff,
)


def test_transcript_edit_workspace_from_resolution_state_ref() -> None:
    workspace = transcript_edit_workspace_from_handoff(
        {"resolution_state_ref": "transcript_edit:resolution_state:practice-row-live-20260619-76"}
    )
    assert workspace == "practice-row-live-20260619-76"


def test_derived_ref_requires_upstream_workspace() -> None:
    row, error, evidence = hydrate_upstream_source_evidence_ref(
        dossier_id="d-example",
        transcription_id="tx-example",
        ref_id="image:derived:abc123",
        handoff_context={},
    )
    assert row is None
    assert error is not None
    assert error["reason"] == "transcript_edit_workspace_unavailable"
    assert evidence is None


def test_hydrate_artifact_refs_supports_image_derived_and_assoc_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dossier_id = "d-upstream-evidence"
    transcription_id = "tx-image"
    workspace_id = "practice-row-live-20260619-76"
    derived_uuid = "abc123def456"
    derived_ref = f"image:derived:{derived_uuid}"

    install_synthetic_transcript_edit_derived_image(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        ref_id=derived_ref,
    )

    handoff_context = {
        "resolution_state_ref": f"transcript_edit:resolution_state:{workspace_id}",
    }
    hydrated = hydrate_artifact_refs(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_ids=[derived_ref, "feature_graph:ir:missing"],
        handoff_context=handoff_context,
    )
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["hydrated_count"] == 1
    assert len(hydrated["outputs"]["errors"]) == 1
    row = hydrated["outputs"]["results"][0]
    assert row["kind"] == "upstream_derived_image"
    dumped = json.dumps(hydrated)
    assert "absolute_path" not in dumped
    assert str(tmp_path) not in dumped


def test_derived_ref_rejects_descriptor_path_outside_derived_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dossier_id = "d-path-guard"
    transcription_id = "tx-path-guard"
    workspace_id = "ws-path-guard"
    derived_uuid = "abc123def456"
    derived_ref = f"image:derived:{derived_uuid}"

    derived_dir = install_synthetic_transcript_edit_derived_image(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        ref_id=derived_ref,
    )
    outside_png = tmp_path / "outside.png"
    outside_png.write_bytes(b"not-a-real-png")

    (derived_dir / f"{derived_uuid}.json").write_text(
        json.dumps(
            {
                "ref_id": derived_ref,
                "absolute_path": str(outside_png.resolve()),
                "basename": f"{derived_uuid}.png",
                "width_height": [1, 1],
            }
        ),
        encoding="utf-8",
    )

    row, error, evidence = hydrate_upstream_source_evidence_ref(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_id=derived_ref,
        handoff_context={"resolution_state_ref": f"transcript_edit:resolution_state:{workspace_id}"},
    )
    assert row is None
    assert error is not None
    assert error["reason"] == "derived_image_path_outside_workspace"
    assert evidence is None

    hydrated = hydrate_artifact_refs(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_ids=[derived_ref],
        handoff_context={"resolution_state_ref": f"transcript_edit:resolution_state:{workspace_id}"},
    )
    assert hydrated["outputs"]["hydrated_count"] == 0
    assert hydrated["outputs"]["errors"][0]["reason"] == "derived_image_path_outside_workspace"
    assert "image_evidence" not in hydrated
