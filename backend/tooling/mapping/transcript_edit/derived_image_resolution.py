"""Recipe-backed derived-image read resolution (STORAGE-BR-006).

Resolves ``image:derived:*`` for read without writing reconstructed bytes, caches,
or temporary materializations. Canonical ``image:assoc:*`` sources remain immutable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .derived_image_descriptor import (
    DerivedImageDescriptorError,
    LoadedDerivedImageDescriptor,
    classify_coordinates_image,
    load_derived_image_descriptor,
    resolve_derived_image_coordinates,
)
from .derived_image_recipe import (
    RecipeValidationError,
    assert_recipe_descriptor_coherence,
    assert_recipe_output_identity,
)
from .derived_image_rendering import (
    GENERIC_SUB_ACTIONS,
    TransformParamError,
    compute_image_identity,
    render_generic_derived_image,
)

MAX_DERIVED_IMAGE_LINEAGE_DEPTH = 32

_ASSOC_PREFIX = "image:assoc:"
_DERIVED_PREFIX = "image:derived:"
_CONTENT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RepresentationKind = Literal["stored_bytes", "reconstructed_recipe"]
SourceIdentityPosture = Literal[
    "content_and_pixel_verified",
    "reconstructed_parent_pixel_verified",
]
ContentIdentityPosture = Literal[
    "stored_bytes_verified",
    "persisted_descriptor_coordinate",
    "unavailable",
]


class DerivedImageResolutionError(Exception):
    """Bounded, host-path-free failure for derived-image read resolution."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


@dataclass(frozen=True)
class ResolvedDerivedImage:
    ref_id: str
    image: Any
    representation_kind: RepresentationKind
    mode: str
    width_height: tuple[int, int]
    pixel_sha256: str
    lineage_depth: int
    source_identity_posture: SourceIdentityPosture
    content_identity_posture: ContentIdentityPosture
    content_sha256: str | None = None


@dataclass(frozen=True)
class RecipeReconstructionResult:
    """In-memory reconstruction from a validated persisted generic recipe."""

    ref_id: str
    image: Any
    mode: str
    width_height: tuple[int, int]
    pixel_sha256: str
    lineage_depth: int
    source_identity_posture: SourceIdentityPosture
    content_identity_posture: ContentIdentityPosture
    recipe: dict[str, Any]
    content_sha256: str | None = None


def _descriptor_content_coordinate(descriptor: Mapping[str, Any]) -> str | None:
    """Historical absence → None; present-but-malformed → stable identity error."""
    if "content_sha256" not in descriptor:
        return None
    value = descriptor["content_sha256"]
    if type(value) is not str or not _CONTENT_SHA256_RE.fullmatch(value):
        raise DerivedImageResolutionError(
            "content_identity_invalid",
            "Descriptor content_sha256 is malformed.",
        )
    return value


def _map_descriptor_error(exc: DerivedImageDescriptorError) -> DerivedImageResolutionError:
    code = exc.code
    if code == "descriptor_missing":
        return DerivedImageResolutionError("descriptor_missing", exc.message)
    if code == "invalid_derived_ref":
        return DerivedImageResolutionError("invalid_derived_ref", exc.message)
    return DerivedImageResolutionError("descriptor_invalid", exc.message)


def _map_recipe_error(exc: RecipeValidationError) -> DerivedImageResolutionError:
    if exc.code == "recipe_fingerprint_mismatch":
        return DerivedImageResolutionError(
            "recipe_incoherent",
            "Persisted recipe fingerprint does not match the recipe identity.",
        )
    if exc.code == "recipe_descriptor_mismatch":
        return DerivedImageResolutionError(
            "recipe_incoherent",
            "Persisted recipe does not agree with the derived descriptor.",
        )
    if exc.code == "recipe_output_mismatch":
        return DerivedImageResolutionError(
            "reconstructed_output_mismatch",
            "Reconstructed pixels do not match recipe.expected_output.",
        )
    return DerivedImageResolutionError(
        "recipe_invalid",
        "Persisted derived-image recipe is invalid.",
    )


def _open_stored_image(path: Path) -> Any:
    from PIL import Image  # type: ignore[import]

    img = Image.open(path)
    img.load()
    return img


