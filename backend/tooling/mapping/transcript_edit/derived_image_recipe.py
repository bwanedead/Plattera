"""Strict candidate recipe contract for transcript-edit derived images.

Audit-only identity shape: JSON-native, path-free, allowlisted fields.
No filesystem I/O. Does not write recipes into production descriptors.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from .derived_image_rendering import GENERIC_SUB_ACTIONS, RENDERER_ID

SCHEMA_VERSION = "transcript_edit.derived_image_recipe.v1"
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_REF_PREFIXES = ("image:assoc:", "image:derived:")

_TOP_KEYS = frozenset({"schema_version", "source", "transform", "renderer", "expected_output"})
_SOURCE_KEYS = frozenset({"ref_id", "content_sha256", "pixel_sha256", "mode", "width_height"})
_TRANSFORM_KEYS = frozenset({"sub_action", "params"})
_RENDERER_KEYS = frozenset({"renderer_id", "pillow_version"})
_EXPECTED_KEYS = frozenset({"pixel_sha256", "mode", "width_height"})

# Never allow host/path/scope identity fields, including nested under params.
_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {
        "path",
        "absolute_path",
        "relative_path",
        "file_path",
        "filepath",
        "dossier_id",
        "transcription_id",
        "run_id",
        "workspace_id",
        "workspace_key",
        "host",
        "host_path",
    }
)


class RecipeValidationError(Exception):
    """Strict refusal for an invalid or non-canonical candidate recipe."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code or "recipe_invalid")
        self.message = str(message or "Candidate recipe validation failed.")
        super().__init__(f"{self.code}: {self.message}" if self.message else self.code)


def is_json_native(value: Any) -> bool:
    """Return True iff ``value`` is JSON-native with no NaN/Inf or foreign types."""
    if value is None:
        return True
    t = type(value)
    if t is bool or t is int or t is str:
        return True
    if t is float:
        return math.isfinite(value)
    if t is list:
        return all(is_json_native(item) for item in value)
    if t is dict:
        return all(type(key) is str and is_json_native(item) for key, item in value.items())
    return False


