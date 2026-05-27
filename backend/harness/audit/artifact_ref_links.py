"""Audit-only helpers for resolving image refs to safe Markdown links."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_INLINE_THUMBNAILS_PER_TURN = 4
_MAX_AUDIT_JSON_DESCRIPTORS = 64
_MAX_DERIVED_DESCRIPTOR_FILES = 512
_MAX_DOSSIER_DIRS = 16
_MAX_TX_DIRS = 16

_IMAGE_DERIVED_PREFIX = "image:derived:"

_REF_KEYS = frozenset(
    {
        "ref_id",
        "ref",
        "derived_ref_id",
        "crop_ref",
        "master_overlay_ref",
        "source_ref",
        "parent_ref_id",
        "previous_crop_set_overlay_ref",
        "view_of_crop_set_overlay_ref",
    }
)
_REF_PAIR_PRIORITY = (
    "ref_id",
    "derived_ref_id",
    "crop_ref",
    "master_overlay_ref",
    "ref",
    "parent_ref_id",
    "source_ref",
    "previous_crop_set_overlay_ref",
    "view_of_crop_set_overlay_ref",
    "root_source_ref",
)
_PATH_KEYS = frozenset({"absolute_path", "path", "file_path"})
_BINARY_KEYS = frozenset(
    {
        "image_bytes",
        "image_b64",
        "image_base64",
        "image_evidence",
        "binary",
        "binary_payload",
        "pdf_bytes",
        "bytes",
        "raw_bytes",
        "data",
    }
)
# Note: `data` is skipped during path-index walks only. Timeline binary stripping uses
# the separate `_BINARY_KEYS` set in `human_timeline.py`, which intentionally keeps
# textual `outputs.data` visible unless it is nested under a binary key name.


@dataclass(frozen=True)
class ArtifactImageLink:
    ref_id: str
    path: str
    markdown_link: str
    markdown_image: str


@dataclass
class ArtifactLinkContext:
    """Bounded link/thumbnail context for one turn's timeline rendering."""

    timeline_path: Path
    ref_path_index: Mapping[str, str]
    inline_budget: int = MAX_INLINE_THUMBNAILS_PER_TURN
    inline_cap_reached: bool = field(default=False, init=False)

    def consume_inline(self) -> bool:
        if self.inline_budget <= 0:
            self.inline_cap_reached = True
            return False
        self.inline_budget -= 1
        return True


