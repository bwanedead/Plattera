"""``transform_artifact`` capability for transcript-edit image refs.

Applies spatial and annotation transforms to source or derived image artifacts,
materializes a new derived ref, and persists the result for later hydration.

Crop geometry accepted forms:
  params.box      = [x1, y1, x2, y2]  (absolute pixel coordinates)
  params.box_norm = [x1, y1, x2, y2]  (normalized 0..1 relative to source dimensions)

Retryable param failures carry ``retryable=True, blocked_by_invariant=False`` and a
``repair_hint`` so the agent can self-correct on the next turn without terminating the run.
"""

from __future__ import annotations

import json
import uuid as _uuid_mod
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .image_loading import hydrate_source_image_context, image_evidence_from_path
from .paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_derived_images_dir,
)
from .artifact_hydration import _load_derived_image_descriptor
from .derived_image_persistence import DerivedImagePersistError, persist_derived_image
from .derived_image_recipe import (
    RecipeValidationError,
    build_derived_image_recipe,
    fingerprint_validated_recipe,
)
from .derived_image_rendering import (
    TransformParamError as _TransformParamError,
    _ANNOTATION_TYPES,
    _validate_adjust,
    _validate_box,
    _validate_box_norm,
    compute_image_identity,
    pillow_version,
    render_generic_derived_image,
)
from .root_projection import (
    copy_projection_fields,
    enrich_point_geometry_with_projection,
    resolve_root_projection_context,
)
from .point_crop_review_table import attach_review_table_to_crop_set
from .point_crop_target_mapping import copy_target_mapping_fields
from .point_crop_key_band import attach_point_key_lines_to_crop_set
from .point_crop_source_lineage import (
    PointCropSourceLineage,
    repair_stored_point_crop_source_ref,
    resolve_point_crop_source_lineage,
)
from .source_window import attach_crop_frame_edge_room_to_point, build_source_window
from .point_crops import (
    PointCropParamError,
    build_crop_set_point_record,
    compute_point_crops,
    compute_point_crops_scaffold,
    compute_point_crops_view,
    point_crops_adjust_repair_hint_for,
    point_crops_repair_hint_for,
    point_crops_scaffold_repair_hint_for,
    point_crops_view_repair_hint_for,
    prepare_point_crops_adjust,
    prepare_point_crops_view,
    validate_point_crops_adjust_params,
    validate_point_crops_params,
    validate_point_crops_scaffold_params,
    validate_point_crops_view_params,
)

_IMAGE_ASSOC_PREFIX = "image:assoc:"
_IMAGE_DERIVED_PREFIX = "image:derived:"
_SUPPORTED_SUB_ACTIONS = frozenset(
    {
        "crop",
        "expand",
        "zoom",
        "annotate",
        "reference_overlay",
        "render_evidence_locators",
        "point_crops",
        "point_crops_scaffold",
        "point_crops_adjust",
        "point_crops_view",
    }
)


def _overlay_metadata_fields(transform_metadata: Mapping[str, Any]) -> dict[str, Any]:
    overlay = transform_metadata.get("overlay")
    if not isinstance(overlay, Mapping):
        return {}
    fields: dict[str, Any] = {}
    for key in (
        "overlay_role",
        "coordinate_lattice",
        "grid",
        "legend",
        "box_render",
        "pin_render",
        "letter_render",
        "render_warnings",
        "point_key_band",
    ):
        if key in overlay:
            fields[key] = overlay[key]
    return fields


def _overlay_role_from_metadata(transform_metadata: Mapping[str, Any]) -> str | None:
    overlay = transform_metadata.get("overlay")
    if isinstance(overlay, Mapping):
        role = overlay.get("overlay_role")
        if isinstance(role, str) and role.strip():
            return role.strip()
    role = transform_metadata.get("overlay_role")
    if isinstance(role, str) and role.strip():
        return role.strip()
    return None


def _point_crop_lineage_dict(lineage: PointCropSourceLineage) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if lineage.placement_surface_ref:
        payload["placement_surface_ref"] = lineage.placement_surface_ref
    if lineage.source_unwrapped_from_ref:
        payload["source_unwrapped_from_ref"] = lineage.source_unwrapped_from_ref
    if lineage.legacy_source_repaired:
        payload["legacy_source_repaired"] = True
    if lineage.legacy_source_repair_warning:
        payload["legacy_source_repair_warning"] = lineage.legacy_source_repair_warning
    return payload


