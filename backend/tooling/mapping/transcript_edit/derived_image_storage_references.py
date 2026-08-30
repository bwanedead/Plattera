"""Structural reference indexing for STORAGE-BR-004 (JSON fields only; no prose)."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from config import paths as config_paths

from .artifact_ref_contract import (
    AUDIT_COLLECTION_REF_KEYS,
    AUDIT_MAPPING_REF_KEYS,
    AUDIT_SINGLE_REF_KEYS,
)
from .derived_image_storage_inventory import rel_coord

# Exact leaf derived refs (uuid4 hex = 32).
_DERIVED_LEAF_RE = re.compile(r"^image:derived:[0-9a-fA-F]{32}$")

_KIND_PRIORITY = (
    "workspace_working",
    "workspace_output",
    "workspace_manifest",
    "dossier_artifact",
    "crop_set_sidecar",
    "harness_audit_root",
    "derived_descriptor",
)


def leaf_from_qualified_ref(value: str) -> str | None:
    """Extract leaf_ref from ``dossier_segment:<sid>:run:<tid>:<leaf>``, or None."""
    key = str(value or "").strip()
    prefix = "dossier_segment:"
    marker = ":run:"
    if not key.startswith(prefix):
        return None
    rest = key[len(prefix) :]
    at = rest.find(marker)
    if at <= 0:
        return None
    after = rest[at + len(marker) :]
    colon = after.find(":")
    if colon <= 0:
        return None
    leaf = after[colon + 1 :].strip()
    return leaf or None


def as_derived_leaf_ref(value: str) -> str | None:
    """Return exact ``image:derived:<32hex>`` from a leaf or qualified wrapper, else None."""
    s = str(value or "").strip()
    if _DERIVED_LEAF_RE.match(s):
        return s
    leaf = leaf_from_qualified_ref(s)
    if leaf and _DERIVED_LEAF_RE.match(leaf):
        return leaf
    return None


def iter_structural_derived_refs(node: Any) -> Iterator[str]:
    """Yield derived leaf refs found only under known structural ref keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in AUDIT_SINGLE_REF_KEYS and isinstance(value, str):
                hit = as_derived_leaf_ref(value)
                if hit:
                    yield hit
            elif key in AUDIT_COLLECTION_REF_KEYS and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        hit = as_derived_leaf_ref(item)
                        if hit:
                            yield hit
                    else:
                        yield from iter_structural_derived_refs(item)
            elif key in AUDIT_MAPPING_REF_KEYS and isinstance(value, dict):
                for map_val in value.values():
                    if isinstance(map_val, str):
                        hit = as_derived_leaf_ref(map_val)
                        if hit:
                            yield hit
                    else:
                        yield from iter_structural_derived_refs(map_val)
            else:
                yield from iter_structural_derived_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_structural_derived_refs(item)


def _scan_json_file(
    path: Path,
    kind: str,
    ref_map: dict[str, list[tuple[str, str]]],
    dossiers_root: Path,
) -> None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    rel = rel_coord(path, dossiers_root) or path.as_posix()
    for ref in iter_structural_derived_refs(obj):
        entry = (rel, kind)
        if entry not in ref_map[ref]:
            ref_map[ref].append(entry)


def build_reference_index(
    records: list[dict[str, Any]],
    scope_dirs: list[tuple[str, str, str, Path]],
    dossier_id: str | None,
    harness_audit_roots: list[Path] | None,
    dossiers_root: Path,
) -> dict[str, list[tuple[str, str]]]:
    """Return map ``{ref_id: [(rel_path, source_kind), ...]}`` from structural JSON fields."""
    ref_map: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for rec in records:
        dp: Path | None = rec.get("_abs_descriptor_path")
        if dp and dp.is_file() and not dp.is_symlink():
            _scan_json_file(dp, "derived_descriptor", ref_map, dossiers_root)

    for _, _, _, di_dir in scope_dirs:
        for cs in di_dir.glob("*_crop_set.json"):
            if cs.is_file() and not cs.is_symlink():
                _scan_json_file(cs, "crop_set_sidecar", ref_map, dossiers_root)

    for _, _, _, di_dir in scope_dirs:
        ws_root = di_dir.parent
        working = ws_root / "working"
        if working.is_dir():
            try:
                for jf in sorted(working.glob("*.json")):
                    if jf.is_file() and not jf.is_symlink():
                        _scan_json_file(jf, "workspace_working", ref_map, dossiers_root)
            except OSError:
                pass
        output_json = ws_root / "output" / "output.json"
        if output_json.is_file() and not output_json.is_symlink():
            _scan_json_file(output_json, "workspace_output", ref_map, dossiers_root)
        manifest_json = ws_root / "manifest.json"
        if manifest_json.is_file() and not manifest_json.is_symlink():
            _scan_json_file(manifest_json, "workspace_manifest", ref_map, dossiers_root)

    if dossier_id:
        te_d = config_paths.dossiers_transcript_edit_dossier_artifacts_root(dossier_id)
        if te_d.is_dir():
            for jf in te_d.rglob("*.json"):
                if jf.is_file() and not jf.is_symlink():
                    _scan_json_file(jf, "dossier_artifact", ref_map, dossiers_root)
    else:
        te_all = config_paths.dossiers_transcript_edit_dossier_artifacts_root()
        if te_all.is_dir():
            for jf in te_all.rglob("*.json"):
                if jf.is_file() and not jf.is_symlink():
                    _scan_json_file(jf, "dossier_artifact", ref_map, dossiers_root)

    if harness_audit_roots:
        for hr in harness_audit_roots:
            if isinstance(hr, Path) and hr.is_dir():
                for jf in hr.rglob("*.json"):
                    if jf.is_file() and not jf.is_symlink():
                        _scan_json_file(jf, "harness_audit_root", ref_map, dossiers_root)

    return dict(ref_map)


def assign_reference_postures(
    records: list[dict[str, Any]],
    ref_map: dict[str, list[tuple[str, str]]],
    dossiers_root: Path,
) -> None:
    """Mutate *records* to fill ``reference_posture`` and ``_reference_source_kind``."""
    for rec in records:
        if rec.get("reference_posture") == "reference_ambiguous":
            continue
        ref_id = rec.get("ref_id")
        if not ref_id:
            rec["reference_posture"] = "unreferenced_observed"
            rec["_reference_source_kind"] = None
            continue

        appearances = ref_map.get(ref_id, [])
        if not appearances:
            rec["reference_posture"] = "unreferenced_observed"
            rec["_reference_source_kind"] = None
            continue

        desc_path: Path | None = rec.get("_abs_descriptor_path")
        desc_rel = rel_coord(desc_path, dossiers_root) if desc_path else None
        external = [(r, k) for r, k in appearances if r != desc_rel]

        if external:
            rec["reference_posture"] = "externally_referenced"
            kinds_present = {k for _, k in external}
            chosen = next((k for k in _KIND_PRIORITY if k in kinds_present), external[0][1])
            rec["_reference_source_kind"] = chosen
        else:
            rec["reference_posture"] = "descriptor_only"
            rec["_reference_source_kind"] = "derived_descriptor"
