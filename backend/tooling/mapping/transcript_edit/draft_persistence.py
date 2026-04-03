"""Append-only transcript-edit working revisions and explicit publish (domain tooling; no T0 mutation)."""

from __future__ import annotations

import hashlib
import json
import re
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