def _verify_assoc_source_identity(
    *,
    dossier_id: str,
    transcription_id: str,
    source_ref_id: str,
    recipe_source: dict[str, Any],
) -> tuple[Any, SourceIdentityPosture]:
    from .image_loading import hydrate_source_image_context

    ctx = hydrate_source_image_context(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_id=source_ref_id,
    )
    if ctx.get("status") != "ok" or not ctx.get("exists"):
        raise DerivedImageResolutionError(
            "source_missing",
            "Canonical source image for the recipe could not be resolved.",
        )
    abs_str = ctx.get("absolute_path")
    if type(abs_str) is not str or not abs_str.strip():
        raise DerivedImageResolutionError(
            "source_missing",
            "Canonical source image for the recipe could not be resolved.",
        )
    path = Path(abs_str)
    if not path.is_file() or path.is_symlink() or os.path.islink(path):
        raise DerivedImageResolutionError(
            "source_missing",
            "Canonical source image for the recipe could not be resolved.",
        )
    try:
        identity = compute_image_identity(path=path)
        image = _open_stored_image(path)
    except Exception as exc:
        raise DerivedImageResolutionError(
            "source_missing",
            "Canonical source image for the recipe could not be read.",
        ) from exc

    if (
        identity.get("content_sha256") != recipe_source.get("content_sha256")
        or identity.get("pixel_sha256") != recipe_source.get("pixel_sha256")
        or identity.get("mode") != recipe_source.get("mode")
        or identity.get("width_height") != recipe_source.get("width_height")
    ):
        raise DerivedImageResolutionError(
            "source_identity_mismatch",
            "Canonical source identity does not match the persisted recipe source.",
        )
    return image, "content_and_pixel_verified"


def _resolve_derived_parent_for_recipe(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    parent_ref_id: str,
    recipe_source: dict[str, Any],
    visited: frozenset[str],
    depth: int,
    memo: dict[str, ResolvedDerivedImage],
) -> tuple[Any, SourceIdentityPosture, int]:
    parent = _resolve_derived_image_for_read_inner(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        ref_id=parent_ref_id,
        visited=visited,
        depth=depth,
        memo=memo,
    )
    if (
        parent.pixel_sha256 != recipe_source.get("pixel_sha256")
        or parent.mode != recipe_source.get("mode")
        or list(parent.width_height) != recipe_source.get("width_height")
    ):
        raise DerivedImageResolutionError(
            "source_identity_mismatch",
            "Parent derived image identity does not match the persisted recipe source.",
        )

    if parent.representation_kind != "stored_bytes":
        # Carry descriptor content coordinate when available; never upgrade to byte-verified.
        if (
            parent.content_sha256 is not None
            and parent.content_sha256 != recipe_source.get("content_sha256")
        ):
            raise DerivedImageResolutionError(
                "source_identity_mismatch",
                "Parent derived image content identity does not match the persisted recipe source.",
            )
        return parent.image, "reconstructed_parent_pixel_verified", parent.lineage_depth

    if parent.content_sha256 != recipe_source.get("content_sha256"):
        raise DerivedImageResolutionError(
            "source_identity_mismatch",
            "Parent derived image content identity does not match the persisted recipe source.",
        )
    return parent.image, "content_and_pixel_verified", parent.lineage_depth


