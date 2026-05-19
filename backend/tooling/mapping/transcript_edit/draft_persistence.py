"""Append-only transcript-edit working revisions and explicit publish (domain tooling; no T0 mutation)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_latest_pointer_path,
    transcript_edit_manifest_path,
    transcript_edit_output_path,
    transcript_edit_revision_path,
    transcript_edit_working_dir,
    transcript_edit_workspace_root,
)

_SCHEMA_VERSION = 1
_WORKING_REV_REF_RE = re.compile(r"^transcript_edit:working:rev:(\d{4})$")

_MAX_COPY_FORWARD_PATHS: int = 32
_MAX_PATH_DEPTH: int = 8
_PAYLOAD_PATH_PREFIX: str = "payload."


def _validate_dot_path(path: str) -> str | None:
    """Return an error string if path is invalid for copy-forward operations, else None."""
    if not isinstance(path, str) or not path:
        return "path must be a non-empty string"
    if not path.startswith(_PAYLOAD_PATH_PREFIX):
        return (
            f"path must start with 'payload.' to scope into the artifact payload"
            f" (got {path!r})"
        )
    parts = path.split(".")
    if len(parts) > _MAX_PATH_DEPTH:
        return f"path exceeds max depth {_MAX_PATH_DEPTH}: {path!r}"
    for part in parts:
        if not part:
            return f"path has empty segment (double-dot?): {path!r}"
    return None


def _get_at_dot_path(obj: Any, parts: list[str]) -> tuple[Any, bool]:
    """Traverse obj following parts. Returns (value, found)."""
    cur: Any = obj
    for part in parts:
        if not isinstance(cur, Mapping):
            return None, False
        if part not in cur:
            return None, False
        cur = cur[part]
    return cur, True


def _set_at_dot_path(obj: dict[str, Any], parts: list[str], value: Any) -> None:
    """Set value in obj at the path described by parts, creating intermediate dicts."""
    cur = obj
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _paths_overlap(a: str, b: str) -> bool:
    """Return True if dot-notation paths are identical or one is an ancestor of the other.

    Ancestor overlap: copying ``payload.parcel_metadata`` and setting
    ``payload.parcel_metadata.forwardability`` would mutate inside a copied subtree.
    Descendant overlap: copying ``payload.parcel_metadata.forwardability`` and setting
    ``payload.parcel_metadata`` would silently overwrite the copied value.
    Both directions are considered overlap.
    """
    if a == b:
        return True
    parts_a = a.split(".")
    parts_b = b.split(".")
    shorter = min(len(parts_a), len(parts_b))
    return parts_a[:shorter] == parts_b[:shorter]


def parse_working_revision_ref(ref_id: str) -> str | None:
    """Return four-digit revision stem if ref is ``transcript_edit:working:rev:NNNN``."""
    m = _WORKING_REV_REF_RE.match(str(ref_id).strip())
    return m.group(1) if m else None


def _refuse_missing_workspace() -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": "workspace_key_required",
            "retryable": False,
        },
        "outputs": {
            "error": "Provide workspace_id or run_id to scope transcript-edit artifact storage.",
        },
    }


def resolve_workspace_key(*, workspace_id: str | None, run_id: str | None) -> str | None:
    """Prefer explicit workspace_id; else use run_id as documented workspace key."""
    w = str(workspace_id).strip() if workspace_id else ""
    if w:
        return w
    r = str(run_id).strip() if run_id else ""
    return r or None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_agent_payload(
    *,
    transcript_text: str | None,
    draft_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    has_text = transcript_text is not None and str(transcript_text).strip() != ""
    has_draft = draft_payload is not None
    if has_text and has_draft:
        raise ValueError("provide_only_one_of_transcript_text_or_draft_payload")
    if has_draft:
        return dict(draft_payload)
    if has_text:
        return {"transcript": str(transcript_text)}
    raise ValueError("transcript_text_or_draft_payload_required")


def _default_manifest(*, dossier_id: str, transcription_id: str, workspace_id: str) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "schema_version": _SCHEMA_VERSION,
        "dossier_id": dossier_id,
        "transcription_id": transcription_id,
        "workspace_id": workspace_id,
        "created_at": now,
        "updated_at": now,
        "revision_count": 0,
        "latest_revision": 0,
        "latest_working_ref_id": None,
        "latest_saved_at": None,
        "latest_content_sha256": None,
        "output_published_at": None,
        "output_source_revision_ref": None,
    }


def _load_or_init_manifest(
    dossier_id: str, transcription_id: str, workspace_id: str
) -> dict[str, Any]:
    path = transcript_edit_manifest_path(dossier_id, transcription_id, workspace_id)
    loaded = _load_json_file(path)
    if loaded and int(loaded.get("schema_version") or 0) >= 1:
        return loaded
    return _default_manifest(
        dossier_id=dossier_id, transcription_id=transcription_id, workspace_id=workspace_id
    )


def save_transcript_edit(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str | None = None,
    run_id: str | None = None,
    transcript_text: str | None = None,
    draft_payload: dict[str, Any] | None = None,
    base_revision_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    """
    Append one agent-authored working revision; update latest.json and manifest.
    Returns executor-shaped success or refusal (no T0 reads/writes).
    """
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    ws = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not ws:
        return _refuse_missing_workspace()
    try:
        agent_payload = _build_agent_payload(
            transcript_text=transcript_text, draft_payload=draft_payload
        )
    except ValueError as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_request", "retryable": False},
            "outputs": {"error": str(exc)},
        }

    try:
        root = transcript_edit_workspace_root(dossier_id, transcription_id, ws)
        work_dir = transcript_edit_working_dir(dossier_id, transcription_id, ws)
        work_dir.mkdir(parents=True, exist_ok=True)

        manifest = _load_or_init_manifest(dossier_id, transcription_id, ws)
        prev = int(manifest.get("latest_revision") or 0)
        next_rev = prev + 1
        rev_digits = f"{next_rev:04d}"
        ref_id = f"transcript_edit:working:rev:{rev_digits}"

        saved_at = _utc_now_iso()
        revision_doc: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "revision": next_rev,
            "ref_id": ref_id,
            "saved_at": saved_at,
            "tool": "save_transcript_edit",
            "base_revision_ref": str(base_revision_ref).strip() if base_revision_ref else None,
            "evidence_refs": [str(x).strip() for x in (evidence_refs or []) if str(x).strip()],
            "rationale": str(rationale).strip() if rationale else None,
            "payload": agent_payload,
        }

        rev_path = transcript_edit_revision_path(dossier_id, transcription_id, ws, rev_digits)
        rev_blob = json.dumps(revision_doc, ensure_ascii=False, sort_keys=True)
        _write_json(rev_path, revision_doc)

        content_sha256 = _sha256_text(rev_blob)
        rel_rev = f"working/rev_{rev_digits}.json"
        latest_pointer = {
            "schema_version": _SCHEMA_VERSION,
            "revision": next_rev,
            "ref_id": ref_id,
            "relative_path": rel_rev,
            "content_sha256": content_sha256,
            "byte_length": len(rev_blob.encode("utf-8")),
            "saved_at": saved_at,
            "tool": "save_transcript_edit",
        }
        _write_json(transcript_edit_latest_pointer_path(dossier_id, transcription_id, ws), latest_pointer)

        manifest["updated_at"] = saved_at
        manifest["revision_count"] = next_rev
        manifest["latest_revision"] = next_rev
        manifest["latest_working_ref_id"] = ref_id
        manifest["latest_saved_at"] = saved_at
        manifest["latest_content_sha256"] = content_sha256
        manifest["last_save_tool"] = "save_transcript_edit"
        _write_json(transcript_edit_manifest_path(dossier_id, transcription_id, ws), manifest)
    except UnsafeArtifactPathSegmentError as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_scope_path", "retryable": False},
            "outputs": {"error": str(exc)},
        }

    aggregate_ref = "transcript_edit:working"
    return {
        "executed": True,
        "artifact_refs": (ref_id, aggregate_ref),
        "outputs": {
            "working_draft_ref": ref_id,
            "aggregate_working_ref": aggregate_ref,
            "revision": next_rev,
            "revision_relative_path": rel_rev,
            "workspace_root": str(root.resolve()),
            "content_sha256": content_sha256,
            "byte_length": latest_pointer["byte_length"],
            "evidence_refs": revision_doc["evidence_refs"],
        },
    }


def publish_transcript_edit_output(
    *,
    dossier_id: str,
    transcription_id: str,
    source_revision_ref: str,
    workspace_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Materialize a chosen working revision into output/output.json (agent must name source ref).
    """
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    ws = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not ws:
        return _refuse_missing_workspace()

    src_ref = str(source_revision_ref).strip()
    rev_digits = parse_working_revision_ref(src_ref)
    if not rev_digits:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_source_revision_ref", "retryable": False},
            "outputs": {
                "error": "source_revision_ref must match transcript_edit:working:rev:NNNN (four digits).",
            },
        }

    try:
        rev_path = transcript_edit_revision_path(dossier_id, transcription_id, ws, rev_digits)
        revision_doc = _load_json_file(rev_path)
        if revision_doc is None:
            return {
                "executed": False,
                "refusal": {"reason_code": "source_revision_not_found", "retryable": False},
                "outputs": {"error": str(rev_path), "code": "not_found"},
            }

        published_at = _utc_now_iso()
        output_doc: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "published_at": published_at,
            "tool": "publish_transcript_edit_output",
            "source_revision_ref": src_ref,
            "source_relative_path": f"working/rev_{rev_digits}.json",
            "revision_snapshot": revision_doc,
        }
        out_path = transcript_edit_output_path(dossier_id, transcription_id, ws)
        _write_json(out_path, output_doc)

        manifest = _load_or_init_manifest(dossier_id, transcription_id, ws)
        manifest["updated_at"] = published_at
        manifest["output_published_at"] = published_at
        manifest["output_source_revision_ref"] = src_ref
        manifest["last_publish_tool"] = "publish_transcript_edit_output"
        _write_json(transcript_edit_manifest_path(dossier_id, transcription_id, ws), manifest)

        root = transcript_edit_workspace_root(dossier_id, transcription_id, ws)
    except UnsafeArtifactPathSegmentError as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_scope_path", "retryable": False},
            "outputs": {"error": str(exc)},
        }

    output_ref = "transcript_edit:output"
    return {
        "executed": True,
        "artifact_refs": (output_ref, src_ref),
        "outputs": {
            "output_ref": output_ref,
            "published_at": published_at,
            "source_revision_ref": src_ref,
            "output_relative_path": "output/output.json",
            "workspace_root": str(root.resolve()),
        },
    }


