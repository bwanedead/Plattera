"""Tests for artifact_transform refusal classification and box_norm support.

Verifies:
- Fixable crop param errors are retryable (retryable=True, blocked_by_invariant=False)
- Repair hint is present in retryable error outputs
- box_norm normalized coordinates produce a valid derived image
- Non-retryable failures (missing source, bad ref kind) remain blocked_by_invariant=True
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import tooling.mapping.transcript_edit.paths as te_paths_mod
import config.paths as paths_mod

from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root


def _tiny_png_bytes(width: int = 100, height: int = 80) -> bytes:
    try:
        from PIL import Image

        img = Image.new("RGB", (width, height), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAADklEQVQI12P4z8BQDwAEgAF/QualIQAAAABJRU5ErkJggg=="
        )


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


def _make_handler(tmp_path, monkeypatch, *, d="d1", tx="tx-1", ws="ws-1"):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes(width=100, height=80))
    _write_association(root, d, tx, img_file)

    handler = make_transform_artifact_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    return handler, f"image:assoc:{tx}:original"


# ---------------------------------------------------------------------------
# Retryable param errors — the run must NOT be killed by these
# ---------------------------------------------------------------------------

def test_crop_missing_box_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {}})

    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True, "missing box must be retryable so the run can continue"
    assert refusal["blocked_by_invariant"] is False
    assert refusal["reason_code"] == "invalid_transform_params"
    # Repair hint must be present so the agent can self-correct
    assert "repair_hint" in result["outputs"]["error"]


def test_crop_malformed_box_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box": [10, 20]}})

    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    assert "repair_hint" in result["outputs"]["error"]


def test_crop_malformed_box_norm_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 1.5, 1.0]}})

    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    assert "repair_hint" in result["outputs"]["error"]


def test_crop_box_norm_out_of_range_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.0, 0.0, 1.5, 1.0]}})

    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_crop_box_norm_inverted_is_retryable(tmp_path, monkeypatch):
    """x1 >= x2 or y1 >= y2 is a fixable mistake."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0.8, 0.0, 0.2, 1.0]}})

    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_crop_box_inverted_is_retryable(tmp_path, monkeypatch):
    """Inverted pixel box [x1, y1, x2, y2] where x1 >= x2 is a fixable mistake, not a fatal failure."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box": [50, 0, 10, 40]}})

    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


# ---------------------------------------------------------------------------
# Successful transforms — verify box and box_norm both produce derived refs
# ---------------------------------------------------------------------------

def test_crop_with_box_succeeds(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box": [0, 0, 50, 40]}})

    assert result["executed"] is True
    derived = result["outputs"]["derived_ref_id"]
    assert derived.startswith("image:derived:")
    w, h = result["outputs"]["width_height"]
    assert w == 50 and h == 40
    evidence = result["image_evidence"]
    assert len(evidence) == 1
    assert evidence[0]["ref_id"] == derived
    assert evidence[0]["media_type"] == "image/png"
    assert base64.b64decode(evidence[0]["b64"])


def test_crop_with_box_norm_succeeds(tmp_path, monkeypatch):
    """box_norm = [0.0, 0.5, 1.0, 1.0] crops the bottom half of the 100x80 test image."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "crop",
        "params": {"box_norm": [0.0, 0.5, 1.0, 1.0]},
    })

    assert result["executed"] is True, f"Unexpected failure: {result}"
    derived = result["outputs"]["derived_ref_id"]
    assert derived.startswith("image:derived:")
    w, h = result["outputs"]["width_height"]
    # Bottom half of 100x80: width=100, height=40
    assert w == 100 and h == 40


def test_crop_box_norm_top_right_quadrant(tmp_path, monkeypatch):
    """box_norm = [0.5, 0.0, 1.0, 0.5] crops the top-right quadrant."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "crop",
        "params": {"box_norm": [0.5, 0.0, 1.0, 0.5]},
    })

    assert result["executed"] is True
    w, h = result["outputs"]["width_height"]
    assert w == 50 and h == 40


# ---------------------------------------------------------------------------
# reference_overlay — deterministic coordinate-reference helper
# ---------------------------------------------------------------------------

def test_reference_overlay_produces_derived_ref(tmp_path, monkeypatch):
    """reference_overlay with default params returns a derived image successfully."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "reference_overlay", "params": {}})

    assert result["executed"] is True, f"Unexpected failure: {result}"
    assert result["outputs"]["derived_ref_id"].startswith("image:derived:")
    assert result["image_evidence"][0]["ref_id"] == result["outputs"]["derived_ref_id"]
    w, h = result["outputs"]["width_height"]
    # Source is 100x80; overlay preserves dimensions
    assert w == 100 and h == 80


def test_reference_overlay_custom_grid(tmp_path, monkeypatch):
    """reference_overlay with explicit cols/rows still produces a valid derived image."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "reference_overlay",
        "params": {"cols": 2, "rows": 3, "line_color": [128, 128, 128], "label_color": [0, 0, 255]},
    })

    assert result["executed"] is True
    w, h = result["outputs"]["width_height"]
    assert w == 100 and h == 80


# ---------------------------------------------------------------------------
# Non-retryable failures — real invariant conditions
# ---------------------------------------------------------------------------

def test_unsupported_ref_kind_is_non_retryable(tmp_path, monkeypatch):
    handler, _ = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": "schema:foo:bar", "sub_action": "crop", "params": {"box": [0, 0, 10, 10]}})

    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is False
    assert refusal["blocked_by_invariant"] is True
    assert refusal["reason_code"] == "unsupported_ref_kind"


def test_missing_source_image_is_non_retryable(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    d, tx, ws = "d1", "tx-ghost", "ws-1"
    ghost = tmp_path / "ghost.png"  # does not exist
    _write_association(root, d, tx, ghost)

    handler = make_transform_artifact_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    result = handler({"ref_id": f"image:assoc:{tx}:original", "sub_action": "crop", "params": {"box": [0, 0, 10, 10]}})

    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is False
    assert refusal["blocked_by_invariant"] is True
