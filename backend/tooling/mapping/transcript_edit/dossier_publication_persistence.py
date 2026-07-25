"""Idempotent append-only dossier transcript-edit output persistence (unwired).

Rebuilds a BR-004 candidate from explicit segment revision refs, then persists
it as an immutable dossier-level output revision. Never chooses among runs or
drafts and never writes per-segment or legacy finalized-dossier outputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from domains.mapping.transcript_edit.payloads.dossier_publication_candidate import (
    DossierPublicationCandidate,
)
from tooling.mapping.transcript_edit.dossier_publication_candidate import (
    DossierPublicationCandidateError,
    build_dossier_publication_candidate,
)
from tooling.mapping.transcript_edit.dossier_publication_paths import (
    dossier_transcript_edit_dossier_output_dir,
    dossier_transcript_edit_dossier_output_latest_pointer_path,
    dossier_transcript_edit_dossier_output_revision_path,
    dossier_transcript_edit_dossier_publish_lock_path,
    require_safe_sha256_hex,
)
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryBundle,
)
from tooling.mapping.transcript_edit.paths import UnsafeArtifactPathSegmentError

OUTPUT_REF = "transcript_edit:output"
OUTPUT_SCHEMA_VERSION = "dossier_transcript_edit_output.v1"
POINTER_SCHEMA_VERSION = "dossier_transcript_edit_output_pointer.v1"
_OUTPUT_REVISION_PREFIX = "transcript_edit:dossier_output:sha256:"
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_FIELDS = frozenset(
    {
        "schema_version",
        "output_ref",
        "output_revision_ref",
        "published_at",
        "candidate_fingerprint",
        "candidate",
    }
)
_POINTER_FIELDS = frozenset(
    {
        "schema_version",
        "output_ref",
        "output_revision_ref",
        "candidate_fingerprint",
        "relative_path",
        "document_sha256",
        "published_at",
        "topology_fingerprint",
    }
)


def publish_dossier_transcript_edit_output(
    *,
    bundle: DossierStartupInventoryBundle,
    workspace_key: str,
    source_revision_refs: Sequence[str],
) -> dict[str, Any]:
    """Persist a freshly rebuilt BR-004 candidate as dossier-level output."""
    try:
        candidate = build_dossier_publication_candidate(
            bundle=bundle,
            workspace_key=workspace_key,
            source_revision_refs=source_revision_refs,
        )
    except DossierPublicationCandidateError as exc:
        return _refusal(exc.code, detail=exc.detail, retryable=False)

    fingerprint = candidate.candidate_fingerprint
    try:
        require_safe_sha256_hex(fingerprint)
    except UnsafeArtifactPathSegmentError:
        return _refusal("dossier_publication_revision_invalid", retryable=False)

    dossier_id = candidate.dossier_id
    workspace_id = candidate.workspace_id
    output_revision_ref = _output_revision_ref(fingerprint)
    relative_path = f"revisions/{fingerprint}.json"

    try:
        output_dir = dossier_transcript_edit_dossier_output_dir(dossier_id, workspace_id)
        pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(
            dossier_id, workspace_id
        )
        revision_path = dossier_transcript_edit_dossier_output_revision_path(
            dossier_id, workspace_id, fingerprint
        )
    except UnsafeArtifactPathSegmentError:
        return _refusal("invalid_scope_path", retryable=False)

    try:
        with _workspace_publish_lock(dossier_id=dossier_id, workspace_id=workspace_id):
            return _publish_under_lock(
                candidate=candidate,
                fingerprint=fingerprint,
                output_revision_ref=output_revision_ref,
                relative_path=relative_path,
                pointer_path=pointer_path,
                revision_path=revision_path,
                output_dir=output_dir,
            )
    except _PublicationLockBusy:
        return _refusal("dossier_publication_in_progress", retryable=True)
    except _PublicationStorageFailed:
        return _refusal("dossier_publication_storage_failed", retryable=False)


def _publish_under_lock(
    *,
    candidate: DossierPublicationCandidate,
    fingerprint: str,
    output_revision_ref: str,
    relative_path: str,
    pointer_path: Path,
    revision_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    expected_candidate = _candidate_payload(candidate)
    pointer_state = _inspect_pointer(
        pointer_path=pointer_path,
        output_dir=output_dir,
    )
    if pointer_state.error is not None:
        return _refusal(pointer_state.error, retryable=False)

    if (
        pointer_state.payload is not None
        and pointer_state.payload["candidate_fingerprint"] == fingerprint
    ):
        loaded = _load_and_validate_revision_document(
            revision_path,
            expected_fingerprint=fingerprint,
            expected_output_revision_ref=output_revision_ref,
            expected_topology_fingerprint=candidate.topology_fingerprint,
            expected_candidate_payload=expected_candidate,
        )
        if isinstance(loaded, str):
            return _refusal(loaded, retryable=False)
        revision_doc, _document_sha256 = loaded
        return _success_from_existing(
            candidate=candidate,
            fingerprint=fingerprint,
            output_revision_ref=output_revision_ref,
            published_at=str(revision_doc["published_at"]),
            idempotent_replay=True,
            recovered_existing_revision=False,
        )

    recovered = False
    if revision_path.is_file():
        loaded = _load_and_validate_revision_document(
            revision_path,
            expected_fingerprint=fingerprint,
            expected_output_revision_ref=output_revision_ref,
            expected_topology_fingerprint=candidate.topology_fingerprint,
            expected_candidate_payload=expected_candidate,
        )
        if isinstance(loaded, str):
            return _refusal(loaded, retryable=False)
        revision_doc, document_sha256 = loaded
        published_at = str(revision_doc["published_at"])
        recovered = True
    else:
        published_at = _utc_now_iso()
        revision_doc = _build_revision_document(
            candidate=candidate,
            fingerprint=fingerprint,
            output_revision_ref=output_revision_ref,
            published_at=published_at,
            candidate_payload=expected_candidate,
        )
        try:
            _atomic_write_json(revision_path, revision_doc)
        except OSError:
            return _refusal("dossier_publication_revision_write_failed", retryable=True)
        document_sha256 = _canonical_document_sha256(revision_doc)

    pointer_doc = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "output_ref": OUTPUT_REF,
        "output_revision_ref": output_revision_ref,
        "candidate_fingerprint": fingerprint,
        "relative_path": relative_path,
        "document_sha256": document_sha256,
        "published_at": published_at,
        "topology_fingerprint": candidate.topology_fingerprint,
    }
    try:
        _atomic_write_json(pointer_path, pointer_doc)
    except OSError:
        return _refusal("dossier_publication_pointer_write_failed", retryable=True)

    return _success_from_existing(
        candidate=candidate,
        fingerprint=fingerprint,
        output_revision_ref=output_revision_ref,
        published_at=published_at,
        idempotent_replay=False,
        recovered_existing_revision=recovered,
    )


class _PublicationLockBusy(Exception):
    """Nonblocking publication lock was already held."""


class _PublicationStorageFailed(Exception):
    """Directory creation or lock-file open failed."""


class _PointerInspection:
    __slots__ = ("payload", "error")

    def __init__(self, *, payload: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.payload = payload
        self.error = error


def _candidate_payload(candidate: DossierPublicationCandidate) -> dict[str, Any]:
    """Canonical JSON-native candidate representation used for persist and reuse checks."""
    return json.loads(_canonical_dumps(asdict(candidate)))


def _inspect_pointer(*, pointer_path: Path, output_dir: Path) -> _PointerInspection:
    if not pointer_path.exists():
        return _PointerInspection(payload=None)
    if not pointer_path.is_file():
        return _PointerInspection(error="dossier_publication_pointer_invalid")
    raw = _read_json_object(pointer_path)
    if raw is None:
        return _PointerInspection(error="dossier_publication_pointer_invalid")
    validated = _validate_pointer_coordinate(raw, output_dir=output_dir)
    if isinstance(validated, str):
        return _PointerInspection(error=validated)
    return _PointerInspection(payload=validated)


def _validate_pointer_coordinate(
    pointer: dict[str, Any], *, output_dir: Path
) -> dict[str, Any] | str:
    if set(pointer.keys()) != _POINTER_FIELDS:
        return "dossier_publication_pointer_invalid"
    if pointer.get("schema_version") != POINTER_SCHEMA_VERSION:
        return "dossier_publication_pointer_invalid"
    if pointer.get("output_ref") != OUTPUT_REF:
        return "dossier_publication_pointer_invalid"
    fingerprint = pointer.get("candidate_fingerprint")
    output_revision_ref = pointer.get("output_revision_ref")
    relative_path = pointer.get("relative_path")
    document_sha256 = pointer.get("document_sha256")
    published_at = pointer.get("published_at")
    topology_fingerprint = pointer.get("topology_fingerprint")
    if type(fingerprint) is not str or not _is_sha256_hex(fingerprint):
        return "dossier_publication_pointer_invalid"
    if type(output_revision_ref) is not str or output_revision_ref != _output_revision_ref(
        fingerprint
    ):
        return "dossier_publication_pointer_invalid"
    expected_relative = f"revisions/{fingerprint}.json"
    if type(relative_path) is not str or relative_path != expected_relative:
        return "dossier_publication_pointer_invalid"
    if type(document_sha256) is not str or not _is_sha256_hex(document_sha256):
        return "dossier_publication_pointer_invalid"
    if type(published_at) is not str or not published_at.strip():
        return "dossier_publication_pointer_invalid"
    if type(topology_fingerprint) is not str or not topology_fingerprint.strip():
        return "dossier_publication_pointer_invalid"

    revision_path = output_dir / relative_path.replace("\\", "/")
    if not revision_path.is_file():
        return "dossier_publication_pointer_invalid"
    loaded = _load_and_validate_revision_document(
        revision_path,
        expected_fingerprint=fingerprint,
        expected_output_revision_ref=output_revision_ref,
        expected_topology_fingerprint=topology_fingerprint,
        expected_candidate_payload=None,
    )
    if isinstance(loaded, str):
        return "dossier_publication_pointer_invalid"
    _revision_doc, actual_hash = loaded
    if actual_hash != document_sha256:
        return "dossier_publication_pointer_invalid"
    return pointer


def _load_and_validate_revision_document(
    path: Path,
    *,
    expected_fingerprint: str,
    expected_output_revision_ref: str,
    expected_topology_fingerprint: str,
    expected_candidate_payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], str] | str:
    raw = _read_json_object(path)
    if raw is None:
        return "dossier_publication_revision_invalid"
    if set(raw.keys()) != _REVISION_FIELDS:
        return "dossier_publication_revision_invalid"
    if raw.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        return "dossier_publication_revision_invalid"
    if raw.get("output_ref") != OUTPUT_REF:
        return "dossier_publication_revision_invalid"
    if raw.get("output_revision_ref") != expected_output_revision_ref:
        return "dossier_publication_revision_invalid"
    if raw.get("candidate_fingerprint") != expected_fingerprint:
        return "dossier_publication_revision_invalid"
    if type(raw.get("published_at")) is not str or not str(raw.get("published_at") or "").strip():
        return "dossier_publication_revision_invalid"
    candidate = raw.get("candidate")
    if not isinstance(candidate, dict):
        return "dossier_publication_revision_invalid"
    if candidate.get("candidate_fingerprint") != expected_fingerprint:
        return "dossier_publication_revision_invalid"
    if candidate.get("topology_fingerprint") != expected_topology_fingerprint:
        return "dossier_publication_revision_invalid"
    if Path(path).name != f"{expected_fingerprint}.json":
        return "dossier_publication_revision_invalid"
    if expected_candidate_payload is not None and candidate != expected_candidate_payload:
        return "dossier_publication_revision_invalid"
    try:
        document_sha256 = _canonical_document_sha256(raw)
    except (TypeError, ValueError):
        return "dossier_publication_revision_invalid"
    return raw, document_sha256


def _build_revision_document(
    *,
    candidate: DossierPublicationCandidate,
    fingerprint: str,
    output_revision_ref: str,
    published_at: str,
    candidate_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = candidate_payload if candidate_payload is not None else _candidate_payload(candidate)
    if payload.get("candidate_fingerprint") != fingerprint:
        raise ValueError("candidate_fingerprint_mismatch")
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "output_ref": OUTPUT_REF,
        "output_revision_ref": output_revision_ref,
        "published_at": published_at,
        "candidate_fingerprint": fingerprint,
        "candidate": payload,
    }


def _success_from_existing(
    *,
    candidate: DossierPublicationCandidate,
    fingerprint: str,
    output_revision_ref: str,
    published_at: str,
    idempotent_replay: bool,
    recovered_existing_revision: bool,
) -> dict[str, Any]:
    return {
        "executed": True,
        "artifact_refs": [OUTPUT_REF, output_revision_ref],
        "outputs": {
            "output_ref": OUTPUT_REF,
            "output_revision_ref": output_revision_ref,
            "candidate_fingerprint": fingerprint,
            "topology_fingerprint": candidate.topology_fingerprint,
            "segment_count": len(candidate.segments),
            "source_revision_count": len(candidate.source_revision_refs),
            "evidence_ref_count": len(candidate.evidence_refs),
            "published_at": published_at,
            "idempotent_replay": idempotent_replay,
            "recovered_existing_revision": recovered_existing_revision,
        },
    }


def _refusal(code: str, *, detail: str = "", retryable: bool = False) -> dict[str, Any]:
    safe_code = str(code or "dossier_publication_failed")
    # Keep refusal messages generic; never echo raw exception or host path text.
    message = safe_code if not detail else f"{safe_code}: {detail}"
    return {
        "executed": False,
        "refusal": {
            "reason_code": safe_code,
            "retryable": bool(retryable),
        },
        "outputs": {
            "error": {
                "code": safe_code,
                "message": message,
            }
        },
    }


def _output_revision_ref(fingerprint: str) -> str:
    return f"{_OUTPUT_REVISION_PREFIX}{fingerprint}"


def _is_sha256_hex(value: Any) -> bool:
    return type(value) is str and bool(_SHA256_HEX_RE.fullmatch(value))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_dumps(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_document_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_dumps(document).encode("utf-8")).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Validate serializability before touching the temp file.
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, tmp_path = tempfile.mkstemp(
        prefix="te_dossier_pub_",
        suffix=".json",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, str(path))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


@contextmanager
def _workspace_publish_lock(*, dossier_id: str, workspace_id: str) -> Iterator[None]:
    try:
        output_dir = dossier_transcript_edit_dossier_output_dir(dossier_id, workspace_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        lock_path = dossier_transcript_edit_dossier_publish_lock_path(dossier_id, workspace_id)
        handle = open(lock_path, "a+b")
    except OSError as exc:
        raise _PublicationStorageFailed() from exc

    locked = False
    try:
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise _PublicationLockBusy() from exc
        yield
    finally:
        # Never let unlock/close failures replace an already-produced result.
        if locked:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            handle.close()
        except OSError:
            pass
