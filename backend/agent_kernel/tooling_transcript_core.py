"""Concrete tool dependency implementations for step-driven kernel actions."""

from __future__ import annotations

import base64
import io
import json
import os
import hashlib
import tempfile
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from config.paths import (
    agent_kernel_artifacts_root,
    dossiers_associations_root,
    dossiers_feature_graphs_artifacts_root,
)
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider
from feature_graph.artifacts import create_compile_artifact, create_ir_artifact, create_judge_artifact
from feature_graph.bundle import bundle_feature_graph
from feature_graph.compiler import compile_graph
from feature_graph.judge import judge_graph
from feature_graph.models import FeatureGraph
from retrieval.engine.retrieval_engine import RetrievalEngine
from retrieval.filters.models import RetrievalFilters
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService
from transcript_edit.apply import (
    apply_plan_to_sections,
    materialize_canonical_input,
)
from transcript_edit.contracts import (
    Confidence,
    EditLoopStartRequestV0,
    EditPlanV0,
    LocatorAnchorsV0,
    TranscriptSpanSeedLabel,
    TranscriptSpanSeedOrigin,
    TranscriptSpanSeedV1,
    TranscriptSpanSeedsArtifactV1,
    TranscriptDocumentV0,
    transcript_text_hash,
)
from transcript_edit.persistence import TranscriptionEditPersistenceService
from transcript_edit.span_seeds import (
    build_transcript_span_seeds_artifact,
    load_transcript_text_for_seeds,
)
from transcript_edit.validators import run_validators
from services.llm.openai import OpenAIService

from .run_artifact import ArtifactRef, ValidationInline

logger = logging.getLogger(__name__)

from .tooling_artifacts import (
    _coerce_artifact_ref,
    _persist_json_artifact,
    _persist_text_artifact,
    _read_str,
    _read_json_dict,
    _tool_refusal_result,
)


def _bounded_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


