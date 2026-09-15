"""Initialize the first working transcript revision from one exact T0 draft ref.

Domain-owned action semantics live in tool specs; this module owns exact T0
loading, payload construction, locking, persistence, and idempotent replay.
"""

from __future__ import annotations

from typing import Any

from domains.mapping.transcript_edit.payloads.initialization_provenance import (
    COPY_POSTURE_UNVERIFIED_CANDIDATE,
    INITIALIZATION_PROVENANCE_FIELD,
    INITIALIZATION_PROVENANCE_SCHEMA_VERSION,
    INITIALIZED_TRANSCRIPT_LANES,
)
from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    MAX_EDIT_TEXT_CHARS,
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
    TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
)
from tooling.mapping.transcript_edit.draft_loading import (
    ExactT0DraftLoadError,
    ExactT0DraftText,
    ExactWorkingRevisionLoadError,
    load_exact_t0_draft_text,
    load_exact_working_revision_document,
)
from tooling.mapping.transcript_edit.draft_persistence import (
    parse_working_revision_ref,
    resolve_workspace_key,
)
from tooling.mapping.transcript_edit.paths import UnsafeArtifactPathSegmentError
from tooling.mapping.transcript_edit.transcript_edit_decisions_validate import (
    PersistedProvenanceError,
    validate_persisted_transcript_edit_decisions,
)
from tooling.mapping.transcript_edit.working_revision_io import SCHEMA_VERSION
from tooling.mapping.transcript_edit.working_revision_state import read_working_storage_state
from tooling.mapping.transcript_edit.working_revision_transaction import (
    append_working_revision_under_lock,
    heal_working_manifest_from_head,
    revision_docs_equivalent,
    revision_saved_at_error,
)
from tooling.mapping.transcript_edit.working_write_lock import (
    WorkingWriteLockBusy,
    WorkingWriteLockFailed,
    working_write_lock,
)

_TOOL_ID = "initialize_working_transcript"
_ALLOWED_REQUEST_KEYS = frozenset({"source_ref"})
_ALLOWED_PROVENANCE_KEYS = frozenset(
    {
        "schema_version",
        "source_ref",
        "source_text_sha256",
        "copy_posture",
        "copied_lanes",
    }
)
_SHA256_HEX_LEN = 64


def initialize_working_transcript(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str | None = None,
    run_id: str | None = None,
    request: dict[str, Any] | None = None,
    durable_source_ref: str | None = None,
) -> dict[str, Any]:
    """Copy one exact T0 draft into working revision 0001 under the lineage lock.

    ``request.source_ref`` is the leaf T0 load ref. Optional ``durable_source_ref`` is
    an internal validated identity for persistence (dossier-qualified). When omitted,
    leaf mode persists the same load ref. Not a caller-authored request field.
    """
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    ws = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not ws:
        return _refuse(
            "workspace_key_required",
            "Provide workspace_id or run_id to scope transcript-edit artifact storage.",
        )

    try:
        load_source_ref = _validate_request(request)
        durable = _validate_durable_source_ref(
            durable_source_ref,
            load_source_ref=load_source_ref,
        )
    except _ContractError as exc:
        return _refuse(exc.reason_code, exc.detail)

    try:
        with working_write_lock(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=ws,
        ):
            return _initialize_under_lock(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=ws,
                load_source_ref=load_source_ref,
                durable_source_ref=durable,
            )
    except WorkingWriteLockBusy:
        return _refuse(
            "working_write_in_progress",
            "Another working write holds the lock for this workspace.",
        )
    except WorkingWriteLockFailed:
        return _refuse("storage_failure", "Unable to acquire working write lock.")
    except UnsafeArtifactPathSegmentError:
        return _refuse("invalid_scope_path", "Scope path segments are invalid.")


def make_initialize_working_transcript_handler(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
):
    """Leaf-mode handler closed over scope."""

    def handler(request: Any) -> Any:
        inputs = (
            dict(request.inputs)
            if hasattr(request, "inputs")
            else dict(request)
            if isinstance(request, dict)
            else {}
        )
        return initialize_working_transcript(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_key,
            request=inputs,
        )

    return handler