def build_ref_path_index(
    *,
    turn: Mapping[str, Any] | None = None,
    audit_dir: Path | None = None,
    run_dir: Path | None = None,
    turns: list[Mapping[str, Any]] | None = None,
    shared_index: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build ref_id -> absolute filesystem path from turn metadata and run artifacts."""
    index: dict[str, str] = dict(shared_index or {})
    if turn is not None:
        _collect_ref_paths_from_value(turn, index)
    if audit_dir is not None:
        _collect_descriptor_paths_from_audit_dir(audit_dir, index)
    if run_dir is not None or turns:
        _collect_derived_image_descriptor_paths(
            run_dir=run_dir,
            audit_dir=audit_dir,
            turns=turns or ([] if turn is None else [turn]),
            index=index,
        )
    return index


def build_run_ref_path_index(
    *,
    audit_dir: Path | None = None,
    run_dir: Path | None = None,
    turns: list[Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Build one run-level ref path index for timeline rendering."""
    index: dict[str, str] = {}
    if turns:
        for turn in turns:
            if isinstance(turn, Mapping):
                _collect_ref_paths_from_value(turn, index)
    if audit_dir is not None:
        _collect_descriptor_paths_from_audit_dir(audit_dir, index)
    if run_dir is not None or turns:
        _collect_derived_image_descriptor_paths(
            run_dir=run_dir,
            audit_dir=audit_dir,
            turns=[turn for turn in (turns or []) if isinstance(turn, Mapping)],
            index=index,
        )
    return index


def resolve_artifact_image_link(
    ref_id: str,
    context: ArtifactLinkContext,
    *,
    link_label: str = "open image",
) -> ArtifactImageLink | None:
    """Resolve one image ref to a safe relative Markdown link, or None."""
    normalized_ref = str(ref_id or "").strip()
    if not normalized_ref:
        return None
    absolute_path = str(context.ref_path_index.get(normalized_ref) or "").strip()
    if not absolute_path:
        return None
    file_path = Path(absolute_path)
    if not file_path.is_file():
        return None
    try:
        relative = os.path.relpath(file_path, context.timeline_path.parent)
    except ValueError:
        return None
    relative = relative.replace("\\", "/")
    target = _markdown_target(relative)
    return ArtifactImageLink(
        ref_id=normalized_ref,
        path=relative,
        markdown_link=f"[{link_label}]({target})",
        markdown_image=f"![{normalized_ref}]({target})",
    )


def format_ref_with_link(
    ref_id: str,
    link: ArtifactImageLink | None,
    *,
    link_label: str = "open image",
) -> str:
    normalized_ref = str(ref_id or "").strip()
    if not normalized_ref:
        return ""
    if link is None:
        return f"`{normalized_ref}`"
    markdown_link = link.markdown_link
    if link_label != "open image":
        markdown_link = f"[{link_label}]({_markdown_target(link.path)})"
    return f"`{normalized_ref}` {markdown_link}"


def maybe_inline_thumbnail(
    ref_id: str,
    link: ArtifactImageLink | None,
    context: ArtifactLinkContext,
    *,
    alt: str | None = None,
) -> list[str]:
    """Return optional inline thumbnail lines when budget allows."""
    if link is None:
        return []
    if not context.consume_inline():
        return []
    label = alt or ref_id
    target = _markdown_target(link.path)
    return [f"![{label}]({target})"]


def inline_cap_notice(context: ArtifactLinkContext) -> str | None:
    if context.inline_cap_reached:
        return "- inline image cap reached; remaining images are link-only"
    return None


def _markdown_target(relative_path: str) -> str:
    normalized = relative_path.replace("\\", "/")
    if any(char in normalized for char in (" ", "(", ")", "<", ">")):
        return f"<{normalized}>"
    return normalized


def _collect_ref_paths_from_value(value: Any, index: dict[str, str]) -> None:
    if isinstance(value, Mapping):
        paired = _pair_ref_and_path(value)
        if paired is not None:
            ref_id, path = paired
            index.setdefault(ref_id, path)
        for key, nested in value.items():
            if key in _BINARY_KEYS:
                continue
            if isinstance(key, str) and key.startswith("image:") and isinstance(nested, str):
                candidate = nested.strip()
                if candidate and _looks_like_path(candidate):
                    index.setdefault(key, candidate)
            _collect_ref_paths_from_value(nested, index)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect_ref_paths_from_value(item, index)


def _pair_ref_and_path(mapping: Mapping[str, Any]) -> tuple[str, str] | None:
    path = _first_path(mapping)
    if not path:
        return None
    for key in _REF_PAIR_PRIORITY:
        if key not in mapping:
            continue
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), path
    return None


def _collect_descriptor_paths_from_audit_dir(audit_dir: Path, index: dict[str, str]) -> None:
    """Bounded scan for descriptor JSON files that map refs to image paths."""
    if not audit_dir.is_dir():
        return
    scanned = 0
    for path in sorted(audit_dir.rglob("*.json")):
        if scanned >= _MAX_AUDIT_JSON_DESCRIPTORS:
            break
        if path.name.startswith("turn_"):
            continue
        scanned += 1
        _load_descriptor_json(path, index)


def _collect_derived_image_descriptor_paths(
    *,
    run_dir: Path | None,
    audit_dir: Path | None,
    turns: list[Mapping[str, Any]],
    index: dict[str, str],
) -> None:
    """Resolve ``image:derived:*`` refs from persisted derived-image descriptor JSON."""
    run_id = _resolve_run_id(run_dir=run_dir, audit_dir=audit_dir, turns=turns)
    derived_dirs = _find_derived_images_dirs(run_id=run_id, run_dir=run_dir)
    scanned = 0
    for derived_dir in derived_dirs:
        for path in sorted(derived_dir.glob("*.json")):
            if scanned >= _MAX_DERIVED_DESCRIPTOR_FILES:
                return
            if path.name.endswith("_crop_set.json"):
                continue
            if _load_descriptor_json(path, index):
                scanned += 1


