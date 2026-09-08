"""Working-revision append orchestration for transcript-edit save/copy/apply.

Public API always acquires the working-write lock. Callers that already hold the
lock must use ``append_working_revision_under_lock`` (explicit locked seam).

Atomic IO: ``working_revision_atomic_io``. Strict state: ``working_revision_state``.
Shared read helpers: ``working_revision_io``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from tooling.mapping.transcript_edit.paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_latest_pointer_path,
    transcript_edit_manifest_path,
    transcript_edit_revision_path,
    transcript_edit_working_dir,
    transcript_edit_workspace_root,
)
from tooling.mapping.transcript_edit.working_revision_atomic_io import (
    RevisionCoordinateExists,
    atomic_write_json,
    compact_dumps,
    content_sha256_of_doc,
    create_only_write_json,
    sha256_text,
)
from tooling.mapping.transcript_edit.working_revision_io import (
    SCHEMA_VERSION,
    JsonObjectFileInvalid,
    ManifestStorageInvalid,
    load_json_file,
    load_or_init_manifest,
    parse_working_revision_ref,
    utc_now_iso,
)
from tooling.mapping.transcript_edit.working_revision_state import (
    MAX_WORKING_REVISION,
    read_working_storage_state,
    revision_coordinate_error,
)
from tooling.mapping.transcript_edit.working_write_lock import working_write_lock

# Rebindable aliases so failure-injection tests can target this module.
_atomic_write_json = atomic_write_json
_create_only_write_json = create_only_write_json

_VOLATILE_EQUALITY_FIELDS = frozenset({"saved_at"})


def _refuse(
    reason_code: str,
    error: str,
    *,
    retryable: bool = False,
    outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(outputs or {})
    out.setdefault("error", error)
    return {
        "executed": False,
        "refusal": {"reason_code": reason_code, "retryable": retryable},
        "outputs": out,
    }


def _success_result(
    *,
    revision_doc: dict[str, Any],
    content_sha256: str,
    byte_length: int,
    root: Path,
    rel_rev: str,
) -> dict[str, Any]:
    ref_id = str(revision_doc["ref_id"])
    next_rev = int(revision_doc["revision"])
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
            "byte_length": byte_length,
            "evidence_refs": list(revision_doc.get("evidence_refs") or []),
        },
    }


def _canonical_for_equality(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    for key in _VOLATILE_EQUALITY_FIELDS:
        out.pop(key, None)
    return out


def _docs_equivalent(existing: dict[str, Any], intended: dict[str, Any]) -> bool:
    """Full canonical equality; only explicitly volatile fields may differ."""
    return content_sha256_of_doc(_canonical_for_equality(existing)) == content_sha256_of_doc(
        _canonical_for_equality(intended)
    )


def _build_revision_doc(
    *,
    next_rev: int,
    payload: dict[str, Any],
    tool: str,
    base_revision_ref: str | None,
    evidence_refs: list[str] | None,
    rationale: str | None,
    extra_revision_fields: dict[str, Any] | None,
    saved_at: str | None = None,
) -> dict[str, Any]:
    rev_digits = f"{next_rev:04d}"
    ref_id = f"transcript_edit:working:rev:{rev_digits}"
    refs: list[str] = []
    for item in evidence_refs or []:
        if type(item) is not str or not item.strip():
            continue
        refs.append(item.strip())
    revision_doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "revision": next_rev,
        "ref_id": ref_id,
        "saved_at": saved_at or utc_now_iso(),
        "tool": tool,
        "base_revision_ref": (
            base_revision_ref.strip()
            if type(base_revision_ref) is str and base_revision_ref.strip()
            else None
        ),
        "evidence_refs": refs,
        "rationale": (
            rationale.strip() if type(rationale) is str and rationale.strip() else None
        ),
        "payload": payload,
    }
    if extra_revision_fields:
        revision_doc.update(extra_revision_fields)
    return revision_doc


def _advance_pointers(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    revision_doc: dict[str, Any],
    content_sha256: str,
    byte_length: int,
    tool: str,
    extra_latest_fields: dict[str, Any] | None,
    extra_manifest_fields: dict[str, Any] | None,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """Advance latest then manifest. Returns a refusal dict on failure, else None."""
    coord_err = revision_coordinate_error(revision_doc)
    if coord_err is not None:
        return _refuse(
            "invalid_revision_coordinate",
            f"Refusing pointer advancement: {coord_err}",
        )

    next_rev = int(revision_doc["revision"])
    ref_id = str(revision_doc["ref_id"])
    saved_at = str(revision_doc["saved_at"])
    rev_digits = f"{next_rev:04d}"
    rel_rev = f"working/rev_{rev_digits}.json"

    latest_pointer: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "revision": next_rev,
        "ref_id": ref_id,
        "relative_path": rel_rev,
        "content_sha256": content_sha256,
        "byte_length": byte_length,
        "saved_at": saved_at,
        "tool": tool,
    }
    if extra_latest_fields:
        latest_pointer.update(extra_latest_fields)

    try:
        _atomic_write_json(
            transcript_edit_latest_pointer_path(dossier_id, transcription_id, workspace_id),
            latest_pointer,
        )
    except OSError:
        return _refuse(
            "storage_failure_partial",
            (
                "Immutable revision was written but working head/manifest update failed. "
                "Do not assume the workspace head advanced."
            ),
            outputs={"orphan_revision_ref": ref_id},
        )

    manifest["updated_at"] = saved_at
    manifest["revision_count"] = next_rev
    manifest["latest_revision"] = next_rev
    manifest["latest_working_ref_id"] = ref_id
    manifest["latest_saved_at"] = saved_at
    manifest["latest_content_sha256"] = content_sha256
    manifest["last_save_tool"] = tool
    if extra_manifest_fields:
        manifest.update(extra_manifest_fields)

    try:
        _atomic_write_json(
            transcript_edit_manifest_path(dossier_id, transcription_id, workspace_id),
            manifest,
        )
    except OSError:
        return _refuse(
            "storage_failure_partial",
            (
                "Working latest pointer advanced but manifest update failed. "
                "Do not assume manifest metadata is current."
            ),
            outputs={"working_draft_ref": ref_id},
        )
    return None


@contextmanager
def working_write_transaction(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> Iterator[None]:
    """Acquire ``working_write_lock`` for a multi-step working-write transaction.

    Do not nest. For append while already holding the lock, call
    ``append_working_revision_under_lock`` instead of nesting this context.
    """
    with working_write_lock(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    ):
        yield


def current_working_head_ref(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> str | None:
    """Return the current working head ref_id, or None when absent/invalid."""
    state = read_working_storage_state(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    )
    if state.kind in {"coherent", "manifest_lag", "recoverable_orphan"}:
        return state.head_ref_id
    return None


def heal_working_manifest_from_head(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> bool:
    """Align ``manifest.json`` to a coherent ``latest.json`` head when it lags.

    Call only while holding the working-write lock. Returns False on invalid state.
    """
    state = read_working_storage_state(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    )
    if state.kind == "coherent":
        return True
    if state.kind != "manifest_lag" or state.head_revision is None or state.head_ref_id is None:
        return False

    try:
        latest = load_json_file(
            transcript_edit_latest_pointer_path(dossier_id, transcription_id, workspace_id)
        )
    except JsonObjectFileInvalid:
        return False
    if not latest:
        return False
    content_sha256 = latest.get("content_sha256")
    if type(content_sha256) is not str or not content_sha256.strip():
        digits = parse_working_revision_ref(state.head_ref_id)
        if digits is None:
            return False
        try:
            rev_doc = load_json_file(
                transcript_edit_revision_path(
                    dossier_id, transcription_id, workspace_id, digits
                )
            )
        except JsonObjectFileInvalid:
            return False
        if not rev_doc:
            return False
        content_sha256 = content_sha256_of_doc(rev_doc)

    saved_at = latest.get("saved_at")
    if type(saved_at) is not str or not saved_at.strip():
        saved_at = utc_now_iso()
    tool = latest.get("tool")
    if type(tool) is not str or not tool.strip():
        tool = "unknown"

    try:
        manifest = load_or_init_manifest(dossier_id, transcription_id, workspace_id)
    except ManifestStorageInvalid:
        return False
    next_rev = state.head_revision
    manifest["updated_at"] = saved_at
    manifest["revision_count"] = next_rev
    manifest["latest_revision"] = next_rev
    manifest["latest_working_ref_id"] = state.head_ref_id
    manifest["latest_saved_at"] = saved_at
    manifest["latest_content_sha256"] = content_sha256
    manifest["last_save_tool"] = tool
    try:
        _atomic_write_json(
            transcript_edit_manifest_path(dossier_id, transcription_id, workspace_id),
            manifest,
        )
    except OSError:
        return False
    return True


def load_current_head_payload(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> dict[str, Any] | None:
    """Load the payload object from the current working head revision, if present."""
    head_ref = current_working_head_ref(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    )
    if head_ref is None:
        return None
    digits = parse_working_revision_ref(head_ref)
    if digits is None:
        return None
    try:
        doc = load_json_file(
            transcript_edit_revision_path(dossier_id, transcription_id, workspace_id, digits)
        )
    except JsonObjectFileInvalid:
        return None
    if not doc:
        return None
    payload = doc.get("payload")
    return payload if isinstance(payload, dict) else None


def append_working_revision(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    payload: dict[str, Any],
    tool: str,
    base_revision_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    rationale: str | None = None,
    extra_revision_fields: dict[str, Any] | None = None,
    extra_latest_fields: dict[str, Any] | None = None,
    extra_manifest_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one immutable working revision under a freshly acquired write lock."""
    with working_write_transaction(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    ):
        return append_working_revision_under_lock(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            payload=payload,
            tool=tool,
            base_revision_ref=base_revision_ref,
            evidence_refs=evidence_refs,
            rationale=rationale,
            extra_revision_fields=extra_revision_fields,
            extra_latest_fields=extra_latest_fields,
            extra_manifest_fields=extra_manifest_fields,
        )


