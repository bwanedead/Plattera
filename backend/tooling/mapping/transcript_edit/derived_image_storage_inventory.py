"""Read-only inventory for STORAGE-BR-004 derived-image storage audit.

Owns path safety helpers, workspace discovery, descriptor/image scanning,
canonical/legacy originals labeling, and conflicting-identity detection.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from config import paths as config_paths

from .derived_image_rendering import compute_image_identity

# Production legacy writer used ``{stem}_derived_{8 hex}.png`` beside originals.
_LEGACY_DERIVED_RE = re.compile(r".+_derived_[0-9a-fA-F]{8}\.png$")
_DERIVED_REF_PREFIX = "image:derived:"


def derived_uuid_from_ref(ref_id: str | None) -> str | None:
    """Return the opaque UUID stem from ``image:derived:<uuid>``, or None."""
    if not isinstance(ref_id, str) or not ref_id.startswith(_DERIVED_REF_PREFIX):
        return None
    opaque = ref_id[len(_DERIVED_REF_PREFIX) :].strip()
    return opaque or None


def stems_agree_for_run_owned(
    *,
    ref_id: str | None,
    descriptor_stem: str,
    image_stem: str,
) -> bool:
    """True iff descriptor stem, ref UUID, and PNG stem are identical."""
    opaque = derived_uuid_from_ref(ref_id)
    if opaque is None:
        return False
    return descriptor_stem == opaque and image_stem == opaque


def rel_coord(path: Path | None, root: Path) -> str | None:
    """Return forward-slash relative path from *root* to resolved *path*, or None."""
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def is_safe_under(path: Path, root: Path) -> bool:
    """True iff *path* is not a symlink and resolves inside *root*."""
    if path.is_symlink() or os.path.islink(path):
        return False
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_inside_dir(path: Path, parent: Path) -> bool:
    """True iff resolved *path* is under resolved *parent* (exact directory tree)."""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def compute_identity_safe(path: Path) -> dict[str, Any]:
    """Return image identity dict from *path*, or ``{}`` on any failure."""
    try:
        return compute_image_identity(path=path)
    except Exception:
        return {}


def make_record(
    *,
    ref_id: str | None,
    storage_posture: str,
    abs_image_path: Path | None,
    abs_descriptor_path: Path | None,
    identity: dict[str, Any],
    sub_action: str | None,
    parent_ref_id: str | None,
    params: Any,
    transform_metadata: Any,
    dossier_id: str,
    tx_id: str,
    ws_id: str,
    obj: dict[str, Any] | None,
    dossiers_root: Path,
) -> dict[str, Any]:
    return {
        "ref_id": ref_id,
        "storage_posture": storage_posture,
        "reconstruction_posture": "not_attempted_incomplete_recipe",
        "reference_posture": "unreferenced_observed",
        "relative_image_path": rel_coord(abs_image_path, dossiers_root),
        "relative_descriptor_path": rel_coord(abs_descriptor_path, dossiers_root),
        "content_sha256": identity.get("content_sha256"),
        "pixel_sha256": identity.get("pixel_sha256"),
        "size_bytes": identity.get("size_bytes"),
        "sub_action": sub_action,
        "byte_equal_to_reconstruction": None,
        "recipe_fingerprint": None,
        "parent_ref_id": parent_ref_id,
        "_abs_image_path": abs_image_path,
        "_abs_descriptor_path": abs_descriptor_path,
        "_params": params if isinstance(params, dict) else None,
        "_transform_metadata": transform_metadata if isinstance(transform_metadata, dict) else None,
        "_dossier_id": dossier_id,
        "_tx_id": tx_id,
        "_ws_id": ws_id,
        "_obj": obj,
        "_reference_source_kind": None,
    }


def iter_derived_images_dirs(
    dossier_id: str | None,
    transcription_id: str | None,
    workspace_id: str | None,
    all_dossiers: bool,
) -> list[tuple[str, str, str, Path]]:
    """Return ``(dossier_id, tx_id, ws_id, derived_images_dir)`` for each workspace in scope."""
    results: list[tuple[str, str, str, Path]] = []

    def _add_dossier(did: str) -> None:
        d_root = config_paths.dossiers_transcript_edit_artifacts_root(did)
        if not d_root.is_dir():
            return
        try:
            tx_dirs = sorted(d_root.iterdir())
        except OSError:
            return
        for tx_dir in tx_dirs:
            if not tx_dir.is_dir():
                continue
            tid = tx_dir.name
            if transcription_id and tid != transcription_id:
                continue
            try:
                ws_dirs = sorted(tx_dir.iterdir())
            except OSError:
                continue
            for ws_dir in ws_dirs:
                if not ws_dir.is_dir():
                    continue
                wid = ws_dir.name
                if workspace_id and wid != workspace_id:
                    continue
                di_dir = ws_dir / "derived_images"
                if di_dir.is_dir():
                    results.append((did, tid, wid, di_dir))

    if all_dossiers:
        te_root = config_paths.dossiers_transcript_edit_artifacts_root()
        if te_root.is_dir():
            try:
                for d_dir in sorted(te_root.iterdir()):
                    if d_dir.is_dir():
                        _add_dossier(d_dir.name)
            except OSError:
                pass
    elif dossier_id:
        _add_dossier(dossier_id)

    return results


def scan_derived_images_dir(
    dossier_id: str,
    tx_id: str,
    ws_id: str,
    di_dir: Path,
    dossiers_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan one ``derived_images/`` directory. Returns ``(records, diagnostics)``."""
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    try:
        all_entries = list(di_dir.iterdir())
    except OSError:
        diagnostics.append(
            {"code": "directory_unreadable", "relative_path": rel_coord(di_dir, dossiers_root)}
        )
        return records, diagnostics

    json_files = sorted(
        p
        for p in all_entries
        if p.is_file() and p.suffix == ".json" and not p.name.endswith("_crop_set.json")
    )
    png_files = sorted(p for p in all_entries if p.is_file() and p.suffix == ".png")
    png_consumed: set[Path] = set()

    for jf in json_files:
        if jf.is_symlink() or os.path.islink(jf):
            diagnostics.append(
                {"code": "symlink_rejected", "relative_path": rel_coord(jf, dossiers_root)}
            )
            continue
        if not is_safe_under(jf, dossiers_root):
            diagnostics.append(
                {
                    "code": "external_or_unsafe_path",
                    "relative_path": rel_coord(jf, dossiers_root),
                }
            )
            continue

        try:
            obj: Any = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            diagnostics.append(
                {"code": "malformed_json", "relative_path": rel_coord(jf, dossiers_root)}
            )
            continue

        if not isinstance(obj, dict):
            diagnostics.append(
                {"code": "malformed_json", "relative_path": rel_coord(jf, dossiers_root)}
            )
            continue

        ref_id: str | None = obj.get("ref_id") if isinstance(obj.get("ref_id"), str) else None
        parent_ref_id: str | None = (
            obj.get("parent_ref_id") if isinstance(obj.get("parent_ref_id"), str) else None
        )
        sub_action: str | None = (
            obj.get("sub_action") if isinstance(obj.get("sub_action"), str) else None
        )
        params: Any = obj.get("params")
        transform_metadata: Any = obj.get("transform_metadata")

        if not ref_id:
            diagnostics.append(
                {
                    "code": "missing_field",
                    "relative_path": rel_coord(jf, dossiers_root),
                    "detail": {"field": "ref_id"},
                }
            )

        png_path: Path | None = None
        abs_path_str = obj.get("absolute_path")
        if isinstance(abs_path_str, str) and abs_path_str:
            candidate = Path(abs_path_str)
            if candidate.is_file():
                png_path = candidate
        if png_path is None:
            fallback = di_dir / f"{jf.stem}.png"
            if fallback.is_file():
                png_path = fallback

        if png_path is not None:
            png_consumed.add(png_path)
            if png_path.is_symlink() or os.path.islink(png_path):
                storage_posture = "external_or_unsafe"
                diagnostics.append(
                    {
                        "code": "symlink_rejected",
                        "relative_path": rel_coord(png_path, dossiers_root),
                    }
                )
            elif not is_safe_under(png_path, dossiers_root) or not is_inside_dir(png_path, di_dir):
                # Run-owned claim requires the image inside this exact derived_images/.
                storage_posture = "external_or_unsafe"
                diagnostics.append(
                    {
                        "code": "external_or_unsafe_path",
                        "relative_path": rel_coord(png_path, dossiers_root),
                    }
                )
            elif not stems_agree_for_run_owned(
                ref_id=ref_id,
                descriptor_stem=jf.stem,
                image_stem=png_path.stem,
            ):
                storage_posture = "conflicting_identity"
                diagnostics.append(
                    {
                        "code": "conflicting_descriptor_image_identity",
                        "relative_path": rel_coord(jf, dossiers_root),
                        "detail": {
                            "descriptor_stem": jf.stem,
                            "image_stem": png_path.stem,
                            "ref_id": ref_id,
                        },
                    }
                )
            else:
                storage_posture = "run_owned"
        else:
            storage_posture = "missing_image"

        identity = (
            compute_identity_safe(png_path)
            if (png_path and storage_posture in {"run_owned", "conflicting_identity"})
            else {}
        )

        rec = make_record(
            ref_id=ref_id,
            storage_posture=storage_posture,
            abs_image_path=png_path,
            abs_descriptor_path=jf,
            identity=identity,
            sub_action=sub_action,
            parent_ref_id=parent_ref_id,
            params=params,
            transform_metadata=transform_metadata,
            dossier_id=dossier_id,
            tx_id=tx_id,
            ws_id=ws_id,
            obj=obj,
            dossiers_root=dossiers_root,
        )
        if storage_posture == "conflicting_identity":
            rec["reference_posture"] = "reference_ambiguous"
            rec["reconstruction_posture"] = "not_attempted_incomplete_recipe"
        records.append(rec)

    for png_path in png_files:
        if png_path in png_consumed:
            continue
        if png_path.is_symlink() or os.path.islink(png_path):
            storage_posture = "external_or_unsafe"
            diagnostics.append(
                {
                    "code": "symlink_rejected",
                    "relative_path": rel_coord(png_path, dossiers_root),
                }
            )
        elif not is_safe_under(png_path, dossiers_root) or not is_inside_dir(png_path, di_dir):
            storage_posture = "external_or_unsafe"
        else:
            storage_posture = "missing_descriptor"

        identity = compute_identity_safe(png_path) if storage_posture == "missing_descriptor" else {}
        records.append(
            make_record(
                ref_id=None,
                storage_posture=storage_posture,
                abs_image_path=png_path,
                abs_descriptor_path=None,
                identity=identity,
                sub_action=None,
                parent_ref_id=None,
                params=None,
                transform_metadata=None,
                dossier_id=dossier_id,
                tx_id=tx_id,
                ws_id=ws_id,
                obj=None,
                dossiers_root=dossiers_root,
            )
        )

    return records, diagnostics