def reconstruct_generic_from_persisted_recipe(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
    descriptor: dict[str, Any] | None = None,
    visited: frozenset[str] | None = None,
    depth: int = 0,
    memo: dict[str, ResolvedDerivedImage] | None = None,
) -> RecipeReconstructionResult:
    """Shared in-memory reconstruction seam for missing-PNG reads and storage audit.

    Never writes image bytes. Requires a coherent persisted generic recipe.
    """
    if depth > MAX_DERIVED_IMAGE_LINEAGE_DEPTH:
        raise DerivedImageResolutionError(
            "lineage_depth_exceeded",
            "Derived image recipe lineage exceeds the maximum allowed depth.",
        )

    try:
        if descriptor is None:
            loaded = load_derived_image_descriptor(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_id,
                ref_id=ref_id,
            )
            descriptor = loaded.descriptor
            canonical_ref = loaded.coordinates.ref_id
        else:
            coords = resolve_derived_image_coordinates(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_id,
                ref_id=ref_id,
            )
            canonical_ref = coords.ref_id
            stored_ref = descriptor.get("ref_id")
            if not (type(stored_ref) is str and stored_ref == canonical_ref):
                raise DerivedImageResolutionError(
                    "descriptor_invalid",
                    "Descriptor ref_id does not agree with the requested derived reference.",
                )
    except DerivedImageDescriptorError as exc:
        raise _map_descriptor_error(exc) from exc

    seen = visited if visited is not None else frozenset()
    if canonical_ref in seen:
        raise DerivedImageResolutionError(
            "lineage_cycle",
            "Derived image recipe lineage contains a cycle.",
        )
    next_visited = seen | {canonical_ref}
    work_memo = memo if memo is not None else {}

    recipe_raw = descriptor.get("recipe")
    fingerprint = descriptor.get("recipe_fingerprint")
    if recipe_raw is None or fingerprint is None:
        raise DerivedImageResolutionError(
            "recipe_unavailable",
            "Persisted generic recipe is required when stored derived bytes are absent.",
        )

    parent_ref_id = descriptor.get("parent_ref_id")
    sub_action = descriptor.get("sub_action")
    params = descriptor.get("params")
    if type(sub_action) is not str or sub_action not in GENERIC_SUB_ACTIONS:
        raise DerivedImageResolutionError(
            "recipe_unavailable",
            "Point-crop and non-generic descriptors cannot use recipe reconstruction.",
        )

    try:
        recipe = assert_recipe_descriptor_coherence(
            recipe=recipe_raw,
            recipe_fingerprint_value=fingerprint,
            parent_ref_id=parent_ref_id,
            sub_action=sub_action,
            params=params,
        )
    except RecipeValidationError as exc:
        raise _map_recipe_error(exc) from exc

    source_ref = str(recipe["source"]["ref_id"])
    if source_ref.startswith(_ASSOC_PREFIX):
        source_image, posture = _verify_assoc_source_identity(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            source_ref_id=source_ref,
            recipe_source=recipe["source"],
        )
        parent_depth = 0
    elif source_ref.startswith(_DERIVED_PREFIX):
        source_image, posture, parent_depth = _resolve_derived_parent_for_recipe(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            parent_ref_id=source_ref,
            recipe_source=recipe["source"],
            visited=next_visited,
            depth=depth + 1,
            memo=work_memo,
        )
    else:
        raise DerivedImageResolutionError(
            "source_missing",
            "Recipe source reference kind is not supported.",
        )

    lineage_depth = parent_depth + 1
    if lineage_depth > MAX_DERIVED_IMAGE_LINEAGE_DEPTH:
        raise DerivedImageResolutionError(
            "lineage_depth_exceeded",
            "Derived image recipe lineage exceeds the maximum allowed depth.",
        )

    try:
        rendered = render_generic_derived_image(
            source_image,
            sub_action,
            recipe["transform"]["params"],
            source_ref_id=source_ref,
        )
        out_id = compute_image_identity(image=rendered.image)
        assert_recipe_output_identity(
            recipe,
            pixel_sha256=str(out_id.get("pixel_sha256") or ""),
            mode=str(out_id.get("mode") or ""),
            width_height=out_id.get("width_height") or [0, 0],
            already_validated=True,
        )
    except DerivedImageResolutionError:
        raise
    except RecipeValidationError as exc:
        raise _map_recipe_error(exc) from exc
    except TransformParamError as exc:
        raise DerivedImageResolutionError(
            "renderer_failure",
            "Generic derived-image renderer rejected the recipe parameters.",
        ) from exc
    except Exception as exc:
        raise DerivedImageResolutionError(
            "renderer_failure",
            "Generic derived-image reconstruction failed during render.",
        ) from exc

    wh_list = out_id.get("width_height") or [0, 0]
    # Logical historical coordinate from the descriptor — never the re-encoded render bytes.
    content_coord = _descriptor_content_coordinate(descriptor)
    if content_coord is not None:
        content_sha256: str | None = content_coord
        content_identity_posture: ContentIdentityPosture = "persisted_descriptor_coordinate"
    else:
        content_sha256 = None
        content_identity_posture = "unavailable"

    return RecipeReconstructionResult(
        ref_id=canonical_ref,
        image=rendered.image,
        mode=str(out_id.get("mode") or ""),
        width_height=(int(wh_list[0]), int(wh_list[1])),
        pixel_sha256=str(out_id.get("pixel_sha256") or ""),
        lineage_depth=lineage_depth,
        source_identity_posture=posture,
        content_identity_posture=content_identity_posture,
        recipe=recipe,
        content_sha256=content_sha256,
    )


