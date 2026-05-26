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

    point = result["outputs"]["crop_set"]["points"][0]
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