def scan_originals(dossiers_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Scan ``images/original/`` for legacy derived images and canonical source images."""
    originals_root = config_paths.dossiers_original_images_root()
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    if not originals_root.is_dir():
        return records, diagnostics

    try:
        entries = sorted(originals_root.iterdir())
    except OSError:
        return records, diagnostics

    image_suffixes = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
    for p in entries:
        if not p.is_file() or p.suffix.lower() not in image_suffixes:
            continue
        if p.is_symlink() or os.path.islink(p):
            storage_posture = "external_or_unsafe"
            diagnostics.append(
                {"code": "symlink_rejected", "relative_path": rel_coord(p, dossiers_root)}
            )
        elif not is_safe_under(p, dossiers_root):
            storage_posture = "external_or_unsafe"
        elif p.suffix.lower() == ".png" and _LEGACY_DERIVED_RE.match(p.name):
            storage_posture = "legacy_source_adjacent"
        else:
            storage_posture = "canonical_source"

        identity = (
            compute_identity_safe(p)
            if storage_posture in {"legacy_source_adjacent", "canonical_source"}
            else {}
        )
        records.append(
            make_record(
                ref_id=None,
                storage_posture=storage_posture,
                abs_image_path=p,
                abs_descriptor_path=None,
                identity=identity,
                sub_action=None,
                parent_ref_id=None,
                params=None,
                transform_metadata=None,
                dossier_id="",
                tx_id="",
                ws_id="",
                obj=None,
                dossiers_root=dossiers_root,
            )
        )

    return records, diagnostics


def flag_conflicting_identity(
    records: list[dict[str, Any]], diagnostics: list[dict[str, Any]]
) -> None:
    """Mutate records: mark ``conflicting_identity`` / ``reference_ambiguous`` on collisions."""
    ref_to_idxs: dict[str, list[int]] = defaultdict(list)
    path_to_idxs: dict[str, list[int]] = defaultdict(list)

    for i, rec in enumerate(records):
        rid = rec.get("ref_id")
        if rid and rec["storage_posture"] not in ("canonical_source", "legacy_source_adjacent"):
            ref_to_idxs[rid].append(i)
        ip = rec.get("relative_image_path")
        if ip:
            path_to_idxs[ip].append(i)

    bad: set[int] = set()
    for rid, idxs in ref_to_idxs.items():
        if len(idxs) > 1:
            bad.update(idxs)
            diagnostics.append(
                {
                    "code": "conflicting_ref_id",
                    "detail": {"ref_id": rid, "duplicate_count": len(idxs)},
                }
            )
    for ip, idxs in path_to_idxs.items():
        if len(idxs) > 1:
            bad.update(idxs)

    for i in bad:
        records[i]["storage_posture"] = "conflicting_identity"
        records[i]["reference_posture"] = "reference_ambiguous"
        records[i]["reconstruction_posture"] = "not_attempted_incomplete_recipe"
