"""Tests for model-visible image evidence in hydrate_artifact_refs.

Covers:
- image:assoc:* hydration returns metadata in outputs (not b64) + image_evidence at top level
- image:derived:* hydration after a transform returns derived evidence at top level
- b64 data is absent from outputs (does not bloat kernel_step_result_records)
- missing image file → no image_evidence, no crash
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import tooling.mapping.transcript_edit.paths as te_paths_mod

from tooling.mapping.transcript_edit.artifact_hydration import make_hydrate_artifact_refs_handler
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root


def _write_association(root: Path, dossier_id: str, transcription_id: str, image_path: Path) -> None:
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True, exist_ok=True)
    assoc_file = assoc_dir / f"assoc_{dossier_id}.json"
    assoc_file.write_text(
        json.dumps({
            "associations": [
                {
                    "transcription_id": transcription_id,
                    "metadata": {
                        "images": {
                            "original_path": str(image_path),
                            "processed_path": str(image_path),
                        }
                    },
                }
            ]
        }),
        encoding="utf-8",
    )


def _tiny_png_bytes() -> bytes:
    """Minimal valid 4x4 white PNG created with PIL."""
    try:
        from PIL import Image
        import io
        img = Image.new("RGB", (4, 4), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Fallback: hard-coded 4x4 white PNG
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAADklEQVQI12P4z8BQDwAEgAF/QualIQAAAABJRU5ErkJggg=="
        )


def test_hydrate_assoc_image_returns_evidence_and_metadata(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)

    d, tx = "d1", "tx-1"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes())

    _write_association(root, d, tx, img_file)

    handler = make_hydrate_artifact_refs_handler(dossier_id=d, transcription_id=tx, workspace_key=None)
    result = handler({"ref_ids": [f"image:assoc:{tx}:original"]})

    assert result["executed"] is True

    # Metadata is in outputs
    outputs = result["outputs"]
    assert outputs["hydrated_count"] == 1
    res0 = outputs["results"][0]
    assert res0["kind"] == "source_image"
    assert res0["exists"] is True
    assert res0["basename"] == "scan.png"
    # b64 is NOT in outputs (avoids kernel_step_result_records token bloat)
    assert "image_b64" not in res0

    # Image evidence is at top level, outside outputs
    evidence = result.get("image_evidence")
    assert isinstance(evidence, list) and len(evidence) == 1
    ev = evidence[0]
    assert ev["ref_id"] == f"image:assoc:{tx}:original"
    assert ev["media_type"] == "image/png"
    # b64 decodes back to the same bytes as the image file
    assert base64.b64decode(ev["b64"]) == img_file.read_bytes()


def test_hydrate_assoc_image_missing_file_no_evidence(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)

    d, tx = "d1", "tx-1"
    img_file = tmp_path / "ghost.png"  # does not exist

    _write_association(root, d, tx, img_file)

    handler = make_hydrate_artifact_refs_handler(dossier_id=d, transcription_id=tx, workspace_key=None)
    result = handler({"ref_ids": [f"image:assoc:{tx}:original"]})

    assert result["executed"] is True
    res0 = result["outputs"]["results"][0]
    assert res0["exists"] is False
    # No image evidence when file is missing
    assert not result.get("image_evidence")


def test_hydrate_derived_image_returns_evidence_after_transform(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)

    d, tx, ws = "d1", "tx-1", "ws-1"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes())

    _write_association(root, d, tx, img_file)

    # Create a derived image via transform
    transform_handler = make_transform_artifact_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    tr = transform_handler({
        "ref_id": f"image:assoc:{tx}:original",
        "sub_action": "zoom",
        "params": {"factor": 1.0},
    })
    assert tr["executed"] is True
    derived_ref = tr["outputs"]["derived_ref_id"]
    assert derived_ref.startswith("image:derived:")
    # transform_artifact emits artifact_refs
    assert derived_ref in tr.get("artifact_refs", [])

    # Now hydrate the derived ref
    hydrate_handler = make_hydrate_artifact_refs_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    result = hydrate_handler({"ref_ids": [derived_ref]})

    assert result["executed"] is True
    res0 = result["outputs"]["results"][0]
    assert res0["kind"] == "derived_image"
    assert res0["ref_id"] == derived_ref

    # Image evidence is present
    evidence = result.get("image_evidence")
    assert isinstance(evidence, list) and len(evidence) == 1
    ev = evidence[0]
    assert ev["ref_id"] == derived_ref
    assert ev["b64"]  # non-empty base64
    assert ev["media_type"] in ("image/png", "image/jpeg")

    # b64 not in outputs
    assert "image_b64" not in res0


def test_image_evidence_not_in_outputs_keys(tmp_path, monkeypatch):
    """Regression: image_evidence must never appear inside the outputs dict (token bloat protection)."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)

    d, tx = "d1", "tx-1"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes())

    _write_association(root, d, tx, img_file)

    handler = make_hydrate_artifact_refs_handler(dossier_id=d, transcription_id=tx, workspace_key=None)
    result = handler({"ref_ids": [f"image:assoc:{tx}:original"]})

    outputs = result["outputs"]
    assert "image_evidence" not in outputs
    assert "image_b64" not in outputs
    for res in outputs.get("results", []):
        assert "image_b64" not in res
        assert "image_evidence" not in res


def test_processed_source_image_ref_rejected(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)

    d, tx = "d1", "tx-1"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes())
    _write_association(root, d, tx, img_file)

    handler = make_hydrate_artifact_refs_handler(dossier_id=d, transcription_id=tx, workspace_key=None)
    result = handler({"ref_ids": [f"image:assoc:{tx}:processed"]})

    assert result["executed"] is True
    errors = result["outputs"]["errors"]
    assert any(e["code"] == "invalid_ref" for e in errors)
    assert result["outputs"]["hydrated_count"] == 0
    assert not result.get("image_evidence")