def _initialize_under_lock(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    load_source_ref: str,
    durable_source_ref: str,
) -> dict[str, Any]:
    try:
        loaded = load_exact_t0_draft_text(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            source_ref=load_source_ref,
        )
    except ExactT0DraftLoadError as exc:
        return _refuse(exc.code, exc.detail or _default_detail(exc.code))

    if len(loaded.text) > MAX_EDIT_TEXT_CHARS:
        return _refuse(
            "source_text_oversized",
            f"Selected T0 text exceeds {MAX_EDIT_TEXT_CHARS} characters.",
        )

    expected_payload = _build_initialization_payload(
        loaded,
        durable_source_ref=durable_source_ref,
    )
    try:
        _assert_initialization_payload_coherent(
            expected_payload,
            loaded=loaded,
            durable_source_ref=durable_source_ref,
        )
    except _ContractError as exc:
        return _refuse(exc.reason_code, exc.detail)

    expected_revision = _build_expected_revision_doc(
        payload=expected_payload,
        durable_source_ref=durable_source_ref,
    )

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

    if state.kind == "empty":
        append_result = append_working_revision_under_lock(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            payload=expected_payload,
            tool=_TOOL_ID,
            base_revision_ref=None,
            evidence_refs=[durable_source_ref],
            rationale=None,
        )
        if append_result.get("executed") is not True:
            return append_result
        return _success_from_append(
            append_result,
            source_ref=durable_source_ref,
            idempotent_replay=False,
        )

    if state.kind == "manifest_lag":
        if not heal_working_manifest_from_head(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
        ):
            return _refuse(
                "invalid_working_storage_state",
                "Unable to heal lagging working manifest before initialization replay.",
            )
        state = read_working_storage_state(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
        )
        if state.kind != "coherent":
            return _refuse(
                "invalid_working_storage_state",
                "Working storage remained incoherent after manifest heal.",
            )

    if state.kind == "recoverable_orphan":
        # Shared append seam recovers equivalent orphan coordinates or refuses conflicts.
        append_result = append_working_revision_under_lock(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            payload=expected_payload,
            tool=_TOOL_ID,
            base_revision_ref=None,
            evidence_refs=[durable_source_ref],
            rationale=None,
        )
        if append_result.get("executed") is not True:
            return append_result
        state_after = read_working_storage_state(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
        )
        if state_after.kind != "coherent":
            return _refuse(
                "invalid_working_storage_state",
                "Working storage remained orphaned after recovery attempt.",
            )
        return _success_from_append(
            append_result,
            source_ref=durable_source_ref,
            idempotent_replay=True,
        )

    if state.kind != "coherent":
        return _refuse(
            "invalid_working_storage_state",
            state.detail or "Working storage state is invalid; refusing write.",
        )

    return _idempotent_coherent_replay(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        head_ref_id=state.head_ref_id,
        expected_revision=expected_revision,
        durable_source_ref=durable_source_ref,
    )


def _idempotent_coherent_replay(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    head_ref_id: str | None,
    expected_revision: dict[str, Any],
    durable_source_ref: str,
) -> dict[str, Any]:
    if type(head_ref_id) is not str or not head_ref_id.strip():
        return _refuse(
            "invalid_working_storage_state",
            "Working lineage is non-empty but has no coherent head.",
        )
    digits = parse_working_revision_ref(head_ref_id)
    if digits is None:
        return _refuse(
            "invalid_working_storage_state",
            "Working head ref is not an exact revision coordinate.",
        )
    if digits != "0001":
        return _refuse(
            "working_lineage_already_initialized",
            "Working lineage already advanced beyond revision 0001; cannot reinitialize.",
        )

    try:
        head = load_exact_working_revision_document(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            revision_ref=head_ref_id,
            workspace_id=workspace_id,
        )
    except ExactWorkingRevisionLoadError as exc:
        return _refuse(
            "invalid_working_storage_state",
            exc.detail or "Failed to load current working head.",
        )

    saved_at_err = revision_saved_at_error(head.document)
    if saved_at_err is not None:
        return _refuse("invalid_working_storage_state", saved_at_err)

    if not revision_docs_equivalent(head.document, expected_revision):
        return _refuse(
            "conflicting_initialization_replay",
            "Revision 0001 exists but does not match this initialization identity.",
        )

    return _success_result(
        working_draft_ref=head_ref_id,
        source_ref=durable_source_ref,
        idempotent_replay=True,
        evidence_refs=list(head.document.get("evidence_refs") or []),
    )


