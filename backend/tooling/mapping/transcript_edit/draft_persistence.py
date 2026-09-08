"""Append-only transcript-edit working revisions and explicit publish (domain tooling; no T0 mutation)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tooling.mapping.transcript_edit.managed_provenance_integrity import (
    ManagedProvenanceIntegrityError,
    assert_managed_provenance_coherent_for_save,
)
from tooling.mapping.transcript_edit.working_revision_io import (
    SCHEMA_VERSION as _SCHEMA_VERSION,
    JsonObjectFileInvalid,
    ManifestStorageInvalid,
    load_json_file as _load_json_file,
    load_or_init_manifest as _load_or_init_manifest,
    parse_working_revision_ref,
    utc_now_iso as _utc_now_iso,
)
from tooling.mapping.transcript_edit.working_revision_transaction import (
    append_working_revision_under_lock,
    current_working_head_ref,
    load_current_head_payload,
)
from tooling.mapping.transcript_edit.working_write_lock import (
    WorkingWriteLockBusy,
    WorkingWriteLockFailed,
    working_write_lock,
)
from .paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_manifest_path,
    transcript_edit_output_path,
    transcript_edit_revision_path,
    transcript_edit_workspace_root,
)

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


def working_revision_exists(
    *,
    dossier_id: str,
    transcription_id: str,
    revision_ref: str,
    workspace_id: str | None = None,
    run_id: str | None = None,
) -> bool:
    """True when the exact working revision file exists in the scoped workspace.

    Mechanical existence only — does not load or interpret revision contents.
    """
    digits = parse_working_revision_ref(revision_ref)
    if digits is None:
        return False
    ws = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not ws:
        return False
    try:
        path = transcript_edit_revision_path(dossier_id, transcription_id, ws, digits)
    except UnsafeArtifactPathSegmentError:
        return False
    return path.is_file()


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    path.write_text(text, encoding="utf-8")


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
        with working_write_lock(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=ws,
        ):
            return _save_transcript_edit_under_lock(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=ws,
                agent_payload=agent_payload,
                base_revision_ref=base_revision_ref,
                evidence_refs=evidence_refs,
                rationale=rationale,
            )
    except WorkingWriteLockBusy:
        return {
            "executed": False,
            "refusal": {"reason_code": "working_write_in_progress", "retryable": False},
            "outputs": {
                "error": "Another working write holds the lock for this workspace.",
            },
        }
    except WorkingWriteLockFailed as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "storage_failure", "retryable": False},
            "outputs": {"error": f"Unable to acquire working write lock: {exc}"},
        }
    except UnsafeArtifactPathSegmentError as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_scope_path", "retryable": False},
            "outputs": {"error": str(exc)},
        }


def _save_transcript_edit_under_lock(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    agent_payload: dict[str, Any],
    base_revision_ref: str | None,
    evidence_refs: list[str] | None,
    rationale: str | None,
) -> dict[str, Any]:
    previous_payload = load_current_head_payload(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    )
    try:
        assert_managed_provenance_coherent_for_save(
            previous_payload=previous_payload,
            next_payload=agent_payload,
        )
    except ManagedProvenanceIntegrityError as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": exc.reason_code, "retryable": False},
            "outputs": {"error": exc.detail or str(exc)},
        }

    result = append_working_revision_under_lock(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        payload=agent_payload,
        tool="save_transcript_edit",
        base_revision_ref=base_revision_ref,
        evidence_refs=evidence_refs,
        rationale=rationale,
    )
    return result


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
        try:
            revision_doc = _load_json_file(rev_path)
        except JsonObjectFileInvalid as exc:
            return {
                "executed": False,
                "refusal": {"reason_code": "invalid_working_storage_state", "retryable": False},
                "outputs": {"error": exc.detail},
            }
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

        try:
            manifest = _load_or_init_manifest(dossier_id, transcription_id, ws)
        except ManifestStorageInvalid as exc:
            return {
                "executed": False,
                "refusal": {"reason_code": "invalid_working_storage_state", "retryable": False},
                "outputs": {"error": exc.detail},
            }
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
    except (TypeError, ValueError) as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "noncanonical_revision_payload", "retryable": False},
            "outputs": {"error": f"Publish payload is not JSON-canonical: {exc}"},
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
    The agent must explicitly name the base ref, all paths to copy, and all paths to author.
    Paths in copy_forward_paths and set_paths must not overlap.

    Base load, provenance checks, head recheck, and append share one working-write lock.
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
        with working_write_lock(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=ws,
        ):
            return _copy_forward_under_lock(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=ws,
                base_ref_str=base_ref_str,
                rev_digits=rev_digits,
                copy_paths=copy_paths,
                set_dict=set_dict,
                evidence_refs=evidence_refs,
                rationale=rationale,
            )
    except WorkingWriteLockBusy:
        return {
            "executed": False,
            "refusal": {"reason_code": "working_write_in_progress", "retryable": False},
            "outputs": {
                "error": "Another working write holds the lock for this workspace.",
            },
        }
    except WorkingWriteLockFailed as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "storage_failure", "retryable": False},
            "outputs": {"error": f"Unable to acquire working write lock: {exc}"},
        }
    except UnsafeArtifactPathSegmentError as exc:
        return {
            "executed": False,
            "refusal": {"reason_code": "invalid_scope_path", "retryable": False},
            "outputs": {"error": str(exc)},
        }


def _copy_forward_under_lock(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    base_ref_str: str,
    rev_digits: str,
    copy_paths: list[str],
    set_dict: dict[str, Any],
    evidence_refs: list[str] | None,
    rationale: str | None,
) -> dict[str, Any]:
    from tooling.mapping.transcript_edit.managed_provenance_integrity import (
        managed_provenance_field_present,
    )

    try:
        rev_path = transcript_edit_revision_path(
            dossier_id, transcription_id, workspace_id, rev_digits
        )
        try:
            base_doc = _load_json_file(rev_path)
        except JsonObjectFileInvalid as exc:
            return {
                "executed": False,
                "refusal": {"reason_code": "invalid_working_storage_state", "retryable": False},
                "outputs": {"error": exc.detail},
            }
        if base_doc is None:
            return {
                "executed": False,
                "refusal": {"reason_code": "base_ref_not_found", "retryable": False},
                "outputs": {
                    "error": f"Base revision not found: {base_ref_str}",
                    "repair_hint": "Verify the base_ref revision exists in this workspace.",
                },
            }

        base_payload = base_doc.get("payload")
        if managed_provenance_field_present(base_payload if isinstance(base_payload, dict) else {}):
            head = current_working_head_ref(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_id,
            )
            if head != base_ref_str:
                return {
                    "executed": False,
                    "refusal": {"reason_code": "stale_base_revision", "retryable": False},
                    "outputs": {
                        "error": (
                            "Managed provenance is present; copy-forward base_ref must be "
                            "the current working head."
                        ),
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

    # Append under the already-held lock (no nested acquisition).
    return _save_transcript_edit_under_lock(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        agent_payload=new_payload,
        base_revision_ref=base_ref_str,
        evidence_refs=evidence_refs,
        rationale=rationale,
    )
