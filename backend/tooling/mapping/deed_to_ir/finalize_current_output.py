"""Current-head deed-to-IR finalizer orchestration (compact decision path).

Accepts only unresolved semantic decision maps for the current lineage session,
persists partial progress, prepares the immutable preview internally, and
publishes via the existing preview publication path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .final_package_preview_persistence import prepare_deed_to_ir_final_package
from .finalization_decisions import (
    convert_compact_decisions_to_prepare_inputs,
    decision_maps_nonempty,
    evaluate_merged_finalization_completeness,
    merge_finalization_decisions,
    validate_compact_finalization_decisions,
    validate_decision_map_shapes,
    validate_persisted_finalization_decisions,
)
from .finalization_session import (
    REQUIREMENTS_CAPACITY_EXCEEDED,
    SCOPE_INVENTORY_UNAVAILABLE,
    STATUS_PENDING_DECISIONS,
    STATUS_PREVIEW_READY,
    STATUS_PUBLISHED,
    STATUS_STALE,
    compact_finalization_session_for_prompt,
)
from .finalization_session_persistence import (
    read_finalization_session,
    write_finalization_session,
)
from .finalizer_result_boundary import normalize_finalizer_agent_visible_result
from .mapping_lineage import read_current_mapping_lineage
from .output_persistence import publish_deed_to_ir_output
from .persistence_io import refusal, retryable_refusal
from .preview_refs import PREVIEW_REV_PREFIX, parse_preview_ref

REASON_SESSION_MISSING = "finalization_session_missing"
REASON_SESSION_STALE = "finalization_session_stale"
REASON_SCOPE_INVENTORY = "finalization_scope_inventory_unavailable"
REASON_CAPACITY = "finalization_requirements_capacity_exceeded"
REASON_DECISIONS_FROZEN = "finalization_decisions_frozen"
REASON_SESSION_PERSISTENCE_FAILED = "finalization_session_persistence_failed"
REASON_PREVIEW_REVISION_MISSING = "final_package_preview_revision_ref_missing"


def finalize_current_deed_to_ir_output(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    transcript_edit_source_revision_ref: str | None,
    resolution_state_ref: str | None,
    scope_statuses: Any = None,
    correction_dispositions: Any = None,
    dependency_dispositions: Any = None,
    rationales: Any = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
    issues: list[Mapping[str, Any]] | None = None,
    persistence: Any | None = None,
) -> dict[str, Any]:
    """Compact current-head finalizer: merge decisions, prepare preview, publish."""
    return normalize_finalizer_agent_visible_result(
        _finalize_current_deed_to_ir_output_impl(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            run_id=run_id,
            transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
            resolution_state_ref=resolution_state_ref,
            scope_statuses=scope_statuses,
            correction_dispositions=correction_dispositions,
            dependency_dispositions=dependency_dispositions,
            rationales=rationales,
            resolution_state_snapshot=resolution_state_snapshot,
            issues=issues,
            persistence=persistence,
        )
    )


def _finalize_current_deed_to_ir_output_impl(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    transcript_edit_source_revision_ref: str | None,
    resolution_state_ref: str | None,
    scope_statuses: Any = None,
    correction_dispositions: Any = None,
    dependency_dispositions: Any = None,
    rationales: Any = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
    issues: list[Mapping[str, Any]] | None = None,
    persistence: Any | None = None,
) -> dict[str, Any]:
    request = {
        "scope_statuses": scope_statuses,
        "correction_dispositions": correction_dispositions,
        "dependency_dispositions": dependency_dispositions,
        "rationales": rationales,
    }

    lineage = read_current_mapping_lineage(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )
    session = read_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )

    preflight = _preflight_session_and_lineage(session=session, lineage=lineage)
    if preflight.get("executed") is False:
        return preflight
    assert isinstance(session, dict)
    assert isinstance(lineage, Mapping)

    # Reject malformed map shapes before any status-branch side effects.
    shape_check = validate_decision_map_shapes(request)
    if shape_check.get("executed") is False:
        return shape_check

    status = str(session.get("status") or "").strip()

    if status == STATUS_PUBLISHED:
        if decision_maps_nonempty(request):
            return retryable_refusal(
                REASON_DECISIONS_FROZEN,
                "Finalization decisions are frozen after publication. "
                "Retry finalize_current_deed_to_ir_output without decision mutations.",
            )
        return _published_replay(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            run_id=run_id,
            transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
            resolution_state_ref=resolution_state_ref,
            session=session,
            persistence=persistence,
        )

    if status == STATUS_PREVIEW_READY:
        if decision_maps_nonempty(request):
            return retryable_refusal(
                REASON_DECISIONS_FROZEN,
                "Finalization decisions are frozen after preview preparation. "
                "Retry finalize_current_deed_to_ir_output without decision mutations.",
            )
        return _publish_stored_preview(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            run_id=run_id,
            transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
            resolution_state_ref=resolution_state_ref,
            session=session,
            persistence=persistence,
        )

    if status != STATUS_PENDING_DECISIONS:
        return retryable_refusal(
            REASON_SESSION_STALE,
            "Finalization session is not pending decisions for the current lineage. "
            "Remap the latest IR, then retry.",
        )

    persisted_check = validate_persisted_finalization_decisions(session)
    if persisted_check.get("executed") is False:
        return persisted_check

    validated = validate_compact_finalization_decisions(session=session, request=request)
    if validated.get("executed") is False:
        return validated
    incoming = validated["incoming"]

    merged = merge_finalization_decisions(session=session, incoming=incoming)
    persist_merged = _persist_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        session=merged,
    )
    if persist_merged.get("executed") is False:
        return persist_merged
    session = persist_merged["session"]

    completeness = evaluate_merged_finalization_completeness(session)
    if not completeness["complete"]:
        return missing_finalization_decisions_refusal(
            missing=completeness["missing"],
            session=session,
        )
    if completeness["needs_hitl"]:
        return finalization_requires_hitl_refusal(session=session)

    converted = convert_compact_decisions_to_prepare_inputs(
        session=session,
        scope_statuses=completeness["scope_statuses"],
        correction_dispositions=completeness["correction_dispositions"],
        dependency_dispositions=completeness["dependency_dispositions"],
        rationales=completeness["rationales"],
    )
    if converted.get("executed") is False:
        return converted

    prepared = prepare_deed_to_ir_final_package(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
        resolution_state_ref=resolution_state_ref,
        resolution_state_snapshot=resolution_state_snapshot,
        persistence=persistence,
        use_current_mapping_lineage=True,
        scope_dispositions=converted["scope_dispositions"],
        closure_dispositions=converted["closure_dispositions"],
        correction_decisions=converted["correction_decisions"],
        dependency_decisions=converted["dependency_decisions"],
        issues=issues,
    )
    if not prepared.get("executed"):
        return prepared

    preview_ref = _immutable_preview_revision_ref(prepared.get("outputs") or {})
    if preview_ref is None:
        return refusal(
            REASON_PREVIEW_REVISION_MISSING,
            "Prepare succeeded but did not return an immutable "
            "final_package_preview_revision_ref. Publication is forbidden.",
        )

    preview_ready = dict(session)
    preview_ready["status"] = STATUS_PREVIEW_READY
    preview_ready["preview_ref"] = preview_ref
    persist_ready = _persist_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        session=preview_ready,
        observability={
            "final_package_preview_ref": preview_ref,
            "finalization_status": STATUS_PREVIEW_READY,
        },
    )
    if persist_ready.get("executed") is False:
        return persist_ready
    session = persist_ready["session"]

    return _publish_stored_preview(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
        resolution_state_ref=resolution_state_ref,
        session=session,
        persistence=persistence,
    )


def _immutable_preview_revision_ref(outputs: Mapping[str, Any]) -> str | None:
    """Return the immutable preview revision ref only — never the base alias."""
    revision = str(outputs.get("final_package_preview_revision_ref") or "").strip()
    if not revision:
        return None
    kind, _digits = parse_preview_ref(revision)
    if kind != "revision" or not revision.startswith(PREVIEW_REV_PREFIX):
        return None
    return revision


def _persist_finalization_session(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    session: Mapping[str, Any],
    observability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Hard durability gate: None or exceptions become a retryable refusal."""
    try:
        written = write_finalization_session(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            run_id=run_id,
            session=session,
        )
    except Exception as exc:
        message = str(exc).strip() or "finalization session write failed"
        payload = retryable_refusal(
            REASON_SESSION_PERSISTENCE_FAILED,
            f"Failed to persist finalization session: {message}",
        )
        return _attach_persistence_observability(payload, observability)
    if not isinstance(written, dict):
        payload = retryable_refusal(
            REASON_SESSION_PERSISTENCE_FAILED,
            "Failed to persist finalization session (write returned no payload).",
        )
        return _attach_persistence_observability(payload, observability)
    return {"executed": True, "session": written}


