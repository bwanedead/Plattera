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
from typing import Any

import pytest
from pydantic import ValidationError

import tooling.mapping.transcript_edit.paths as te_paths_mod
import config.paths as paths_mod

from harness.mission_state import EvidenceLocator
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


def _make_handler(tmp_path, monkeypatch, *, d="d1", tx="tx-1", ws="ws-1", image_width=100, image_height=80):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)

    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    img_file.write_bytes(_tiny_png_bytes(width=image_width, height=image_height))
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
    assert w == 100 and h == 80


def test_reference_overlay_default_grid_is_denser(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, "sub_action": "reference_overlay", "params": {}})
    assert result["executed"] is True
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", result["outputs"]["derived_ref_id"])
    overlay = desc["transform_metadata"]["overlay"]
    grid = overlay["grid"]
    lattice = overlay["coordinate_lattice"]
    assert lattice["major_step_norm"] == 0.10
    assert lattice["minor_step_norm"] == 0.025
    assert lattice["x_increases"] == "right"
    assert lattice["y_increases"] == "down"
    assert lattice["major_labels"][0] == "0.10"
    assert overlay["overlay_role"] == "plain_coordinate_reference"
    assert result["outputs"]["overlay_role"] == "plain_coordinate_reference"
    assert grid["major_step_norm"] == 0.10
    assert grid["minor_step_norm"] == 0.025
    assert grid["cols"] == 10
    assert grid["rows"] == 10
    from PIL import Image

    img = Image.open(desc["absolute_path"])
    bg = (200, 200, 200)
    assert img.getpixel((2, 5)) != bg
    assert img.getpixel((10, 5)) != bg


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
# point_crops_scaffold — zero-point placement coordinate surface
# ---------------------------------------------------------------------------

def test_point_crops_scaffold_produces_one_derived_image(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "point_crops_scaffold", "params": {}})

    assert result["executed"] is True, f"Unexpected failure: {result}"
    assert len(result["artifact_refs"]) == 1
    assert result["outputs"]["derived_ref_id"].startswith("image:derived:")
    assert result["image_evidence"][0]["ref_id"] == result["outputs"]["derived_ref_id"]


def test_point_crops_scaffold_output_metadata_and_no_crop_sidecars(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, "sub_action": "point_crops_scaffold", "params": {"show": ["grid"]}})

    assert result["executed"] is True
    outputs = result["outputs"]
    assert outputs["overlay_role"] == "point_crop_placement_scaffold"
    assert outputs["point_count"] == 0
    assert outputs["crop_records"] == []
    assert outputs["crop_set"]["points"] == []
    assert outputs["crop_set"]["point_count"] == 0
    lattice = outputs["coordinate_lattice"]
    assert lattice["major_step_norm"] == 0.10
    assert lattice["minor_step_norm"] == 0.025
    assert lattice["reference_cells"] == {"cols": 10, "rows": 10, "cell_labels": True}
    assert outputs["crop_set"]["grid"]["cols"] == 10
    assert outputs["crop_set"]["grid"]["cell_labels"] is True
    assert "delegation_lines" not in outputs
    assert "review_lines" not in outputs.get("crop_set", {})

    derived_ref = outputs["derived_ref_id"]
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", derived_ref)
    assert desc is not None
    assert desc["sub_action"] == "point_crops_scaffold"
    derived_dir = Path(desc["absolute_path"]).parent
    json_sidecars = [p for p in derived_dir.glob("*.json") if p.stem != Path(desc["absolute_path"]).stem]
    assert json_sidecars == []


def test_point_crops_scaffold_image_has_visible_grid_pixels(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor
    from tooling.mapping.transcript_edit.coordinate_lattice import _GRID_MAJOR_COLOR
    from PIL import Image

    handler, ref_id = _make_handler(tmp_path, monkeypatch, image_width=100, image_height=80)
    result = handler({"ref_id": ref_id, "sub_action": "point_crops_scaffold", "params": {}})
    assert result["executed"] is True

    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", result["outputs"]["derived_ref_id"])
    img = Image.open(desc["absolute_path"]).convert("RGB")
    bg = (200, 200, 200)
    major_x = int(round(0.10 * img.width))
    major_x2 = int(round(0.20 * img.width))
    major_y2 = int(round(0.20 * img.height))
    assert img.getpixel((major_x, img.height // 2)) != bg
    assert img.getpixel((major_x2, img.height // 2)) != bg
    assert img.getpixel((img.width // 2, major_y2)) != bg


def test_point_crops_scaffold_has_reference_cell_label_backing(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor
    from tooling.mapping.transcript_edit.coordinate_lattice import _GRID_LABEL_BG_COLOR
    from PIL import Image

    handler, ref_id = _make_handler(tmp_path, monkeypatch, image_width=100, image_height=80)
    result = handler({"ref_id": ref_id, "sub_action": "point_crops_scaffold", "params": {}})
    assert result["executed"] is True
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", result["outputs"]["derived_ref_id"])
    img = Image.open(desc["absolute_path"]).convert("RGB")
    cell_cx = int(0.5 * (img.width / 10))
    cell_cy = int(0.5 * (img.height / 10))
    backed = any(
        img.getpixel((x, y)) == _GRID_LABEL_BG_COLOR
        for x in range(max(0, cell_cx - 6), min(img.width, cell_cx + 7))
        for y in range(max(0, cell_cy - 6), min(img.height, cell_cy + 7))
    )
    assert backed


def test_point_crops_master_overlay_includes_reference_cells(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    crop_set = result["outputs"]["crop_set"]
    lattice = crop_set["coordinate_lattice"]
    assert lattice["reference_cells"] == {"cols": 10, "rows": 10, "cell_labels": True}
    assert crop_set["grid"]["cols"] == 10
    assert crop_set["grid"]["rows"] == 10


def test_point_crops_scaffold_rejects_invalid_show(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops_scaffold",
        "params": {"show": ["pin"]},
    })
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "invalid_transform_params"


# ---------------------------------------------------------------------------
# render_evidence_locators — claim-local rendered evidence
# ---------------------------------------------------------------------------


def test_render_evidence_locators_renders_image_region_and_preserves_lineage(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    locators = [
        {
            "ref_id": ref_id,
            "locator_kind": "image_region",
            "label": "Value A",
            "box_norm": [0.1, 0.2, 0.4, 0.5],
        },
        {
            "ref_id": ref_id,
            "locator_kind": "text_span",
            "label": "Text mention",
            "line_start": 3,
            "line_end": 4,
        },
    ]
    result = handler({"ref_id": ref_id, "sub_action": "render_evidence_locators", "params": {"locators": locators}})

    assert result["executed"] is True, f"Unexpected failure: {result}"
    derived = result["outputs"]["derived_ref_id"]
    assert derived.startswith("image:derived:")
    rendered = result["outputs"]["rendered_evidence_refs"][0]
    assert rendered["source_ref"] == ref_id
    assert rendered["rendered_ref"] == derived
    assert rendered["locator_count"] == 2
    assert rendered["rendered_locator_count"] == 1
    assert rendered["summary_only_locator_count"] == 1
    assert rendered["unsupported_locator_count"] == 0
    assert result["outputs"]["rendered_locators"][0]["label"] == "Value A"
    summary_only = result["outputs"]["summary_only_locators"][0]
    assert summary_only["locator_kind"] == "text_span"
    assert summary_only["reason"] == "summary_only"
    assert result["image_evidence"][0]["ref_id"] == derived


def test_render_evidence_locators_reports_unknown_kind_without_silent_drop(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "render_evidence_locators",
        "params": {"locators": [{"ref_id": ref_id, "locator_kind": "future_kind", "label": "Future"}]},
    })

    assert result["executed"] is True
    assert result["outputs"]["rendered_evidence_refs"][0]["rendered_locator_count"] == 0
    assert result["outputs"]["rendered_evidence_refs"][0]["unsupported_locator_count"] == 1
    assert result["outputs"]["unsupported_locators"][0]["reason"] == "unsupported_locator_kind"


def test_render_evidence_locators_missing_locator_list_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "render_evidence_locators", "params": {}})

    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert result["refusal"]["reason_code"] == "invalid_transform_params"


def test_evidence_locator_schema_rejects_invalid_image_region_geometry():
    with pytest.raises(ValidationError):
        EvidenceLocator(
            ref_id="image:assoc:tx-1:original",
            locator_kind="image_region",
            box_norm=[0.4, 0.2, 0.1, 0.5],
        )


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


# ---------------------------------------------------------------------------
# annotate — box and box_norm both accepted, with adjustments and resolved geometry
# ---------------------------------------------------------------------------

def test_annotate_accepts_pixel_box(tmp_path, monkeypatch):
    """Existing pixel-box annotation surface keeps working unchanged."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "annotate",
        "params": {"annotations": [{"type": "bbox", "box": [10, 10, 50, 40], "color": [255, 0, 0], "width": 2}]},
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    resolved = result["outputs"]["resolved_annotations"]
    assert len(resolved) == 1
    assert resolved[0]["type"] == "bbox"
    geo = resolved[0]["resolved_geometry"]
    assert geo["box"] == [10, 10, 50, 40]
    assert geo["source_width_height"] == [100, 80]
    assert geo["input"] == {"box": [10, 10, 50, 40]}
    # Both forms surfaced — same region in normalized coords.
    assert geo["box_norm"] == [0.1, 0.125, 0.5, 0.5]


def test_annotate_accepts_box_norm(tmp_path, monkeypatch):
    """Per-annotation box_norm is converted to pixels using source dimensions."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "annotate",
        "params": {"annotations": [{"type": "bbox", "box_norm": [0.25, 0.40, 0.55, 0.52], "color": [255, 0, 0]}]},
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    geo = result["outputs"]["resolved_annotations"][0]["resolved_geometry"]
    # 100x80 image: [round(0.25*100), round(0.40*80), round(0.55*100), round(0.52*80)]
    # = [25, 32, 55, 42]  (0.52*80=41.6 → 42 under banker's rounding)
    assert geo["box"] == [25, 32, 55, 42]
    assert geo["input"] == {"box_norm": [0.25, 0.40, 0.55, 0.52]}


def test_annotate_rejects_both_box_and_box_norm(tmp_path, monkeypatch):
    """Providing both box AND box_norm on a single annotation is a retryable error."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "annotate",
        "params": {"annotations": [{"type": "bbox", "box": [0, 0, 50, 40], "box_norm": [0.0, 0.0, 0.5, 0.5]}]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert "repair_hint" in result["outputs"]["error"]


def test_annotate_skips_annotation_without_any_geometry(tmp_path, monkeypatch):
    """An annotation with neither box nor box_norm is silently skipped (prior behavior)."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "annotate",
        "params": {"annotations": [
            {"type": "bbox"},  # no geometry — skipped
            {"type": "bbox", "box_norm": [0.1, 0.1, 0.3, 0.3]},  # rendered
        ]},
    })
    assert result["executed"] is True
    resolved = result["outputs"]["resolved_annotations"]
    assert len(resolved) == 1
    assert resolved[0]["index"] == 1  # the second annotation


def test_annotate_missing_annotations_list_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "annotate", "params": {}})
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


# ---------------------------------------------------------------------------
# zoom — pixel box, normalized box, factor-only, all three
# ---------------------------------------------------------------------------

def test_zoom_with_pixel_box_crops_region(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "zoom", "params": {"box": [10, 10, 60, 50]}})
    assert result["executed"] is True
    w, h = result["outputs"]["width_height"]
    assert w == 50 and h == 40
    geo = result["outputs"]["resolved_geometry"]
    assert geo["box"] == [10, 10, 60, 50]


def test_zoom_with_box_norm_crops_region(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "zoom", "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]}})
    assert result["executed"] is True, f"Unexpected failure: {result}"
    # Top-left quadrant of 100x80 = 50x40
    w, h = result["outputs"]["width_height"]
    assert w == 50 and h == 40
    geo = result["outputs"]["resolved_geometry"]
    assert geo["input"] == {"box_norm": [0.0, 0.0, 0.5, 0.5]}
    assert geo["box"] == [0, 0, 50, 40]


def test_zoom_box_norm_with_factor_crops_then_scales(tmp_path, monkeypatch):
    """zoom with box_norm AND factor: crop the region, then scale up by factor."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "zoom",
        "params": {"box_norm": [0.0, 0.0, 0.5, 0.5], "factor": 2.0},
    })
    assert result["executed"] is True
    # Cropped 50x40, then scaled 2x → 100x80
    w, h = result["outputs"]["width_height"]
    assert w == 100 and h == 80
    geo = result["outputs"]["resolved_geometry"]
    assert geo.get("factor_applied") == 2.0


def test_zoom_factor_only_preserves_existing_behavior(tmp_path, monkeypatch):
    """zoom with only factor (no box/box_norm) scales the whole image."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "zoom", "params": {"factor": 2.0}})
    assert result["executed"] is True
    w, h = result["outputs"]["width_height"]
    assert w == 200 and h == 160
    # No resolved_geometry for factor-only — no box to resolve.
    assert "resolved_geometry" not in result["outputs"]
    assert result["outputs"]["factor_applied"] == 2.0


def test_zoom_default_factor_when_no_params(tmp_path, monkeypatch):
    """zoom with empty params defaults to factor=2.0 (backward compat)."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "zoom", "params": {}})
    assert result["executed"] is True
    w, h = result["outputs"]["width_height"]
    assert w == 200 and h == 160


def test_zoom_rejects_negative_factor(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "zoom", "params": {"factor": -1.0}})
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "repair_hint" in result["outputs"]["error"]


# ---------------------------------------------------------------------------
# Adjustment controls — adjust_norm and adjust_px on crop/zoom/annotate
# ---------------------------------------------------------------------------

def test_crop_with_adjust_norm_expands_region(tmp_path, monkeypatch):
    """adjust_norm expand_x/expand_y grow the box on both sides."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {
            "box_norm": [0.3, 0.3, 0.5, 0.5],
            "adjust_norm": {"expand_x": 0.1, "expand_y": 0.1},
        },
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    geo = result["outputs"]["resolved_geometry"]
    # Original norm [0.3, 0.3, 0.5, 0.5] → after expand_x=0.1, expand_y=0.1:
    # [0.2, 0.2, 0.6, 0.6] → in 100x80 pixels: [20, 16, 60, 48]
    assert geo["box"] == [20, 16, 60, 48]
    assert geo["adjustments_applied"]["adjust_norm"] == {"expand_x": 0.1, "expand_y": 0.1}


def test_crop_with_adjust_norm_shift_moves_region(tmp_path, monkeypatch):
    """adjust_norm shift_x positive moves right, shift_y positive moves down."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {
            "box_norm": [0.1, 0.1, 0.3, 0.3],
            "adjust_norm": {"shift_x": 0.1, "shift_y": 0.05},
        },
    })
    assert result["executed"] is True
    geo = result["outputs"]["resolved_geometry"]
    # [0.1+0.1, 0.1+0.05, 0.3+0.1, 0.3+0.05] = [0.2, 0.15, 0.4, 0.35]
    # 100x80 → [20, 12, 40, 28]
    assert geo["box"] == [20, 12, 40, 28]


def test_crop_with_adjust_px_expands_pixel_box(tmp_path, monkeypatch):
    """adjust_px expand_x grows the pixel box by N on each side."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [30, 30, 50, 50], "adjust_px": {"expand_x": 5, "expand_y": 3}},
    })
    assert result["executed"] is True
    geo = result["outputs"]["resolved_geometry"]
    assert geo["box"] == [25, 27, 55, 53]
    assert geo["adjustments_applied"]["adjust_px"] == {"expand_x": 5, "expand_y": 3}