def _build_initialization_payload(
    loaded: ExactT0DraftText,
    *,
    durable_source_ref: str,
) -> dict[str, Any]:
    text = loaded.text
    return {
        "source_transcript_verbatim": text,
        "normalized_or_mapping_transcript": text,
        "evidence_refs": [durable_source_ref],
        TRANSCRIPT_EDIT_DECISIONS_FIELD: {
            "schema_version": TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
            "decisions": [],
        },
        INITIALIZATION_PROVENANCE_FIELD: {
            "schema_version": INITIALIZATION_PROVENANCE_SCHEMA_VERSION,
            "source_ref": durable_source_ref,
            "source_text_sha256": loaded.source_text_sha256,
            "copy_posture": COPY_POSTURE_UNVERIFIED_CANDIDATE,
            "copied_lanes": list(INITIALIZED_TRANSCRIPT_LANES),
        },
    }


def _build_expected_revision_doc(
    *,
    payload: dict[str, Any],
    durable_source_ref: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "ref_id": "transcript_edit:working:rev:0001",
        "tool": _TOOL_ID,
        "base_revision_ref": None,
        "evidence_refs": [durable_source_ref],
        "rationale": None,
        "payload": payload,
    }


def _assert_initialization_payload_coherent(
    payload: dict[str, Any],
    *,
    loaded: ExactT0DraftText,
    durable_source_ref: str,
) -> None:
    for lane in INITIALIZED_TRANSCRIPT_LANES:
        value = payload.get(lane)
        if type(value) is not str or value != loaded.text:
            raise _ContractError(
                "conflicting_initialization_replay",
                f"Transcript lane {lane!r} does not match the selected T0 text.",
            )

    evidence = payload.get("evidence_refs")
    if type(evidence) is not list or evidence != [durable_source_ref]:
        raise _ContractError(
            "conflicting_initialization_replay",
            "Payload evidence_refs must equal the durable source_ref.",
        )

    try:
        validate_persisted_transcript_edit_decisions(payload=payload, require_present=True)
    except PersistedProvenanceError as exc:
        raise _ContractError(exc.reason_code, exc.detail) from exc

    block = payload.get(TRANSCRIPT_EDIT_DECISIONS_FIELD)
    if type(block) is not dict or block.get("decisions") != []:
        raise _ContractError(
            "conflicting_initialization_replay",
            "Initialization requires an empty schema-v2 decision ledger.",
        )

    _validate_initialization_provenance(
        payload.get(INITIALIZATION_PROVENANCE_FIELD),
        loaded=loaded,
        durable_source_ref=durable_source_ref,
    )


def _validate_initialization_provenance(
    block: Any,
    *,
    loaded: ExactT0DraftText,
    durable_source_ref: str,
) -> None:
    if type(block) is not dict:
        raise _ContractError(
            "invalid_initialization_provenance",
            "initialization_provenance must be an object.",
        )
    unknown = sorted(set(block) - _ALLOWED_PROVENANCE_KEYS)
    if unknown:
        raise _ContractError(
            "invalid_initialization_provenance",
            f"Unknown initialization_provenance fields: {unknown}",
        )
    schema = block.get("schema_version")
    if type(schema) is not int or isinstance(schema, bool):
        raise _ContractError(
            "invalid_initialization_provenance",
            "schema_version must be an exact integer.",
        )
    if schema != INITIALIZATION_PROVENANCE_SCHEMA_VERSION:
        raise _ContractError(
            "unsupported_provenance_schema",
            f"Only initialization provenance schema_version "
            f"{INITIALIZATION_PROVENANCE_SCHEMA_VERSION} is accepted.",
        )
    source_ref = block.get("source_ref")
    if type(source_ref) is not str or source_ref != durable_source_ref:
        raise _ContractError(
            "conflicting_initialization_replay",
            "initialization_provenance.source_ref does not match the durable source identity.",
        )
    digest = block.get("source_text_sha256")
    if (
        type(digest) is not str
        or len(digest) != _SHA256_HEX_LEN
        or digest != digest.lower()
        or any(ch not in "0123456789abcdef" for ch in digest)
        or digest != loaded.source_text_sha256
    ):
        raise _ContractError(
            "conflicting_initialization_replay",
            "initialization_provenance.source_text_sha256 does not match source text.",
        )
    if block.get("copy_posture") != COPY_POSTURE_UNVERIFIED_CANDIDATE:
        raise _ContractError(
            "invalid_initialization_provenance",
            "copy_posture must be unverified_candidate_copy.",
        )
    lanes = block.get("copied_lanes")
    if type(lanes) is not list or lanes != list(INITIALIZED_TRANSCRIPT_LANES):
        raise _ContractError(
            "invalid_initialization_provenance",
            "copied_lanes must list both transcript lanes in canonical order.",
        )
    for key in ("path", "absolute_path", "workspace_root", "b64", "bytes"):
        if key in block:
            raise _ContractError(
                "invalid_initialization_provenance",
                "initialization_provenance must not include host or binary material.",
            )