def copy_forward_save(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str | None = None,
    run_id: str | None = None,
    base_ref: str,
    copy_forward_paths: list[str],
    set_paths: dict[str, Any],
    evidence_refs: list[str] | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    """Create a new revision by copying named payload paths from a base revision and applying agent-authored updates.

    Deterministic code copies exact named values; no semantic inference.
    The agent must explicitly name the base ref, all copied paths, and all authored paths.
    Paths in copy_forward_paths and set_paths must not overlap.
    """
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    ws = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not ws:
        return _refuse_missing_workspace()

    base_ref_str = str(base_ref).strip() if base_ref else ""
    rev_digits = parse_working_revision_ref(base_ref_str)
    if not rev_digits:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_base_ref", "retryable": False},
            "outputs": {
                "error": "base_ref must match transcript_edit:working:rev:NNNN.",
                "repair_hint": "Use a specific revision ref such as 'transcript_edit:working:rev:0001'.",
            },
        }

    copy_paths: list[str] = list(copy_forward_paths or [])
    set_dict: dict[str, Any] = dict(set_paths or {})

    if len(copy_paths) + len(set_dict) > _MAX_COPY_FORWARD_PATHS:
        return {
            "executed": False,
            "refusal": {"reason_code": "too_many_paths", "retryable": False},
            "outputs": {
                "error": (
                    f"Total path count ({len(copy_paths)} copy + {len(set_dict)} set)"
                    f" exceeds max {_MAX_COPY_FORWARD_PATHS}."
                ),
            },
        }

    for path in copy_paths:
        err = _validate_dot_path(path)
        if err:
            return {
                "executed": False,
                "refusal": {"reason_code": "invalid_path_syntax", "retryable": False},
                "outputs": {
                    "error": err,
                    "repair_hint": (
                        "Use dot-notation paths starting with 'payload.' "
                        "— e.g., 'payload.source_transcript_verbatim'."
                    ),
                    "invalid_path": path,
                },
            }
    for path in set_dict:
        err = _validate_dot_path(path)
        if err:
            return {
                "executed": False,
                "refusal": {"reason_code": "invalid_path_syntax", "retryable": False},
                "outputs": {
                    "error": err,
                    "repair_hint": (
                        "Use dot-notation paths starting with 'payload.' "
                        "— e.g., 'payload.issues'."
                    ),
                    "invalid_path": path,
                },
            }

    overlap_involved: set[str] = set()
    for cp in copy_paths:
        for sp in set_dict:
            if _paths_overlap(cp, sp):
                overlap_involved.add(cp)
                overlap_involved.add(sp)
    if overlap_involved:
        return {
            "executed": False,
            "refusal": {"reason_code": "overlapping_paths", "retryable": False},
            "outputs": {
                "error": (
                    "Paths in copy_forward_paths and set_paths overlap "
                    "(exact match or ancestor/descendant). Remove from one list."
                ),
                "overlapping_paths": sorted(overlap_involved),
            },
        }

    try:
        rev_path = transcript_edit_revision_path(dossier_id, transcription_id, ws, rev_digits)
        base_doc = _load_json_file(rev_path)
        if base_doc is None:
            return {
                "executed": False,
                "refusal": {"reason_code": "base_ref_not_found", "retryable": False},
                "outputs": {
                    "error": f"Base revision not found: {base_ref_str}",
                    "repair_hint": "Verify the base_ref revision exists in this workspace.",
                },
            }

        new_payload: dict[str, Any] = {}
        missing: list[str] = []
        for path in copy_paths:
            parts = path.split(".")
            value, found = _get_at_dot_path(base_doc, parts)
            if not found:
                missing.append(path)
            else:
                _set_at_dot_path(new_payload, parts[1:], value)

        if missing:
            return {
                "executed": False,
                "refusal": {"reason_code": "missing_copy_paths", "retryable": False},
                "outputs": {
                    "error": f"Paths not found in base artifact {base_ref_str}: {missing}",
                    "missing_copy_paths": missing,
                    "repair_hint": (
                        "Check that the base artifact has these paths. "
                        "Hydrate the base ref to inspect its payload structure."
                    ),
                },
            }

        for path, value in set_dict.items():
            parts = path.split(".")
            _set_at_dot_path(new_payload, parts[1:], value)

    except UnsafeArtifactPathSegmentError as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_scope_path", "retryable": False},
            "outputs": {"error": str(exc)},
        }

    return save_transcript_edit(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=ws,
        draft_payload=new_payload,
        base_revision_ref=base_ref_str,
        evidence_refs=evidence_refs,
        rationale=rationale,
    )