def test_zoom_applies_adjust_norm_before_crop(tmp_path, monkeypatch):
    """zoom path also honors adjust_norm — single resolver across crop/zoom/annotate."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "zoom",
        "params": {"box_norm": [0.4, 0.4, 0.6, 0.6], "adjust_norm": {"expand_x": 0.05}},
    })
    assert result["executed"] is True
    geo = result["outputs"]["resolved_geometry"]
    # [0.35, 0.4, 0.65, 0.6] in 100x80 → [35, 32, 65, 48]
    assert geo["box"] == [35, 32, 65, 48]


def test_annotate_applies_adjust_norm(tmp_path, monkeypatch):
    """Per-annotation adjust_norm nudges the box before drawing."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{
            "type": "bbox",
            "box_norm": [0.4, 0.4, 0.6, 0.6],
            "adjust_norm": {"shift_x": 0.1},
        }]},
    })
    assert result["executed"] is True
    geo = result["outputs"]["resolved_annotations"][0]["resolved_geometry"]
    # [0.5, 0.4, 0.7, 0.6] in 100x80 → [50, 32, 70, 48]
    assert geo["box"] == [50, 32, 70, 48]


# ---------------------------------------------------------------------------
# Clamping and collapse — boundary behavior
# ---------------------------------------------------------------------------

def test_adjust_px_clamps_to_image_bounds(tmp_path, monkeypatch):
    """Adjustments that push partially outside are clamped (without collapsing)."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    # Image is 100x80; box [80,30,95,50] + expand_x=10 → pre-clamp [70,30,105,50];
    # x2 clamps to 100 → [70,30,100,50] (still positive area).
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [80, 30, 95, 50], "adjust_px": {"expand_x": 10}},
    })
    assert result["executed"] is True
    geo = result["outputs"]["resolved_geometry"]
    assert geo["box"] == [70, 30, 100, 50]


def test_adjust_norm_collapse_is_retryable(tmp_path, monkeypatch):
    """Negative expand that shrinks the box past zero width is a retryable error."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box_norm": [0.4, 0.4, 0.5, 0.5], "adjust_norm": {"expand_x": -0.10}},
    })
    # -0.10 expansion on a 0.1-wide box collapses it: [0.5, 0.4, 0.4, 0.5] → x1>=x2.
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert "repair_hint" in result["outputs"]["error"]


def test_adjust_px_collapse_after_clamp_is_retryable(tmp_path, monkeypatch):
    """A pixel shift that pushes the entire box past image bounds collapses it."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [80, 30, 95, 50], "adjust_px": {"shift_x": 50}},
    })
    # Pre-clamp [130, 30, 145, 50]; post-clamp both x clipped to 100 → [100, 30, 100, 50] (zero width)
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


# ---------------------------------------------------------------------------
# Pixel box is integer-only — fractional/bool/string values must not silently truncate
# ---------------------------------------------------------------------------

def test_crop_fractional_pixel_box_is_retryable(tmp_path, monkeypatch):
    """box: [20.9, 20, 60, 50] would silently truncate to [20, 20, 60, 50] — must be retryable."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20.9, 20, 60, 50]},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    error = result["outputs"]["error"]
    assert "integer" in error["message"]
    assert "20.9" in error["message"]
    # Repair message points fractional intent to box_norm
    assert "box_norm" in error["message"]


def test_crop_negative_fractional_pixel_box_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [-0.5, 0, 50, 40]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_crop_bool_in_pixel_box_is_retryable(tmp_path, monkeypatch):
    """True in a box would coerce to 1 — must not slip through as a pixel value."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [True, 0, 50, 40]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_crop_string_in_pixel_box_is_retryable(tmp_path, monkeypatch):
    """Numeric-looking strings like '20' would parse via int() — must be rejected."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": ["20", 0, 50, 40]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_crop_integer_valued_float_pixel_box_accepted(tmp_path, monkeypatch):
    """JSON often serializes 20 as 20.0 — integer-valued floats must still work."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20.0, 20.0, 60.0, 50.0]},
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    geo = result["outputs"]["resolved_geometry"]
    assert geo["box"] == [20, 20, 60, 50]


def test_annotate_pixel_box_integer_only_per_annotation(tmp_path, monkeypatch):
    """Per-annotation pixel box also enforces integer-only — field error names the annotation index."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{"type": "bbox", "box": [10.5, 10, 50, 40]}]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "annotations[0]" in result["outputs"]["error"]["message"]


# ---------------------------------------------------------------------------
# Fractional adjust_px is retryable — pixel units must be whole, no silent truncation
# ---------------------------------------------------------------------------

def test_adjust_px_fractional_shift_is_retryable(tmp_path, monkeypatch):
    """Fractional adjust_px values would silently truncate to 0 — must be retryable."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20, 20, 60, 50], "adjust_px": {"shift_x": 0.9}},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    error = result["outputs"]["error"]
    assert "integer" in error["message"]
    assert "0.9" in error["message"]
    # Repair hint points the agent to adjust_norm for sub-pixel intent
    assert "adjust_norm" in error["repair_hint"]


def test_adjust_px_fractional_expand_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20, 20, 60, 50], "adjust_px": {"expand_x": 2.5}},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "integer" in result["outputs"]["error"]["message"]


def test_adjust_px_negative_fractional_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20, 20, 60, 50], "adjust_px": {"shift_y": -1.5}},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_adjust_px_integer_valued_float_accepted(tmp_path, monkeypatch):
    """JSON often serializes 5 as 5.0 — integer-valued floats must still work."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20, 20, 60, 50], "adjust_px": {"shift_x": 5.0}},
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    geo = result["outputs"]["resolved_geometry"]
    assert geo["box"] == [25, 20, 65, 50]