def append_working_revision_under_lock(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    payload: dict[str, Any],
    tool: str,
    base_revision_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    rationale: str | None = None,
    extra_revision_fields: dict[str, Any] | None = None,
    extra_latest_fields: dict[str, Any] | None = None,
    extra_manifest_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append while the caller already holds ``working_write_lock`` for this workspace.

    Do not call this without holding the lock. Prefer ``append_working_revision`` when
    the caller does not already own the lock.
    """
    try:
        root = transcript_edit_workspace_root(dossier_id, transcription_id, workspace_id)
        work_dir = transcript_edit_working_dir(dossier_id, transcription_id, workspace_id)
        work_dir.mkdir(parents=True, exist_ok=True)

        state = read_working_storage_state(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
        )
        if state.kind == "invalid":
            return _refuse(
                "invalid_working_storage_state",
                state.detail or "Working storage state is invalid; refusing write.",
            )

        try:
            manifest = load_or_init_manifest(dossier_id, transcription_id, workspace_id)
        except ManifestStorageInvalid as exc:
            return _refuse("invalid_working_storage_state", exc.detail)

        build_kwargs = dict(
            payload=payload,
            tool=tool,
            base_revision_ref=base_revision_ref,
            evidence_refs=evidence_refs,
            rationale=rationale,
            extra_revision_fields=extra_revision_fields,
        )

        if state.kind == "recoverable_orphan":
            orphan_digits = f"{state.file_max:04d}"
            orphan_path = transcript_edit_revision_path(
                dossier_id, transcription_id, workspace_id, orphan_digits
            )
            try:
                existing = load_json_file(orphan_path)
            except JsonObjectFileInvalid as exc:
                return _refuse("invalid_working_storage_state", exc.detail)
            intended = _build_revision_doc(next_rev=state.file_max, **build_kwargs)
            if existing is None:
                return _refuse(
                    "storage_failure",
                    "Orphan revision coordinate is unreadable; refusing to overwrite.",
                    outputs={
                        "orphan_revision_ref": f"transcript_edit:working:rev:{orphan_digits}"
                    },
                )
            return _recover_equivalent_existing_revision(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_id,
                root=root,
                existing=existing,
                intended=intended,
                expected_revision=state.file_max,
                tool=tool,
                extra_latest_fields=extra_latest_fields,
                extra_manifest_fields=extra_manifest_fields,
                manifest=manifest,
                conflict_message=(
                    "An orphan revision exists at this coordinate with different content; "
                    "refusing to overwrite."
                ),
            )

        if state.storage_max >= MAX_WORKING_REVISION:
            return _refuse(
                "revision_capacity_exceeded",
                f"Working revision capacity is exhausted at {MAX_WORKING_REVISION}.",
            )

        next_rev = state.storage_max + 1
        revision_doc = _build_revision_doc(next_rev=next_rev, **build_kwargs)
        rev_digits = f"{next_rev:04d}"
        ref_id = str(revision_doc["ref_id"])
        rev_path = transcript_edit_revision_path(
            dossier_id, transcription_id, workspace_id, rev_digits
        )
        try:
            rev_blob = compact_dumps(revision_doc)
        except (TypeError, ValueError) as exc:
            return _refuse(
                "noncanonical_revision_payload",
                f"Revision document is not JSON-canonical (NaN/Inf refused): {exc}",
            )
        content_sha256 = sha256_text(rev_blob)
        byte_length = len(rev_blob.encode("utf-8"))
        rel_rev = f"working/rev_{rev_digits}.json"

        try:
            _create_only_write_json(rev_path, revision_doc)
        except RevisionCoordinateExists:
            try:
                existing = load_json_file(rev_path)
            except JsonObjectFileInvalid as exc:
                return _refuse("invalid_working_storage_state", exc.detail)
            if existing is None:
                return _refuse(
                    "conflicting_revision_coordinate",
                    (
                        "Revision coordinate already exists with different content; "
                        "refusing to overwrite."
                    ),
                    outputs={"orphan_revision_ref": ref_id},
                )
            return _recover_equivalent_existing_revision(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=workspace_id,
                root=root,
                existing=existing,
                intended=revision_doc,
                expected_revision=next_rev,
                tool=tool,
                extra_latest_fields=extra_latest_fields,
                extra_manifest_fields=extra_manifest_fields,
                manifest=manifest,
                conflict_message=(
                    "Revision coordinate already exists with different content; "
                    "refusing to overwrite."
                ),
            )
        except (OSError, TypeError, ValueError) as exc:
            if isinstance(exc, (TypeError, ValueError)):
                return _refuse(
                    "noncanonical_revision_payload",
                    f"Revision document is not JSON-canonical (NaN/Inf refused): {exc}",
                )
            return _refuse(
                "storage_failure",
                "Failed to write immutable revision file.",
            )

        if not rev_path.is_file():
            return _refuse(
                "storage_failure",
                "Revision promotion did not produce a durable revision file.",
            )

        partial = _advance_pointers(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            revision_doc=revision_doc,
            content_sha256=content_sha256,
            byte_length=byte_length,
            tool=tool,
            extra_latest_fields=extra_latest_fields,
            extra_manifest_fields=extra_manifest_fields,
            manifest=manifest,
        )
        if partial is not None:
            return partial

        return _success_result(
            revision_doc=revision_doc,
            content_sha256=content_sha256,
            byte_length=byte_length,
            root=root,
            rel_rev=rel_rev,
        )
    except UnsafeArtifactPathSegmentError as exc:
        return _refuse("invalid_scope_path", str(exc))


def _recover_equivalent_existing_revision(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    root: Path,
    existing: dict[str, Any],
    intended: dict[str, Any],
    expected_revision: int,
    tool: str,
    extra_latest_fields: dict[str, Any] | None,
    extra_manifest_fields: dict[str, Any] | None,
    manifest: dict[str, Any],
    conflict_message: str,
) -> dict[str, Any]:
    coord_err = revision_coordinate_error(existing, expected_revision=expected_revision)
    if coord_err is not None:
        return _refuse(
            "invalid_revision_coordinate",
            f"Existing revision coordinate is incoherent: {coord_err}",
            outputs={
                "orphan_revision_ref": str(
                    existing.get("ref_id") or intended.get("ref_id") or ""
                )
            },
        )
    if not _docs_equivalent(existing, intended):
        return _refuse(
            "conflicting_revision_coordinate",
            conflict_message,
            outputs={
                "orphan_revision_ref": str(
                    existing.get("ref_id") or intended.get("ref_id") or ""
                )
            },
        )
    content_sha256 = content_sha256_of_doc(existing)
    byte_length = len(compact_dumps(existing).encode("utf-8"))
    digits = f"{expected_revision:04d}"
    partial = _advance_pointers(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        revision_doc=existing,
        content_sha256=content_sha256,
        byte_length=byte_length,
        tool=str(existing.get("tool") or tool),
        extra_latest_fields=extra_latest_fields,
        extra_manifest_fields=extra_manifest_fields,
        manifest=manifest,
    )
    if partial is not None:
        return partial
    return _success_result(
        revision_doc=existing,
        content_sha256=content_sha256,
        byte_length=byte_length,
        root=root,
        rel_rev=f"working/rev_{digits}.json",
    )