def canonical_json_bytes(obj: Any) -> bytes:
    """Compact UTF-8 JSON with recursively sorted object keys; ``allow_nan=False``."""
    if not is_json_native(obj):
        raise RecipeValidationError(
            "recipe_not_json_native",
            "Value is not JSON-native (NaN/Inf, bytes, Path, or other foreign types).",
        )
    try:
        text = json.dumps(
            obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise RecipeValidationError(
            "recipe_not_json_native",
            "Value could not be serialized as strict JSON.",
        ) from exc
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 digest of ``data``."""
    if type(data) is not bytes:
        raise TypeError("sha256_hex requires bytes")
    return hashlib.sha256(data).hexdigest()


def build_candidate_recipe(
    *,
    source_ref_id: str,
    source_content_sha256: str,
    source_pixel_sha256: str,
    source_mode: str,
    source_width_height: Any,
    sub_action: str,
    params: Any,
    pillow_version: str,
    expected_pixel_sha256: str,
    expected_mode: str,
    expected_width_height: Any,
) -> dict[str, Any]:
    """Build and validate a path-free candidate recipe dict."""
    recipe = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "ref_id": source_ref_id,
            "content_sha256": source_content_sha256,
            "pixel_sha256": source_pixel_sha256,
            "mode": source_mode,
            "width_height": _as_width_height_list(source_width_height, field="source.width_height"),
        },
        "transform": {"sub_action": sub_action, "params": params},
        "renderer": {"renderer_id": RENDERER_ID, "pillow_version": pillow_version},
        "expected_output": {
            "pixel_sha256": expected_pixel_sha256,
            "mode": expected_mode,
            "width_height": _as_width_height_list(
                expected_width_height, field="expected_output.width_height"
            ),
        },
    }
    return validate_candidate_recipe(recipe)


def validate_candidate_recipe(recipe: Any) -> dict[str, Any]:
    """Return a normalized deep copy of a valid candidate recipe, or raise."""
    if type(recipe) is not dict:
        raise RecipeValidationError("recipe_not_object", "Recipe must be a JSON object.")
    _require_exact_keys(recipe, _TOP_KEYS, field="recipe")

    if type(recipe["schema_version"]) is not str or recipe["schema_version"] != SCHEMA_VERSION:
        raise RecipeValidationError(
            "schema_version_invalid",
            f"schema_version must be {SCHEMA_VERSION!r}.",
        )

    source = recipe["source"]
    transform = recipe["transform"]
    renderer = recipe["renderer"]
    expected = recipe["expected_output"]
    for name, obj in (
        ("source", source),
        ("transform", transform),
        ("renderer", renderer),
        ("expected_output", expected),
    ):
        if type(obj) is not dict:
            raise RecipeValidationError(f"{name}_not_object", f"{name} must be a JSON object.")

    _require_exact_keys(source, _SOURCE_KEYS, field="source")
    _require_exact_keys(transform, _TRANSFORM_KEYS, field="transform")
    _require_exact_keys(renderer, _RENDERER_KEYS, field="renderer")
    _require_exact_keys(expected, _EXPECTED_KEYS, field="expected_output")

    ref_id = _require_image_ref_id(source["ref_id"], field="source.ref_id")
    content_sha256 = _require_sha256_hex(source["content_sha256"], field="source.content_sha256")
    source_pixel = _require_sha256_hex(source["pixel_sha256"], field="source.pixel_sha256")
    source_mode = _require_nonempty_str(source["mode"], field="source.mode")
    source_wh = _require_width_height(source["width_height"], field="source.width_height")

    sub_action = transform["sub_action"]
    if type(sub_action) is not str or sub_action not in GENERIC_SUB_ACTIONS:
        raise RecipeValidationError(
            "sub_action_unsupported",
            "transform.sub_action is not a supported generic recipe sub_action.",
        )
    params = transform["params"]
    if type(params) is not dict:
        raise RecipeValidationError("params_not_object", "transform.params must be a JSON object.")
    if not is_json_native(params):
        raise RecipeValidationError(
            "params_not_json_native",
            "transform.params must be JSON-native with no NaN/Inf or foreign types.",
        )
    _reject_forbidden_keys(params, field="transform.params")

    if type(renderer["renderer_id"]) is not str or renderer["renderer_id"] != RENDERER_ID:
        raise RecipeValidationError(
            "renderer_id_invalid",
            f"renderer.renderer_id must be {RENDERER_ID!r}.",
        )
    pillow_version = _require_nonempty_str(renderer["pillow_version"], field="renderer.pillow_version")

    expected_pixel = _require_sha256_hex(
        expected["pixel_sha256"], field="expected_output.pixel_sha256"
    )
    expected_mode = _require_nonempty_str(expected["mode"], field="expected_output.mode")
    expected_wh = _require_width_height(
        expected["width_height"], field="expected_output.width_height"
    )

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "ref_id": ref_id,
            "content_sha256": content_sha256,
            "pixel_sha256": source_pixel,
            "mode": source_mode,
            "width_height": source_wh,
        },
        "transform": {"sub_action": sub_action, "params": _json_clone(params)},
        "renderer": {"renderer_id": RENDERER_ID, "pillow_version": pillow_version},
        "expected_output": {
            "pixel_sha256": expected_pixel,
            "mode": expected_mode,
            "width_height": expected_wh,
        },
    }
    canonical_json_bytes(normalized)
    return normalized


def recipe_fingerprint(recipe: Any) -> str:
    """Return ``sha256:<hex>`` over the canonical identity JSON of a validated recipe."""
    normalized = validate_candidate_recipe(recipe)
    return f"sha256:{sha256_hex(canonical_json_bytes(normalized))}"


def _require_exact_keys(obj: dict[str, Any], allowed: frozenset[str], *, field: str) -> None:
    keys = frozenset(obj.keys())
    if keys == allowed:
        return
    extra = sorted(keys - allowed)
    missing = sorted(allowed - keys)
    parts = []
    if extra:
        parts.append(f"extra={extra}")
    if missing:
        parts.append(f"missing={missing}")
    raise RecipeValidationError(
        "recipe_keys_invalid",
        f"{field} keys must be exactly {sorted(allowed)}; {', '.join(parts)}.",
    )


def _reject_forbidden_keys(value: Any, *, field: str) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is str and key in _FORBIDDEN_IDENTITY_KEYS:
                raise RecipeValidationError(
                    "recipe_forbidden_field",
                    f"{field} must not include identity field {key!r}.",
                )
            _reject_forbidden_keys(item, field=field)
    elif type(value) is list:
        for item in value:
            _reject_forbidden_keys(item, field=field)


def _require_nonempty_str(value: Any, *, field: str) -> str:
    if type(value) is not str or value == "":
        raise RecipeValidationError("recipe_string_invalid", f"{field} must be a non-empty string.")
    return value


def _require_sha256_hex(value: Any, *, field: str) -> str:
    if type(value) is not str or not _SHA256_HEX_RE.fullmatch(value):
        raise RecipeValidationError(
            "recipe_sha256_invalid",
            f"{field} must be a 64-char lowercase hex SHA-256 digest.",
        )
    return value


def _require_image_ref_id(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise RecipeValidationError("recipe_ref_id_invalid", f"{field} must be a non-empty string.")
    if not value.startswith(_IMAGE_REF_PREFIXES):
        raise RecipeValidationError(
            "recipe_ref_id_invalid",
            f"{field} must start with image:assoc: or image:derived:.",
        )
    return value


def _require_width_height(value: Any, *, field: str) -> list[int]:
    if type(value) is not list or len(value) != 2:
        raise RecipeValidationError(
            "recipe_width_height_invalid",
            f"{field} must be a list of two positive integers.",
        )
    w, h = value[0], value[1]
    if type(w) is not int or type(h) is not int or w <= 0 or h <= 0:
        raise RecipeValidationError(
            "recipe_width_height_invalid",
            f"{field} must be a list of two positive integers.",
        )
    return [w, h]


def _as_width_height_list(value: Any, *, field: str) -> list[int]:
    """Normalize builder input list/tuple to a validated ``[w, h]`` list."""
    if type(value) is list:
        return _require_width_height(value, field=field)
    if isinstance(value, tuple) and len(value) == 2:
        return _require_width_height([value[0], value[1]], field=field)
    raise RecipeValidationError(
        "recipe_width_height_invalid",
        f"{field} must be a list or tuple of two positive integers.",
    )


def _json_clone(value: Any) -> Any:
    """Deep-clone a JSON-native value via strict serialization."""
    return json.loads(canonical_json_bytes(value).decode("utf-8"))