def _resolve_stored_bytes(
    *,
    loaded: LoadedDerivedImageDescriptor,
) -> ResolvedDerivedImage:
    coords = loaded.coordinates
    png = coords.image_path
    status = classify_coordinates_image(coords)
    if status == "absent":
        raise DerivedImageResolutionError(
            "stored_image_missing",
            "Stored derived image bytes are absent.",
        )
    if status != "safe_regular_file":
        raise DerivedImageResolutionError(
            "stored_image_corrupt",
            "Stored derived image path is unsafe or unreadable.",
        )
    # Never follow a tampered absolute_path — mechanical image_path only.
    try:
        identity = compute_image_identity(path=png)
        image = _open_stored_image(png)
    except Exception as exc:
        raise DerivedImageResolutionError(
            "stored_image_corrupt",
            "Stored derived image bytes are corrupt or unreadable.",
        ) from exc

    actual_content = identity.get("content_sha256")
    if type(actual_content) is not str or not _CONTENT_SHA256_RE.fullmatch(actual_content):
        raise DerivedImageResolutionError(
            "stored_image_corrupt",
            "Stored derived image content identity could not be established.",
        )

    descriptor_coord = _descriptor_content_coordinate(loaded.descriptor)
    if descriptor_coord is not None and descriptor_coord != actual_content:
        raise DerivedImageResolutionError(
            "content_identity_mismatch",
            "Descriptor content_sha256 does not match stored PNG bytes.",
        )

    wh_list = identity.get("width_height") or [0, 0]
    return ResolvedDerivedImage(
        ref_id=coords.ref_id,
        image=image,
        representation_kind="stored_bytes",
        mode=str(identity.get("mode") or ""),
        width_height=(int(wh_list[0]), int(wh_list[1])),
        pixel_sha256=str(identity.get("pixel_sha256") or ""),
        lineage_depth=0,
        source_identity_posture="content_and_pixel_verified",
        content_identity_posture="stored_bytes_verified",
        content_sha256=actual_content,
    )


def _resolve_derived_image_for_read_inner(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
    visited: frozenset[str],
    depth: int,
    memo: dict[str, ResolvedDerivedImage],
) -> ResolvedDerivedImage:
    if depth > MAX_DERIVED_IMAGE_LINEAGE_DEPTH:
        raise DerivedImageResolutionError(
            "lineage_depth_exceeded",
            "Derived image recipe lineage exceeds the maximum allowed depth.",
        )

    try:
        loaded = load_derived_image_descriptor(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            ref_id=ref_id,
        )
    except DerivedImageDescriptorError as exc:
        raise _map_descriptor_error(exc) from exc

    canonical = loaded.coordinates.ref_id
    if canonical in memo:
        return memo[canonical]
    if canonical in visited:
        raise DerivedImageResolutionError(
            "lineage_cycle",
            "Derived image recipe lineage contains a cycle.",
        )

    status = classify_coordinates_image(loaded.coordinates)
    if status == "safe_regular_file":
        resolved = _resolve_stored_bytes(loaded=loaded)
        memo[canonical] = resolved
        return resolved
    if status == "unsafe":
        # Present path entry that is a symlink/escape — never hide via recipe fallback.
        raise DerivedImageResolutionError(
            "stored_image_corrupt",
            "Stored derived image path is unsafe or unreadable.",
        )

    recon = reconstruct_generic_from_persisted_recipe(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        ref_id=canonical,
        descriptor=loaded.descriptor,
        visited=visited,
        depth=depth,
        memo=memo,
    )
    resolved = ResolvedDerivedImage(
        ref_id=recon.ref_id,
        image=recon.image,
        representation_kind="reconstructed_recipe",
        mode=recon.mode,
        width_height=recon.width_height,
        pixel_sha256=recon.pixel_sha256,
        lineage_depth=recon.lineage_depth,
        source_identity_posture=recon.source_identity_posture,
        content_identity_posture=recon.content_identity_posture,
        content_sha256=recon.content_sha256,
    )
    memo[canonical] = resolved
    return resolved


def resolve_derived_image_for_read(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    ref_id: str,
) -> ResolvedDerivedImage:
    """Canonical read resolution for ``image:derived:*`` (stored bytes or recipe reconstruct)."""
    return _resolve_derived_image_for_read_inner(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        ref_id=ref_id,
        visited=frozenset(),
        depth=0,
        memo={},
    )


# Public surface for STORAGE-BR-006/007 read resolution.
__all__ = [
    "MAX_DERIVED_IMAGE_LINEAGE_DEPTH",
    "ContentIdentityPosture",
    "DerivedImageResolutionError",
    "RecipeReconstructionResult",
    "ResolvedDerivedImage",
    "reconstruct_generic_from_persisted_recipe",
    "resolve_derived_image_for_read",
]
