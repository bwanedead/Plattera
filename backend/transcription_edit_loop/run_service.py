"""Orchestration service for transcription edit loop v0."""

from __future__ import annotations

from uuid import uuid4

from .apply import apply_plan_to_sections, materialize_canonical_input
from .contracts import (
    EditPlanV0,
    TranscriptDocumentV0,
    TranscriptionEditRunRequestV0,
    TranscriptionEditRunSnapshotV0,
)
from .persistence import TranscriptionEditPersistenceService
from .validators import run_validators


class TranscriptionEditRunService:
    def __init__(self, persistence: TranscriptionEditPersistenceService | None = None) -> None:
        self._persistence = persistence if persistence is not None else TranscriptionEditPersistenceService()

    def run(self, request: TranscriptionEditRunRequestV0) -> TranscriptionEditRunSnapshotV0:
        run_id = f"tx_edit_{uuid4().hex[:12]}"
        canonical = materialize_canonical_input(request.start)
        dossier_id = str(request.start.dossier_id or "adhoc")
        document = TranscriptDocumentV0(
            source_transcript_ref=canonical.source_transcript_ref,
            source_transcript_hash=canonical.source_transcript_hash,
            sections=canonical.transcript_sections,
            metadata={"mode": canonical.mode.value, "run_id": run_id},
        )
        canonical_source_ref = self._persistence.save_source_transcript_input(
            dossier_id=dossier_id,
            document=document,
        )
        validator_report = run_validators(
            document=document,
            source_transcript_ref=canonical_source_ref,
        )
        validator_report_ref = self._persistence.save_validator_report(
            dossier_id=dossier_id,
            report_payload=validator_report.model_dump(mode="json"),
        )
        if request.plan is None:
            return TranscriptionEditRunSnapshotV0(
                run_id=run_id,
                dossier_id=dossier_id,
                status="completed",
                mode=canonical.mode,
                source_transcript_ref=canonical_source_ref,
                source_transcript_hash=canonical.source_transcript_hash,
                validator_report_ref=validator_report_ref,
                review_required=bool(validator_report.summary.get("errors", 0) > 0),
            )

        plan = _ensure_plan_source_ref(plan=request.plan, source_transcript_ref=canonical_source_ref)
        plan_ref = self._persistence.save_edit_plan(dossier_id=dossier_id, plan=plan)
        apply_report, output_doc = apply_plan_to_sections(plan=plan, document=document)
        apply_ref = self._persistence.save_apply_report(dossier_id=dossier_id, report=apply_report)
        edited_ref = self._persistence.save_edited_transcript(dossier_id=dossier_id, document=output_doc)

        latest_mapping_pointer_ref = None
        if request.promote_for_mapping:
            latest_mapping_pointer_ref = self._persistence.write_latest_transcript_for_mapping(
                dossier_id=dossier_id,
                transcript_ref=edited_ref,
                transcript_hash=apply_report.output_transcript_hash,
                run_id=run_id,
            )

        review_required = bool(request.plan.global_flags.review_required)
        if any(op.review_required for op in request.plan.ops):
            review_required = True
        if any(op.change_class.value in {"semantic", "structural"} for op in request.plan.ops):
            review_required = True

        return TranscriptionEditRunSnapshotV0(
            run_id=run_id,
            dossier_id=dossier_id,
            status="completed",
            mode=canonical.mode,
            source_transcript_ref=canonical_source_ref,
            source_transcript_hash=canonical.source_transcript_hash,
            validator_report_ref=validator_report_ref,
            edit_plan_ref=plan_ref,
            apply_report_ref=apply_ref,
            edited_transcript_ref=edited_ref,
            latest_mapping_pointer_ref=latest_mapping_pointer_ref,
            review_required=review_required,
        )


def _ensure_plan_source_ref(*, plan: EditPlanV0, source_transcript_ref: str) -> EditPlanV0:
    if plan.source_transcript_ref == source_transcript_ref:
        return plan
    payload = plan.model_dump(mode="json")
    payload["source_transcript_ref"] = source_transcript_ref
    payload["plan_fingerprint"] = None
    return EditPlanV0.model_validate(payload)
