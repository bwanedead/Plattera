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

from .evidence_locator_rendering import build_locator_render_plan, summarize_locator
from .image_loading import hydrate_source_image_context, image_evidence_from_path
from .paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_derived_images_dir,
)
from .artifact_hydration import _load_derived_image_descriptor
from .root_projection import (
    copy_projection_fields,
    enrich_point_geometry_with_projection,
    resolve_root_projection_context,
)
from .coordinate_lattice import (
    DEFAULT_REFERENCE_COLS,
    DEFAULT_REFERENCE_ROWS,
    OVERLAY_ROLE_PLAIN_COORDINATE_REFERENCE,
    build_reference_cell_overlay_metadata,
    draw_reference_cell_coordinate_foundation,
)
from .point_crop_review_table import attach_review_table_to_crop_set
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
        "source_width_height": source_width_height,
        "points": list(crop_refs),
    }
    if previous_crop_set_overlay_ref:
        crop_set["previous_crop_set_overlay_ref"] = previous_crop_set_overlay_ref
    if adjustments_applied:
        crop_set["adjustments_applied"] = list(adjustments_applied)
    crop_set.update(_overlay_metadata_fields(transform_metadata))
    attach_review_table_to_crop_set(crop_set)

    (derived_dir / f"{master_uuid}_crop_set.json").write_text(
        json.dumps(crop_set, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    master_crop_set_meta: dict[str, Any] = {"points": list(crop_refs)}
    for key in ("review_rows", "review_lines", "overlay_role"):
        if key in crop_set:
            master_crop_set_meta[key] = crop_set[key]

    master_transform_metadata: dict[str, Any] = {
        "source_ref": source_ref,
        "show": show,
        "legend_height": legend_height,
        "source_width_height": source_width_height,
        "point_count": point_count,
        "crop_set": master_crop_set_meta,
    }
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
    for key in ("review_rows", "review_lines", "overlay_role"):
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
            source_path, resolve_error = _resolve_source_path(
                ref_id=adjust_bundle["source_ref"],
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
                source_ref=adjust_bundle["source_ref"],
                sub_action=sub_action,
                params=params,
                transform_metadata=transform_metadata,
                lineage={
                    "previous_crop_set_overlay_ref": adjust_bundle["previous_crop_set_overlay_ref"],
                    "adjustment_source_ref": adjust_bundle["adjustment_source_ref"],
                    "adjustments_applied": adjust_bundle["adjustments_applied"],
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

        # Apply transform
        try:
            derived_path, width_height, transform_metadata = _apply_transform(
                source_path,
                sub_action,
                params,
                source_ref_id=ref_id,
            )
        except _TransformParamError as exc:
            # Param errors discovered at transform time (e.g. after image open) are retryable.
            return _param_error("invalid_transform_params", str(exc), repair_hint=exc.repair_hint)
        except Exception as exc:
            return _error_result("transform_failed", f"Transform failed: {exc}")

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

        # Special multi-output handling for point_crops (Brief 1).
        # The apply step now returns PIL images + rich geometry in metadata (pure computation).
        # Handler is the single owner of all ref minting, file I/O, and descriptors.
        if sub_action == "point_crops":
            return _persist_point_crop_set(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_key=workspace_key,
                source_ref=ref_id,
                sub_action=sub_action,
                params=params,
                transform_metadata=transform_metadata,
            )

        # Normal single-output path for all other sub-actions
        derived_uuid = _uuid_mod.uuid4().hex
        derived_ref_id = f"{_IMAGE_DERIVED_PREFIX}{derived_uuid}"
        _attach_rendered_ref(transform_metadata, rendered_ref=derived_ref_id)
        descriptor: dict[str, Any] = {
            "ref_id": derived_ref_id,
            "parent_ref_id": ref_id,
            "sub_action": sub_action,
            "params": params,
            "transform_metadata": transform_metadata,
            "absolute_path": str(derived_path.resolve()),
            "basename": derived_path.name,
            "size_bytes": derived_path.stat().st_size if derived_path.exists() else None,
            "width_height": width_height,
        }
        try:
            derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_key)
            derived_dir.mkdir(parents=True, exist_ok=True)
            desc_path = derived_dir / f"{derived_uuid}.json"
            desc_path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            return _error_result("derived_persist_failed", f"Could not save derived descriptor: {exc}")

        result: dict[str, Any] = {
            "executed": True,
            "artifact_refs": [derived_ref_id],
            "outputs": {
                "derived_ref_id": derived_ref_id,
                "parent_ref_id": ref_id,
                "sub_action": sub_action,
                "basename": derived_path.name,
                "width_height": width_height,
            },
        }
        if transform_metadata:
            result["outputs"].update(transform_metadata)
        overlay_role = _overlay_role_from_metadata(transform_metadata)
        if overlay_role:
            result["outputs"]["overlay_role"] = overlay_role
        evidence = image_evidence_from_path(derived_ref_id, derived_path)
        if evidence:
            result["image_evidence"] = [evidence]
        return result

    return handler


class _TransformParamError(Exception):
    """Raised inside ``_apply_transform`` for fixable param problems."""

    def __init__(self, message: str, *, repair_hint: str | None = None) -> None:
        super().__init__(message)
        self.repair_hint = repair_hint


def _coerce_pixel_integer(v: Any) -> int | None:
    """Return ``v`` as an integer pixel value, or ``None`` if it is not a clean integer.

    Accepts: ``int`` (excluding bool), ``float`` that ``is_integer()`` (so JSON's
    loose ``5`` vs ``5.0`` distinction does not break agents).

    Rejects: ``bool`` (subclass of ``int``), fractional floats (``20.9``), strings
    (even numeric-looking like ``"5"``), and any other type.  Used to keep pixel
    geometry honest: fractional pixel coordinates would silently truncate and
    erase agent intent.  For fractional/normalized intent, the agent should use
    ``box_norm`` + ``adjust_norm``.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def _validate_box(box: Any, *, field: str = "params.box") -> str | None:
    """Return an error message string if *box* is not a valid 4-element pixel box."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return f"{field} must be a list of exactly 4 numbers [x1, y1, x2, y2]."
    vals: list[int] = []
    for v in box:
        coerced = _coerce_pixel_integer(v)
        if coerced is None:
            return (
                f"{field} values must be integer pixel coordinates (no fractional pixels, no bools, "
                f"no strings); got {v!r}.  Use {field.replace('.box', '.box_norm')} with normalized "
                "[0..1] values for fractional or sub-pixel-precision geometry."
            )
        vals.append(coerced)
    if vals[0] >= vals[2] or vals[1] >= vals[3]:
        return f"{field} requires x1 < x2 and y1 < y2; got {vals}."
    return None


def _validate_box_norm(box_norm: Any, *, field: str = "params.box_norm") -> str | None:
    """Return an error message string if *box_norm* is not a valid normalized 4-element list."""
    if not isinstance(box_norm, (list, tuple)) or len(box_norm) != 4:
        return f"{field} must be a list of exactly 4 numbers [x1, y1, x2, y2] in range 0..1."
    try:
        vals = [float(v) for v in box_norm]
    except (TypeError, ValueError):
        return f"{field} values must be numeric."
    if any(v < 0.0 or v > 1.0 for v in vals):
        return f"{field} values must be in [0.0, 1.0]; got {vals}."
    if vals[0] >= vals[2] or vals[1] >= vals[3]:
        return f"{field} requires x1 < x2 and y1 < y2; got {vals}."
    return None


_ADJUST_KEYS: frozenset[str] = frozenset({"expand_x", "expand_y", "shift_x", "shift_y"})

# Annotation types the renderer can actually draw.  An unknown type would
# otherwise resolve geometry, render nothing, and still appear in
# resolved_annotations — misleading the next turn about what was drawn.
_ANNOTATION_TYPES: frozenset[str] = frozenset({"highlight", "bbox", "label"})


def _validate_adjust(adjust: Any, *, field: str, require_integer: bool = False) -> str | None:
    """Validate an adjust_norm or adjust_px object shape (does not range-check).

    When ``require_integer`` is True (used for ``adjust_px``), fractional values
    are rejected: pixel units are naturally whole, and silently truncating a
    fractional value (e.g. ``shift_x: 0.9`` → ``0``) would erase agent intent.
    Integer-valued floats like ``5.0`` are accepted to handle JSON's loose
    int/float distinction.
    """
    if adjust is None:
        return None
    if not isinstance(adjust, dict):
        return f"{field} must be a JSON object with optional expand_x, expand_y, shift_x, shift_y."
    for k, v in adjust.items():
        if k not in _ADJUST_KEYS:
            return f"{field} has unknown key {k!r}; allowed: {sorted(_ADJUST_KEYS)}."
        # Booleans are a subclass of int in Python; reject them explicitly so
        # adjust values cannot accidentally smuggle non-numeric intent.
        if isinstance(v, bool):
            return f"{field}.{k} must be numeric, not bool."
        try:
            float(v)
        except (TypeError, ValueError):
            return f"{field}.{k} must be numeric."
        if require_integer and _coerce_pixel_integer(v) is None:
            return (
                f"{field}.{k} must be an integer pixel value (no fractional pixels); got {v!r}.  "
                f"Use {field.replace('adjust_px', 'adjust_norm')} with a box_norm for sub-pixel-precision "
                "normalized nudges."
            )
    return None


def _apply_adjust_norm(
    box_norm: list[float],
    adjust: dict[str, Any] | None,
) -> tuple[list[float], dict[str, float]]:
    """Apply normalized adjustments to a box_norm.  Returns (new_box_norm, applied_dict).

    Semantics (mirroring brief):
      - expand_x grows both left and right by the given amount (negative shrinks)
      - expand_y grows both top and bottom by the given amount (negative shrinks)
      - shift_x positive moves right, negative moves left
      - shift_y positive moves down, negative moves up
    Clamping to [0,1] happens after, in the resolver.
    """
    applied: dict[str, float] = {}
    if not isinstance(adjust, dict):
        return list(box_norm), applied
    expand_x = float(adjust.get("expand_x", 0.0) or 0.0)
    expand_y = float(adjust.get("expand_y", 0.0) or 0.0)
    shift_x = float(adjust.get("shift_x", 0.0) or 0.0)
    shift_y = float(adjust.get("shift_y", 0.0) or 0.0)
    x1, y1, x2, y2 = (float(v) for v in box_norm)
    x1 = x1 - expand_x + shift_x
    x2 = x2 + expand_x + shift_x
    y1 = y1 - expand_y + shift_y
    y2 = y2 + expand_y + shift_y
    if expand_x:
        applied["expand_x"] = expand_x
    if expand_y:
        applied["expand_y"] = expand_y
    if shift_x:
        applied["shift_x"] = shift_x
    if shift_y:
        applied["shift_y"] = shift_y
    return [x1, y1, x2, y2], applied


def _apply_adjust_px(
    box: list[int],
    adjust: dict[str, Any] | None,
) -> tuple[list[int], dict[str, int]]:
    """Apply pixel adjustments to a box.  Returns (new_box, applied_dict)."""
    applied: dict[str, int] = {}
    if not isinstance(adjust, dict):
        return list(box), applied
    expand_x = int(adjust.get("expand_x", 0) or 0)
    expand_y = int(adjust.get("expand_y", 0) or 0)
    shift_x = int(adjust.get("shift_x", 0) or 0)
    shift_y = int(adjust.get("shift_y", 0) or 0)
    x1, y1, x2, y2 = (int(v) for v in box)
    x1 = x1 - expand_x + shift_x
    x2 = x2 + expand_x + shift_x
    y1 = y1 - expand_y + shift_y
    y2 = y2 + expand_y + shift_y
    if expand_x:
        applied["expand_x"] = expand_x
    if expand_y:
        applied["expand_y"] = expand_y
    if shift_x:
        applied["shift_x"] = shift_x
    if shift_y:
        applied["shift_y"] = shift_y
    return [x1, y1, x2, y2], applied


def _resolve_box_geometry(
    *,
    box: Any = None,
    box_norm: Any = None,
    adjust_px: Any = None,
    adjust_norm: Any = None,
    image_width: int,
    image_height: int,
    field_prefix: str = "params",
) -> tuple[list[int], dict[str, Any]]:
    """Resolve final pixel box from inputs and return (box_px, resolved_geometry_dict).

    Accepts either pixel ``box`` or normalized ``box_norm`` (not both — that is an
    explicit retryable error).  Optionally applies ``adjust_px`` (pixel-form box)
    or ``adjust_norm`` (norm-form box).  Clamps to image bounds, then validates
    the final box has strictly positive width and height.  Returns both pixel and
    normalized forms plus the metadata an agent needs to refine the call.

    Raises ``_TransformParamError`` (retryable) on conflicting inputs, missing
    inputs, or post-adjustment collapse.
    """
    if box is not None and box_norm is not None:
        raise _TransformParamError(
            f"{field_prefix}: provide either box or box_norm, not both.",
            repair_hint=f"Choose one geometry form: remove {field_prefix}.box or {field_prefix}.box_norm.",
        )
    if box is None and box_norm is None:
        raise _TransformParamError(
            f"{field_prefix} requires box or box_norm.",
            repair_hint=(
                f"Provide {field_prefix}.box = [x1, y1, x2, y2] (pixel) or "
                f"{field_prefix}.box_norm = [x1, y1, x2, y2] (normalized 0..1)."
            ),
        )

    original_input: dict[str, Any] = {}
    adjustments_applied: dict[str, Any] = {}

    if box_norm is not None:
        vals_n = [float(v) for v in box_norm]
        original_input["box_norm"] = list(vals_n)
        if adjust_norm is not None:
            vals_n, applied_norm = _apply_adjust_norm(vals_n, adjust_norm)
            if applied_norm:
                adjustments_applied["adjust_norm"] = applied_norm
        # Clamp to [0,1]
        vals_n = [max(0.0, min(1.0, v)) for v in vals_n]
        # Check positive area in norm space before converting
        if vals_n[0] >= vals_n[2] or vals_n[1] >= vals_n[3]:
            raise _TransformParamError(
                f"{field_prefix}: adjusted box_norm collapsed to zero/negative area; got {vals_n}.",
                repair_hint=(
                    "Reduce shrink magnitudes (negative expand_*) or shift magnitudes so the final "
                    "box keeps x1<x2 and y1<y2 after clamping to [0,1]."
                ),
            )
        # ``round()`` (not ``int``) tolerates floating-point noise from adjust math
        # (e.g. 0.3 - 0.1 = 0.19999999999...) and preserves the agent's intended
        # box edges.  Truncation here would silently shift edges by 1 px under FP drift.
        px = [
            round(vals_n[0] * image_width),
            round(vals_n[1] * image_height),
            round(vals_n[2] * image_width),
            round(vals_n[3] * image_height),
        ]
    else:
        px = [int(v) for v in box]
        original_input["box"] = list(px)
        if adjust_px is not None:
            px, applied_px = _apply_adjust_px(px, adjust_px)
            if applied_px:
                adjustments_applied["adjust_px"] = applied_px
        # Clamp to image bounds
        px = [
            max(0, min(image_width, px[0])),
            max(0, min(image_height, px[1])),
            max(0, min(image_width, px[2])),
            max(0, min(image_height, px[3])),
        ]

    if px[0] >= px[2] or px[1] >= px[3]:
        raise _TransformParamError(
            f"{field_prefix}: resolved pixel box collapsed to zero/negative area after clamping; got {px}.",
            repair_hint=(
                "Choose a region inside the image with strictly positive width and height after "
                "any adjustments.  Image bounds are [0,0,width,height]."
            ),
        )

    # Compute resolved normalized form from the final pixel box (canonical roundtrip).
    safe_w = image_width if image_width > 0 else 1
    safe_h = image_height if image_height > 0 else 1
    resolved_norm = [
        round(px[0] / safe_w, 6),
        round(px[1] / safe_h, 6),
        round(px[2] / safe_w, 6),
        round(px[3] / safe_h, 6),
    ]

    geometry: dict[str, Any] = {
        "box": list(px),
        "box_norm": resolved_norm,
        "source_width_height": [image_width, image_height],
        "input": original_input,
    }
    if adjustments_applied:
        geometry["adjustments_applied"] = adjustments_applied
    return list(px), geometry


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


def _apply_transform(
    source: Path,
    sub_action: str,
    params: dict[str, Any],
    *,
    source_ref_id: str,
) -> tuple[Path, tuple[int, int] | None, dict[str, Any]]:
    """Apply a PIL transform and save result to a temp path alongside the source; return (path, wh)."""
    from PIL import Image, ImageDraw, ImageFont  # type: ignore[import]

    img = Image.open(source)
    transform_metadata: dict[str, Any] = {}

    if sub_action == "crop":
        resolved_box, geo = _resolve_box_geometry(
            box=params.get("box"),
            box_norm=params.get("box_norm"),
            adjust_px=params.get("adjust_px"),
            adjust_norm=params.get("adjust_norm"),
            image_width=img.width,
            image_height=img.height,
            field_prefix="params",
        )
        img = img.crop(tuple(resolved_box))
        transform_metadata["resolved_geometry"] = geo

    elif sub_action == "expand":
        padding = params.get("padding", [0, 0, 0, 0])
        if isinstance(padding, int):
            padding = [padding] * 4
        if not isinstance(padding, (list, tuple)) or len(padding) != 4:
            raise ValueError("expand requires params.padding = [top, right, bottom, left] or single int")
        top, right, bottom, left = (int(v) for v in padding)
        fill = params.get("fill", "white")
        new_w = img.width + left + right
        new_h = img.height + top + bottom
        out = Image.new(img.mode, (new_w, new_h), fill)
        out.paste(img, (left, top))
        img = out

    elif sub_action == "zoom":
        # Three accepted shapes:
        #   1. box (+ optional adjust_px) + optional factor: crop to box, then scale by factor (default 1.0)
        #   2. box_norm (+ optional adjust_norm) + optional factor: crop to normalized box, then scale by factor
        #   3. factor only: scale the whole image (preserves prior factor-only behavior)
        box = params.get("box")
        box_norm = params.get("box_norm")
        factor_raw = params.get("factor")
        has_box_input = box is not None or box_norm is not None
        if has_box_input:
            resolved_box, geo = _resolve_box_geometry(
                box=box,
                box_norm=box_norm,
                adjust_px=params.get("adjust_px"),
                adjust_norm=params.get("adjust_norm"),
                image_width=img.width,
                image_height=img.height,
                field_prefix="params",
            )
            img = img.crop(tuple(resolved_box))
            # After cropping, optional factor scales the cropped region.
            zoom_factor = float(factor_raw) if factor_raw is not None else 1.0
            if zoom_factor != 1.0:
                new_w = max(1, int(img.width * zoom_factor))
                new_h = max(1, int(img.height * zoom_factor))
                img = img.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]
                geo["factor_applied"] = zoom_factor
            transform_metadata["resolved_geometry"] = geo
        else:
            # Factor-only zoom — no box geometry to resolve.
            zoom_factor = float(factor_raw) if factor_raw is not None else 2.0
            new_w = max(1, int(img.width * zoom_factor))
            new_h = max(1, int(img.height * zoom_factor))
            img = img.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]
            transform_metadata["factor_applied"] = zoom_factor

    elif sub_action == "reference_overlay":
        # Legacy compatibility path: reuse the shared reference-cell foundation.
        cols = max(2, int(params.get("cols", DEFAULT_REFERENCE_COLS)))
        rows = max(2, int(params.get("rows", DEFAULT_REFERENCE_ROWS)))
        line_color_raw = params.get("line_color", [140, 140, 140])
        label_color_raw = params.get("label_color", [180, 0, 0])
        if isinstance(line_color_raw, list) and len(line_color_raw) >= 3:
            line_color: tuple[int, int, int] = tuple(int(v) for v in line_color_raw[:3])  # type: ignore[assignment]
        else:
            line_color = (140, 140, 140)
        if isinstance(label_color_raw, list) and len(label_color_raw) >= 3:
            label_color: tuple[int, int, int] = tuple(int(v) for v in label_color_raw[:3])  # type: ignore[assignment]
        else:
            label_color = (180, 0, 0)

        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        draw_reference_cell_coordinate_foundation(
            draw,
            img.width,
            img.height,
            cols=cols,
            rows=rows,
            cell_line_color=line_color,
            cell_label_text_color=label_color,
        )
        transform_metadata["overlay"] = build_reference_cell_overlay_metadata(
            overlay_role=OVERLAY_ROLE_PLAIN_COORDINATE_REFERENCE,
            cols=cols,
            rows=rows,
        )

    elif sub_action == "annotate":
        annotations = params.get("annotations", [])
        if not isinstance(annotations, list):
            raise _TransformParamError(
                "params.annotations must be a list of annotation objects.",
                repair_hint="Wrap annotation objects in a JSON array.",
            )
        img = img.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        resolved_annotations: list[dict[str, Any]] = []
        for ann_idx, ann in enumerate(annotations):
            if not isinstance(ann, dict):
                continue
            ann_type = str(ann.get("type") or "").lower()
            has_box = ann.get("box") is not None
            has_box_norm = ann.get("box_norm") is not None
            if not has_box and not has_box_norm:
                # Skip annotations with no geometry — consistent with prior behavior.
                continue
            resolved_box, geo = _resolve_box_geometry(
                box=ann.get("box"),
                box_norm=ann.get("box_norm"),
                adjust_px=ann.get("adjust_px"),
                adjust_norm=ann.get("adjust_norm"),
                image_width=img.width,
                image_height=img.height,
                field_prefix=f"params.annotations[{ann_idx}]",
            )
            b = tuple(resolved_box)
            color = ann.get("color", (255, 255, 0))
            if isinstance(color, list):
                color = tuple(color)
            if ann_type == "highlight":
                alpha = int(ann.get("alpha", 100))
                fill_color = (*color[:3], alpha) if len(color) >= 3 else (255, 255, 0, alpha)  # type: ignore[misc]
                draw.rectangle(b, fill=fill_color)
            elif ann_type == "bbox":
                outline_color = (*color[:3], 255) if len(color) >= 3 else (255, 0, 0, 255)  # type: ignore[misc]
                width = int(ann.get("width", 2))
                draw.rectangle(b, outline=outline_color, width=width)
            elif ann_type == "label":
                text = str(ann.get("text", ""))
                if text:
                    draw.text((b[0], max(0, b[1] - 16)), text, fill=(255, 0, 0, 255))
            resolved_annotations.append({
                "index": ann_idx,
                "type": ann_type,
                "resolved_geometry": geo,
            })
        img = Image.alpha_composite(img, overlay).convert("RGB")
        if resolved_annotations:
            transform_metadata["resolved_annotations"] = resolved_annotations

    elif sub_action == "render_evidence_locators":
        plan = build_locator_render_plan(
            source_ref=source_ref_id,
            locators=list(params.get("locators") or []),
            image_width=img.width,
            image_height=img.height,
        )
        img = img.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for ann in plan["annotations"]:
            b = tuple(int(v) for v in ann["box"])
            color = tuple(ann.get("color") or [255, 0, 0])
            ann_type = ann.get("type")
            if ann_type == "highlight":
                alpha = int(ann.get("alpha", 90))
                draw.rectangle(b, fill=(*color[:3], alpha))
            elif ann_type == "bbox":
                draw.rectangle(b, outline=(*color[:3], 255), width=int(ann.get("width", 3)))
            elif ann_type == "label" and ann.get("text"):
                draw.text((b[0], max(0, b[1] - 16)), str(ann["text"]), fill=(*color[:3], 255))
        img = Image.alpha_composite(img, overlay).convert("RGB")
        locator_summaries = [
            summarize_locator(locator, index=i)
            for i, locator in enumerate(params.get("locators") or [])
            if isinstance(locator, dict)
        ]
        transform_metadata = {
            "rendered_evidence_refs": [
                {
                    "source_ref": source_ref_id,
                    "rendered_ref": None,
                    "locator_count": len(params.get("locators") or []),
                    "rendered_locator_count": len(plan["rendered_locators"]),
                    "summary_only_locator_count": len(plan["summary_only_locators"]),
                    "unsupported_locator_count": len(plan["unsupported_locators"]),
                }
            ],
            "rendered_locators": plan["rendered_locators"],
            "summary_only_locators": plan["summary_only_locators"],
            "unsupported_locators": plan["unsupported_locators"],
            "locator_summaries": locator_summaries,
        }

    elif sub_action == "point_crops":
        try:
            transform_metadata = compute_point_crops(img, params)
        except PointCropParamError as exc:
            raise _TransformParamError(str(exc), repair_hint=exc.repair_hint) from exc
        wh = (transform_metadata["master_pil"].width, transform_metadata["master_pil"].height)
        return source, wh, transform_metadata

    out_suffix = ".png"
    out_path = source.parent / (source.stem + f"_derived_{_uuid_mod.uuid4().hex[:8]}{out_suffix}")
    img.save(out_path)
    wh: tuple[int, int] | None = (img.width, img.height)
    return out_path, wh, transform_metadata


def _attach_rendered_ref(metadata: dict[str, Any], *, rendered_ref: str) -> None:
    rows = metadata.get("rendered_evidence_refs")
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            row["rendered_ref"] = rendered_ref


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