@dataclass
class TranscriptAuditTool:
    """Run deterministic transcript validators and persist validator artifacts."""

    persistence: TranscriptionEditPersistenceService = field(default_factory=TranscriptionEditPersistenceService)

    def audit_transcript(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        source_ref = _read_str(
            inputs.get("source_transcript_ref")
            or inputs.get("transcript_ref")
            or inputs.get("tx_source_transcript_ref")
        )
        source_text = _read_str(inputs.get("source_text"))
        if source_ref is None and source_text is None:
            return _tool_refusal_result("tx_audit_missing_source_transcript")
        try:
            canonical = materialize_canonical_input(
                EditLoopStartRequestV0(
                    dossier_id=dossier_id,
                    source_transcript_ref=source_ref,
                    source_text=source_text,
                    mode="audit_only",
                )
            )
        except Exception:
            return _tool_refusal_result("tx_audit_invalid_source_transcript")
        document = TranscriptDocumentV0(
            source_transcript_ref=canonical.source_transcript_ref,
            source_transcript_hash=canonical.source_transcript_hash,
            sections=canonical.transcript_sections,
            metadata={"source": "agent_kernel_tx_audit"},
        )
        source_artifact_ref = canonical.source_transcript_ref
        if source_text is not None:
            source_artifact_ref = self.persistence.save_source_transcript_input(
                dossier_id=dossier_id,
                document=document,
            )
        report = run_validators(document=document, source_transcript_ref=source_artifact_ref)
        report_ref = self.persistence.save_validator_report(
            dossier_id=dossier_id,
            report_payload=report.model_dump(mode="json"),
        )
        findings_count = len(report.findings)
        top_findings: list[dict[str, Any]] = []
        for finding in report.findings[:12]:
            top_findings.append(
                {
                    "finding_id": finding.finding_id,
                    "finding_type": finding.finding_type,
                    "severity": finding.severity,
                    "message": finding.message,
                    "section_id": finding.section_id,
                    "span": finding.span,
                }
            )
        return {
            "artifact_ref": ArtifactRef(artifact_path=report_ref),
            "reason_codes": ["tx_audit_completed"],
            "tx_source_transcript_ref": source_artifact_ref,
            "tx_source_transcript_hash": report.source_transcript_hash,
            "tx_validator_summary": report.summary,
            "tx_findings_count": findings_count,
            "tx_error_findings_count": int(report.summary.get("errors", 0)),
            "tx_warning_findings_count": int(report.summary.get("warnings", 0)),
            "tx_has_findings": findings_count > 0,
            "tx_top_findings": top_findings,
        }


@dataclass
class TranscriptEditPlanApplyTool:
    """Apply EditPlanV0 against section-preserving transcript documents."""

    persistence: TranscriptionEditPersistenceService = field(default_factory=TranscriptionEditPersistenceService)

    def apply_edit_plan(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        plan_ref_from_inputs = _read_str(inputs.get("edit_plan_ref") or inputs.get("tx_edit_plan_ref"))
        plan_payload: dict[str, Any] | None = None
        if plan_ref_from_inputs:
            path = Path(plan_ref_from_inputs)
            if not path.exists():
                return _tool_refusal_result("tx_apply_missing_edit_plan_ref")
            loaded = _read_json_dict(path)
            if not isinstance(loaded, dict):
                return _tool_refusal_result("tx_apply_invalid_edit_plan_ref")
            plan_payload = loaded
        raw_plan = inputs.get("edit_plan")
        if plan_payload is None and isinstance(raw_plan, dict):
            plan_payload = raw_plan
        if not isinstance(plan_payload, dict):
            return _tool_refusal_result("tx_apply_missing_edit_plan")
        try:
            plan = EditPlanV0.model_validate(plan_payload)
        except Exception:
            return _tool_refusal_result("tx_apply_invalid_edit_plan")
        try:
            canonical = materialize_canonical_input(
                EditLoopStartRequestV0(
                    dossier_id=dossier_id,
                    source_transcript_ref=plan.source_transcript_ref,
                    mode="repair",
                )
            )
        except Exception:
            return _tool_refusal_result("tx_apply_invalid_source_transcript")
        source_document = TranscriptDocumentV0(
            source_transcript_ref=canonical.source_transcript_ref,
            source_transcript_hash=canonical.source_transcript_hash,
            sections=canonical.transcript_sections,
            metadata={"source": "agent_kernel_tx_apply"},
        )
        plan_ref = plan_ref_from_inputs or self.persistence.save_edit_plan(dossier_id=dossier_id, plan=plan)
        apply_report, output_doc = apply_plan_to_sections(plan=plan, document=source_document)
        apply_ref = self.persistence.save_apply_report(dossier_id=dossier_id, report=apply_report)
        if apply_report.root_status == "refused":
            return {
                "artifact_ref": ArtifactRef(artifact_path=apply_ref),
                "reason_codes": [f"tx_apply_refused:{apply_report.root_reason_code or 'unknown'}"],
                "kernel_refusal": {
                    "reason_code": f"tx_apply_refused:{apply_report.root_reason_code or 'unknown'}",
                    "retryable": True,
                    "missing_inputs": [],
                    "blocked_by_budget": False,
                    "blocked_by_invariant": False,
                },
                "tx_edit_plan_ref": plan_ref,
                "tx_source_transcript_ref": canonical.source_transcript_ref,
                "tx_source_transcript_hash": canonical.source_transcript_hash,
                "tx_apply_summary": {
                    "applied_count": apply_report.applied_count,
                    "refused_count": apply_report.refused_count,
                    "root_status": apply_report.root_status,
                    "root_reason_code": apply_report.root_reason_code,
                },
            }
        edited_ref = self.persistence.save_edited_transcript(dossier_id=dossier_id, document=output_doc)
        return {
            "artifact_ref": ArtifactRef(artifact_path=apply_ref),
            "reason_codes": ["tx_apply_completed"],
            "tx_edit_plan_ref": plan_ref,
            "tx_source_transcript_ref": canonical.source_transcript_ref,
            "tx_source_transcript_hash": canonical.source_transcript_hash,
            "tx_apply_report_ref": apply_ref,
            "tx_edited_transcript_ref": edited_ref,
            "tx_apply_summary": {
                "applied_count": apply_report.applied_count,
                "refused_count": apply_report.refused_count,
                "root_status": apply_report.root_status,
                "root_reason_code": apply_report.root_reason_code,
            },
        }


@dataclass
class TranscriptSpanSeedsSaverTool:
    """Build and persist transcript span seeds through kernel action execution."""

    persistence: TranscriptionEditPersistenceService = field(default_factory=TranscriptionEditPersistenceService)

    def save_transcript_span_seeds(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        source_ref = _read_str(inputs.get("source_transcript_ref") or inputs.get("tx_source_transcript_ref"))
        source_hash = _read_str(inputs.get("source_transcript_hash") or inputs.get("tx_source_transcript_hash"))
        max_seeds = _bounded_int(inputs.get("max_seeds"), default=24, minimum=1, maximum=30)
        if source_ref is None or source_hash is None:
            return _tool_refusal_result("tx_span_seeds_missing_source")
        transcript_text = load_transcript_text_for_seeds(source_ref)
        if not transcript_text:
            return _tool_refusal_result("tx_span_seeds_missing_source_text")
        artifact = build_transcript_span_seeds_artifact(
            dossier_id=dossier_id,
            source_transcript_ref=source_ref,
            source_transcript_hash=source_hash,
            transcript_text=transcript_text,
            max_seeds=max_seeds,
        )
        seeds_ref = self.persistence.save_transcript_span_seeds(dossier_id=dossier_id, artifact=artifact)
        return {
            "artifact_ref": ArtifactRef(artifact_path=seeds_ref),
            "reason_codes": ["tx_span_seeds_saved"],
            "tx_source_transcript_ref": source_ref,
            "tx_source_transcript_hash": source_hash,
            "tx_span_seeds_ref": seeds_ref,
            "tx_span_seeds_count": len(artifact.seeds),
        }


@dataclass
class TranscriptMappingPromoterTool:
    """Promote a transcript artifact for downstream mapping hydration."""

    persistence: TranscriptionEditPersistenceService = field(default_factory=TranscriptionEditPersistenceService)

    def promote_transcript_for_mapping(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        transcript_ref = _read_str(
            inputs.get("transcript_ref")
            or inputs.get("tx_edited_transcript_ref")
            or inputs.get("source_transcript_ref")
        )
        if transcript_ref is None:
            return _tool_refusal_result("tx_promote_missing_transcript_ref")
        transcript_hash = _read_str(inputs.get("transcript_hash"))
        if transcript_hash is None:
            try:
                canonical = materialize_canonical_input(
                    EditLoopStartRequestV0(
                        dossier_id=dossier_id,
                        source_transcript_ref=transcript_ref,
                        mode="audit_only",
                    )
                )
            except Exception:
                return _tool_refusal_result("tx_promote_invalid_transcript_ref")
            transcript_hash = transcript_text_hash(canonical.transcript_text)
        pointer_ref = self.persistence.write_latest_transcript_for_mapping(
            dossier_id=dossier_id,
            transcript_ref=transcript_ref,
            transcript_hash=transcript_hash,
            run_id=_read_str(inputs.get("run_id")),
        )
        span_seeds_ref = _read_str(inputs.get("tx_span_seeds_ref"))
        return {
            "artifact_ref": ArtifactRef(artifact_path=pointer_ref),
            "reason_codes": ["tx_promote_completed"],
            "tx_mapping_pointer_ref": pointer_ref,
            "tx_promoted_transcript_ref": transcript_ref,
            "tx_promoted_transcript_hash": transcript_hash,
            "tx_span_seeds_ref": span_seeds_ref,
        }
