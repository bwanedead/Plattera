"""Persist apply_transcript_edits against the shared working-revision layout."""

from __future__ import annotations

from typing import Any

from tooling.mapping.transcript_edit.apply_transcript_edits_contract import (
    ApplyTranscriptEditsContractError,
    ValidatedApplyTranscriptEditsRequest,
    validate_apply_transcript_edits_request,
)
from tooling.mapping.transcript_edit.apply_transcript_edits_engine import (
    ApplyTranscriptEditsEngineError,
    apply_transcript_edits_to_payload,
)
from tooling.mapping.transcript_edit.draft_loading import (
    ExactWorkingRevisionLoadError,
    load_exact_working_revision_document,
)
from tooling.mapping.transcript_edit.draft_persistence import (
    parse_working_revision_ref,
    resolve_workspace_key,
)
from tooling.mapping.transcript_edit.paths import UnsafeArtifactPathSegmentError
from tooling.mapping.transcript_edit.working_revision_transaction import (
    append_working_revision_under_lock,
    current_working_head_ref,
    heal_working_manifest_from_head,
)
from tooling.mapping.transcript_edit.working_write_lock import (
    WorkingWriteLockBusy,
    WorkingWriteLockFailed,
    working_write_lock,
)


def apply_transcript_edits(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str | None = None,
    run_id: str | None = None,
    request: dict[str, Any] | ValidatedApplyTranscriptEditsRequest,
) -> dict[str, Any]:
    """Apply exact revision-bound edits and persist decision provenance."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    ws = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not ws:
        return {
            "executed": False,
            "refusal": {"reason_code": "workspace_key_required", "retryable": False},
            "outputs": {
                "error": "Provide workspace_id or run_id to scope transcript-edit artifact storage.",
            },
        }

    try:
        validated = (
            request
            if isinstance(request, ValidatedApplyTranscriptEditsRequest)
            else validate_apply_transcript_edits_request(request)
        )
    except ApplyTranscriptEditsContractError as exc:
        return _refuse(exc.reason_code, exc.detail, repair_hint=exc.repair_hint)

    if parse_working_revision_ref(validated.base_revision_ref) is None:
        return _refuse(
            "invalid_base_revision_ref",
            "base_revision_ref must match transcript_edit:working:rev:NNNN.",
        )

    try:
        with working_write_lock(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=ws,
        ):
            return _apply_under_lock(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                workspace_id=ws,
                validated=validated,
            )
    except WorkingWriteLockBusy:
        return _refuse(
            "working_write_in_progress",
            "Another working write holds the lock for this workspace.",
        )
    except WorkingWriteLockFailed as exc:
        return _refuse("storage_failure", f"Unable to acquire working write lock: {exc}")
    except UnsafeArtifactPathSegmentError as exc:
        return _refuse("invalid_scope_path", str(exc))


def make_apply_transcript_edits_handler(
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
        return apply_transcript_edits(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_key,
            request=inputs,
        )

    return handler


def _apply_under_lock(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    validated: ValidatedApplyTranscriptEditsRequest,
) -> dict[str, Any]:
    head_ref = current_working_head_ref(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    )
    if head_ref is None:
        return _refuse(
            "working_head_missing",
            "No working head exists; create an initial draft with save_workspace_artifact first.",
        )

    replay = _maybe_idempotent_replay(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        head_ref=head_ref,
        validated=validated,
    )
    if replay is not None:
        return replay

    if head_ref != validated.base_revision_ref:
        return _refuse(
            "stale_base_revision",
            "base_revision_ref is not the current working head; hydrate the head and retry.",
        )

    try:
        loaded = load_exact_working_revision_document(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            revision_ref=validated.base_revision_ref,
            workspace_id=workspace_id,
        )
    except ExactWorkingRevisionLoadError as exc:
        return _refuse(exc.code, exc.detail or "Failed to load base revision.")

    base_doc = loaded.document
    base_payload = base_doc.get("payload")
    if type(base_payload) is not dict:
        return _refuse("malformed_revision_document", "Base revision payload must be an object.")

    base_evidence = base_doc.get("evidence_refs")
    if type(base_evidence) is not list:
        return _refuse("malformed_revision_document", "Base revision evidence_refs must be a list.")
    base_evidence_refs = [
        str(x).strip() for x in base_evidence if type(x) is str and str(x).strip()
    ]

    try:
        engine_result = apply_transcript_edits_to_payload(
            base_payload=base_payload,
            base_revision_evidence_refs=base_evidence_refs,
            base_revision_ref=validated.base_revision_ref,
            request=validated,
        )
    except ApplyTranscriptEditsEngineError as exc:
        return _refuse(exc.reason_code, exc.detail)

    if (
        current_working_head_ref(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
        )
        != validated.base_revision_ref
    ):
        return _refuse(
            "stale_base_revision",
            "Working head changed before persistence; no write performed.",
        )

    persisted = append_working_revision_under_lock(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        payload=engine_result.payload,
        tool="apply_transcript_edits",
        base_revision_ref=validated.base_revision_ref,
        evidence_refs=list(engine_result.revision_evidence_refs),
        extra_revision_fields={
            "apply_request_identity": validated.request_identity,
            "apply_result_summary": {
                "applied_decision_ids": list(engine_result.applied_decision_ids),
                "changed_lanes": dict(engine_result.changed_lanes),
            },
        },
        extra_latest_fields={
            "apply_request_identity": validated.request_identity,
            "apply_base_revision_ref": validated.base_revision_ref,
        },
        extra_manifest_fields={"last_apply_request_identity": validated.request_identity},
    )
    if not persisted.get("executed"):
        return persisted

    outputs = dict(persisted.get("outputs") or {})
    outputs["base_revision_ref"] = validated.base_revision_ref
    outputs["applied_decision_ids"] = list(engine_result.applied_decision_ids)
    outputs["changed_lanes"] = dict(engine_result.changed_lanes)
    outputs["idempotent_replay"] = False
    return {
        "executed": True,
        "artifact_refs": persisted.get("artifact_refs"),
        "outputs": outputs,
    }


def _maybe_idempotent_replay(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    head_ref: str,
    validated: ValidatedApplyTranscriptEditsRequest,
) -> dict[str, Any] | None:
    if head_ref == validated.base_revision_ref:
        return None
    try:
        head_doc = load_exact_working_revision_document(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            revision_ref=head_ref,
            workspace_id=workspace_id,
        ).document
    except ExactWorkingRevisionLoadError:
        return None
    if head_doc.get("tool") != "apply_transcript_edits":
        return None
    if head_doc.get("apply_request_identity") != validated.request_identity:
        return None
    if head_doc.get("base_revision_ref") != validated.base_revision_ref:
        return None

    summary = head_doc.get("apply_result_summary")
    if type(summary) is not dict:
        return {
            "executed": False,
            "refusal": {"reason_code": "corrupt_replay_metadata", "retryable": False},
            "outputs": {
                "error": "Idempotent replay requires a valid apply_result_summary on the head revision.",
            },
        }
    applied_ids = summary.get("applied_decision_ids")
    changed_lanes = summary.get("changed_lanes")
    if type(applied_ids) is not list or not all(type(x) is str and x.strip() for x in applied_ids):
        return {
            "executed": False,
            "refusal": {"reason_code": "corrupt_replay_metadata", "retryable": False},
            "outputs": {"error": "apply_result_summary.applied_decision_ids is invalid."},
        }
    if type(changed_lanes) is not dict:
        return {
            "executed": False,
            "refusal": {"reason_code": "corrupt_replay_metadata", "retryable": False},
            "outputs": {"error": "apply_result_summary.changed_lanes is invalid."},
        }
    for lane, count in changed_lanes.items():
        if type(lane) is not str or type(count) is not int or isinstance(count, bool) or count < 0:
            return {
                "executed": False,
                "refusal": {"reason_code": "corrupt_replay_metadata", "retryable": False},
                "outputs": {"error": "apply_result_summary.changed_lanes has invalid entries."},
            }
    expected_ids = [d.decision_id for d in validated.decisions]
    if list(applied_ids) != expected_ids:
        return {
            "executed": False,
            "refusal": {"reason_code": "corrupt_replay_metadata", "retryable": False},
            "outputs": {
                "error": "Stored applied_decision_ids do not match the replayed request.",
            },
        }

    # Latest may have advanced while manifest lagged; heal under the held lock.
    if not heal_working_manifest_from_head(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    ):
        return {
            "executed": False,
            "refusal": {"reason_code": "storage_failure_partial", "retryable": False},
            "outputs": {
                "error": (
                    "Idempotent replay matched the head revision but could not heal "
                    "a lagging manifest from the current working head."
                ),
            },
        }

    aggregate_ref = "transcript_edit:working"
    return {
        "executed": True,
        "artifact_refs": (head_ref, aggregate_ref),
        "outputs": {
            "working_draft_ref": head_ref,
            "aggregate_working_ref": aggregate_ref,
            "base_revision_ref": validated.base_revision_ref,
            "revision": head_doc.get("revision"),
            "evidence_refs": list(head_doc.get("evidence_refs") or []),
            "applied_decision_ids": list(applied_ids),
            "changed_lanes": dict(changed_lanes),
            "idempotent_replay": True,
        },
    }


def _refuse(
    reason_code: str,
    detail: str = "",
    *,
    repair_hint: str | None = None,
) -> dict[str, Any]:
    """Terminal tooling refusal. Domain tool_refusal_boundary owns retryability."""
    message = detail or reason_code
    error: dict[str, Any] = {"code": reason_code, "message": message}
    if type(repair_hint) is str:
        hint = repair_hint.strip()
        if hint:
            error["repair_hint"] = hint
    return {
        "executed": False,
        "refusal": {"reason_code": reason_code, "retryable": False},
        "outputs": {"error": error},
    }