def _persist_point_crop_set(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    source_ref: str,
    sub_action: str,
    params: dict[str, Any],
    transform_metadata: dict[str, Any],
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mint refs, write descriptors/sidecar, and return the tool result payload."""
    derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_key)
    derived_dir.mkdir(parents=True, exist_ok=True)

    master_pil = transform_metadata["master_pil"]
    per_point = transform_metadata["per_point"]
    show = transform_metadata.get("show")
    legend_height = transform_metadata.get("legend_height")
    key_band_height = transform_metadata.get("key_band_height")
    source_width_height = transform_metadata.get("source_width_height")
    point_count = transform_metadata.get("point_count")
    lineage = lineage or {}

    master_uuid = _uuid_mod.uuid4().hex
    master_ref = f"{_IMAGE_DERIVED_PREFIX}{master_uuid}"
    master_path = derived_dir / f"{master_uuid}.png"
    master_pil.save(master_path)

    previous_crop_set_overlay_ref = lineage.get("previous_crop_set_overlay_ref")
    adjustment_source_ref = lineage.get("adjustment_source_ref")
    adjustments_applied = lineage.get("adjustments_applied")
    placement_surface_ref = lineage.get("placement_surface_ref")
    source_unwrapped_from_ref = lineage.get("source_unwrapped_from_ref")
    legacy_source_repaired = lineage.get("legacy_source_repaired")
    legacy_source_repair_warning = lineage.get("legacy_source_repair_warning")

    projection_ctx = resolve_root_projection_context(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_key=workspace_key,
        source_ref=source_ref,
        local_width_height=list(source_width_height) if isinstance(source_width_height, (list, tuple)) else None,
    )

    crop_refs: list[dict[str, Any]] = []
    artifact_refs = [master_ref]
    for pt in per_point:
        enrich_point_geometry_with_projection(pt, projection_ctx=projection_ctx)
        attach_crop_frame_edge_room_to_point(pt)
        c_uuid = _uuid_mod.uuid4().hex
        c_ref = f"{_IMAGE_DERIVED_PREFIX}{c_uuid}"
        c_path = derived_dir / f"{c_uuid}.png"
        pt["crop_img"].save(c_path)

        crop_record = build_crop_set_point_record(pt, crop_ref=c_ref)
        crop_refs.append(crop_record)

        crop_transform_metadata: dict[str, Any] = {
            "alias": pt["alias"],
            "letter": pt["letter"],
            "color": pt["color"],
            "size": pt["size"],
            "shape": pt["shape"],
            "point_norm": pt["point_norm"],
            "box_px": pt["box_px"],
            "box_norm": pt["box_norm"],
            "source_width_height": source_width_height,
            "crop_set_overlay_ref": master_ref,
        }
        crop_transform_metadata.update(
            {
                key: pt[key]
                for key in (
                    "zoom_factor",
                    "unzoomed_width_height",
                    "output_width_height",
                    "zoom_cap_applied",
                    "requested_zoom_factor",
                    "max_output_dimension",
                    "scale_x",
                    "scale_y",
                    "explicit_width_height_norm",
                    "template_width_height_norm",
                    "resolved_width_height_norm",
                )
                if key in pt
            }
        )
        crop_transform_metadata.update(copy_projection_fields(pt))
        for key in (
            "crop_frame_room_norm",
            "crop_frame_touches_edge",
            "crop_frame_can_expand",
            "root_crop_frame_room_norm",
            "root_crop_frame_touches_edge",
            "root_crop_frame_can_expand",
        ):
            if key in pt:
                crop_transform_metadata[key] = pt[key]
        crop_transform_metadata.update(copy_target_mapping_fields(pt))
        if previous_crop_set_overlay_ref:
            crop_transform_metadata["previous_crop_set_overlay_ref"] = previous_crop_set_overlay_ref

        c_desc: dict[str, Any] = {
            "ref_id": c_ref,
            "parent_ref_id": source_ref,
            "crop_set_overlay_ref": master_ref,
            "sub_action": "point_crops_crop",
            "params": {"parent_point_alias": pt["alias"]},
            "absolute_path": str(c_path.resolve()),
            "basename": c_path.name,
            "size_bytes": c_path.stat().st_size if c_path.exists() else None,
            "width_height": [pt["crop_img"].width, pt["crop_img"].height],
            "transform_metadata": crop_transform_metadata,
        }
        if pt.get("root_source_ref"):
            c_desc["root_source_ref"] = pt["root_source_ref"]
        if previous_crop_set_overlay_ref:
            c_desc["previous_crop_set_overlay_ref"] = previous_crop_set_overlay_ref
        (derived_dir / f"{c_uuid}.json").write_text(
            json.dumps(c_desc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        artifact_refs.append(c_ref)

    crop_set: dict[str, Any] = {
        "master_overlay_ref": master_ref,
        "source_ref": source_ref,
        "show": show,
        "legend_height": legend_height,
        "key_band_height": key_band_height,
        "source_width_height": source_width_height,
        "points": list(crop_refs),
    }
    if placement_surface_ref:
        crop_set["placement_surface_ref"] = placement_surface_ref
    if source_unwrapped_from_ref:
        crop_set["source_unwrapped_from_ref"] = source_unwrapped_from_ref
    if legacy_source_repaired:
        crop_set["legacy_source_repaired"] = True
    if legacy_source_repair_warning:
        crop_set["legacy_source_repair_warning"] = legacy_source_repair_warning
    if previous_crop_set_overlay_ref:
        crop_set["previous_crop_set_overlay_ref"] = previous_crop_set_overlay_ref
    if adjustments_applied:
        crop_set["adjustments_applied"] = list(adjustments_applied)
    crop_set.update(_overlay_metadata_fields(transform_metadata))
    attach_review_table_to_crop_set(crop_set)
    attach_point_key_lines_to_crop_set(crop_set)

    (derived_dir / f"{master_uuid}_crop_set.json").write_text(
        json.dumps(crop_set, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    master_crop_set_meta: dict[str, Any] = {"points": list(crop_refs)}
    for key in ("review_rows", "review_lines", "point_key_lines", "overlay_role"):
        if key in crop_set:
            master_crop_set_meta[key] = crop_set[key]

    master_transform_metadata: dict[str, Any] = {
        "source_ref": source_ref,
        "show": show,
        "legend_height": legend_height,
        "key_band_height": key_band_height,
        "source_width_height": source_width_height,
        "point_count": point_count,
        "crop_set": master_crop_set_meta,
    }
    if placement_surface_ref:
        master_transform_metadata["placement_surface_ref"] = placement_surface_ref
    if source_unwrapped_from_ref:
        master_transform_metadata["source_unwrapped_from_ref"] = source_unwrapped_from_ref
    if legacy_source_repaired:
        master_transform_metadata["legacy_source_repaired"] = True
    if legacy_source_repair_warning:
        master_transform_metadata["legacy_source_repair_warning"] = legacy_source_repair_warning
    if previous_crop_set_overlay_ref:
        master_transform_metadata["previous_crop_set_overlay_ref"] = previous_crop_set_overlay_ref
    if adjustment_source_ref:
        master_transform_metadata["adjustment_source_ref"] = adjustment_source_ref
    if adjustments_applied:
        master_transform_metadata["adjustments_applied"] = list(adjustments_applied)
    master_transform_metadata.update(_overlay_metadata_fields(transform_metadata))

    master_desc = {
        "ref_id": master_ref,
        "parent_ref_id": source_ref,
        "sub_action": sub_action,
        "params": params,
        "transform_metadata": master_transform_metadata,
        "absolute_path": str(master_path.resolve()),
        "basename": master_path.name,
        "size_bytes": master_path.stat().st_size if master_path.exists() else None,
        "width_height": [master_pil.width, master_pil.height],
    }
    if previous_crop_set_overlay_ref:
        master_desc["previous_crop_set_overlay_ref"] = previous_crop_set_overlay_ref
    (derived_dir / f"{master_uuid}.json").write_text(
        json.dumps(master_desc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    outputs: dict[str, Any] = {
        "derived_ref_id": master_ref,
        "parent_ref_id": source_ref,
        "sub_action": sub_action,
        "basename": master_path.name,
        "width_height": [master_pil.width, master_pil.height],
        "crop_set": crop_set,
        "crop_records": crop_refs,
    }
    if previous_crop_set_overlay_ref:
        outputs["previous_crop_set_overlay_ref"] = previous_crop_set_overlay_ref
    if adjustment_source_ref:
        outputs["adjustment_source_ref"] = adjustment_source_ref
    if adjustments_applied:
        outputs["adjustments_applied"] = list(adjustments_applied)
    if placement_surface_ref:
        outputs["placement_surface_ref"] = placement_surface_ref
    if source_unwrapped_from_ref:
        outputs["source_unwrapped_from_ref"] = source_unwrapped_from_ref
    if legacy_source_repaired:
        outputs["legacy_source_repaired"] = True
    if legacy_source_repair_warning:
        outputs["legacy_source_repair_warning"] = legacy_source_repair_warning
    overlay_role = crop_set.get("overlay_role")
    if isinstance(overlay_role, str) and overlay_role.strip():
        outputs["overlay_role"] = overlay_role.strip()

    result: dict[str, Any] = {
        "executed": True,
        "artifact_refs": artifact_refs,
        "outputs": outputs,
    }
    evidence = image_evidence_from_path(master_ref, master_path)
    if evidence:
        result["image_evidence"] = [evidence]
    return result


def _persist_point_crop_view(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    source_ref: str,
    sub_action: str,
    params: dict[str, Any],
    transform_metadata: dict[str, Any],
    view_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Persist a filtered crop-set overlay view (no new per-point crop refs)."""
    derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_key)
    derived_dir.mkdir(parents=True, exist_ok=True)

    master_pil = transform_metadata["master_pil"]
    per_point = transform_metadata["per_point"]
    show = transform_metadata.get("show")
    legend_height = transform_metadata.get("legend_height")
    source_width_height = transform_metadata.get("source_width_height")
    view_of_ref = view_bundle.get("view_of_crop_set_overlay_ref")
    filter_applied = view_bundle.get("filter")

    master_uuid = _uuid_mod.uuid4().hex
    master_ref = f"{_IMAGE_DERIVED_PREFIX}{master_uuid}"
    master_path = derived_dir / f"{master_uuid}.png"
    master_pil.save(master_path)

    view_points = [build_crop_set_point_record(pt) for pt in per_point]
    crop_set: dict[str, Any] = {
        "master_overlay_ref": master_ref,
        "source_ref": source_ref,
        "show": show,
        "legend_height": legend_height,
        "source_width_height": source_width_height,
        "points": view_points,
        "view_of_crop_set_overlay_ref": view_of_ref,
    }
    if filter_applied:
        crop_set["filter"] = filter_applied
    crop_set.update(_overlay_metadata_fields(transform_metadata))
    attach_review_table_to_crop_set(crop_set)

    view_crop_set_meta: dict[str, Any] = {"points": view_points}
    for key in ("review_rows", "review_lines", "point_key_lines", "overlay_role"):
        if key in crop_set:
            view_crop_set_meta[key] = crop_set[key]

    master_transform_metadata: dict[str, Any] = {
        "source_ref": source_ref,
        "show": show,
        "legend_height": legend_height,
        "source_width_height": source_width_height,
        "point_count": len(view_points),
        "crop_set": view_crop_set_meta,
        "view_of_crop_set_overlay_ref": view_of_ref,
    }
    if filter_applied:
        master_transform_metadata["filter"] = filter_applied
    master_transform_metadata.update(_overlay_metadata_fields(transform_metadata))

    master_desc = {
        "ref_id": master_ref,
        "parent_ref_id": source_ref,
        "sub_action": sub_action,
        "params": params,
        "transform_metadata": master_transform_metadata,
        "absolute_path": str(master_path.resolve()),
        "basename": master_path.name,
        "size_bytes": master_path.stat().st_size if master_path.exists() else None,
        "width_height": [master_pil.width, master_pil.height],
        "view_of_crop_set_overlay_ref": view_of_ref,
    }
    (derived_dir / f"{master_uuid}.json").write_text(
        json.dumps(master_desc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    outputs: dict[str, Any] = {
        "derived_ref_id": master_ref,
        "parent_ref_id": source_ref,
        "sub_action": sub_action,
        "basename": master_path.name,
        "width_height": [master_pil.width, master_pil.height],
        "crop_set": crop_set,
        "crop_records": view_points,
        "view_of_crop_set_overlay_ref": view_of_ref,
    }
    if filter_applied:
        outputs["filter"] = filter_applied
    overlay_role = crop_set.get("overlay_role")
    if isinstance(overlay_role, str) and overlay_role.strip():
        outputs["overlay_role"] = overlay_role.strip()

    result: dict[str, Any] = {
        "executed": True,
        "artifact_refs": [master_ref],
        "outputs": outputs,
    }
    evidence = image_evidence_from_path(master_ref, master_path)
    if evidence:
        result["image_evidence"] = [evidence]
    return result


def _persist_point_crop_scaffold(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    source_ref: str,
    sub_action: str,
    params: dict[str, Any],
    transform_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Persist a zero-point placement scaffold (single derived image only)."""
    derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_key)
    derived_dir.mkdir(parents=True, exist_ok=True)

    master_pil = transform_metadata["master_pil"]
    source_width_height = transform_metadata.get("source_width_height")
    point_count = int(transform_metadata.get("point_count") or 0)

    master_uuid = _uuid_mod.uuid4().hex
    master_ref = f"{_IMAGE_DERIVED_PREFIX}{master_uuid}"
    master_path = derived_dir / f"{master_uuid}.png"
    master_pil.save(master_path)

    crop_set: dict[str, Any] = {
        "master_overlay_ref": master_ref,
        "source_ref": source_ref,
        "source_width_height": source_width_height,
        "points": [],
        "point_count": point_count,
    }
    crop_set.update(_overlay_metadata_fields(transform_metadata))

    scaffold_crop_set_meta: dict[str, Any] = {
        "points": [],
        "point_count": point_count,
    }
    for key in ("overlay_role", "coordinate_lattice", "grid", "legend"):
        if key in crop_set:
            scaffold_crop_set_meta[key] = crop_set[key]

    master_transform_metadata: dict[str, Any] = {
        "source_ref": source_ref,
        "source_width_height": source_width_height,
        "point_count": point_count,
        "crop_set": scaffold_crop_set_meta,
    }
    master_transform_metadata.update(_overlay_metadata_fields(transform_metadata))

    master_desc = {
        "ref_id": master_ref,
        "parent_ref_id": source_ref,
        "sub_action": sub_action,
        "params": params,
        "transform_metadata": master_transform_metadata,
        "absolute_path": str(master_path.resolve()),
        "basename": master_path.name,
        "size_bytes": master_path.stat().st_size if master_path.exists() else None,
        "width_height": [master_pil.width, master_pil.height],
    }
    (derived_dir / f"{master_uuid}.json").write_text(
        json.dumps(master_desc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    outputs: dict[str, Any] = {
        "derived_ref_id": master_ref,
        "parent_ref_id": source_ref,
        "sub_action": sub_action,
        "basename": master_path.name,
        "width_height": [master_pil.width, master_pil.height],
        "point_count": point_count,
        "crop_set": crop_set,
        "crop_records": [],
    }
    overlay_role = crop_set.get("overlay_role")
    if isinstance(overlay_role, str) and overlay_role.strip():
        outputs["overlay_role"] = overlay_role.strip()
    lattice = crop_set.get("coordinate_lattice")
    if isinstance(lattice, Mapping):
        outputs["coordinate_lattice"] = dict(lattice)

    result: dict[str, Any] = {
        "executed": True,
        "artifact_refs": [master_ref],
        "outputs": outputs,
    }
    evidence = image_evidence_from_path(master_ref, master_path)
    if evidence:
        result["image_evidence"] = [evidence]
    return result


def make_transform_artifact_handler(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> Callable[[Any], Any]:
    """Return a handler for ``transform_artifact`` closed over the run scope."""

    def handler(request: Any) -> Any:
        if not workspace_key:
            return _error_result("workspace_required", "workspace_id or run_id is required to create derived artifacts.")

        inputs: dict[str, Any] = dict(request.inputs) if hasattr(request, "inputs") else dict(request) if isinstance(request, dict) else {}
        ref_id = str(inputs.get("ref_id") or "").strip()
        if not ref_id:
            return _error_result("ref_id_required", "ref_id is required.")

        sub_action = str(inputs.get("sub_action") or "").strip().lower()
        if sub_action not in _SUPPORTED_SUB_ACTIONS:
            return _error_result(
                "unsupported_sub_action",
                f"sub_action must be one of: {', '.join(sorted(_SUPPORTED_SUB_ACTIONS))}.",
            )

        params = inputs.get("params") or {}
        if not isinstance(params, dict):
            return _error_result("params_invalid", "params must be a JSON object.")

        # Pre-validate sub-action params before touching disk; fixable shape errors are retryable.
        param_error = _validate_params(sub_action, params)
        if param_error is not None:
            return param_error

        if sub_action == "point_crops":
            lineage_res, lineage_err = resolve_point_crop_source_lineage(
                ref_id=ref_id,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            )
            if lineage_err:
                return _error_result(lineage_err["code"], lineage_err["message"])
            assert lineage_res is not None
            source_path, resolve_error = _resolve_source_path(
                ref_id=lineage_res.clean_source_ref,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            )
            if resolve_error:
                return _error_result(resolve_error["code"], resolve_error["message"])
            assert source_path is not None
            try:
                from PIL import Image  # type: ignore[import]

                img = Image.open(source_path)
                transform_metadata = compute_point_crops(img, params)
            except PointCropParamError as exc:
                return _param_error(
                    "invalid_transform_params",
                    str(exc),
                    repair_hint=exc.repair_hint or point_crops_repair_hint_for(str(exc)),
                )
            except Exception as exc:
                return _error_result("transform_failed", f"Transform failed: {exc}")
            return _persist_point_crop_set(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
                source_ref=lineage_res.clean_source_ref,
                sub_action=sub_action,
                params=params,
                transform_metadata=transform_metadata,
                lineage=_point_crop_lineage_dict(lineage_res),
            )

        if sub_action == "point_crops_adjust":
            if not ref_id.startswith(_IMAGE_DERIVED_PREFIX):
                return _param_error(
                    "invalid_transform_params",
                    "point_crops_adjust ref_id must be a prior point_crops master overlay ref (image:derived:*).",
                    repair_hint="Set ref_id to outputs.derived_ref_id from a prior point_crops call.",
                )
            master_desc = _load_derived_image_descriptor(
                dossier_id, transcription_id, workspace_key, ref_id
            )
            if master_desc is None:
                return _error_result("derived_ref_not_found", "Derived image ref not found.")
            try:
                adjust_bundle = prepare_point_crops_adjust(
                    master_desc,
                    params,
                    adjustment_source_ref=ref_id,
                )
            except PointCropParamError as exc:
                return _param_error(
                    "invalid_transform_params",
                    str(exc),
                    repair_hint=exc.repair_hint or point_crops_adjust_repair_hint_for(str(exc)),
                )
            lineage_res, lineage_err = repair_stored_point_crop_source_ref(
                adjust_bundle["source_ref"],
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
                placement_surface_ref=adjust_bundle.get("placement_surface_ref"),
            )
            if lineage_err:
                return _error_result(lineage_err["code"], lineage_err["message"])
            assert lineage_res is not None
            source_path, resolve_error = _resolve_source_path(
                ref_id=lineage_res.clean_source_ref,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            )
            if resolve_error:
                return _error_result(resolve_error["code"], resolve_error["message"])
            assert source_path is not None
            try:
                from PIL import Image  # type: ignore[import]

                img = Image.open(source_path)
                transform_metadata = compute_point_crops(
                    img,
                    {"points": adjust_bundle["points"], "show": adjust_bundle["show"]},
                )
            except PointCropParamError as exc:
                return _param_error(
                    "invalid_transform_params",
                    str(exc),
                    repair_hint=exc.repair_hint,
                )
            except Exception as exc:
                return _error_result("transform_failed", f"Transform failed: {exc}")
            return _persist_point_crop_set(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
                source_ref=lineage_res.clean_source_ref,
                sub_action=sub_action,
                params=params,
                transform_metadata=transform_metadata,
                lineage={
                    "previous_crop_set_overlay_ref": adjust_bundle["previous_crop_set_overlay_ref"],
                    "adjustment_source_ref": adjust_bundle["adjustment_source_ref"],
                    "adjustments_applied": adjust_bundle["adjustments_applied"],
                    **_point_crop_lineage_dict(lineage_res),
                },
            )

        if sub_action == "point_crops_view":
            if not ref_id.startswith(_IMAGE_DERIVED_PREFIX):
                return _param_error(
                    "invalid_transform_params",
                    "point_crops_view ref_id must be a prior point_crops master overlay ref (image:derived:*).",
                    repair_hint="Set ref_id to outputs.derived_ref_id from a prior point_crops call.",
                )
            master_desc = _load_derived_image_descriptor(
                dossier_id, transcription_id, workspace_key, ref_id
            )
            if master_desc is None:
                return _error_result("derived_ref_not_found", "Derived image ref not found.")
            try:
                view_bundle = prepare_point_crops_view(
                    master_desc,
                    params,
                    view_source_ref=ref_id,
                )
            except PointCropParamError as exc:
                return _param_error(
                    "invalid_transform_params",
                    str(exc),
                    repair_hint=exc.repair_hint or point_crops_view_repair_hint_for(str(exc)),
                )
            source_path, resolve_error = _resolve_source_path(
                ref_id=view_bundle["source_ref"],
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
            )
            if resolve_error:
                return _error_result(resolve_error["code"], resolve_error["message"])
            assert source_path is not None
            try:
                from PIL import Image  # type: ignore[import]

                img = Image.open(source_path)
                transform_metadata = compute_point_crops_view(
                    img,
                    view_bundle["points"],
                    show=view_bundle["show"],
                )
            except PointCropParamError as exc:
                return _param_error(
                    "invalid_transform_params",
                    str(exc),
                    repair_hint=exc.repair_hint,
                )
            except Exception as exc:
                return _error_result("transform_failed", f"Transform failed: {exc}")
            return _persist_point_crop_view(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
                source_ref=view_bundle["source_ref"],
                sub_action=sub_action,
                params=params,
                transform_metadata=transform_metadata,
                view_bundle=view_bundle,
            )

        # Resolve source image path
        source_path, resolve_error = _resolve_source_path(
            ref_id=ref_id,
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_key=workspace_key,
        )
        if resolve_error:
            return _error_result(resolve_error["code"], resolve_error["message"])
        assert source_path is not None

        # Apply transform (in-memory; persistence is run-owned below).
        if sub_action == "point_crops_scaffold":
            try:
                from PIL import Image  # type: ignore[import]

                img = Image.open(source_path)
                transform_metadata = compute_point_crops_scaffold(img, params)
            except PointCropParamError as exc:
                return _param_error(
                    "invalid_transform_params",
                    str(exc),
                    repair_hint=exc.repair_hint,
                )
            except Exception as exc:
                return _error_result("transform_failed", f"Transform failed: {exc}")
            return _persist_point_crop_scaffold(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
                source_ref=ref_id,
                sub_action=sub_action,
                params=params,
                transform_metadata=transform_metadata,
            )

        try:
            rendered = render_generic_derived_image(
                source_path,
                sub_action,
                params,
                source_ref_id=ref_id,
            )
            rendered_image = rendered.image
            width_height = rendered.width_height
            transform_metadata = rendered.transform_metadata
        except _TransformParamError as exc:
            # Param errors discovered at transform time (e.g. after image open) are retryable.
            return _param_error("invalid_transform_params", str(exc), repair_hint=exc.repair_hint)
        except Exception as exc:
            return _error_result("transform_failed", f"Transform failed: {exc}")

        _attach_source_window_metadata(
            transform_metadata,
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_key=workspace_key,
            source_ref=ref_id,
            sub_action=sub_action,
        )

        # Special multi-output handling for point_crops is handled earlier (clean-source unwrap).

        # Normal single-output path for all other sub-actions
        derived_uuid = _uuid_mod.uuid4().hex
        derived_ref_id = f"{_IMAGE_DERIVED_PREFIX}{derived_uuid}"
        _attach_rendered_ref(transform_metadata, rendered_ref=derived_ref_id)
        try:
            source_identity = compute_image_identity(path=source_path)
            output_identity = compute_image_identity(image=rendered_image)
            recipe = build_derived_image_recipe(
                source_ref_id=ref_id,
                source_content_sha256=source_identity["content_sha256"],
                source_pixel_sha256=source_identity["pixel_sha256"],
                source_mode=source_identity["mode"],
                source_width_height=source_identity["width_height"],
                sub_action=sub_action,
                params=params,
                pillow_version=pillow_version(),
                expected_pixel_sha256=output_identity["pixel_sha256"],
                expected_mode=output_identity["mode"],
                expected_width_height=output_identity["width_height"],
            )
            fingerprint = fingerprint_validated_recipe(recipe)
        except (RecipeValidationError, Exception):
            return _error_result(
                "derived_recipe_invalid",
                "Could not build a valid reconstruction recipe for the derived image.",
            )
        descriptor: dict[str, Any] = {
            "ref_id": derived_ref_id,
            "parent_ref_id": ref_id,
            "sub_action": sub_action,
            "params": params,
            "transform_metadata": transform_metadata,
            "recipe": recipe,
            "recipe_fingerprint": fingerprint,
        }
        try:
            persisted = persist_derived_image(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_key,
                derived_uuid=derived_uuid,
                image=rendered_image,
                descriptor=descriptor,
                expected_width_height=width_height,
            )
        except DerivedImagePersistError as exc:
            return _error_result(exc.code, exc.message)
        except Exception:
            return _error_result(
                "derived_persist_failed",
                "Could not persist derived image into the run workspace.",
            )

        result: dict[str, Any] = {
            "executed": True,
            "artifact_refs": [derived_ref_id],
            "outputs": {
                "derived_ref_id": derived_ref_id,
                "parent_ref_id": ref_id,
                "sub_action": sub_action,
                "basename": persisted.basename,
                "width_height": list(persisted.width_height),
            },
        }
        if transform_metadata:
            result["outputs"].update(transform_metadata)
        overlay_role = _overlay_role_from_metadata(transform_metadata)
        if overlay_role:
            result["outputs"]["overlay_role"] = overlay_role
        evidence = image_evidence_from_path(derived_ref_id, persisted.absolute_path)
        if evidence:
            result["image_evidence"] = [evidence]
        return result

    return handler


def _param_error(code: str, message: str, repair_hint: str | None = None) -> dict[str, Any]:
    """Retryable failure: the request shape is fixable; the run should continue."""
    error_payload: dict[str, Any] = {"code": code, "message": message}
    if repair_hint:
        error_payload["repair_hint"] = repair_hint
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": error_payload},
    }


def _validate_box_inputs(params: dict[str, Any], *, field_prefix: str = "params") -> dict[str, Any] | None:
    """Validate box/box_norm/adjust_px/adjust_norm shape on a params dict.

    Returns a retryable param-error result if anything is fixably wrong, else None.
    Does not require either box or box_norm to be present (callers decide that).

    Adjustment forms must match the geometry form so the agent's nudge is never
    silently dropped:
      - ``box``      ↔ ``adjust_px`` only
      - ``box_norm`` ↔ ``adjust_norm`` only
      - ``adjust_*`` without any box geometry is rejected
    """
    box = params.get("box")
    box_norm = params.get("box_norm")
    has_adjust_norm = "adjust_norm" in params and params.get("adjust_norm") is not None
    has_adjust_px = "adjust_px" in params and params.get("adjust_px") is not None

    if box is not None and box_norm is not None:
        return _param_error(
            "invalid_transform_params",
            f"{field_prefix}: provide either box or box_norm, not both.",
            repair_hint=f"Choose one geometry form: remove {field_prefix}.box or {field_prefix}.box_norm.",
        )

    # Mismatched adjustment forms — agent's nudge would be silently dropped otherwise.
    if box is not None and has_adjust_norm:
        return _param_error(
            "invalid_transform_params",
            f"{field_prefix}: adjust_norm cannot be used with pixel box.  Use adjust_px instead.",
            repair_hint=(
                f"Either change {field_prefix}.box → {field_prefix}.box_norm to keep "
                f"{field_prefix}.adjust_norm, or replace {field_prefix}.adjust_norm with "
                f"{field_prefix}.adjust_px (integer expand_x/expand_y/shift_x/shift_y in pixels)."
            ),
        )
    if box_norm is not None and has_adjust_px:
        return _param_error(
            "invalid_transform_params",
            f"{field_prefix}: adjust_px cannot be used with normalized box_norm.  Use adjust_norm instead.",
            repair_hint=(
                f"Either change {field_prefix}.box_norm → {field_prefix}.box to keep "
                f"{field_prefix}.adjust_px, or replace {field_prefix}.adjust_px with "
                f"{field_prefix}.adjust_norm (numeric expand_x/expand_y/shift_x/shift_y in 0..1 units)."
            ),
        )
    if box is None and box_norm is None and (has_adjust_norm or has_adjust_px):
        return _param_error(
            "invalid_transform_params",
            f"{field_prefix}: adjust_norm/adjust_px requires a box or box_norm to nudge.",
            repair_hint=(
                f"Provide {field_prefix}.box or {field_prefix}.box_norm so the adjustment has a target, "
                "or remove the adjust_* object."
            ),
        )

    if box is not None:
        err = _validate_box(box, field=f"{field_prefix}.box")
        if err:
            return _param_error(
                "invalid_transform_params", err,
                repair_hint=f"Use {field_prefix}.box = [x1, y1, x2, y2] with integer pixel coordinates.",
            )
    if box_norm is not None:
        err = _validate_box_norm(box_norm, field=f"{field_prefix}.box_norm")
        if err:
            return _param_error(
                "invalid_transform_params", err,
                repair_hint=(
                    f"Use {field_prefix}.box_norm = [x1, y1, x2, y2] where all values are in [0.0, 1.0] "
                    "and x1<x2, y1<y2.  Example: [0.0, 0.5, 1.0, 1.0] crops the bottom half."
                ),
            )
    if has_adjust_norm:
        err = _validate_adjust(params.get("adjust_norm"), field=f"{field_prefix}.adjust_norm")
        if err:
            return _param_error(
                "invalid_transform_params", err,
                repair_hint=(
                    f"{field_prefix}.adjust_norm accepts optional numeric expand_x, expand_y, shift_x, "
                    "shift_y in normalized [0..1] units.  Positive expand_* grows the box on both sides; "
                    "positive shift_x/y moves right/down."
                ),
            )
    if has_adjust_px:
        err = _validate_adjust(
            params.get("adjust_px"), field=f"{field_prefix}.adjust_px", require_integer=True
        )
        if err:
            return _param_error(
                "invalid_transform_params", err,
                repair_hint=(
                    f"{field_prefix}.adjust_px accepts optional integer expand_x, expand_y, shift_x, "
                    "shift_y in pixel units.  Positive expand_* grows the box on both sides; "
                    "positive shift_x/y moves right/down.  For sub-pixel-precision nudges, switch "
                    f"to {field_prefix}.box_norm + {field_prefix}.adjust_norm with normalized values."
                ),
            )
    return None


def _validate_params(sub_action: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Return a retryable param-error result dict if params are fixably wrong, else None."""
    if sub_action == "crop":
        box = params.get("box")
        box_norm = params.get("box_norm")
        if box is None and box_norm is None:
            return _param_error(
                "invalid_transform_params",
                "crop requires either params.box = [x1, y1, x2, y2] (pixel coordinates) "
                "or params.box_norm = [x1, y1, x2, y2] (normalized 0..1 relative to source dimensions).",
                repair_hint=(
                    "Provide params.box with absolute pixel coordinates, e.g. {\"box\": [100, 200, 400, 600]}, "
                    "or params.box_norm with normalized coordinates where 0.0 is the start and 1.0 is the end of that axis, "
                    "e.g. {\"box_norm\": [0.0, 0.5, 1.0, 1.0]} crops the bottom half.  "
                    "Optionally include adjust_norm or adjust_px with expand_x/expand_y/shift_x/shift_y "
                    "to nudge the box without recomputing coordinates from scratch."
                ),
            )
        err = _validate_box_inputs(params, field_prefix="params")
        if err:
            return err
    if sub_action == "zoom":
        # zoom accepts box, box_norm, or factor-only.  At least one must be present.
        box = params.get("box")
        box_norm = params.get("box_norm")
        factor = params.get("factor")
        if box is None and box_norm is None and factor is None:
            # Factor defaults to 2.0 when nothing is supplied — preserves existing behavior.
            pass
        if box is not None or box_norm is not None or "adjust_norm" in params or "adjust_px" in params:
            err = _validate_box_inputs(params, field_prefix="params")
            if err:
                return err
        if factor is not None:
            try:
                fval = float(factor)
            except (TypeError, ValueError):
                return _param_error(
                    "invalid_transform_params",
                    "params.factor must be numeric.",
                    repair_hint="Use params.factor = 2.0 (or another positive scale) for factor-only zoom.",
                )
            if fval <= 0.0:
                return _param_error(
                    "invalid_transform_params",
                    f"params.factor must be > 0; got {fval}.",
                    repair_hint="Use a positive scale factor such as 1.5 or 2.0.",
                )
    if sub_action == "annotate":
        annotations = params.get("annotations")
        if annotations is None:
            return _param_error(
                "invalid_transform_params",
                "annotate requires params.annotations as a non-empty list of annotation objects.",
                repair_hint=(
                    "Provide params.annotations = [{type: 'bbox'|'highlight'|'label', "
                    "box: [x1,y1,x2,y2] OR box_norm: [x1,y1,x2,y2], color: [R,G,B], text?: str, "
                    "adjust_px?: {...}, adjust_norm?: {...}}]."
                ),
            )
        if not isinstance(annotations, list):
            return _param_error(
                "invalid_transform_params",
                "params.annotations must be a list.",
                repair_hint="Wrap annotation objects in a JSON array.",
            )
        for i, ann in enumerate(annotations):
            if not isinstance(ann, dict):
                return _param_error(
                    "invalid_transform_params",
                    f"params.annotations[{i}] must be a JSON object.",
                    repair_hint="Each annotation is an object with type and box or box_norm.",
                )
            # Validate annotation type — unknown types would otherwise render nothing
            # but still appear in resolved_annotations, misleading the next turn.
            # Annotations without any geometry are intentionally permitted (skipped
            # silently in the apply path); type still must be valid when it is given.
            ann_type_raw = ann.get("type")
            if ann_type_raw is None or not isinstance(ann_type_raw, str) or not ann_type_raw.strip():
                return _param_error(
                    "invalid_transform_params",
                    f"params.annotations[{i}].type is required.",
                    repair_hint="Set type to 'highlight', 'bbox', or 'label'.",
                )
            ann_type = ann_type_raw.strip().lower()
            if ann_type not in _ANNOTATION_TYPES:
                return _param_error(
                    "invalid_transform_params",
                    f"params.annotations[{i}].type must be one of "
                    f"{sorted(_ANNOTATION_TYPES)}; got {ann_type_raw!r}.",
                    repair_hint=(
                        "Use type 'highlight' (filled rectangle), 'bbox' (outline), "
                        "or 'label' (text at the top-left of the box)."
                    ),
                )
            # ``label`` annotations require non-empty text — without it the renderer
            # draws nothing but would still report a resolved annotation, mis-signalling
            # to the next turn that a visual label exists.
            if ann_type == "label":
                text_raw = ann.get("text")
                if not isinstance(text_raw, str) or not text_raw.strip():
                    return _param_error(
                        "invalid_transform_params",
                        f"params.annotations[{i}].text is required and must be a non-empty string "
                        "when type == 'label'.",
                        repair_hint=(
                            f"Provide params.annotations[{i}].text with the label text to render at "
                            "the top-left of the box, e.g. {\"type\": \"label\", \"box_norm\": [...], "
                            "\"text\": \"Section 2\"}."
                        ),
                    )
            err = _validate_box_inputs(ann, field_prefix=f"params.annotations[{i}]")
            if err:
                return err
    if sub_action == "render_evidence_locators":
        locators = params.get("locators")
        if not isinstance(locators, list) or not locators:
            return _param_error(
                "invalid_transform_params",
                "render_evidence_locators requires params.locators as a non-empty list.",
                repair_hint="Pass params.locators as the agent-authored evidence_locators list for the selected source ref.",
            )
    if sub_action == "point_crops_scaffold":
        message = validate_point_crops_scaffold_params(params)
        if message is not None:
            return _param_error(
                "invalid_transform_params",
                message,
                repair_hint=point_crops_scaffold_repair_hint_for(message),
            )
    if sub_action == "point_crops":
        message = validate_point_crops_params(params)
        if message is not None:
            return _param_error(
                "invalid_transform_params",
                message,
                repair_hint=point_crops_repair_hint_for(message),
            )
    if sub_action == "point_crops_adjust":
        message = validate_point_crops_adjust_params(params)
        if message is not None:
            return _param_error(
                "invalid_transform_params",
                message,
                repair_hint=point_crops_adjust_repair_hint_for(message),
            )
    if sub_action == "point_crops_view":
        message = validate_point_crops_view_params(params)
        if message is not None:
            return _param_error(
                "invalid_transform_params",
                message,
                repair_hint=point_crops_view_repair_hint_for(message),
            )
    return None


def _resolve_source_path(
    *,
    ref_id: str,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
) -> tuple[Path | None, dict[str, Any] | None]:
    if ref_id.startswith(_IMAGE_ASSOC_PREFIX):
        raw = hydrate_source_image_context(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            ref_id=ref_id,
        )
        if raw.get("status") != "ok":
            return None, {"code": raw.get("code", "source_error"), "message": raw.get("message", "")}
        if not raw.get("exists"):
            return None, {"code": "source_image_not_found", "message": f"Source image file does not exist: {raw.get('absolute_path')}"}
        return Path(raw["absolute_path"]), None

    if ref_id.startswith(_IMAGE_DERIVED_PREFIX):
        desc = _load_derived_image_descriptor(dossier_id, transcription_id, workspace_key, ref_id)
        if desc is None:
            return None, {"code": "derived_ref_not_found", "message": "Derived image ref not found."}
        p = Path(str(desc.get("absolute_path") or ""))
        if not p.is_file():
            return None, {"code": "derived_image_missing", "message": str(p)}
        return p, None

    return None, {"code": "unsupported_ref_kind", "message": "transform_artifact only supports image:assoc:* and image:derived:* refs."}


def _attach_source_window_metadata(
    transform_metadata: dict[str, Any],
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    source_ref: str,
    sub_action: str,
) -> None:
    """Attach mechanical source-window edge metadata for crop and boxed zoom."""
    if sub_action not in {"crop", "zoom"}:
        return
    geo = transform_metadata.get("resolved_geometry")
    if not isinstance(geo, dict):
        return
    box_norm = geo.get("box_norm")
    if not isinstance(box_norm, (list, tuple)) or len(box_norm) != 4:
        return

    local_wh = geo.get("source_width_height")
    local_width_height = None
    if isinstance(local_wh, (list, tuple)) and len(local_wh) == 2:
        try:
            local_width_height = [int(local_wh[0]), int(local_wh[1])]
        except (TypeError, ValueError):
            local_width_height = None

    projection_ctx = resolve_root_projection_context(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_key=workspace_key,
        source_ref=source_ref,
        local_width_height=local_width_height,
    )
    transform_metadata["source_window"] = build_source_window(
        local_source_ref=source_ref,
        local_box_norm=[float(v) for v in box_norm],
        projection_ctx=projection_ctx,
    )


def _attach_rendered_ref(metadata: dict[str, Any], *, rendered_ref: str) -> None:
    rows = metadata.get("rendered_evidence_refs")
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            row["rendered_ref"] = rendered_ref


def _error_result(code: str, message: str) -> dict[str, Any]:
    """Non-retryable failure: a real invariant or missing-resource condition."""
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": code, "message": message}},
    }