def test_adjust_px_bool_is_retryable(tmp_path, monkeypatch):
    """Bool is a subclass of int in Python — but it must not slip through as a pixel value."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20, 20, 60, 50], "adjust_px": {"shift_x": True}},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_adjust_norm_fractional_still_allowed(tmp_path, monkeypatch):
    """Fractional values are the WHOLE POINT of adjust_norm — must not regress under the px rule."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box_norm": [0.2, 0.2, 0.4, 0.4], "adjust_norm": {"shift_x": 0.05, "expand_y": 0.025}},
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    geo = result["outputs"]["resolved_geometry"]
    # shift_x=0.05, expand_y=0.025 → [0.25, 0.175, 0.45, 0.425] → 100x80 px
    assert geo["box"] == [25, 14, 45, 34]


def test_unknown_adjust_key_is_retryable(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [0, 0, 50, 40], "adjust_px": {"rotate": 45}},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "repair_hint" in result["outputs"]["error"]


# ---------------------------------------------------------------------------
# "Both box and box_norm" rejection — explicit retryable error
# ---------------------------------------------------------------------------

def test_crop_rejects_both_box_and_box_norm(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [0, 0, 50, 40], "box_norm": [0.0, 0.0, 0.5, 0.5]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "repair_hint" in result["outputs"]["error"]


# ---------------------------------------------------------------------------
# Resolved geometry round-trips: input form preserved + both forms emitted
# ---------------------------------------------------------------------------

def test_resolved_geometry_includes_both_forms_and_input(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box": [20, 16, 60, 48]}})
    assert result["executed"] is True
    geo = result["outputs"]["resolved_geometry"]
    assert set(geo.keys()) >= {"box", "box_norm", "source_width_height", "input"}
    assert geo["box"] == [20, 16, 60, 48]
    assert geo["box_norm"] == [0.2, 0.2, 0.6, 0.6]
    assert geo["source_width_height"] == [100, 80]
    assert geo["input"] == {"box": [20, 16, 60, 48]}
    # No adjustments applied → key absent
    assert "adjustments_applied" not in geo


# ---------------------------------------------------------------------------
# Mismatched adjustment forms — must be retryable, never silently dropped
# ---------------------------------------------------------------------------

def test_crop_box_with_adjust_norm_is_retryable_mismatch(tmp_path, monkeypatch):
    """Pixel box + normalized adjust = silent intent loss without rejection."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box": [20, 20, 40, 40], "adjust_norm": {"shift_x": 0.05}},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    error = result["outputs"]["error"]
    assert "adjust_norm" in error["message"]
    assert "adjust_px" in error["repair_hint"]


def test_crop_box_norm_with_adjust_px_is_retryable_mismatch(tmp_path, monkeypatch):
    """Normalized box + pixel adjust = silent intent loss without rejection."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "crop",
        "params": {"box_norm": [0.2, 0.2, 0.4, 0.4], "adjust_px": {"shift_x": 5}},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    error = result["outputs"]["error"]
    assert "adjust_px" in error["message"]
    assert "adjust_norm" in error["repair_hint"]


def test_zoom_factor_only_with_adjust_is_retryable(tmp_path, monkeypatch):
    """adjust_* without any box geometry must not be silently dropped by factor-only zoom."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "zoom",
        "params": {"factor": 2.0, "adjust_norm": {"shift_x": 0.1}},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    assert "box" in result["outputs"]["error"]["message"]


def test_annotate_mismatched_adjustment_form_is_retryable(tmp_path, monkeypatch):
    """Per-annotation form mismatch must also be caught — not just top-level."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{
            "type": "bbox",
            "box_norm": [0.1, 0.1, 0.3, 0.3],
            "adjust_px": {"shift_x": 5},
        }]},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert "annotations[0]" in result["outputs"]["error"]["message"]


# ---------------------------------------------------------------------------
# Unknown annotation type — must be retryable, not silently "resolved"
# ---------------------------------------------------------------------------

def test_annotate_unknown_type_is_retryable(tmp_path, monkeypatch):
    """A typo like 'bbbox' must not render zero shapes but still report a resolved annotation."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{"type": "bbbox", "box_norm": [0.2, 0.2, 0.4, 0.4]}]},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    error = result["outputs"]["error"]
    assert "type" in error["message"]
    # Repair hint names the allowed types so the agent can self-correct.
    hint = error["repair_hint"]
    assert "highlight" in hint and "bbox" in hint and "label" in hint


def test_annotate_missing_type_is_retryable(tmp_path, monkeypatch):
    """A missing/empty type field is also rejected with a clear repair hint."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{"box": [10, 10, 50, 40]}]},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert "type" in result["outputs"]["error"]["message"]


# ---------------------------------------------------------------------------
# Label annotations require non-empty text — same class as unknown-type bug
# ---------------------------------------------------------------------------

def test_annotate_label_without_text_is_retryable(tmp_path, monkeypatch):
    """A label annotation with no text field draws nothing — must be retryable, not silently 'resolved'."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{"type": "label", "box_norm": [0.2, 0.2, 0.4, 0.4]}]},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    error = result["outputs"]["error"]
    assert "text" in error["message"]
    assert "label" in error["message"]
    # Repair hint shows the agent how to fix it
    assert "text" in error["repair_hint"]


def test_annotate_label_with_empty_text_is_retryable(tmp_path, monkeypatch):
    """text='' is the same class — draws nothing, must be retryable."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{"type": "label", "box_norm": [0.2, 0.2, 0.4, 0.4], "text": ""}]},
    })
    assert result["executed"] is False
    refusal = result["refusal"]
    assert refusal["retryable"] is True
    assert "text" in result["outputs"]["error"]["message"]


def test_annotate_label_with_whitespace_only_text_is_retryable(tmp_path, monkeypatch):
    """text='   ' renders nothing visually — caught at validation."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{"type": "label", "box_norm": [0.2, 0.2, 0.4, 0.4], "text": "   "}]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_annotate_label_with_valid_text_still_renders(tmp_path, monkeypatch):
    """Positive path: a label with non-empty text renders and shows up in resolved_annotations."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [{
            "type": "label", "box_norm": [0.2, 0.2, 0.4, 0.4], "text": "Section 2",
        }]},
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    resolved = result["outputs"]["resolved_annotations"]
    assert len(resolved) == 1
    assert resolved[0]["type"] == "label"