def _validate_request(request: dict[str, Any] | None) -> str:
    if request is None or type(request) is not dict:
        raise _ContractError("invalid_request", "Request must be a JSON object.")
    unknown = sorted(set(request) - _ALLOWED_REQUEST_KEYS)
    if unknown:
        raise _ContractError(
            "unknown_request_fields",
            f"Unknown fields: {unknown}",
        )
    if "source_ref" not in request:
        raise _ContractError("source_ref_required", "source_ref is required.")
    raw = request.get("source_ref")
    if type(raw) is not str:
        raise _ContractError(
            "source_ref_invalid_type",
            "source_ref must be an exact nonblank string.",
        )
    if not raw.strip():
        raise _ContractError(
            "source_ref_required",
            "source_ref must be an exact nonblank string.",
        )
    if raw != raw.strip():
        raise _ContractError(
            "source_ref_invalid_type",
            "source_ref must be an exact nonblank string with no surrounding whitespace.",
        )
    return raw


def _validate_durable_source_ref(
    durable_source_ref: str | None,
    *,
    load_source_ref: str,
) -> str:
    if durable_source_ref is None:
        return load_source_ref
    if type(durable_source_ref) is not str:
        raise _ContractError(
            "source_ref_invalid_type",
            "durable source identity must be an exact nonblank string.",
        )
    if not durable_source_ref.strip() or durable_source_ref != durable_source_ref.strip():
        raise _ContractError(
            "source_ref_invalid_type",
            "durable source identity must be an exact nonblank string.",
        )
    return durable_source_ref


def _success_from_append(
    append_result: dict[str, Any],
    *,
    source_ref: str,
    idempotent_replay: bool,
) -> dict[str, Any]:
    outputs = append_result.get("outputs")
    if type(outputs) is not dict:
        return _refuse("storage_failure", "Append succeeded without outputs.")
    working_draft_ref = outputs.get("working_draft_ref")
    if type(working_draft_ref) is not str or not working_draft_ref.strip():
        return _refuse("storage_failure", "Append succeeded without working_draft_ref.")
    return _success_result(
        working_draft_ref=working_draft_ref,
        source_ref=source_ref,
        idempotent_replay=idempotent_replay,
        evidence_refs=list(outputs.get("evidence_refs") or [source_ref]),
        artifact_refs=append_result.get("artifact_refs"),
    )


def _success_result(
    *,
    working_draft_ref: str,
    source_ref: str,
    idempotent_replay: bool,
    evidence_refs: list[str],
    artifact_refs: Any = None,
) -> dict[str, Any]:
    aggregate = "transcript_edit:working"
    refs = artifact_refs
    if refs is None:
        refs = (working_draft_ref, aggregate)
    return {
        "executed": True,
        "artifact_refs": refs,
        "outputs": {
            "working_draft_ref": working_draft_ref,
            "aggregate_working_ref": aggregate,
            "source_ref": source_ref,
            "initialization_posture": COPY_POSTURE_UNVERIFIED_CANDIDATE,
            "copied_lanes": list(INITIALIZED_TRANSCRIPT_LANES),
            "idempotent_replay": bool(idempotent_replay),
            "evidence_refs": list(evidence_refs),
        },
    }


def _refuse(reason_code: str, error: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {"reason_code": reason_code, "retryable": False},
        "outputs": {"error": error},
    }


def _default_detail(code: str) -> str:
    return {
        "source_ref_required": "source_ref must be an exact nonblank string.",
        "source_ref_invalid_type": "source_ref must be an exact nonblank string.",
        "unsupported_source_ref": "source_ref must be an exact hydratable T0 draft ref.",
        "source_ref_unresolved": "The named T0 draft ref could not be resolved.",
        "source_text_missing": "Selected T0 draft text is missing or blank.",
        "source_text_invalid": "Selected T0 draft text is invalid.",
        "invalid_scope_path": "Scope path segments are invalid.",
    }.get(code, "")


class _ContractError(Exception):
    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = str(reason_code)
        self.detail = str(detail or "")
        super().__init__(
            self.reason_code if not self.detail else f"{self.reason_code}: {self.detail}"
        )
