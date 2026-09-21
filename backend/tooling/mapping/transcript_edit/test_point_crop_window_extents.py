"""MAPDEP-BR-039: point-anchored window_extents_norm acceptance (A–L)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from tooling.mapping.transcript_edit.point_crop_set_projection import project_point_crop_set_summary
from tooling.mapping.transcript_edit.point_crop_window_extents import (
    WindowExtentsError,
    resolve_window_extents_geometry,
    validate_window_extents_object,
)
from tooling.mapping.transcript_edit.point_crops import (
    compute_point_crops,
    validate_point_crops_params,
)


def _synthetic_img(*, width: int = 200, height: int = 100, color=(220, 220, 220)):
    from PIL import Image

    return Image.new("RGB", (width, height), color=color)


def _line_wrap_img(*, width: int = 200, height: int = 100):
    """Dark ink band extending right and down from an anchor (geometry coverage only)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    # Horizontal phrase to the right of (0.40, 0.40), then a wrap line below.
    ax, ay = int(0.40 * width), int(0.40 * height)
    draw.rectangle([ax, ay - 4, ax + 70, ay + 4], fill=(20, 20, 20))
    draw.rectangle([ax + 10, ay + 10, ax + 55, ay + 18], fill=(20, 20, 20))
    return img


# --- A / B / C / K: pure geometry ---


def test_a_asymmetric_window_resolves_expected_box_with_point_inside() -> None:
    img = _synthetic_img()
    extents = validate_window_extents_object(
        {"left": 0.08, "right": 0.22, "up": 0.03, "down": 0.09},
        field_prefix="window_extents_norm",
    )
    geo = resolve_window_extents_geometry(img, point_norm=[0.50, 0.50], extents=extents)
    assert geo["box_norm"] == [0.42, 0.47, 0.72, 0.59]
    assert geo["requested_box_norm"] == [0.42, 0.47, 0.72, 0.59]
    assert geo["source_edge_clipping"] == []
    x, y = geo["point_norm"]
    bx = geo["box_norm"]
    assert bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3]
    assert geo["geometry_form"] == "window_extents"


def test_b_symmetric_extents_without_template() -> None:
    img = _synthetic_img()
    extents = validate_window_extents_object(
        {"left": 0.10, "right": 0.10, "up": 0.05, "down": 0.05},
        field_prefix="window_extents_norm",
    )
    geo = resolve_window_extents_geometry(img, point_norm=[0.50, 0.50], extents=extents)
    assert geo["box_norm"] == [0.4, 0.45, 0.6, 0.55]
    assert "size" not in geo


def test_c_right_and_bottom_edge_clamp_report_clipping() -> None:
    img = _synthetic_img(width=100, height=80)
    extents = validate_window_extents_object(
        {"left": 0.05, "right": 0.30, "up": 0.04, "down": 0.25},
        field_prefix="window_extents_norm",
    )
    geo = resolve_window_extents_geometry(img, point_norm=[0.90, 0.85], extents=extents)
    assert geo["requested_box_norm"] == [0.85, 0.81, 1.2, 1.1]
    assert geo["box_norm"][2] == 1.0
    assert geo["box_norm"][3] == 1.0
    # Left/up sides preserved from request (not shift-clamped); pixel round-trip may nudge slightly.
    assert geo["box_norm"][0] == pytest.approx(0.85, abs=5e-3)
    assert geo["box_norm"][1] == pytest.approx(0.81, abs=5e-3)
    assert set(geo["source_edge_clipping"]) == {"right", "down"}
    x, y = geo["point_norm"]
    bx = geo["box_norm"]
    assert bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3]