def _load_descriptor_json(path: Path, index: dict[str, str]) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, Mapping):
        return False
    ref_id = str(payload.get("ref_id") or "").strip()
    absolute_path = str(payload.get("absolute_path") or "").strip()
    if not ref_id.startswith("image:") or not absolute_path:
        return False
    if not Path(absolute_path).is_file():
        return False
    index.setdefault(ref_id, absolute_path)
    return True


def _resolve_run_id(
    *,
    run_dir: Path | None,
    audit_dir: Path | None,
    turns: list[Mapping[str, Any]],
) -> str | None:
    if audit_dir is not None:
        index_path = audit_dir / "index.json"
        if index_path.is_file():
            try:
                payload = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, Mapping):
                run_id = str(payload.get("run_id") or "").strip()
                if run_id:
                    return run_id
    for turn in reversed(turns):
        run_id = str(turn.get("run_id") or "").strip()
        if run_id:
            return run_id
    if run_dir is not None:
        run_id = run_dir.name.strip()
        if run_id:
            return run_id
    return None


def _find_derived_images_dirs(*, run_id: str | None, run_dir: Path | None) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        key = str(path.resolve())
        if key in seen or not path.is_dir():
            return
        seen.add(key)
        dirs.append(path)

    for derived_dir in _derived_dirs_from_run_metadata(run_dir):
        _add(derived_dir)
    if run_id:
        for derived_dir in _scan_transcript_edit_workspaces(run_id):
            _add(derived_dir)
    return dirs


def _derived_dirs_from_run_metadata(run_dir: Path | None) -> list[Path]:
    if run_dir is None or not run_dir.is_dir():
        return []
    for filename in ("result.json", "done.json", "kernel_resume.json"):
        path = run_dir / filename
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        derived_dir = _derived_dir_from_launch_context(payload)
        if derived_dir is not None:
            return [derived_dir]
    return []


def _derived_dir_from_launch_context(payload: Any) -> Path | None:
    if not isinstance(payload, Mapping):
        return None
    for key in ("launch_context", "opaque_launch_context", "run_context"):
        derived_dir = _derived_dir_from_mapping(payload.get(key))
        if derived_dir is not None:
            return derived_dir
    return _derived_dir_from_mapping(payload)


def _derived_dir_from_mapping(mapping: Any) -> Path | None:
    if not isinstance(mapping, Mapping):
        return None
    scope_key = "dossier" + "_id"
    transcription_key = "transcription" + "_id"
    scope_id = str(mapping.get(scope_key) or "").strip()
    transcription_id = str(mapping.get(transcription_key) or "").strip()
    workspace_id = str(
        mapping.get("workspace_id")
        or mapping.get("workspace_key")
        or mapping.get("run_id")
        or ""
    ).strip()
    if not scope_id or not transcription_id or not workspace_id:
        return None
    try:
        from tooling.mapping.transcript_edit.paths import transcript_edit_derived_images_dir

        return transcript_edit_derived_images_dir(scope_id, transcription_id, workspace_id)
    except Exception:
        return None


def _scan_transcript_edit_workspaces(run_id: str) -> list[Path]:
    try:
        from config.paths import dossiers_transcript_edit_artifacts_root

        te_root = dossiers_transcript_edit_artifacts_root()
    except Exception:
        return []
    if not te_root.is_dir():
        return []
    found: list[Path] = []
    scope_count = 0
    for scope_dir in sorted(te_root.iterdir()):
        if scope_count >= _MAX_DOSSIER_DIRS:
            break
        if not scope_dir.is_dir():
            continue
        scope_count += 1
        tx_count = 0
        for tx_dir in sorted(scope_dir.iterdir()):
            if tx_count >= _MAX_TX_DIRS:
                break
            if not tx_dir.is_dir():
                continue
            tx_count += 1
            derived_dir = tx_dir / run_id / "derived_images"
            if derived_dir.is_dir():
                found.append(derived_dir)
    return found


def _first_path(mapping: Mapping[str, Any]) -> str | None:
    for key in _PATH_KEYS:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip() and _looks_like_path(value.strip()):
            return value.strip()
    return None


def _looks_like_path(value: str) -> bool:
    if value.startswith("image:"):
        return False
    if value.startswith(("http://", "https://")):
        return False
    if "/" in value or "\\" in value:
        return True
    return value.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))
