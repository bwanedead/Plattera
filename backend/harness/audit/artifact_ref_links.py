"""Audit-only helpers for resolving image refs to safe Markdown links."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.paths import dossiers_artifacts_root

MAX_INLINE_THUMBNAILS_PER_TURN = 4
_MAX_AUDIT_JSON_DESCRIPTORS = 64
_MAX_DERIVED_DESCRIPTOR_FILES = 512
_MAX_DOSSIER_DIRS = 16
_MAX_TX_DIRS = 16

_IMAGE_DERIVED_PREFIX = "image:derived:"
_IMAGE_DERIVED_MARKER = ":image:derived:"

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
_REF_LIST_KEYS = frozenset(
    {
        "artifact_refs",
        "context_refs",
        "input_refs",
        "evidence_refs",
        "pin_refs",
        "unpin_refs",
        "hydrate_next",
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
    collisions: set[str] = set()
    turn_list = turns or ([] if turn is None else [turn])
    if turn is not None:
        _collect_ref_paths_from_value(turn, index, collisions)
    if audit_dir is not None:
        _collect_descriptor_paths_from_audit_dir(audit_dir, index, collisions)
    if run_dir is not None or turns or turn is not None:
        _collect_derived_image_descriptor_paths(
            run_dir=run_dir,
            audit_dir=audit_dir,
            turns=turn_list,
            index=index,
            collisions=collisions,
        )
    _reconcile_wrapper_qualified_derived_refs(
        index=index,
        collisions=collisions,
        turns=turn_list,
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
    collisions: set[str] = set()
    turn_list = [turn for turn in (turns or []) if isinstance(turn, Mapping)]
    for turn in turn_list:
        _collect_ref_paths_from_value(turn, index, collisions)
    if audit_dir is not None:
        _collect_descriptor_paths_from_audit_dir(audit_dir, index, collisions)
    if run_dir is not None or turn_list:
        _collect_derived_image_descriptor_paths(
            run_dir=run_dir,
            audit_dir=audit_dir,
            turns=turn_list,
            index=index,
            collisions=collisions,
        )
    _reconcile_wrapper_qualified_derived_refs(
        index=index,
        collisions=collisions,
        turns=turn_list,
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
        dossier_path = _resolve_dossiers_artifact_file(normalized_ref)
        if dossier_path is not None:
            absolute_path = str(dossier_path)
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


def _resolve_dossiers_artifact_file(ref_id: str) -> Path | None:
    prefix = "artifact://dossiers/"
    text = str(ref_id or "").strip()
    if not text.startswith(prefix):
        return None
    if not text.lower().endswith(".png"):
        return None
    relative = text[len(prefix) :].replace("\\", "/")
    parts = [part for part in relative.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        return None
    root = dossiers_artifacts_root().resolve()
    candidate = (root / Path(*parts)).resolve()
    if root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def _collect_ref_paths_from_value(
    value: Any,
    index: dict[str, str],
    collisions: set[str],
) -> None:
    if isinstance(value, Mapping):
        paired = _pair_ref_and_path(value)
        if paired is not None:
            ref_id, path = paired
            _record_ref_path(index, collisions, ref_id, path)
        for key, nested in value.items():
            if key in _BINARY_KEYS:
                continue
            if isinstance(key, str) and key.startswith("image:") and isinstance(nested, str):
                candidate = nested.strip()
                if candidate and _looks_like_path(candidate):
                    _record_ref_path(index, collisions, key, candidate)
            _collect_ref_paths_from_value(nested, index, collisions)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect_ref_paths_from_value(item, index, collisions)


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


def _collect_descriptor_paths_from_audit_dir(
    audit_dir: Path,
    index: dict[str, str],
    collisions: set[str],
) -> None:
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
        _load_descriptor_json(path, index, collisions)


def _collect_derived_image_descriptor_paths(
    *,
    run_dir: Path | None,
    audit_dir: Path | None,
    turns: list[Mapping[str, Any]],
    index: dict[str, str],
    collisions: set[str],
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
            if _load_descriptor_json(path, index, collisions):
                scanned += 1


def _load_descriptor_json(
    path: Path,
    index: dict[str, str],
    collisions: set[str],
) -> bool:
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
    _record_ref_path(index, collisions, ref_id, absolute_path)
    return True


def _record_ref_path(
    index: dict[str, str],
    collisions: set[str],
    ref_id: str,
    absolute_path: str,
) -> None:
    """Record a ref→path binding; track multi-path leaf collisions for wrapper safety."""
    existing = index.get(ref_id)
    if existing is None:
        index[ref_id] = absolute_path
        return
    if existing != absolute_path:
        collisions.add(ref_id)


def _reconcile_wrapper_qualified_derived_refs(
    *,
    index: dict[str, str],
    collisions: set[str],
    turns: Sequence[Mapping[str, Any]],
) -> None:
    """Bind wrapper-qualified refs to uniquely resolved native ``image:derived:*`` paths."""
    for qualified in _collect_image_refs_from_turns(turns):
        leaf = _extract_image_derived_leaf(qualified)
        if leaf is None or leaf == qualified:
            continue
        if leaf in collisions:
            continue
        leaf_path = str(index.get(leaf) or "").strip()
        if not leaf_path:
            continue
        if not Path(leaf_path).is_file():
            continue
        # Never invent a path from the qualified identity; only reuse the leaf descriptor path.
        index.setdefault(qualified, leaf_path)


def _collect_image_refs_from_turns(turns: Sequence[Mapping[str, Any]]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def _add(ref_id: str) -> None:
        text = str(ref_id or "").strip()
        if not text or text in seen:
            return
        if text.startswith(_IMAGE_DERIVED_PREFIX) or _IMAGE_DERIVED_MARKER in text:
            seen.add(text)
            found.append(text)

    def _walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if key in _BINARY_KEYS:
                    continue
                key_text = str(key or "")
                if key_text in _REF_KEYS and isinstance(nested, str):
                    _add(nested)
                elif key_text in _REF_LIST_KEYS and isinstance(nested, (list, tuple)):
                    for item in nested:
                        if isinstance(item, str):
                            _add(item)
                _walk(nested)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    for turn in turns:
        if isinstance(turn, Mapping):
            _walk(turn)
    return found


def _extract_image_derived_leaf(ref_id: str) -> str | None:
    """Return an exact delimiter-bounded ``image:derived:*`` leaf, or None."""
    text = str(ref_id or "").strip()
    if not text:
        return None
    if text.startswith(_IMAGE_DERIVED_PREFIX):
        opaque = text[len(_IMAGE_DERIVED_PREFIX) :]
        return text if opaque else None
    marker_at = text.rfind(_IMAGE_DERIVED_MARKER)
    if marker_at < 0:
        return None
    leaf = text[marker_at + 1 :]
    if not leaf.startswith(_IMAGE_DERIVED_PREFIX):
        return None
    opaque = leaf[len(_IMAGE_DERIVED_PREFIX) :]
    if not opaque:
        return None
    return leaf


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