def _attach_persistence_observability(
    payload: dict[str, Any],
    observability: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(observability, Mapping) or not observability:
        return payload
    outputs = payload.setdefault("outputs", {})
    if isinstance(outputs, dict):
        for key, value in observability.items():
            if value is not None and key not in outputs:
                outputs[key] = value
    return payload


def _preflight_session_and_lineage(
    *,
    session: Mapping[str, Any] | None,
    lineage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(session, Mapping) or not session:
        return retryable_refusal(
            REASON_SESSION_MISSING,
            "No finalization session is available. Submit IR for mapping, then retry.",
        )
    if not isinstance(lineage, Mapping) or not lineage:
        return retryable_refusal(
            REASON_SESSION_STALE,
            "Current mapping lineage is missing; finalization session cannot be used. "
            "Remap the latest IR, then retry.",
        )

    status = str(session.get("status") or "").strip()
    if status == STATUS_STALE or session.get("stale"):
        return retryable_refusal(
            REASON_SESSION_STALE,
            "Finalization session is stale. Remap the latest IR, then retry.",
        )
    if lineage.get("stale") or not lineage.get("lineage_current") or not lineage.get(
        "use_for_next_preview"
    ):
        return retryable_refusal(
            REASON_SESSION_STALE,
            "Current mapping lineage is stale; finalization session cannot be used. "
            "Remap the latest IR, then retry.",
        )

    session_lineage = (
        session.get("lineage") if isinstance(session.get("lineage"), Mapping) else {}
    )
    session_mapping = str(session_lineage.get("mapping_artifact_ref") or "").strip()
    session_ir = str(session_lineage.get("source_ir_artifact_ref") or "").strip()
    lineage_mapping = str(lineage.get("mapping_artifact_ref") or "").strip()
    lineage_ir = str(lineage.get("source_ir_artifact_ref") or "").strip()
    if (
        not session_mapping
        or not session_ir
        or session_mapping != lineage_mapping
        or session_ir != lineage_ir
    ):
        return retryable_refusal(
            REASON_SESSION_STALE,
            "Finalization session mapping/IR refs do not match the current mapping lineage. "
            "Remap the latest IR, then retry.",
        )

    diagnostics = session.get("diagnostics") if isinstance(session.get("diagnostics"), list) else []
    diagnostic_codes = {
        str(row.get("code") or "").strip()
        for row in diagnostics
        if isinstance(row, Mapping)
    }
    if SCOPE_INVENTORY_UNAVAILABLE in diagnostic_codes:
        return refusal(
            REASON_SCOPE_INVENTORY,
            "Finalization scope inventory is unavailable; cannot finalize from an empty scope set. "
            "This is not recoverable by ordinary decision retry.",
        )
    if REQUIREMENTS_CAPACITY_EXCEEDED in diagnostic_codes:
        return refusal(
            REASON_CAPACITY,
            "Finalization requirements exceeded capacity; publishing from a truncated inventory "
            "is forbidden. This is not recoverable by ordinary decision retry.",
        )

    return {"executed": True}


def _publish_stored_preview(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    transcript_edit_source_revision_ref: str | None,
    resolution_state_ref: str | None,
    session: Mapping[str, Any],
    persistence: Any | None,
) -> dict[str, Any]:
    preview_ref = str(session.get("preview_ref") or "").strip()
    kind, _digits = parse_preview_ref(preview_ref)
    if kind != "revision" or not preview_ref.startswith(PREVIEW_REV_PREFIX):
        return refusal(
            REASON_PREVIEW_REVISION_MISSING,
            "Finalization session preview_ref must be an immutable "
            "deed_to_ir:final_package_preview:rev:NNNN revision ref.",
        )

    published = publish_deed_to_ir_output(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
        resolution_state_ref=resolution_state_ref,
        final_package_preview_ref=preview_ref,
        persistence=persistence,
    )
    if not published.get("executed"):
        result = dict(published)
        outputs = result.setdefault("outputs", {})
        if isinstance(outputs, dict):
            outputs.setdefault("final_package_preview_ref", preview_ref)
            outputs["finalization_status"] = STATUS_PREVIEW_READY
            outputs["next_required_action"] = "finalize_current_deed_to_ir_output"
        return result

    outputs = dict(published.get("outputs") or {})
    output_revision_ref = str(outputs.get("output_revision_ref") or "").strip()
    success_outputs = {
        **outputs,
        "finalization_status": STATUS_PUBLISHED,
        "final_package_preview_ref": preview_ref,
    }
    published_session = dict(session)
    published_session["status"] = STATUS_PUBLISHED
    published_session["preview_ref"] = preview_ref
    published_session["output_revision_ref"] = output_revision_ref or None
    published_session["published_result"] = {
        "executed": True,
        "artifact_refs": list(published.get("artifact_refs") or []),
        "outputs": success_outputs,
    }
    persist_published = _persist_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        session=published_session,
        observability={
            "final_package_preview_ref": preview_ref,
            "output_revision_ref": output_revision_ref or None,
            "finalization_status": STATUS_PREVIEW_READY,
            "next_required_action": "finalize_current_deed_to_ir_output",
        },
    )
    if persist_published.get("executed") is False:
        # preview_ready remains authoritative on disk; do not claim published.
        return persist_published

    return {
        "executed": True,
        "artifact_refs": list(published.get("artifact_refs") or []),
        "outputs": success_outputs,
    }


def _published_replay(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    transcript_edit_source_revision_ref: str | None,
    resolution_state_ref: str | None,
    session: Mapping[str, Any],
    persistence: Any | None,
) -> dict[str, Any]:
    stored = session.get("published_result")
    if isinstance(stored, Mapping) and stored.get("executed") is True:
        outputs = dict(stored.get("outputs") or {})
        outputs["idempotent_replay"] = True
        outputs["finalization_status"] = STATUS_PUBLISHED
        if session.get("preview_ref") and "final_package_preview_ref" not in outputs:
            outputs["final_package_preview_ref"] = session.get("preview_ref")
        if session.get("output_revision_ref") and "output_revision_ref" not in outputs:
            outputs["output_revision_ref"] = session.get("output_revision_ref")
        return {
            "executed": True,
            "artifact_refs": list(stored.get("artifact_refs") or []),
            "outputs": outputs,
        }

    result = _publish_stored_preview(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
        resolution_state_ref=resolution_state_ref,
        session=session,
        persistence=persistence,
    )
    if result.get("executed"):
        outputs = result.setdefault("outputs", {})
        if isinstance(outputs, dict):
            outputs["idempotent_replay"] = True
    return result


def missing_finalization_decisions_refusal(
    *,
    missing: Mapping[str, Sequence[str]],
    session: Mapping[str, Any],
) -> dict[str, Any]:
    """Retryable refusal listing exact still-missing decision IDs."""
    payload = retryable_refusal(
        "missing_finalization_decisions",
        "Finalization decisions remain unresolved for the current lineage session.",
    )
    compact = compact_finalization_session_for_prompt(session)
    outputs = payload.setdefault("outputs", {})
    if isinstance(outputs, dict):
        outputs["missing"] = {
            "scope_ids": list(missing.get("scope_ids") or []),
            "correction_ids": list(missing.get("correction_ids") or []),
            "dependency_ids": list(missing.get("dependency_ids") or []),
            "rationale_ids": list(missing.get("rationale_ids") or []),
        }
        if compact is not None:
            outputs["active_finalization_session"] = compact
    return payload


def finalization_requires_hitl_refusal(
    *,
    session: Mapping[str, Any],
) -> dict[str, Any]:
    payload = retryable_refusal(
        "finalization_requires_hitl",
        "One or more correction dispositions require HITL before preview preparation.",
    )
    compact = compact_finalization_session_for_prompt(session)
    outputs = payload.setdefault("outputs", {})
    if isinstance(outputs, dict) and compact is not None:
        outputs["active_finalization_session"] = compact
        outputs["finalization_status"] = "pending_decisions"
    return payload