def test_annotate_bbox_and_highlight_do_not_require_text(tmp_path, monkeypatch):
    """text is only required for label — bbox/highlight remain unaffected by the new rule."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [
            {"type": "bbox", "box_norm": [0.1, 0.1, 0.3, 0.3]},
            {"type": "highlight", "box_norm": [0.4, 0.4, 0.6, 0.6]},
        ]},
    })
    assert result["executed"] is True
    assert len(result["outputs"]["resolved_annotations"]) == 2


def test_annotate_valid_type_with_no_geometry_still_skipped_not_errored(tmp_path, monkeypatch):
    """A valid type without box or box_norm is silently skipped (not an error).

    Pins the prior behavior: annotations missing geometry are skipped by the
    renderer.  The type validation does not regress that contract.
    """
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id, "sub_action": "annotate",
        "params": {"annotations": [
            {"type": "bbox"},  # skipped
            {"type": "bbox", "box_norm": [0.1, 0.1, 0.3, 0.3]},  # rendered
        ]},
    })
    assert result["executed"] is True
    resolved = result["outputs"]["resolved_annotations"]
    assert len(resolved) == 1
    assert resolved[0]["index"] == 1


def test_render_evidence_locators_behavior_unchanged_by_geometry_refactor(tmp_path, monkeypatch):
    """The durable evidence path must not regress under the new resolver wiring."""
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    locators = [{
        "ref_id": ref_id, "locator_kind": "image_region",
        "label": "Value A", "box_norm": [0.1, 0.2, 0.4, 0.5],
    }]
    result = handler({"ref_id": ref_id, "sub_action": "render_evidence_locators", "params": {"locators": locators}})
    assert result["executed"] is True
    rendered = result["outputs"]["rendered_evidence_refs"][0]
    assert rendered["rendered_locator_count"] == 1
    # No resolved_geometry/resolved_annotations on this path — locators are the durable evidence.
    assert "resolved_geometry" not in result["outputs"]
    assert "resolved_annotations" not in result["outputs"]


# ---------------------------------------------------------------------------
# tool_specs mention both geometry forms and adjustment controls
# ---------------------------------------------------------------------------

def test_tool_spec_documents_box_norm_and_adjustments_for_annotate_and_zoom() -> None:
    """Tool spec text must surface both geometry forms and adjustment controls."""
    from domains.mapping.transcript_edit.execution.tool_specs import (
        build_transcript_edit_tool_specs,
    )
    specs = build_transcript_edit_tool_specs()
    spec = next(s for s in specs if s.tool_id == "transform_artifact")
    text = (spec.purpose + " " + spec.expected_request_shape).lower()
    # Both geometry forms accepted
    assert "box_norm" in text
    assert "annotate" in text
    assert "zoom" in text
    # Adjustment controls documented
    assert "adjust_norm" in text
    assert "adjust_px" in text
    for verb in ("expand_x", "expand_y", "shift_x", "shift_y"):
        assert verb in text, f"adjustment verb {verb!r} missing from tool spec"
    # Resolved geometry surfaced
    assert "resolved_geometry" in spec.expected_result_shape.lower()
    # render_evidence_locators kept as the durable path
    assert "render_evidence_locators" in text
    assert "durable" in text
    # Integer-only pixel intent + fractional → box_norm guidance
    assert "integer" in text
    # Label text contract is surfaced — must not look optional any more
    assert "label" in text and "text" in text
    json_shape_text = str(spec.expected_request_json_shape).lower()
    assert "required when type='label'" in json_shape_text or "required for type='label'" in json_shape_text


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


# ---------------------------------------------------------------------------
# point_crops — template crop packets (Brief 1 follow-up)
# ---------------------------------------------------------------------------

def _point_crops_request(
    *,
    alias: str = "parcel_1_tie_bearing",
    point_norm: list[float] | None = None,
    size: str = "medium",
    shape: str = "wide",
    show: list[str] | None = None,
    extra_points: list[dict] | None = None,
) -> dict:
    points = [
        {
            "alias": alias,
            "point_norm": point_norm or [0.42, 0.58],
            "size": size,
            "shape": shape,
        }
    ]
    if extra_points:
        points.extend(extra_points)
    params: dict = {"points": points}
    if show is not None:
        params["show"] = show
    return {"sub_action": "point_crops", "params": params}


def _dict_has_b64_key(value: Any) -> bool:
    if isinstance(value, dict):
        if "b64" in value:
            return True
        return any(_dict_has_b64_key(v) for v in value.values())
    if isinstance(value, list):
        return any(_dict_has_b64_key(v) for v in value)
    return False


def test_point_crops_happy_path_executes(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})

    assert result["executed"] is True, f"Unexpected failure: {result}"
    master = result["outputs"]["derived_ref_id"]
    assert master.startswith("image:derived:")
    assert len(result["image_evidence"]) == 1
    assert result["image_evidence"][0]["ref_id"] == master
    crop_refs = [r for r in result["artifact_refs"] if r != master]
    assert len(crop_refs) == 1
    assert master in result["artifact_refs"]
    assert crop_refs[0] in result["artifact_refs"]


def test_point_crops_outputs_crop_set_geometry_and_alias_map(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})

    crop_set = result["outputs"]["crop_set"]
    assert crop_set.get("review_rows")
    assert crop_set.get("review_lines")
    review_row = crop_set["review_rows"][0]
    assert review_row["letter"] == "A"
    assert review_row["alias"] == "parcel_1_tie_bearing"
    assert review_row["crop_ref"].startswith("image:derived:")
    assert len(review_row["point_norm"]) == 2
    assert len(review_row["box_norm"]) == 4
    assert review_row["size"] == "medium"
    assert review_row["shape"] == "wide"
    assert review_row.get("zoom_factor") is not None
    assert "nearest_major_anchor" in review_row
    assert "offset_from_anchor" in review_row
    assert "+0." in crop_set["review_lines"][0] or "-0." in crop_set["review_lines"][0]
    assert not _dict_has_b64_key(crop_set.get("review_rows"))

    point = crop_set["points"][0]
    assert point["alias"] == "parcel_1_tie_bearing"
    assert point["letter"] == "A"
    assert point["color"] == [255, 200, 0]
    assert point["size"] == "medium"
    assert point["shape"] == "wide"
    assert point["crop_ref"].startswith("image:derived:")
    assert len(point["point_norm"]) == 2
    assert len(point["box_px"]) == 4
    assert len(point["box_norm"]) == 4
    assert point["box_px"][2] > point["box_px"][0]
    assert point["box_px"][3] > point["box_px"][1]


def test_point_crops_labels_and_colors_are_deterministic(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    req = {
        "ref_id": ref_id,
        **_point_crops_request(
            extra_points=[
                {"alias": "second_point", "point_norm": [0.2, 0.3], "size": "small", "shape": "square"},
                {"alias": "third_point", "point_norm": [0.7, 0.4], "size": "large", "shape": "portrait"},
            ]
        ),
    }
    result = handler(req)
    assert result["executed"] is True
    points = result["outputs"]["crop_set"]["points"]
    assert [p["letter"] for p in points] == ["A", "B", "C"]
    assert [p["color"] for p in points] == [[255, 200, 0], [0, 200, 220], [255, 100, 180]]


def test_point_crops_master_and_crop_descriptors_hydrate_with_metadata(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    master_ref = result["outputs"]["derived_ref_id"]
    crop_ref = result["outputs"]["crop_set"]["points"][0]["crop_ref"]

    master_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", master_ref)
    crop_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", crop_ref)
    assert master_desc is not None
    assert crop_desc is not None

    master_meta = master_desc["transform_metadata"]
    assert master_meta["source_ref"] == ref_id
    assert master_meta["point_count"] == 1
    assert master_meta["crop_set"]["points"][0]["alias"] == "parcel_1_tie_bearing"
    assert master_meta["crop_set"]["points"][0]["crop_ref"] == crop_ref
    assert master_meta["crop_set"]["review_rows"][0]["letter"] == "A"
    assert master_meta["crop_set"]["review_lines"]

    import json
    from tooling.mapping.transcript_edit.paths import transcript_edit_derived_images_dir

    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    sidecar_path = next(derived_dir.glob("*_crop_set.json"))
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["review_rows"][0]["letter"] == "A"
    assert sidecar["review_lines"]

    crop_meta = crop_desc["transform_metadata"]
    assert crop_meta["alias"] == "parcel_1_tie_bearing"
    assert crop_meta["letter"] == "A"
    assert crop_meta["crop_set_overlay_ref"] == master_ref
    assert crop_desc["parent_ref_id"] == ref_id
    assert crop_desc["crop_set_overlay_ref"] == master_ref


def test_point_crops_edge_point_shift_clamp_produces_valid_crop(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        **_point_crops_request(point_norm=[0.0, 0.0], size="large", shape="wide"),
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["box_px"][0] == 0
    assert point["box_px"][1] == 0
    assert point["box_px"][2] > point["box_px"][0]
    assert point["box_px"][3] > point["box_px"][1]
    crop_ref = point["crop_ref"]
    crop_row = next(r for r in result["outputs"]["crop_records"] if r["crop_ref"] == crop_ref)
    assert crop_row["box_px"][2] > crop_row["box_px"][0]


def test_point_crops_rejects_more_than_sixteen_points(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    points = [
        {"alias": f"p{i}", "point_norm": [0.1, 0.1], "size": "small", "shape": "square"}
        for i in range(17)
    ]
    result = handler({"ref_id": ref_id, "sub_action": "point_crops", "params": {"points": points}})
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "16" in result["outputs"]["error"]["message"]


def test_point_crops_rejects_duplicate_alias(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {"alias": "dup", "point_norm": [0.2, 0.2], "size": "small", "shape": "square"},
                {"alias": "dup", "point_norm": [0.8, 0.8], "size": "small", "shape": "square"},
            ]
        },
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "Duplicate alias" in result["outputs"]["error"]["message"]


def test_point_crops_rejects_invalid_point_norm(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {"points": [{"alias": "bad", "point_norm": [1.2, 0.5], "size": "small", "shape": "square"}]},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_rejects_invalid_show(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        **_point_crops_request(show=["pin", "opacity"]),
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert "show" in result["outputs"]["error"]["message"]


def test_point_crops_normalizes_mixed_case_size_and_shape(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "mixed_case",
                    "point_norm": [0.5, 0.5],
                    "size": "MeDiUm",
                    "shape": "WiDe",
                }
            ]
        },
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["size"] == "medium"
    assert point["shape"] == "wide"


def test_point_crops_no_b64_in_persisted_descriptors(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor
    from tooling.mapping.transcript_edit.paths import transcript_edit_derived_images_dir

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    master_ref = result["outputs"]["derived_ref_id"]
    crop_ref = result["outputs"]["crop_set"]["points"][0]["crop_ref"]

    for ref in (master_ref, crop_ref):
        desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", ref)
        assert desc is not None
        assert not _dict_has_b64_key(desc)

    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    master_uuid = master_ref.split(":")[-1]
    sidecar = derived_dir / f"{master_uuid}_crop_set.json"
    assert sidecar.is_file()
    sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert not _dict_has_b64_key(sidecar_data)
    assert not _dict_has_b64_key(result["outputs"])


# ---------------------------------------------------------------------------
# point_crops — zoomed per-point crop refs (M1)
# ---------------------------------------------------------------------------

def test_point_crops_applies_default_zoom_by_size(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {"alias": "small_pt", "point_norm": [0.5, 0.5], "size": "small", "shape": "wide"},
                {"alias": "medium_pt", "point_norm": [0.5, 0.5], "size": "medium", "shape": "wide"},
                {"alias": "large_pt", "point_norm": [0.5, 0.5], "size": "large", "shape": "wide"},
            ]
        },
    })
    assert result["executed"] is True
    by_alias = {p["alias"]: p for p in result["outputs"]["crop_set"]["points"]}
    assert by_alias["small_pt"]["zoom_factor"] == 3.0
    assert by_alias["medium_pt"]["zoom_factor"] == 2.25
    assert by_alias["large_pt"]["zoom_factor"] == 1.5
    for alias, expected in [("small_pt", 3.0), ("medium_pt", 2.25), ("large_pt", 1.5)]:
        pt = by_alias[alias]
        uw, uh = pt["unzoomed_width_height"]
        ow, oh = pt["output_width_height"]
        assert ow == max(1, int(round(uw * expected)))
        assert oh == max(1, int(round(uh * expected)))


def test_point_crops_global_zoom_factor_applies_to_all_points(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "zoom_factor": 2.0,
            "points": [
                {"alias": "first", "point_norm": [0.42, 0.58], "size": "medium", "shape": "wide"},
                {"alias": "second", "point_norm": [0.2, 0.3], "size": "small", "shape": "square"},
            ],
        },
    })
    assert result["executed"] is True
    for point in result["outputs"]["crop_set"]["points"]:
        assert point["zoom_factor"] == 2.0


def test_point_crops_per_point_zoom_factor_overrides_global(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "zoom_factor": 2.0,
            "points": [
                {
                    "alias": "override_pt",
                    "point_norm": [0.5, 0.5],
                    "size": "medium",
                    "shape": "wide",
                    "zoom_factor": 3.0,
                },
                {
                    "alias": "global_pt",
                    "point_norm": [0.2, 0.3],
                    "size": "small",
                    "shape": "square",
                },
            ],
        },
    })
    assert result["executed"] is True
    by_alias = {p["alias"]: p for p in result["outputs"]["crop_set"]["points"]}
    assert by_alias["override_pt"]["zoom_factor"] == 3.0
    assert by_alias["global_pt"]["zoom_factor"] == 2.0


def test_point_crops_master_overlay_remains_unzoomed(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    assert result["executed"] is True
    assert result["outputs"]["width_height"] == [100, 200]
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["output_width_height"][0] > point["unzoomed_width_height"][0]


def test_point_crops_geometry_metadata_stays_source_based(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request(point_norm=[0.42, 0.58])})
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["point_norm"] == [0.42, 0.58]
    assert len(point["box_norm"]) == 4
    assert point["box_px"][2] > point["box_px"][0]
    assert point["box_norm"][2] > point["box_norm"][0]


def test_point_crops_persisted_crop_descriptor_records_zoom_metadata(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request(size="small", shape="wide")})
    crop_ref = result["outputs"]["crop_set"]["points"][0]["crop_ref"]
    crop_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", crop_ref)
    assert crop_desc is not None
    meta = crop_desc["transform_metadata"]
    assert meta["zoom_factor"] == 3.0
    assert meta["unzoomed_width_height"]
    assert meta["output_width_height"]
    assert meta["zoom_cap_applied"] is False
    assert crop_desc["width_height"] == meta["output_width_height"]
    assert not _dict_has_b64_key(crop_desc)


def test_point_crops_rejects_invalid_zoom_factor(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    for bad_zoom in (0.5, 7.0):
        result = handler({
            "ref_id": ref_id,
            "sub_action": "point_crops",
            "params": {
                "zoom_factor": bad_zoom,
                "points": [
                    {"alias": "bad", "point_norm": [0.5, 0.5], "size": "small", "shape": "square"},
                ],
            },
        })
        assert result["executed"] is False
        assert result["refusal"]["retryable"] is True
        assert "zoom_factor" in result["outputs"]["error"]["message"]


def test_point_crops_applies_zoom_output_cap(tmp_path, monkeypatch):
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    monkeypatch.setattr(point_crops_mod, "MAX_CROP_OUTPUT_DIMENSION", 20)
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "capped",
                    "point_norm": [0.5, 0.5],
                    "size": "medium",
                    "shape": "wide",
                    "zoom_factor": 6.0,
                }
            ]
        },
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["zoom_cap_applied"] is True
    assert point["requested_zoom_factor"] == 6.0
    assert point["max_output_dimension"] == 20
    assert max(point["output_width_height"]) <= 20


# ---------------------------------------------------------------------------
# point_crops — retuned template sizes (M6)
# ---------------------------------------------------------------------------


class _FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height


def test_point_crop_templates_match_retuned_normalized_sizes() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    expected = {
        "small": {
            "wide": (0.32, 0.18),
            "square": (0.18, 0.18),
            "portrait": (0.18, 0.24),
        },
        "small_plus": {
            "wide": (0.48, 0.13),
            "square": (0.24, 0.24),
            "portrait": (0.24, 0.32),
        },
        "medium": {
            "wide": (0.62, 0.30),
            "square": (0.30, 0.30),
            "portrait": (0.30, 0.42),
        },
        "large": {
            "wide": (0.82, 0.48),
            "square": (0.48, 0.48),
            "portrait": (0.48, 0.82),
        },
    }
    assert point_crops_mod._POINT_CROP_TEMPLATES == expected


def test_point_crop_wide_templates_widened_heights_unchanged() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    templates = point_crops_mod._POINT_CROP_TEMPLATES
    assert templates["small"]["wide"] == (0.32, 0.18)
    assert templates["small_plus"]["wide"] == (0.48, 0.13)
    assert templates["medium"]["wide"] == (0.62, 0.30)
    assert templates["large"]["wide"] == (0.82, 0.48)
    assert templates["small"]["wide"][1] == 0.18
    assert templates["medium"]["wide"][1] == 0.30
    assert templates["large"]["wide"][1] == 0.48
    assert templates["small"]["square"] == (0.18, 0.18)
    assert templates["small_plus"]["wide"][0] > 0.32


def test_point_crop_small_plus_wide_substantially_wider_than_m7() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    width = point_crops_mod._POINT_CROP_TEMPLATES["small_plus"]["wide"][0]
    assert width >= 0.48
    assert width - 0.32 >= 0.15


@pytest.mark.parametrize(
    ("size", "shape"),
    [
        ("small", "wide"),
        ("small", "square"),
        ("small", "portrait"),
        ("small_plus", "wide"),
        ("small_plus", "square"),
        ("small_plus", "portrait"),
        ("medium", "wide"),
        ("medium", "square"),
        ("medium", "portrait"),
        ("large", "wide"),
        ("large", "square"),
        ("large", "portrait"),
    ],
)
def test_point_crop_template_geometry_uses_all_size_shape_pairs(size: str, shape: str) -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    img = _FakeImage(4000, 3000)
    geom = point_crops_mod._compute_single_point_geometry(
        img,
        point_norm=[0.5, 0.5],
        size=size,
        shape=shape,
    )
    norm_w, norm_h = point_crops_mod._POINT_CROP_TEMPLATES[size][shape]
    expected_w = int(round(norm_w * img.width))
    expected_h = int(round(norm_h * img.height))
    actual_w = geom["box_px"][2] - geom["box_px"][0]
    actual_h = geom["box_px"][3] - geom["box_px"][1]
    assert actual_w == expected_w
    assert actual_h == expected_h


def test_point_crop_medium_wide_is_readable_on_large_source() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    geom = point_crops_mod._compute_single_point_geometry(
        _FakeImage(4000, 3000),
        point_norm=[0.42, 0.58],
        size="medium",
        shape="wide",
    )
    width = geom["box_px"][2] - geom["box_px"][0]
    height = geom["box_px"][3] - geom["box_px"][1]
    assert width >= 2400
    assert height >= 850


def test_point_crop_large_template_shift_first_clamps_at_image_edge() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    geom = point_crops_mod._compute_single_point_geometry(
        _FakeImage(4000, 3000),
        point_norm=[0.0, 0.0],
        size="large",
        shape="wide",
    )
    assert geom["box_px"][0] == 0
    assert geom["box_px"][1] == 0
    assert geom["box_px"][2] > geom["box_px"][0]
    assert geom["box_px"][3] > geom["box_px"][1]


def test_point_crop_large_template_still_applies_zoom_output_cap(tmp_path, monkeypatch) -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    monkeypatch.setattr(point_crops_mod, "MAX_CROP_OUTPUT_DIMENSION", 20)
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "large_packet",
                    "point_norm": [0.5, 0.5],
                    "size": "large",
                    "shape": "wide",
                    "zoom_factor": 6.0,
                }
            ]
        },
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["zoom_cap_applied"] is True
    assert max(point["output_width_height"]) <= 20


# ---------------------------------------------------------------------------
# point_crops — small_plus, axis scaling (M7)
# ---------------------------------------------------------------------------


def test_point_crop_invalid_size_rejects_updated_message() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    err = point_crops_mod.validate_point_crops_params(
        {
            "points": [
                {
                    "alias": "bad_size",
                    "point_norm": [0.5, 0.5],
                    "size": "tiny",
                    "shape": "wide",
                }
            ]
        }
    )
    assert err is not None
    assert "small|small_plus|medium|large" in err


def test_point_crop_global_scale_changes_box_size() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    img = _FakeImage(4000, 3000)
    base = point_crops_mod._compute_single_point_geometry(
        img,
        point_norm=[0.5, 0.5],
        size="medium",
        shape="wide",
    )
    scaled = point_crops_mod._compute_single_point_geometry(
        img,
        point_norm=[0.5, 0.5],
        size="medium",
        shape="wide",
        scale_x=1.25,
        scale_y=1.1,
    )
    base_w = base["box_px"][2] - base["box_px"][0]
    base_h = base["box_px"][3] - base["box_px"][1]
    scaled_w = scaled["box_px"][2] - scaled["box_px"][0]
    scaled_h = scaled["box_px"][3] - scaled["box_px"][1]
    assert scaled_w > base_w
    assert scaled_h > base_h
    assert scaled["scale_x"] == 1.25
    assert scaled["scale_y"] == 1.1
    assert scaled["template_width_height_norm"] == [0.62, 0.30]
    assert scaled["resolved_width_height_norm"] == [0.775, 0.33]


def test_point_crop_per_point_scale_overrides_global() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    img = _FakeImage(1000, 800)
    global_geo = point_crops_mod._compute_single_point_geometry(
        img,
        point_norm=[0.5, 0.5],
        size="small",
        shape="square",
        scale_x=2.0,
        scale_y=2.0,
    )
    override_geo = point_crops_mod._compute_single_point_geometry(
        img,
        point_norm=[0.5, 0.5],
        size="small",
        shape="square",
        scale_x=1.0,
        scale_y=1.0,
    )
    global_w = global_geo["box_px"][2] - global_geo["box_px"][0]
    override_w = override_geo["box_px"][2] - override_geo["box_px"][0]
    assert global_w > override_w
    resolved = point_crops_mod.resolve_point_axis_scale(
        global_scale_x=2.0,
        global_scale_y=2.0,
        point_scale_x=1.0,
        point_scale_y=1.0,
    )
    assert resolved == (1.0, 1.0)


def test_point_crop_scale_bounds_reject() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    low = point_crops_mod.validate_point_crops_params(
        {
            "scale_x": 0.25,
            "points": [
                {
                    "alias": "a",
                    "point_norm": [0.5, 0.5],
                    "size": "medium",
                    "shape": "wide",
                }
            ],
        }
    )
    high = point_crops_mod.validate_point_crops_params(
        {
            "points": [
                {
                    "alias": "a",
                    "point_norm": [0.5, 0.5],
                    "size": "medium",
                    "shape": "wide",
                    "scale_y": 3.5,
                }
            ],
        }
    )
    assert low is not None and "0.5" in low and "3.0" in low
    assert high is not None and "scale_y" in high


def test_point_crop_scale_metadata_persists_in_sidecar_and_descriptor(tmp_path, monkeypatch) -> None:
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "scale_x": 1.2,
            "points": [
                {
                    "alias": "cursive_atom",
                    "point_norm": [0.36, 0.63],
                    "size": "small_plus",
                    "shape": "wide",
                    "scale_y": 1.15,
                }
            ],
        },
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["size"] == "small_plus"
    assert point["scale_x"] == 1.2
    assert point["scale_y"] == 1.15
    assert point["template_width_height_norm"] == [0.48, 0.13]
    assert point["resolved_width_height_norm"] == [0.576, 0.1495]

    master_ref = result["outputs"]["derived_ref_id"]
    master_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", master_ref)
    sidecar_point = master_desc["transform_metadata"]["crop_set"]["points"][0]
    assert sidecar_point["scale_x"] == 1.2
    assert sidecar_point["resolved_width_height_norm"] == [0.576, 0.1495]

    crop_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", point["crop_ref"])
    meta = crop_desc["transform_metadata"]
    assert meta["scale_x"] == 1.2
    assert meta["scale_y"] == 1.15
    assert meta["template_width_height_norm"] == [0.48, 0.13]


def test_point_crops_adjust_can_change_only_scale(tmp_path, monkeypatch) -> None:
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = handler({
        "ref_id": source_ref,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "parcel_1_tie_bearing",
                    "point_norm": [0.42, 0.58],
                    "size": "medium",
                    "shape": "wide",
                }
            ]
        },
    })
    prior_master = created["outputs"]["derived_ref_id"]
    prior_point = created["outputs"]["crop_set"]["points"][0]
    prior_w = prior_point["box_px"][2] - prior_point["box_px"][0]
    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "A", "scale_x": 1.5, "scale_y": 1.2}],
    ))
    assert adjusted["executed"] is True
    new_point = adjusted["outputs"]["crop_set"]["points"][0]
    new_w = new_point["box_px"][2] - new_point["box_px"][0]
    assert new_w > prior_w
    assert new_point["scale_x"] == 1.5
    assert new_point["scale_y"] == 1.2
    applied = adjusted["outputs"]["adjustments_applied"][0]
    assert applied["prior_scale_x"] == 1.0
    assert applied["new_scale_x"] == 1.5
    assert applied["prior_scale_y"] == 1.0
    assert applied["new_scale_y"] == 1.2


def test_point_crop_scaled_expansion_still_applies_zoom_output_cap(tmp_path, monkeypatch) -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    monkeypatch.setattr(point_crops_mod, "MAX_CROP_OUTPUT_DIMENSION", 20)
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "large_scaled",
                    "point_norm": [0.5, 0.5],
                    "size": "large",
                    "shape": "wide",
                    "scale_x": 1.5,
                    "scale_y": 1.5,
                    "zoom_factor": 6.0,
                }
            ]
        },
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["zoom_cap_applied"] is True
    assert max(point["output_width_height"]) <= 20


def test_point_crop_widened_medium_wide_stays_readable_with_output_cap(tmp_path, monkeypatch) -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    assert point_crops_mod.MAX_CROP_OUTPUT_DIMENSION == 3200
    handler, ref_id = _make_handler(
        tmp_path,
        monkeypatch,
        image_width=4000,
        image_height=3000,
    )
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "clause_wide",
                    "point_norm": [0.5, 0.5],
                    "size": "medium",
                    "shape": "wide",
                }
            ]
        },
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point.get("zoom_cap_applied") is True
    assert max(point["output_width_height"]) == 3200
    assert point["requested_zoom_factor"] == 2.25
    assert point["max_output_dimension"] == 3200
    assert point["zoom_factor"] >= 1.2


# ---------------------------------------------------------------------------
# point_crops — targeting ergonomics (M10)
# ---------------------------------------------------------------------------


def test_point_crop_small_plus_wide_is_atom_line_scoped() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    wide = point_crops_mod._POINT_CROP_TEMPLATES["small_plus"]["wide"]
    assert wide == (0.48, 0.13)
    assert wide[1] < 0.24


def test_point_crop_explicit_dimensions_override_template() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    img = _FakeImage(4000, 3000)
    explicit_geo = point_crops_mod._compute_single_point_geometry(
        img,
        point_norm=[0.45, 0.56],
        size="medium",
        shape="wide",
        width_norm=0.48,
        height_norm=0.13,
    )
    assert explicit_geo["explicit_width_height_norm"] == [0.48, 0.13]
    assert explicit_geo["template_width_height_norm"] == [0.62, 0.30]
    assert explicit_geo["resolved_width_height_norm"] == [0.48, 0.13]
    assert explicit_geo["box_px"][3] - explicit_geo["box_px"][1] == int(round(0.13 * 3000))


def test_point_crop_explicit_dimensions_reject_partial_pair() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    err = point_crops_mod.validate_point_crops_params(
        {
            "points": [
                {
                    "alias": "partial_dims",
                    "point_norm": [0.5, 0.5],
                    "size": "small_plus",
                    "shape": "wide",
                    "width_norm": 0.48,
                }
            ]
        }
    )
    assert err is not None
    assert "both width_norm and height_norm" in err


def test_point_crop_explicit_dimensions_reject_out_of_bounds() -> None:
    import tooling.mapping.transcript_edit.point_crops as point_crops_mod

    err = point_crops_mod.validate_point_crops_params(
        {
            "points": [
                {
                    "alias": "too_tall",
                    "point_norm": [0.5, 0.5],
                    "size": "small_plus",
                    "shape": "wide",
                    "width_norm": 0.48,
                    "height_norm": 1.5,
                }
            ]
        }
    )
    assert err is not None
    assert "height_norm" in err


def test_point_crops_default_show_omits_box_but_still_creates_crop_refs(tmp_path, monkeypatch) -> None:
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    assert result["executed"] is True
    assert result["outputs"]["crop_set"]["show"] == ["pin", "letter"]
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["crop_ref"].startswith("image:derived:")
    assert point["box_norm"][2] > point["box_norm"][0]


def test_point_crops_explicit_show_includes_box(tmp_path, monkeypatch) -> None:
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request(show=["pin", "letter", "box"])})
    assert result["outputs"]["crop_set"]["show"] == ["pin", "letter", "box"]
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", result["outputs"]["derived_ref_id"])
    from PIL import Image

    img = Image.open(desc["absolute_path"])
    point = result["outputs"]["crop_set"]["points"][0]
    cx = (point["box_px"][0] + point["box_px"][2]) // 2
    cy = (point["box_px"][1] + point["box_px"][3]) // 2
    assert img.getpixel((cx, cy)) != (200, 200, 200)


def test_point_crops_explicit_dimensions_persist_in_sidecar(tmp_path, monkeypatch) -> None:
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "parcel1_tie_bearing",
                    "point_norm": [0.45, 0.56],
                    "size": "small_plus",
                    "shape": "wide",
                    "width_norm": 0.48,
                    "height_norm": 0.13,
                }
            ]
        },
    })
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["explicit_width_height_norm"] == [0.48, 0.13]
    assert point["resolved_width_height_norm"] == [0.48, 0.13]


def test_point_crops_adjust_preserves_and_updates_explicit_dimensions(tmp_path, monkeypatch) -> None:
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = handler({
        "ref_id": source_ref,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "parcel1_tie_bearing",
                    "point_norm": [0.45, 0.56],
                    "size": "small_plus",
                    "shape": "wide",
                    "width_norm": 0.48,
                    "height_norm": 0.13,
                }
            ]
        },
    })
    prior_master = created["outputs"]["derived_ref_id"]
    prior_point = created["outputs"]["crop_set"]["points"][0]
    prior_h = prior_point["box_px"][3] - prior_point["box_px"][1]
    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "A", "width_norm": 0.48, "height_norm": 0.18}],
    ))
    assert adjusted["executed"] is True
    new_point = adjusted["outputs"]["crop_set"]["points"][0]
    new_h = new_point["box_px"][3] - new_point["box_px"][1]
    assert new_h > prior_h
    assert new_point["explicit_width_height_norm"] == [0.48, 0.18]
    applied = adjusted["outputs"]["adjustments_applied"][0]
    assert applied["prior_width_height_norm"] == [0.48, 0.13]
    assert applied["new_width_height_norm"] == [0.48, 0.18]


def test_point_crops_master_overlay_pin_renders_at_point_norm(tmp_path, monkeypatch) -> None:
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({
        "ref_id": ref_id,
        **_point_crops_request(point_norm=[0.42, 0.58], size="small_plus", shape="wide"),
    })
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", result["outputs"]["derived_ref_id"])
    from PIL import Image

    img = Image.open(desc["absolute_path"])
    px = int(round(0.42 * 100))
    py = int(round(0.58 * 80))
    assert img.getpixel((px, py)) != (200, 200, 200)


# ---------------------------------------------------------------------------
# point_crops — master overlay grid + legend (M2)
# ---------------------------------------------------------------------------

def test_point_crops_master_overlay_includes_grid_metadata(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    assert result["executed"] is True
    assert result["outputs"]["width_height"] == [100, 200]
    crop_set = result["outputs"]["crop_set"]
    lattice = crop_set["coordinate_lattice"]
    assert lattice["major_step_norm"] == 0.10
    assert lattice["minor_step_norm"] == 0.025
    assert lattice["coordinate_space"] == "normalized_source_image"
    assert lattice["label_placement"]["major_x"] == ["top", "bottom"]
    assert crop_set["overlay_role"] == "point_crop_master"
    assert result["outputs"]["overlay_role"] == "point_crop_master"
    grid = crop_set["grid"]
    assert grid["enabled"] is True
    assert grid["major_step_norm"] == 0.10
    assert grid["minor_step_norm"] == 0.025
    assert grid["coordinate_space"] == "source_image_norm"
    assert grid["major_line"]["width"] == 2
    assert result["outputs"]["crop_set"]["box_render"]["fill_alpha"] == 48
    assert result["outputs"]["crop_set"]["pin_render"]["radius_px"] == 12
    assert result["outputs"]["crop_set"]["pin_render"]["halo_padding_px"] == 5
    assert result["outputs"]["crop_set"]["letter_render"]["font_size_px"] == 14
    assert lattice["label_style"]["background"] is True
    assert result["outputs"]["crop_set"]["show"] == ["pin", "letter"]
    legend = result["outputs"]["crop_set"]["legend"]
    assert legend["size_colors"]["small"] == [220, 70, 70]
    assert legend["size_colors"]["small_plus"] == [245, 166, 35]
    assert legend["size_colors"]["medium"] == [70, 130, 220]
    assert legend["size_colors"]["large"] == [80, 180, 100]
    assert legend["size_labels"]["small_plus"] == "small+"


def test_point_crops_master_overlay_renders_dense_grid_on_image_area(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    master_ref = result["outputs"]["derived_ref_id"]
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", master_ref)
    assert desc is not None
    from PIL import Image

    img = Image.open(desc["absolute_path"])
    bg = (200, 200, 200)
    # Minor grid at x=2 (0.025) and major at x=10 (0.10) on a 100px-wide source.
    assert img.getpixel((2, 10)) != bg
    assert img.getpixel((10, 10)) != bg
    # Major margin labels with backgrounds on all four edges near x=10 / y=20 (0.20).
    assert img.getpixel((12, 2)) != bg
    assert img.getpixel((12, 78)) != bg
    assert img.getpixel((2, 22)) != bg
    assert img.getpixel((88, 22)) != bg
    assert img.height == 200


def test_point_crops_master_overlay_renders_box_fill_and_letter(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request(show=["pin", "letter", "box"])})
    master_ref = result["outputs"]["derived_ref_id"]
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", master_ref)
    from PIL import Image

    img = Image.open(desc["absolute_path"])
    point = result["outputs"]["crop_set"]["points"][0]
    cx = (point["box_px"][0] + point["box_px"][2]) // 2
    cy = (point["box_px"][1] + point["box_px"][3]) // 2
    bg = (200, 200, 200)
    assert img.getpixel((cx, cy)) != bg
    from tooling.mapping.transcript_edit.point_crops import _letter_position_near_pin, _pin_center_px

    cx, cy = _pin_center_px(point)
    lx, ly = _letter_position_near_pin(cx, cy, img_w=100, img_h=80)
    assert img.getpixel((lx + 1, ly + 1)) != bg
    assert img.getpixel((cx, cy)) != bg


def test_point_crops_default_show_remains_pin_and_letter_only(tmp_path, monkeypatch) -> None:
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    assert result["outputs"]["crop_set"]["show"] == ["pin", "letter"]


def test_point_crops_master_overlay_box_renders_when_requested(tmp_path, monkeypatch) -> None:
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request(show=["pin", "letter", "box"])})
    point = result["outputs"]["crop_set"]["points"][0]
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", result["outputs"]["derived_ref_id"])
    from PIL import Image

    img = Image.open(desc["absolute_path"])
    bg = (200, 200, 200)
    edge = (
        point["box_px"][0] + 2,
        point["box_px"][1] + 2,
    )
    assert img.getpixel(edge) != bg
    assert result["outputs"]["crop_set"]["box_render"]["outline_width"] == 4


def test_point_crops_overlay_render_metadata_has_no_paths_or_b64(tmp_path, monkeypatch) -> None:
    import json

    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    dumped = json.dumps(result["outputs"]["crop_set"]).lower()
    assert "b64" not in dumped
    assert "absolute_path" not in dumped
    assert "c:\\" not in dumped


def test_reference_overlay_preserves_lattice_label_style(tmp_path, monkeypatch) -> None:
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, "sub_action": "reference_overlay", "params": {}})
    desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", result["outputs"]["derived_ref_id"])
    lattice = desc["transform_metadata"]["overlay"]["coordinate_lattice"]
    assert lattice["label_style"]["background"] is True
    assert lattice["major_step_norm"] == 0.10


def test_point_crops_per_point_crop_refs_exclude_grid(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    point = result["outputs"]["crop_set"]["points"][0]
    crop_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", point["crop_ref"])
    assert crop_desc is not None
    assert crop_desc["width_height"] == point["output_width_height"]
    assert "grid" not in crop_desc["transform_metadata"]
    assert crop_desc["width_height"][1] < 200


def test_point_crops_view_includes_grid_and_legend(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    viewed = handler({
        "ref_id": created["outputs"]["derived_ref_id"],
        "sub_action": "point_crops_view",
        "params": {"filter": {"letters": ["A"]}},
    })
    assert viewed["executed"] is True
    assert viewed["outputs"]["width_height"][1] == 200
    crop_set = viewed["outputs"]["crop_set"]
    assert crop_set["grid"]["enabled"] is True
    assert crop_set["coordinate_lattice"]["major_step_norm"] == 0.10
    assert crop_set["overlay_role"] == "point_crop_view"
    assert viewed["outputs"]["overlay_role"] == "point_crop_view"
    assert crop_set["legend"]["size_colors"]["medium"] == [70, 130, 220]


def test_point_crops_adjust_preserves_prior_zoom(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = handler({
        "ref_id": source_ref,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "parcel_1_tie_bearing",
                    "point_norm": [0.42, 0.58],
                    "size": "medium",
                    "shape": "wide",
                    "zoom_factor": 2.5,
                }
            ]
        },
    })
    prior_master = created["outputs"]["derived_ref_id"]
    prior_zoom = created["outputs"]["crop_set"]["points"][0]["zoom_factor"]
    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "A", "shift_norm": [0.01, 0.0]}],
    ))
    assert adjusted["executed"] is True
    new_point = adjusted["outputs"]["crop_set"]["points"][0]
    assert new_point["zoom_factor"] == prior_zoom


def test_point_crops_adjust_can_change_zoom_factor(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    prior_master = created["outputs"]["derived_ref_id"]
    prior_b = next(p for p in created["outputs"]["crop_set"]["points"] if p["letter"] == "B")
    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "B", "zoom_factor": 4.0}],
    ))
    assert adjusted["executed"] is True
    new_b = next(p for p in adjusted["outputs"]["crop_set"]["points"] if p["letter"] == "B")
    assert new_b["zoom_factor"] == 4.0
    assert new_b["crop_ref"] != prior_b["crop_ref"]
    applied = adjusted["outputs"]["adjustments_applied"][0]
    assert applied["prior_zoom_factor"] == prior_b["zoom_factor"]
    assert applied["new_zoom_factor"] == 4.0


# ---------------------------------------------------------------------------
# point_crops_adjust — reuse and revision (Brief 2)
# ---------------------------------------------------------------------------

def _create_two_point_crop_set(handler, source_ref: str) -> dict:
    result = handler({
        "ref_id": source_ref,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "parcel_1_tie_bearing",
                    "point_norm": [0.42, 0.58],
                    "size": "medium",
                    "shape": "wide",
                },
                {
                    "alias": "parcel_1_acreage",
                    "point_norm": [0.2, 0.3],
                    "size": "small",
                    "shape": "square",
                },
            ],
            "show": ["pin", "box", "letter"],
        },
    })
    assert result["executed"] is True, f"Unexpected failure: {result}"
    return result


def _point_crops_adjust_request(*, master_ref: str, adjust: list[dict], show: list[str] | None = None) -> dict:
    params: dict = {"adjust": adjust}
    if show is not None:
        params["show"] = show
    return {
        "ref_id": master_ref,
        "sub_action": "point_crops_adjust",
        "params": params,
    }


def test_point_crops_adjust_by_letter(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    prior_master = created["outputs"]["derived_ref_id"]
    prior_b = created["outputs"]["crop_set"]["points"][1]
    prior_b_norm = list(prior_b["point_norm"])
    prior_review_b = created["outputs"]["crop_set"]["review_rows"][1]

    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "B", "shift_norm": [0.05, 0.0]}],
    ))
    assert adjusted["executed"] is True, f"Unexpected failure: {adjusted}"
    new_master = adjusted["outputs"]["derived_ref_id"]
    assert new_master != prior_master
    assert adjusted["outputs"]["previous_crop_set_overlay_ref"] == prior_master
    assert adjusted["outputs"]["adjustment_source_ref"] == prior_master
    assert len(adjusted["image_evidence"]) == 1
    assert adjusted["image_evidence"][0]["ref_id"] == new_master

    new_b = next(p for p in adjusted["outputs"]["crop_set"]["points"] if p["letter"] == "B")
    assert new_b["crop_ref"] != prior_b["crop_ref"]
    assert new_b["point_norm"][0] > prior_b_norm[0]
    assert adjusted["outputs"]["adjustments_applied"][0]["target"] == {"letter": "B"}
    review_b = next(r for r in adjusted["outputs"]["crop_set"]["review_rows"] if r["letter"] == "B")
    assert review_b["point_norm"] == new_b["point_norm"]
    assert review_b["offset_from_anchor"] != prior_review_b["offset_from_anchor"]
    assert adjusted["outputs"]["crop_set"]["coordinate_lattice"]["major_step_norm"] == 0.10
    assert adjusted["outputs"]["crop_set"]["overlay_role"] == "point_crop_master"
    assert adjusted["outputs"]["overlay_role"] == "point_crop_master"


def test_point_crops_adjust_by_alias(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    prior_master = created["outputs"]["derived_ref_id"]
    prior_a = created["outputs"]["crop_set"]["points"][0]

    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"alias": "parcel_1_tie_bearing", "size": "large", "shape": "wide"}],
    ))
    assert adjusted["executed"] is True
    new_a = next(
        p for p in adjusted["outputs"]["crop_set"]["points"] if p["alias"] == "parcel_1_tie_bearing"
    )
    assert new_a["size"] == "large"
    assert new_a["shape"] == "wide"
    assert new_a["box_px"] != prior_a["box_px"]
    assert adjusted["outputs"]["adjustments_applied"][0]["target"] == {"alias": "parcel_1_tie_bearing"}


def test_point_crops_adjust_shift_norm_clamps_at_bounds(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = handler({
        "ref_id": source_ref,
        **_point_crops_request(point_norm=[0.05, 0.5], alias="edge_point"),
    })
    prior_master = created["outputs"]["derived_ref_id"]

    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "A", "shift_norm": [-0.2, 0.0]}],
    ))
    assert adjusted["executed"] is True
    point = adjusted["outputs"]["crop_set"]["points"][0]
    assert point["point_norm"][0] == 0.0
    assert point["box_px"][2] > point["box_px"][0]


def test_point_crops_adjust_creates_new_refs_and_preserves_old_hydration(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor

    handler, source_ref = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    created = _create_two_point_crop_set(handler, source_ref)
    prior_master = created["outputs"]["derived_ref_id"]
    prior_crop = created["outputs"]["crop_set"]["points"][0]["crop_ref"]

    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "A", "shift_norm": [0.01, 0.0]}],
    ))
    new_master = adjusted["outputs"]["derived_ref_id"]
    new_crop = adjusted["outputs"]["crop_set"]["points"][0]["crop_ref"]
    assert new_master != prior_master
    assert new_crop != prior_crop

    assert _load_derived_image_descriptor("d1", "tx-1", "ws-1", prior_master) is not None
    assert _load_derived_image_descriptor("d1", "tx-1", "ws-1", prior_crop) is not None


def test_point_crops_adjust_sidecar_and_descriptors_include_lineage(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor
    from tooling.mapping.transcript_edit.paths import transcript_edit_derived_images_dir

    handler, source_ref = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    created = _create_two_point_crop_set(handler, source_ref)
    prior_master = created["outputs"]["derived_ref_id"]

    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "B", "size": "Large", "shape": "Square"}],
    ))
    new_master = adjusted["outputs"]["derived_ref_id"]
    sidecar = json.loads(
        (
            transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
            / f"{new_master.split(':')[-1]}_crop_set.json"
        ).read_text(encoding="utf-8")
    )
    assert sidecar["previous_crop_set_overlay_ref"] == prior_master
    assert sidecar["adjustments_applied"][0]["new_size"] == "large"
    assert sidecar["adjustments_applied"][0]["new_shape"] == "square"

    master_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", new_master)
    crop_desc = _load_derived_image_descriptor(
        "d1", "tx-1", "ws-1", adjusted["outputs"]["crop_set"]["points"][1]["crop_ref"]
    )
    assert master_desc is not None and crop_desc is not None
    assert master_desc["transform_metadata"]["previous_crop_set_overlay_ref"] == prior_master
    assert crop_desc["transform_metadata"]["previous_crop_set_overlay_ref"] == prior_master
    assert crop_desc["previous_crop_set_overlay_ref"] == prior_master
    assert not _dict_has_b64_key(master_desc)
    assert not _dict_has_b64_key(crop_desc)
    assert not _dict_has_b64_key(adjusted["outputs"])


def test_point_crops_adjust_rejects_invalid_letter(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    result = handler(_point_crops_adjust_request(
        master_ref=created["outputs"]["derived_ref_id"],
        adjust=[{"letter": "Z", "shift_norm": [0.01, 0.0]}],
    ))
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_adjust_rejects_invalid_alias(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    result = handler(_point_crops_adjust_request(
        master_ref=created["outputs"]["derived_ref_id"],
        adjust=[{"alias": "missing_alias", "size": "large", "shape": "wide"}],
    ))
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_adjust_rejects_both_letter_and_alias(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    result = handler(_point_crops_adjust_request(
        master_ref=created["outputs"]["derived_ref_id"],
        adjust=[{"letter": "A", "alias": "parcel_1_tie_bearing", "shift_norm": [0.01, 0.0]}],
    ))
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_adjust_rejects_missing_selector(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    result = handler(_point_crops_adjust_request(
        master_ref=created["outputs"]["derived_ref_id"],
        adjust=[{"shift_norm": [0.01, 0.0]}],
    ))
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_adjust_rejects_empty_adjust_list(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    result = handler({
        "ref_id": created["outputs"]["derived_ref_id"],
        "sub_action": "point_crops_adjust",
        "params": {"adjust": []},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_adjust_rejects_no_op_adjustment(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    point = created["outputs"]["crop_set"]["points"][0]
    result = handler(_point_crops_adjust_request(
        master_ref=created["outputs"]["derived_ref_id"],
        adjust=[{
            "letter": "A",
            "point_norm": point["point_norm"],
            "size": point["size"],
            "shape": point["shape"],
        }],
    ))
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_adjust_rejects_invalid_shift_norm(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    result = handler(_point_crops_adjust_request(
        master_ref=created["outputs"]["derived_ref_id"],
        adjust=[{"letter": "A", "shift_norm": [0.01]}],
    ))
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_tool_spec_documents_point_crops() -> None:
    from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs

    specs = build_transcript_edit_tool_specs()
    spec = next(s for s in specs if s.tool_id == "transform_artifact")
    text = (
        spec.purpose
        + " "
        + spec.expected_request_shape
        + " "
        + spec.expected_result_shape
        + " "
        + str(spec.expected_request_json_shape)
        + " "
        + str(spec.example_request)
    ).lower()
    assert "point_crops" in text
    assert "point_norm" in text
    assert "small" in text and "medium" in text and "large" in text
    assert "wide" in text and "portrait" in text and "square" in text
    assert "pin" in text and "box" in text and "letter" in text
    assert "crop_set" in text or "crop_records" in text
    assert spec.example_request.get("sub_action") == "point_crops"
    assert "point_crops_adjust" in text
    assert "point_crops_view" in text
    assert "shift_norm" in text
    assert "delegate_subtask" in text or "context_refs" in text
    assert "previous_crop_set_overlay_ref" in text or "adjustment_source_ref" in text


def test_point_crops_accepts_bounded_graph_ref(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "parcel_1_tie_bearing",
                    "point_norm": [0.42, 0.58],
                    "size": "medium",
                    "shape": "wide",
                    "graph_ref": {
                        "item_id": "parcel_1_description",
                        "covered_unit_id": "p1_tie_bearing",
                    },
                }
            ]
        },
    })
    assert result["executed"] is True
    assert result["outputs"]["crop_set"]["points"][0]["graph_ref"]["item_id"] == "parcel_1_description"


def test_point_crops_rejects_nested_graph_ref(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({
        "ref_id": ref_id,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "bad_graph",
                    "point_norm": [0.5, 0.5],
                    "size": "small",
                    "shape": "square",
                    "graph_ref": {"item_id": {"nested": True}},
                }
            ]
        },
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


def test_point_crops_view_renders_all_points(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    prior_master = created["outputs"]["derived_ref_id"]
    viewed = handler({"ref_id": prior_master, "sub_action": "point_crops_view", "params": {}})
    assert viewed["executed"] is True
    assert viewed["outputs"]["derived_ref_id"] != prior_master
    assert viewed["artifact_refs"] == [viewed["outputs"]["derived_ref_id"]]
    assert len(viewed["image_evidence"]) == 1
    assert len(viewed["outputs"]["crop_set"]["points"]) == 2


def test_point_crops_view_filters_by_letters(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    viewed = handler({
        "ref_id": created["outputs"]["derived_ref_id"],
        "sub_action": "point_crops_view",
        "params": {"filter": {"letters": ["B"]}},
    })
    assert viewed["executed"] is True
    assert len(viewed["outputs"]["crop_set"]["points"]) == 1
    assert viewed["outputs"]["crop_set"]["points"][0]["letter"] == "B"
    assert len(viewed["outputs"]["crop_set"]["review_rows"]) == 1
    assert viewed["outputs"]["crop_set"]["review_rows"][0]["letter"] == "B"
    assert viewed["outputs"]["crop_set"]["review_lines"][0].startswith("B ")


def test_point_crops_view_filters_by_aliases(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    viewed = handler({
        "ref_id": created["outputs"]["derived_ref_id"],
        "sub_action": "point_crops_view",
        "params": {"filter": {"aliases": ["parcel_1_acreage"]}},
    })
    assert viewed["executed"] is True
    assert len(viewed["outputs"]["crop_set"]["points"]) == 1
    assert viewed["outputs"]["crop_set"]["points"][0]["alias"] == "parcel_1_acreage"


def test_point_crops_view_rejects_invalid_filter_target(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    created = _create_two_point_crop_set(handler, source_ref)
    result = handler({
        "ref_id": created["outputs"]["derived_ref_id"],
        "sub_action": "point_crops_view",
        "params": {"filter": {"letters": ["Z"]}},
    })
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True


# ---------------------------------------------------------------------------
# point_crops — nested root projection metadata (M3)
# ---------------------------------------------------------------------------

def _approx_norm(actual: list[float], expected: list[float], *, tol: float = 0.03) -> None:
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected):
        assert abs(float(got) - float(want)) <= tol


def test_point_crops_on_source_records_root_equal_to_local(tmp_path, monkeypatch):
    handler, ref_id = _make_handler(tmp_path, monkeypatch)
    result = handler({"ref_id": ref_id, **_point_crops_request()})
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["projection_available"] is True
    assert point["root_source_ref"] == ref_id
    assert point["local_source_ref"] == ref_id
    assert point["local_point_norm"] == point["point_norm"]
    assert point["root_point_norm"] == point["point_norm"]
    assert point["root_box_norm"] == point["box_norm"]


def test_point_crops_inside_crop_projects_to_root_source(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    cropped = handler({
        "ref_id": source_ref,
        "sub_action": "crop",
        "params": {"box_norm": [0.25, 0.25, 0.75, 0.75]},
    })
    assert cropped["executed"] is True
    crop_ref = cropped["outputs"]["derived_ref_id"]
    nested = handler({
        "ref_id": crop_ref,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "nested_center",
                    "point_norm": [0.5, 0.5],
                    "size": "small",
                    "shape": "square",
                }
            ]
        },
    })
    assert nested["executed"] is True
    point = nested["outputs"]["crop_set"]["points"][0]
    assert point["projection_available"] is True
    assert point["root_source_ref"] == source_ref
    assert point["local_source_ref"] == crop_ref
    _approx_norm(point["root_point_norm"], [0.5, 0.5])
    assert point["root_box_norm"][0] >= 0.24
    assert point["root_box_norm"][2] <= 0.76


def test_point_crops_inside_per_point_crop_composes_projection_chain(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    outer = handler({
        "ref_id": source_ref,
        **_point_crops_request(point_norm=[0.5, 0.5], alias="outer_point"),
    })
    assert outer["executed"] is True
    outer_crop_ref = outer["outputs"]["crop_set"]["points"][0]["crop_ref"]
    inner = handler({
        "ref_id": outer_crop_ref,
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "inner_point",
                    "point_norm": [0.5, 0.5],
                    "size": "small",
                    "shape": "square",
                }
            ]
        },
    })
    assert inner["executed"] is True
    point = inner["outputs"]["crop_set"]["points"][0]
    assert point["projection_available"] is True
    assert point["root_source_ref"] == source_ref
    assert len(point["projection_chain"]) >= 1
    assert point["projection_chain"][0]["sub_action"] == "point_crops_crop"
    _approx_norm(point["root_point_norm"], [0.5, 0.5], tol=0.08)


def test_point_crops_projection_metadata_persists_in_descriptors(tmp_path, monkeypatch):
    from tooling.mapping.transcript_edit.artifact_hydration import _load_derived_image_descriptor
    from tooling.mapping.transcript_edit.paths import transcript_edit_derived_images_dir

    handler, source_ref = _make_handler(tmp_path, monkeypatch, d="d1", tx="tx-1", ws="ws-1")
    cropped = handler({
        "ref_id": source_ref,
        "sub_action": "crop",
        "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]},
    })
    nested = handler({
        "ref_id": cropped["outputs"]["derived_ref_id"],
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "persist_probe",
                    "point_norm": [0.5, 0.5],
                    "size": "medium",
                    "shape": "wide",
                }
            ]
        },
    })
    master_ref = nested["outputs"]["derived_ref_id"]
    crop_ref = nested["outputs"]["crop_set"]["points"][0]["crop_ref"]
    master_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", master_ref)
    crop_desc = _load_derived_image_descriptor("d1", "tx-1", "ws-1", crop_ref)
    assert master_desc is not None
    assert crop_desc is not None
    master_point = master_desc["transform_metadata"]["crop_set"]["points"][0]
    assert master_point["projection_available"] is True
    assert master_point["root_source_ref"] == source_ref
    assert crop_desc["root_source_ref"] == source_ref
    assert crop_desc["transform_metadata"]["root_point_norm"]
    derived_dir = transcript_edit_derived_images_dir("d1", "tx-1", "ws-1")
    sidecar = derived_dir / f"{master_ref.split(':')[-1]}_crop_set.json"
    sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_data["points"][0]["local_point_norm"]
    assert not _dict_has_b64_key(master_desc)
    assert not _dict_has_b64_key(crop_desc)


def test_point_crops_on_unsupported_parent_marks_projection_unavailable(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    overlay = handler({"ref_id": source_ref, "sub_action": "reference_overlay", "params": {}})
    assert overlay["executed"] is True
    result = handler({"ref_id": overlay["outputs"]["derived_ref_id"], **_point_crops_request()})
    assert result["executed"] is True
    point = result["outputs"]["crop_set"]["points"][0]
    assert point["projection_available"] is False
    assert point["projection_unavailable_reason"]
    assert "reference_overlay" in point["projection_unavailable_reason"]


def test_point_crops_adjust_recomputes_root_projection(tmp_path, monkeypatch):
    handler, source_ref = _make_handler(tmp_path, monkeypatch)
    cropped = handler({
        "ref_id": source_ref,
        "sub_action": "crop",
        "params": {"box_norm": [0.25, 0.25, 0.75, 0.75]},
    })
    nested = handler({
        "ref_id": cropped["outputs"]["derived_ref_id"],
        "sub_action": "point_crops",
        "params": {
            "points": [
                {
                    "alias": "adjust_probe",
                    "point_norm": [0.4, 0.4],
                    "size": "small",
                    "shape": "square",
                }
            ]
        },
    })
    prior_master = nested["outputs"]["derived_ref_id"]
    prior_root = nested["outputs"]["crop_set"]["points"][0]["root_point_norm"]
    adjusted = handler(_point_crops_adjust_request(
        master_ref=prior_master,
        adjust=[{"letter": "A", "shift_norm": [0.1, 0.0]}],
    ))
    assert adjusted["executed"] is True
    new_point = adjusted["outputs"]["crop_set"]["points"][0]
    assert new_point["projection_available"] is True
    assert new_point["root_point_norm"] != prior_root
    assert new_point["root_point_norm"][0] > prior_root[0]


def test_delegate_batch_parser_accepts_projected_crop_ref() -> None:
    import json

    from harness.runtime.orchestration.action_plan_parser import parse_action_plan_response
    from harness.runtime.orchestration.subtasks.batch_policy import delegate_subtask_tool_batch_policy
    from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE

    crop_ref = "image:derived:crop-a"
    plan = parse_action_plan_response(
        json.dumps(
            {
                "actions": [
                    {
                        "alias": "obs_p1_tie_bearing",
                        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                        "action_inputs": {
                            "profile": "harness.observation",
                            "task": "Read the source-visible bearing text in this crop.",
                            "context_refs": [crop_ref],
                        },
                    }
                ],
                "rationale": "Delegate using crop ref from projected crop-set summary.",
            }
        ),
        available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
        tool_batch_policies={DELEGATE_SUBTASK_ACTION_TYPE: delegate_subtask_tool_batch_policy()},
    )
    assert plan.actions[0].action_inputs["context_refs"] == [crop_ref]
