"""STORAGE-BR-005: derived-image recipe contract (path-free, deterministic)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tooling.mapping.transcript_edit.derived_image_recipe import (
    RENDERER_ID,
    SCHEMA_VERSION,
    RecipeValidationError,
    assert_recipe_descriptor_coherence,
    assert_recipe_output_identity,
    build_derived_image_recipe,
    recipe_fingerprint,
    validate_derived_image_recipe,
)
from tooling.mapping.transcript_edit.derived_image_rendering import (
    RENDERER_ID as RENDERING_RENDERER_ID,
    compute_image_identity,
    pillow_version,
    render_generic_derived_image,
)

_HEX_A = "a" * 64
_HEX_B = "b" * 64
_HEX_C = "c" * 64
_HEX_D = "d" * 64
_SOURCE_REF = "image:assoc:tx-1:original"
_DERIVED_REF = "image:derived:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _save_png(path: Path, *, color: tuple[int, int, int] = (10, 20, 30), size=(40, 30)) -> Path:
    Image.new("RGB", size, color=color).save(path, format="PNG")
    return path


def _build_from_paths(
    source_path: Path,
    *,
    sub_action: str = "crop",
    params: dict[str, Any] | None = None,
    source_ref: str = _SOURCE_REF,
) -> tuple[dict[str, Any], Any]:
    params = params if params is not None else {"box_norm": [0.0, 0.0, 0.5, 1.0]}
    src = compute_image_identity(path=source_path)
    rendered = render_generic_derived_image(
        source_path, sub_action, params, source_ref_id=source_ref
    )
    out = compute_image_identity(image=rendered.image)
    recipe = build_derived_image_recipe(
        source_ref_id=source_ref,
        source_content_sha256=src["content_sha256"],
        source_pixel_sha256=src["pixel_sha256"],
        source_mode=src["mode"],
        source_width_height=src["width_height"],
        sub_action=sub_action,
        params=params,
        pillow_version=pillow_version(),
        expected_pixel_sha256=out["pixel_sha256"],
        expected_mode=out["mode"],
        expected_width_height=out["width_height"],
    )
    return recipe, rendered.image


def _collect_keys(obj: Any, *, acc: set[str] | None = None) -> set[str]:
    acc = acc if acc is not None else set()
    if type(obj) is dict:
        for key, value in obj.items():
            if type(key) is str:
                acc.add(key)
            _collect_keys(value, acc=acc)
    elif type(obj) is list:
        for item in obj:
            _collect_keys(item, acc=acc)
    return acc


def test_renderer_id_shared() -> None:
    assert RENDERER_ID == RENDERING_RENDERER_ID == "transcript_edit.pillow.v1"
    assert SCHEMA_VERSION == "transcript_edit.derived_image_recipe.v1"


def test_build_validate_roundtrip_and_fingerprint_prefix(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    recipe, _img = _build_from_paths(source)
    validated = validate_derived_image_recipe(recipe)
    assert validated == recipe
    fp = recipe_fingerprint(recipe)
    assert fp.startswith("sha256:")
    assert len(fp) == len("sha256:") + 64
    assert fp == recipe_fingerprint(validated)


def test_identical_inputs_same_fingerprint(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    params = {"box_norm": [0.0, 0.0, 0.5, 1.0]}
    a, _ = _build_from_paths(source, params=params)
    b, _ = _build_from_paths(source, params=copy.deepcopy(params))
    assert recipe_fingerprint(a) == recipe_fingerprint(b)
    assert a["transform"]["params"] == b["transform"]["params"]


def test_source_content_sha256_change_alters_fingerprint_same_pixel(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    recipe, _ = _build_from_paths(source)
    mutated = copy.deepcopy(recipe)
    # Keep pixel identity; change only content digest (encoding-independent field).
    assert mutated["source"]["pixel_sha256"]
    other = _HEX_D if mutated["source"]["content_sha256"] != _HEX_D else _HEX_C
    mutated["source"]["content_sha256"] = other
    mutated = validate_derived_image_recipe(mutated)
    assert mutated["source"]["pixel_sha256"] == recipe["source"]["pixel_sha256"]
    assert recipe_fingerprint(mutated) != recipe_fingerprint(recipe)


def test_transform_params_change_alters_fingerprint(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    a, _ = _build_from_paths(source, params={"box_norm": [0.0, 0.0, 0.5, 1.0]})
    b, _ = _build_from_paths(source, params={"box_norm": [0.0, 0.0, 0.6, 1.0]})
    assert recipe_fingerprint(a) != recipe_fingerprint(b)


def test_path_bearing_and_forbidden_keys_refuse(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    recipe, _ = _build_from_paths(source)
    for forbidden in ("path", "dossier_id", "workspace_id", "run_id", "absolute_path"):
        bad = copy.deepcopy(recipe)
        bad["transform"]["params"] = {**bad["transform"]["params"], forbidden: "/tmp/x"}
        with pytest.raises(RecipeValidationError) as exc:
            validate_derived_image_recipe(bad)
        assert exc.value.code == "recipe_forbidden_field"


def test_non_json_native_nan_refuses(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    recipe, _ = _build_from_paths(source)
    bad = copy.deepcopy(recipe)
    bad["transform"]["params"] = {"box_norm": [0.0, 0.0, 0.5, float("nan")]}
    with pytest.raises(RecipeValidationError) as exc:
        validate_derived_image_recipe(bad)
    assert exc.value.code == "params_not_json_native"


def test_assert_recipe_descriptor_coherence_success_and_mismatches(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    params = {"box_norm": [0.0, 0.0, 0.5, 1.0]}
    recipe, _ = _build_from_paths(source, params=params)
    fp = recipe_fingerprint(recipe)

    ok = assert_recipe_descriptor_coherence(
        recipe=recipe,
        recipe_fingerprint_value=fp,
        parent_ref_id=_SOURCE_REF,
        sub_action="crop",
        params=params,
    )
    assert ok["source"]["ref_id"] == _SOURCE_REF

    with pytest.raises(RecipeValidationError) as parent_exc:
        assert_recipe_descriptor_coherence(
            recipe=recipe,
            recipe_fingerprint_value=fp,
            parent_ref_id=_DERIVED_REF,
            sub_action="crop",
            params=params,
        )
    assert parent_exc.value.code == "recipe_descriptor_mismatch"

    with pytest.raises(RecipeValidationError) as sub_exc:
        assert_recipe_descriptor_coherence(
            recipe=recipe,
            recipe_fingerprint_value=fp,
            parent_ref_id=_SOURCE_REF,
            sub_action="zoom",
            params=params,
        )
    assert sub_exc.value.code == "recipe_descriptor_mismatch"

    with pytest.raises(RecipeValidationError) as params_exc:
        assert_recipe_descriptor_coherence(
            recipe=recipe,
            recipe_fingerprint_value=fp,
            parent_ref_id=_SOURCE_REF,
            sub_action="crop",
            params={"box_norm": [0.0, 0.0, 0.9, 1.0]},
        )
    assert params_exc.value.code == "recipe_descriptor_mismatch"

    with pytest.raises(RecipeValidationError) as fp_exc:
        assert_recipe_descriptor_coherence(
            recipe=recipe,
            recipe_fingerprint_value="sha256:" + _HEX_A,
            parent_ref_id=_SOURCE_REF,
            sub_action="crop",
            params=params,
        )
    assert fp_exc.value.code == "recipe_fingerprint_mismatch"


def test_assert_recipe_output_identity_mismatch_refuses(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    recipe, image = _build_from_paths(source)
    out = compute_image_identity(image=image)
    assert_recipe_output_identity(
        recipe,
        pixel_sha256=out["pixel_sha256"],
        mode=out["mode"],
        width_height=out["width_height"],
    )
    with pytest.raises(RecipeValidationError) as exc:
        assert_recipe_output_identity(
            recipe,
            pixel_sha256=_HEX_B,
            mode=out["mode"],
            width_height=out["width_height"],
        )
    assert exc.value.code == "recipe_output_mismatch"


def test_recipe_json_has_no_path_dossier_workspace_run_keys(tmp_path: Path) -> None:
    source = _save_png(tmp_path / "src.png")
    recipe, _ = _build_from_paths(source)
    keys = {k.lower() for k in _collect_keys(recipe)}
    forbidden_substrings = ("path", "dossier", "workspace", "run")
    for key in keys:
        for token in forbidden_substrings:
            assert token not in key, f"forbidden identity key {key!r}"
    # Serialized form must also stay path-free for persistence.
    blob = json.dumps(recipe, sort_keys=True)
    assert "dossier_id" not in blob
    assert "workspace_id" not in blob
    assert "run_id" not in blob
    assert "absolute_path" not in blob