def test_k_line_wrap_extra_right_and_down_covers_ink() -> None:
    img = _line_wrap_img()
    extents = validate_window_extents_object(
        {"left": 0.02, "right": 0.40, "up": 0.05, "down": 0.22},
        field_prefix="window_extents_norm",
    )
    geo = resolve_window_extents_geometry(img, point_norm=[0.40, 0.40], extents=extents)
    crop = img.crop(tuple(geo["box"]))
    # Packet coverage: both ink bands fall inside the resolved crop.
    assert any(crop.getpixel((x, 4))[0] < 80 for x in range(0, crop.width, 4))
    wrap_y = int(0.14 * img.height)  # ~ relative to crop top
    # Find dark pixels in lower portion of crop (wrap line).
    lower = crop.crop((0, crop.height // 2, crop.width, crop.height))
    assert any(lower.getpixel((x, y))[0] < 80 for x in range(0, lower.width, 3) for y in range(0, lower.height, 3))
    assert geo["box_norm"][2] - geo["box_norm"][0] > geo["box_norm"][3] - geo["box_norm"][1]


# --- D / E: validation ---


@pytest.mark.parametrize(
    "raw,needle",
    [
        ({"left": 0.1, "right": 0.1, "up": 0.1}, "missing"),
        ({"left": -0.1, "right": 0.1, "up": 0.1, "down": 0.1}, ">="),
        ({"left": 0.0, "right": 0.0, "up": 0.1, "down": 0.1}, "horizontal"),
        ({"left": 0.1, "right": 0.1, "up": 0.0, "down": 0.0}, "vertical"),
        ({"left": "0.1", "right": 0.1, "up": 0.1, "down": 0.1}, "finite"),
        ({"left": True, "right": 0.1, "up": 0.1, "down": 0.1}, "finite"),
        ({"left": float("nan"), "right": 0.1, "up": 0.1, "down": 0.1}, "finite"),
        ({"left": float("inf"), "right": 0.1, "up": 0.1, "down": 0.1}, "finite"),
    ],
)
def test_d_invalid_extents_refuse(raw: dict[str, Any], needle: str) -> None:
    with pytest.raises(WindowExtentsError) as exc:
        validate_window_extents_object(raw, field_prefix="window_extents_norm")
    assert needle in str(exc.value).lower()


def test_e_conflicting_extents_and_template_refuse() -> None:
    err = validate_point_crops_params(
        {
            "points": [
                {
                    "alias": "x",
                    "point_norm": [0.5, 0.5],
                    "size": "medium",
                    "shape": "wide",
                    "window_extents_norm": {"left": 0.1, "right": 0.1, "up": 0.05, "down": 0.05},
                }
            ]
        }
    )
    assert err is not None
    assert "cannot combine" in err


def test_e_conflicting_extents_and_trim_refuse() -> None:
    err = validate_point_crops_params(
        {
            "points": [
                {
                    "alias": "x",
                    "point_norm": [0.5, 0.5],
                    "window_extents_norm": {"left": 0.1, "right": 0.1, "up": 0.05, "down": 0.05},
                    "trim_to_text_block": True,
                }
            ]
        }
    )
    assert err is not None
    assert "cannot combine" in err


def _extents_point(**extra: Any) -> dict[str, Any]:
    row = {
        "alias": "extent-pt",
        "point_norm": [0.5, 0.5],
        "window_extents_norm": {"left": 0.1, "right": 0.1, "up": 0.05, "down": 0.05},
    }
    row.update(extra)
    return row


def test_conflict_global_scale_x_refuses_with_extents() -> None:
    err = validate_point_crops_params(
        {"scale_x": 1.2, "points": [_extents_point()]}
    )
    assert err is not None
    assert "scale_x" in err
    assert "window_extents_norm" in err


def test_conflict_global_scale_y_refuses_with_extents() -> None:
    err = validate_point_crops_params(
        {"scale_y": 0.8, "points": [_extents_point()]}
    )
    assert err is not None
    assert "scale_y" in err


def test_conflict_global_scale_null_keys_still_refuse_with_extents() -> None:
    err = validate_point_crops_params(
        {"scale_x": None, "scale_y": None, "points": [_extents_point()]}
    )
    assert err is not None
    assert "scale_x" in err or "scale_y" in err


def test_conflict_global_trim_null_key_refuses_with_extents() -> None:
    err = validate_point_crops_params(
        {"trim_to_text_block": None, "points": [_extents_point()]}
    )
    assert err is not None
    assert "trim_to_text_block" in err


def test_extents_plus_trim_axis_null_still_refuses_by_key_presence() -> None:
    err = validate_point_crops_params(
        {"trim_axis": None, "points": [_extents_point()]}
    )
    assert err is not None
    assert "trim_axis" in err
    assert "window_extents_norm" in err


def test_template_only_trim_axis_null_validates_as_unset() -> None:
    params = {
        "trim_axis": None,
        "points": [
            {
                "alias": "t",
                "point_norm": [0.42, 0.58],
                "size": "medium",
                "shape": "wide",
            }
        ],
    }
    assert validate_point_crops_params(params) is None


def test_template_only_invalid_trim_axis_still_refuses() -> None:
    err = validate_point_crops_params(
        {
            "trim_axis": "y",
            "points": [
                {
                    "alias": "t",
                    "point_norm": [0.42, 0.58],
                    "size": "medium",
                    "shape": "wide",
                }
            ],
        }
    )
    assert err is not None
    assert "trim_axis" in err
    assert "must be x" in err


@pytest.mark.parametrize(
    "conflict_key,conflict_value",
    [
        ("scale_x", None),
        ("scale_y", None),
        ("size", None),
        ("shape", None),
        ("width_norm", None),
        ("height_norm", None),
        ("trim_to_text_block", None),
        ("trim_axis", None),
        ("trim_padding_norm", None),
        ("size", ""),
        ("scale_x", 1.1),
    ],
)
def test_conflict_per_point_null_or_present_keys_refuse_cleanly(
    conflict_key: str,
    conflict_value: Any,
) -> None:
    err = validate_point_crops_params(
        {"points": [_extents_point(**{conflict_key: conflict_value})]}
    )
    assert err is not None, f"expected refuse for {conflict_key}={conflict_value!r}"
    assert "cannot combine" in err
    assert conflict_key in err


def test_extents_zoom_remains_accepted_and_applied() -> None:
    img = _synthetic_img(width=100, height=80)
    params = {
        "zoom_factor": 1.5,
        "points": [_extents_point()],
        "show": ["pin", "letter"],
    }
    assert validate_point_crops_params(params) is None
    out = compute_point_crops(img, params)
    pt = out["per_point"][0]
    assert pt["geometry_form"] == "window_extents"
    assert pt["zoom_factor"] == pytest.approx(1.5, abs=1e-4)


def test_mixed_template_and_extents_packet_valid_without_global_scale() -> None:
    params = {
        "points": [
            {
                "alias": "tmpl",
                "point_norm": [0.3, 0.3],
                "size": "medium",
                "shape": "wide",
            },
            _extents_point(alias="ext"),
        ]
    }
    assert validate_point_crops_params(params) is None
    img = _synthetic_img()
    out = compute_point_crops(img, params)
    forms = {p["alias"]: p["geometry_form"] for p in out["per_point"]}
    assert forms["tmpl"] == "template"
    assert forms["ext"] == "window_extents"


def test_mixed_packet_refuses_global_scale() -> None:
    err = validate_point_crops_params(
        {
            "scale_x": 1.1,
            "points": [
                {
                    "alias": "tmpl",
                    "point_norm": [0.3, 0.3],
                    "size": "medium",
                    "shape": "wide",
                },
                _extents_point(alias="ext"),
            ],
        }
    )
    assert err is not None
    assert "scale_x" in err


def test_legacy_template_only_global_scaling_unchanged() -> None:
    params = {
        "scale_x": 1.25,
        "scale_y": 0.9,
        "points": [
            {
                "alias": "t",
                "point_norm": [0.42, 0.58],
                "size": "medium",
                "shape": "wide",
            }
        ],
    }
    assert validate_point_crops_params(params) is None
    assert params["scale_x"] == pytest.approx(1.25)
    assert params["scale_y"] == pytest.approx(0.9)
    img = _synthetic_img(width=100, height=80)
    out = compute_point_crops(img, params)
    pt = out["per_point"][0]
    assert pt["geometry_form"] == "template"
    assert pt["scale_x"] == pytest.approx(1.25)
    assert pt["scale_y"] == pytest.approx(0.9)


def test_e_zero_on_one_side_allowed_when_axis_positive() -> None:
    extents = validate_window_extents_object(
        {"left": 0.0, "right": 0.2, "up": 0.0, "down": 0.1},
        field_prefix="window_extents_norm",
    )
    assert extents["left"] == 0.0
    img = _synthetic_img()
    geo = resolve_window_extents_geometry(img, point_norm=[0.5, 0.5], extents=extents)
    assert geo["box_norm"][0] == pytest.approx(0.5, abs=1e-3)


# --- J: template parity ---


def test_j_template_geometry_unchanged_vs_prior_centered_path() -> None:
    img = _synthetic_img(width=100, height=80)
    params = {
        "points": [
            {
                "alias": "t",
                "point_norm": [0.42, 0.58],
                "size": "medium",
                "shape": "wide",
            }
        ],
        "show": ["pin", "letter"],
    }
    assert validate_point_crops_params(params) is None
    out = compute_point_crops(img, params)
    pt = out["per_point"][0]
    # medium/wide template is (0.62, 0.30) before edge shift-clamp around center.
    assert pt["geometry_form"] == "template"
    assert pt["size"] == "medium"
    assert pt["shape"] == "wide"
    assert "window_extents_norm" not in pt
    assert pt["resolved_width_height_norm"][0] == pytest.approx(0.62, abs=0.02)
    assert pt["resolved_width_height_norm"][1] == pytest.approx(0.30, abs=0.02)


def test_compute_point_crops_extents_path_records_clipping_metadata() -> None:
    img = _synthetic_img(width=100, height=80)
    params = {
        "points": [
            {
                "alias": "edge",
                "point_norm": [0.92, 0.10],
                "window_extents_norm": {"left": 0.05, "right": 0.20, "up": 0.08, "down": 0.05},
            }
        ],
        "show": ["pin", "letter", "box"],
    }
    assert validate_point_crops_params(params) is None
    out = compute_point_crops(img, params)
    pt = out["per_point"][0]
    assert pt["geometry_form"] == "window_extents"
    assert "right" in pt["source_edge_clipping"]
    assert pt["requested_box_norm"][2] > 1.0
    assert pt["box_norm"][2] <= 1.0
    assert "render_warnings" not in out["overlay"]


# --- Integration F / G / H / I / L via transform handler ---


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    return root


def _png_bytes(width: int = 200, height: int = 100, *, color=(200, 200, 200)) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_handler(tmp_path, monkeypatch, *, image_bytes: bytes | None = None):
    import config.paths as paths_mod
    import tooling.mapping.transcript_edit.paths as te_paths_mod
    from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler

    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)

    d, tx, ws = "d1", "tx-1", "ws-1"
    img_path = root / "images" / "src.png"
    img_path.parent.mkdir(parents=True, exist_ok=True)
    img_path.write_bytes(image_bytes or _png_bytes())

    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True, exist_ok=True)
    (assoc_dir / f"assoc_{d}.json").write_text(
        json.dumps(
            {
                "associations": [
                    {
                        "transcription_id": tx,
                        "metadata": {
                            "images": {
                                "original_path": str(img_path),
                                "processed_path": str(img_path),
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    handler = make_transform_artifact_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    return handler, f"image:assoc:{tx}:original", img_path


def test_f_g_i_l_adjust_extents_lineage_and_canonical_untouched(tmp_path, monkeypatch) -> None:
    from tooling.mapping.transcript_edit.derived_image_descriptor import (
        load_derived_image_descriptor_dict as _load,
    )

    handler, source_ref, img_path = _make_handler(tmp_path, monkeypatch)
    before = img_path.read_bytes()

    created = handler(
        {
            "ref_id": source_ref,
            "sub_action": "point_crops",
            "params": {
                "points": [
                    {
                        "alias": "wrap-target",
                        "point_norm": [0.40, 0.40],
                        "size": "small_plus",
                        "shape": "wide",
                        "target_atom_id": "atom-1",
                        "target_hint": "candidate token",
                    }
                ],
                "show": ["pin", "letter"],
            },
        }
    )
    assert created["executed"] is True, created
    prior_master = created["outputs"]["derived_ref_id"]
    prior_crop = created["outputs"]["crop_set"]["points"][0]["crop_ref"]
    prior_bytes = Path(_load("d1", "tx-1", "ws-1", prior_crop)["absolute_path"]).read_bytes()

    # F: convert template → explicit extents
    converted = handler(
        {
            "ref_id": prior_master,
            "sub_action": "point_crops_adjust",
            "params": {
                "adjust": [
                    {
                        "alias": "wrap-target",
                        "window_extents_norm": {
                            "left": 0.05,
                            "right": 0.25,
                            "up": 0.04,
                            "down": 0.12,
                        },
                    }
                ],
                "show": ["pin", "letter", "box"],
            },
        }
    )
    assert converted["executed"] is True, converted
    mid_master = converted["outputs"]["derived_ref_id"]
    mid_pt = converted["outputs"]["crop_set"]["points"][0]
    assert mid_pt["geometry_form"] == "window_extents"
    assert mid_pt["window_extents_norm"]["right"] == 0.25
    assert mid_pt["target_atom_id"] == "atom-1"
    assert mid_pt["crop_ref"] != prior_crop
    assert converted["outputs"]["previous_crop_set_overlay_ref"] == prior_master
    # Old crop bytes unchanged
    assert Path(_load("d1", "tx-1", "ws-1", prior_crop)["absolute_path"]).read_bytes() == prior_bytes

    # F continued: revise extents
    revised = handler(
        {
            "ref_id": mid_master,
            "sub_action": "point_crops_adjust",
            "params": {
                "adjust": [
                    {
                        "alias": "wrap-target",
                        "window_extents_norm": {
                            "left": 0.05,
                            "right": 0.30,
                            "up": 0.04,
                            "down": 0.18,
                        },
                    }
                ]
            },
        }
    )
    assert revised["executed"] is True, revised
    revised_pt = revised["outputs"]["crop_set"]["points"][0]
    assert revised_pt["window_extents_norm"]["right"] == 0.30
    assert revised_pt["window_extents_norm"]["down"] == 0.18
    assert revised_pt["point_norm"] == mid_pt["point_norm"]

    # G: move anchor, retain extents → window moves with point
    moved = handler(
        {
            "ref_id": revised["outputs"]["derived_ref_id"],
            "sub_action": "point_crops_adjust",
            "params": {
                "adjust": [{"alias": "wrap-target", "point_norm": [0.55, 0.45]}],
            },
        }
    )
    assert moved["executed"] is True, moved
    moved_pt = moved["outputs"]["crop_set"]["points"][0]
    assert moved_pt["point_norm"] == [0.55, 0.45]
    assert moved_pt["window_extents_norm"] == revised_pt["window_extents_norm"]
    assert moved_pt["box_norm"][0] == pytest.approx(0.50, abs=1e-3)  # 0.55 - 0.05
    assert moved_pt["box_norm"][2] == pytest.approx(0.85, abs=1e-3)  # 0.55 + 0.30

    # I: projection / review / key lines preserve extents + target
    summary = project_point_crop_set_summary(moved["outputs"])
    assert summary is not None
    sp = summary["points"][0]
    assert sp["geometry_form"] == "window_extents"
    assert sp["window_extents_norm"]["right"] == 0.3
    assert sp["target_atom_id"] == "atom-1"
    review = moved["outputs"]["crop_set"]["review_rows"][0]
    assert review["geometry_form"] == "window_extents"
    assert "extents" in moved["outputs"]["crop_set"]["review_lines"][0] or "window_extents" in str(
        review.get("window_extents_norm")
    )

    # L: canonical source untouched
    assert img_path.read_bytes() == before
    assert mid_master.startswith("image:derived:")
    assert moved_pt["crop_ref"].startswith("image:derived:")


def test_h_show_box_paints_extents_bounds(tmp_path, monkeypatch) -> None:
    from tooling.mapping.transcript_edit.derived_image_descriptor import (
        load_derived_image_descriptor_dict as _load,
    )
    from tooling.mapping.transcript_edit.point_crops import _BOX_FILL_ALPHA
    from PIL import Image

    handler, source_ref, _ = _make_handler(tmp_path, monkeypatch)
    default = handler(
        {
            "ref_id": source_ref,
            "sub_action": "point_crops",
            "params": {
                "points": [
                    {
                        "alias": "e",
                        "point_norm": [0.5, 0.5],
                        "window_extents_norm": {
                            "left": 0.12,
                            "right": 0.12,
                            "up": 0.08,
                            "down": 0.08,
                        },
                    }
                ]
            },
        }
    )
    with_box = handler(
        {
            "ref_id": source_ref,
            "sub_action": "point_crops",
            "params": {
                "points": [
                    {
                        "alias": "e",
                        "point_norm": [0.5, 0.5],
                        "window_extents_norm": {
                            "left": 0.12,
                            "right": 0.12,
                            "up": 0.08,
                            "down": 0.08,
                        },
                    }
                ],
                "show": ["pin", "letter", "box"],
            },
        }
    )
    assert default["outputs"]["crop_set"]["show"] == ["pin", "letter"]
    assert with_box["outputs"]["crop_set"]["show"] == ["pin", "letter", "box"]
    assert "render_warnings" not in with_box["outputs"]["crop_set"]
    point = with_box["outputs"]["crop_set"]["points"][0]
    img = Image.open(_load("d1", "tx-1", "ws-1", with_box["outputs"]["derived_ref_id"])["absolute_path"])
    default_img = Image.open(
        _load("d1", "tx-1", "ws-1", default["outputs"]["derived_ref_id"])["absolute_path"]
    )
    sample = (point["box_px"][0] + 6, point["box_px"][1] + 6)
    master_px = default_img.getpixel(sample)
    col = tuple(int(v) for v in point["color"][:3])
    blended = tuple(
        int(master_px[i] + (_BOX_FILL_ALPHA / 255) * (col[i] - master_px[i])) for i in range(3)
    )
    assert img.getpixel(sample) != master_px
    assert all(abs(img.getpixel(sample)[i] - blended[i]) <= 2 for i in range(3))
