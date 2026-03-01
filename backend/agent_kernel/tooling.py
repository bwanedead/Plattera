"""Concrete tool dependency implementations for step-driven kernel actions."""

from __future__ import annotations

import json
import os
import hashlib
import tempfile
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root, dossiers_feature_graphs_artifacts_root
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
    EditLoopStartRequestV0,
    EditPlanV0,
    TranscriptDocumentV0,
    transcript_text_hash,
)
from transcript_edit.persistence import TranscriptionEditPersistenceService
from transcript_edit.validators import run_validators

from .run_artifact import ArtifactRef, ValidationInline


@dataclass
class CorpusDeedHydrator:
    """Hydrate deed text through the shared corpus provider surface."""

    provider: VirtualCorpusProvider = field(default_factory=VirtualCorpusProvider)

    def hydrate_deed(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        ref = _resolve_deed_ref(inputs)
        if ref is None:
            return {"artifact_ref": None, "reason_codes": ["hydrate_deed_missing_ref_inputs"]}
        entry = self.provider.hydrate_entry(ref)
        provenance_error = str((entry.provenance or {}).get("error") or "").strip()
        if provenance_error:
            return {"artifact_ref": None, "reason_codes": [f"hydrate_deed_failed:{provenance_error}"]}

        artifact_ref = _persist_json_artifact(
            category="hydrated_deeds",
            dossier_id=entry.ref.dossier_id,
            payload={
                "artifact_type": "hydrated_deed",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "entry_ref": _entry_ref_to_dict(entry.ref),
                "text": entry.text,
                "title": entry.title,
                "content_hash": entry.content_hash,
                "provenance": entry.provenance,
            },
        )
        return {"artifact_ref": artifact_ref, "reason_codes": ["deed_hydrated"]}


@dataclass
class CorpusArtifactOpener:
    """Open artifact references with bounded summaries for controller inspection."""

    provider: VirtualCorpusProvider = field(default_factory=VirtualCorpusProvider)

    def open_artifact(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        corpus_ref = _parse_corpus_entry_ref(inputs.get("corpus_entry_ref"))
        if corpus_ref is not None:
            entry = self.provider.hydrate_entry(corpus_ref)
            error = str((entry.provenance or {}).get("error") or "").strip()
            if error:
                return {"reason_codes": [f"artifact_open_failed:{error}"], "summary": ""}
            return {
                "reason_codes": ["artifact_opened"],
                "summary": _summarize_text(entry.text),
                "artifact_ref": None,
            }

        artifact_ref = _coerce_artifact_ref(inputs.get("artifact_ref") or inputs.get("artifact_path"))
        if artifact_ref is None:
            return {"reason_codes": ["artifact_open_missing_ref"], "summary": ""}
        path = Path(artifact_ref.artifact_path)
        if not path.exists():
            return {"reason_codes": ["artifact_open_not_found"], "summary": ""}
        summary = _summarize_path(path)
        result: dict[str, Any] = {
            "reason_codes": ["artifact_opened"],
            "summary": summary,
            "artifact_ref": artifact_ref,
        }
        repair_view = _repair_view_for_json_artifact(path)
        if isinstance(repair_view, dict):
            result["repair_view"] = repair_view
        return result


@dataclass
class TextSpanOpenerTool:
    """Open bounded verbatim text spans from canonical deed-text artifacts."""

    def open_text_spans(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        deed_ref = _coerce_artifact_ref(inputs.get("deed_text_artifact_ref"))
        if deed_ref is None:
            return _tool_refusal_result("open_text_spans_missing_deed_ref")
        deed_payload = _read_json_dict(Path(deed_ref.artifact_path))
        if deed_payload is None:
            return _tool_refusal_result("open_text_spans_missing_deed_ref")
        deed_text = deed_payload.get("text")
        if not isinstance(deed_text, str):
            return _tool_refusal_result("open_text_spans_missing_deed_ref")
        text = deed_text
        max_chars_per_span = _bounded_int(inputs.get("max_chars_per_span"), default=2500, minimum=1, maximum=5000)
        max_total_chars = _bounded_int(inputs.get("max_total_chars"), default=8000, minimum=1, maximum=10000)
        include_context_chars = _bounded_int(inputs.get("include_context_chars"), default=120, minimum=0, maximum=500)

        requested_spans, failure, partial_failures = _resolve_requested_text_spans(inputs=inputs, deed_text=text)
        if failure is not None:
            return failure
        out_spans: list[dict[str, Any]] = []
        total_chars = 0
        for item in requested_spans:
            start_char = int(item["start_char"])
            end_char = int(item["end_char"])
            if start_char < 0 or end_char <= start_char or end_char > len(text):
                return _tool_refusal_result("open_text_spans_invalid_range")
            context_start = max(0, start_char - include_context_chars)
            context_end = min(len(text), end_char + include_context_chars)
            extracted = text[context_start:context_end]
            truncated = False
            if len(extracted) > max_chars_per_span:
                extracted = extracted[:max_chars_per_span]
                truncated = True
            if total_chars + len(extracted) > max_total_chars:
                return _tool_refusal_result("open_text_spans_budget_exceeded")
            total_chars += len(extracted)
            out_spans.append(
                {
                    "span_id": item.get("span_id"),
                    "start_char": start_char,
                    "end_char": end_char,
                    "text": extracted,
                    "truncated": truncated,
                    "fingerprint_ok": bool(item.get("fingerprint_ok", True)),
                }
            )
        result: dict[str, Any] = {"artifact_ref": None, "reason_codes": ["spans_opened"], "spans": out_spans}
        if partial_failures:
            result["not_found"] = partial_failures[:5]
            result["reason_codes"] = ["spans_opened_partial"]
        return result


@dataclass
class DeedSpanIndexUpserterTool:
    """Persist versioned deed span index artifacts under agent-kernel artifacts root."""

    def upsert_deed_span_index(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        deed_ref = _coerce_artifact_ref(inputs.get("deed_text_artifact_ref"))
        deed_fp = inputs.get("deed_fingerprint")
        raw_upserts = inputs.get("upserts")
        if deed_ref is None or not isinstance(deed_fp, dict) or not isinstance(raw_upserts, list):
            return _tool_refusal_result("upsert_deed_span_index_missing_inputs")
        deed_payload = _read_json_dict(Path(deed_ref.artifact_path))
        if deed_payload is None or not isinstance(deed_payload.get("text"), str):
            return _tool_refusal_result("upsert_deed_span_index_missing_inputs")
        deed_text = str(deed_payload["text"])
        computed_fp = _deed_fingerprint(deed_text)
        if not _fingerprint_matches_dict(expected=deed_fp, actual=computed_fp):
            return _tool_refusal_result("upsert_deed_span_index_fingerprint_mismatch")

        existing = _load_span_index(inputs.get("deed_span_index_ref"))
        if isinstance(existing, dict):
            existing_fp = existing.get("deed_fingerprint")
            if isinstance(existing_fp, dict) and not _fingerprint_matches_dict(expected=existing_fp, actual=computed_fp):
                return _tool_refusal_result("upsert_deed_span_index_fingerprint_mismatch")
        existing_spans = []
        if isinstance(existing, dict) and isinstance(existing.get("spans"), list):
            existing_spans = [s for s in existing["spans"] if isinstance(s, dict)]
        span_map: dict[str, dict[str, Any]] = {}
        for span in existing_spans:
            sid = _read_str(span.get("span_id"))
            if sid:
                span_map[sid] = dict(span)
        now = int(datetime.now(timezone.utc).timestamp())
        for raw in raw_upserts:
            if not isinstance(raw, dict):
                return _tool_refusal_result("upsert_deed_span_index_invalid_span")
            sid = _read_str(raw.get("span_id"))
            kind = _read_str(raw.get("kind"))
            start_char = raw.get("start_char")
            end_char = raw.get("end_char")
            status = _read_str(raw.get("status")) or "proposed"
            if not sid or not kind or not isinstance(start_char, int) or not isinstance(end_char, int):
                return _tool_refusal_result("upsert_deed_span_index_invalid_span")
            if start_char < 0 or end_char <= start_char or end_char > len(deed_text):
                return _tool_refusal_result("upsert_deed_span_index_invalid_span")
            intended = raw.get("agent_intent")
            bounded_intent = None
            if isinstance(intended, dict):
                iv = dict(intended)
                txt = iv.get("intended_verbatim_text")
                if isinstance(txt, str):
                    iv["intended_verbatim_text"] = txt[:2000]
                bounded_intent = iv
            base = span_map.get(sid, {})
            span_map[sid] = {
                "span_id": sid,
                "kind": kind,
                "labels": [str(v)[:64] for v in (raw.get("labels") or []) if isinstance(v, (str, int, float))][:8]
                if isinstance(raw.get("labels"), list)
                else [],
                "status": status,
                "start_char": start_char,
                "end_char": end_char,
                "anchor": raw.get("anchor") if isinstance(raw.get("anchor"), dict) else None,
                "agent_intent": bounded_intent,
                "created_at_epoch_seconds": int(base.get("created_at_epoch_seconds", now) or now),
                "updated_at_epoch_seconds": now,
            }
        spans = sorted(span_map.values(), key=lambda s: (int(s.get("start_char", 0)), str(s.get("span_id", ""))))
        dossier_id = _read_str(inputs.get("dossier_id")) or _read_str(deed_payload.get("dossier_id")) or "unknown"
        payload = {
            "artifact_type": "deed_span_index",
            "version": 1,
            "deed_text_artifact_ref": deed_ref.model_dump(mode="json"),
            "deed_fingerprint": computed_fp,
            "spans": spans,
            "created_at_epoch_seconds": int(existing.get("created_at_epoch_seconds", now)) if isinstance(existing, dict) else now,
            "updated_at_epoch_seconds": now,
        }
        artifact_ref = _persist_json_artifact(category="deed_span_indexes", dossier_id=dossier_id, payload=payload)
        return {
            "artifact_ref": artifact_ref,
            "reason_codes": ["deed_span_index_saved"],
            "span_catalog_excerpt": _span_catalog_excerpt(spans),
        }


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
class TranscriptSpanOpenerTool:
    """Open bounded transcript spans for planner context."""

    def open_transcript_spans(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        source_ref = _read_str(
            inputs.get("source_transcript_ref")
            or inputs.get("tx_source_transcript_ref")
            or inputs.get("transcript_ref")
        )
        source_text = _read_str(inputs.get("source_text"))
        if source_ref is None and source_text is None:
            return _tool_refusal_result("tx_open_spans_missing_source_transcript")
        try:
            canonical = materialize_canonical_input(
                EditLoopStartRequestV0(
                    source_transcript_ref=source_ref,
                    source_text=source_text,
                    mode="audit_only",
                )
            )
        except Exception:
            return _tool_refusal_result("tx_open_spans_invalid_source_transcript")

        text = canonical.transcript_text
        max_chars_per_span = _bounded_int(inputs.get("max_chars_per_span"), default=1800, minimum=1, maximum=5000)
        max_total_chars = _bounded_int(inputs.get("max_total_chars"), default=7000, minimum=1, maximum=12000)
        spans: list[dict[str, Any]] = []
        total_chars = 0

        raw_spans = inputs.get("spans")
        if isinstance(raw_spans, list):
            for idx, raw in enumerate(raw_spans):
                if not isinstance(raw, dict):
                    continue
                start_char = raw.get("start_char")
                end_char = raw.get("end_char")
                if not isinstance(start_char, int) or not isinstance(end_char, int):
                    continue
                if start_char < 0 or end_char <= start_char or end_char > len(text):
                    continue
                excerpt = text[start_char:end_char]
                truncated = False
                if len(excerpt) > max_chars_per_span:
                    excerpt = excerpt[:max_chars_per_span]
                    truncated = True
                if total_chars + len(excerpt) > max_total_chars:
                    break
                total_chars += len(excerpt)
                spans.append(
                    {
                        "span_id": _read_str(raw.get("span_id")) or f"offset_{idx + 1}",
                        "start_char": start_char,
                        "end_char": end_char,
                        "text": excerpt,
                        "truncated": truncated,
                    }
                )

        raw_anchors = inputs.get("anchors")
        if isinstance(raw_anchors, list):
            for idx, raw in enumerate(raw_anchors):
                if not isinstance(raw, dict):
                    continue
                start_anchor = _read_str(raw.get("start_anchor"))
                end_anchor = _read_str(raw.get("end_anchor"))
                if not start_anchor or not end_anchor:
                    continue
                occurrence = _bounded_int(raw.get("occurrence"), default=1, minimum=1, maximum=200)
                start_from = 0
                start_idx = -1
                end_idx = -1
                for _ in range(occurrence):
                    start_idx = text.find(start_anchor, start_from)
                    if start_idx < 0:
                        break
                    end_search_from = start_idx + len(start_anchor)
                    end_idx = text.find(end_anchor, end_search_from)
                    if end_idx < 0:
                        break
                    start_from = end_idx + len(end_anchor)
                if start_idx < 0 or end_idx < 0:
                    continue
                span_start = start_idx
                span_end = end_idx + len(end_anchor)
                excerpt = text[span_start:span_end]
                truncated = False
                if len(excerpt) > max_chars_per_span:
                    excerpt = excerpt[:max_chars_per_span]
                    truncated = True
                if total_chars + len(excerpt) > max_total_chars:
                    break
                total_chars += len(excerpt)
                spans.append(
                    {
                        "span_id": _read_str(raw.get("span_id")) or f"anchor_{idx + 1}",
                        "start_char": span_start,
                        "end_char": span_end,
                        "text": excerpt,
                        "truncated": truncated,
                    }
                )

        if not spans:
            excerpt = text[: min(max_chars_per_span, len(text))]
            spans.append(
                {
                    "span_id": "fallback_1",
                    "start_char": 0,
                    "end_char": len(excerpt),
                    "text": excerpt,
                    "truncated": len(excerpt) < len(text),
                }
            )

        artifact_ref = _persist_json_artifact(
            category="transcript_spans",
            dossier_id=dossier_id,
            payload={
                "artifact_type": "transcript_spans_open_v1",
                "source_transcript_ref": canonical.source_transcript_ref,
                "spans": spans,
                "max_chars_per_span": max_chars_per_span,
                "max_total_chars": max_total_chars,
            },
        )
        return {
            "artifact_ref": artifact_ref,
            "reason_codes": ["tx_spans_opened"],
            "tx_source_transcript_ref": canonical.source_transcript_ref,
            "spans": spans,
        }


@dataclass
class TranscriptEditPlanApplyTool:
    """Apply EditPlanV0 against section-preserving transcript documents."""

    persistence: TranscriptionEditPersistenceService = field(default_factory=TranscriptionEditPersistenceService)

    def apply_edit_plan(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        raw_plan = inputs.get("edit_plan")
        if not isinstance(raw_plan, dict):
            return _tool_refusal_result("tx_apply_missing_edit_plan")
        try:
            plan = EditPlanV0.model_validate(raw_plan)
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
        plan_ref = self.persistence.save_edit_plan(dossier_id=dossier_id, plan=plan)
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
            },
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
        return {
            "artifact_ref": ArtifactRef(artifact_path=pointer_ref),
            "reason_codes": ["tx_promote_completed"],
            "tx_mapping_pointer_ref": pointer_ref,
            "tx_promoted_transcript_ref": transcript_ref,
            "tx_promoted_transcript_hash": transcript_hash,
        }


@dataclass
class DraftIRFilesystemProposer:
    """Persist deterministic draft-IR stubs as durable artifact refs."""

    persistence: FeatureGraphPersistenceService = field(default_factory=FeatureGraphPersistenceService)

    def draft_ir(self, inputs: Mapping[str, Any]) -> Any:
        dossier_id = _read_str(inputs.get("dossier_id")) or "unknown"
        inline_graph = inputs.get("graph") if isinstance(inputs.get("graph"), dict) else None
        source_ref = _coerce_artifact_ref(inputs.get("hydrated_deed_artifact_ref"))
        if source_ref is None:
            source_ref = _coerce_artifact_ref(inputs.get("deed_text_artifact_ref"))
        if source_ref is None:
            source_ref = _coerce_artifact_ref(inputs.get("deed_artifact_ref"))
        if inline_graph is not None:
            try:
                graph = FeatureGraph.model_validate(inline_graph)
            except Exception as exc:
                rejected_ref = _persist_json_artifact(
                    category="rejected_ir_graphs",
                    dossier_id=dossier_id,
                    payload={
                        "artifact_type": "rejected_ir_graph",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "dossier_id": dossier_id,
                        "validation_error": str(exc)[:1000],
                        "graph": inline_graph,
                    },
                )
                return {
                    "artifact_ref": None,
                    "reason_codes": ["draft_ir_graph_validation_failed"],
                    "kernel_refusal": {
                        "reason_code": "draft_ir_graph_validation_failed",
                        "retryable": True,
                        "missing_inputs": [],
                        "blocked_by_budget": False,
                        "blocked_by_invariant": False,
                    },
                    "rejected_graph_artifact_ref": rejected_ref.model_dump(mode="json"),
                    "rejected_graph_summary": _summarize_rejected_graph(inline_graph, error=str(exc)),
                }
            if not graph.nodes:
                rejected_ref = _persist_json_artifact(
                    category="rejected_ir_graphs",
                    dossier_id=dossier_id,
                    payload={
                        "artifact_type": "rejected_ir_graph",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "dossier_id": dossier_id,
                        "validation_error": "draft_ir_graph_empty",
                        "graph": inline_graph,
                    },
                )
                return {
                    "artifact_ref": None,
                    "reason_codes": ["draft_ir_graph_empty"],
                    "kernel_refusal": {
                        "reason_code": "draft_ir_graph_empty",
                        "retryable": True,
                        "missing_inputs": ["graph.nodes[0]"],
                        "blocked_by_budget": False,
                        "blocked_by_invariant": False,
                    },
                    "rejected_graph_artifact_ref": rejected_ref.model_dump(mode="json"),
                    "rejected_graph_summary": _summarize_rejected_graph(inline_graph, error="draft_ir_graph_empty"),
                }
            artifact_id = f"ir_{graph.graph_id}_{uuid4().hex[:8]}"
            ir_artifact = create_ir_artifact(
                artifact_id=artifact_id,
                graph=graph,
                created_by="agent_kernel",
                source_document_id=dossier_id,
            )
            saved = self.persistence.save_artifact(artifact=ir_artifact, dossier_id=dossier_id)
            return {
                "artifact_ref": ArtifactRef(artifact_path=str(saved["path"])),
                "reason_codes": ["ir_drafted", "ir_inline_graph_validated"],
            }

        payload = {
            "artifact_type": "ir_draft_stub",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dossier_id": dossier_id,
            "source_artifact_ref": source_ref.model_dump(mode="json") if source_ref is not None else None,
            "graph": (
                inline_graph
                if inline_graph is not None
                else {
                    "graph_id": f"graph_draft_{uuid4().hex[:12]}",
                    "metadata": {
                        "drafted_by": "kernel_step_tool_stub",
                        "dossier_id": dossier_id,
                    },
                    "nodes": [],
                    "edges": [],
                }
            ),
        }
        return _persist_json_artifact(
            category="ir_drafts",
            dossier_id=dossier_id,
            payload=payload,
        )


@dataclass
class FeatureGraphCompilerTool:
    """Compile a FeatureGraph IR artifact and persist a compile artifact ref."""

    persistence: FeatureGraphPersistenceService = field(default_factory=FeatureGraphPersistenceService)

    def compile(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        graph, reason_codes = _load_feature_graph_from_inputs(inputs)
        if graph is None:
            return {"artifact_ref": None, "reason_codes": reason_codes}
        dossier_id = _resolve_dossier_id(inputs, graph)
        compile_result = compile_graph(graph)
        gap_dicts = [gap.model_dump(mode="json") for gap in compile_result.gaps]
        artifact_id = f"compile_{graph.graph_id}_{uuid4().hex[:8]}"
        parent_ids = _infer_parent_artifact_ids(inputs)
        artifact = create_compile_artifact(
            artifact_id=artifact_id,
            graph_id=graph.graph_id,
            compiled_features=compile_result.compiled_features,
            gaps=gap_dicts,
            warnings=compile_result.warnings,
            parent_artifact_ids=parent_ids,
            created_by="agent_kernel",
        )
        saved = self.persistence.save_artifact(artifact=artifact, dossier_id=dossier_id)
        codes = ["compiled"]
        if compile_result.gaps:
            codes.append("compile_has_gaps")
        return {"artifact_ref": ArtifactRef(artifact_path=str(saved["path"])), "reason_codes": codes}


@dataclass
class FeatureGraphJudgeTool:
    """Judge a FeatureGraph IR artifact and persist a judge artifact ref."""

    persistence: FeatureGraphPersistenceService = field(default_factory=FeatureGraphPersistenceService)

    def judge(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        graph, reason_codes = _load_feature_graph_from_inputs(inputs)
        if graph is None:
            return {"artifact_ref": None, "reason_codes": reason_codes}
        dossier_id = _resolve_dossier_id(inputs, graph)
        report = judge_graph(graph, include_warnings=True)
        artifact_id = f"judge_{graph.graph_id}_{uuid4().hex[:8]}"
        parent_ids = _infer_parent_artifact_ids(inputs)
        artifact = create_judge_artifact(
            artifact_id=artifact_id,
            graph_id=graph.graph_id,
            report=report,
            parent_artifact_ids=parent_ids,
            created_by="agent_kernel",
        )
        saved = self.persistence.save_artifact(artifact=artifact, dossier_id=dossier_id)
        codes = ["judged"]
        if report.gaps:
            codes.append("judge_has_gaps")
            first_kind = report.gaps[0].kind.value
            codes.append(f"gap_kind:{first_kind}")
        return {"artifact_ref": ArtifactRef(artifact_path=str(saved["path"])), "reason_codes": codes}


@dataclass
class FeatureGraphBundlerTool:
    """Bundle a FeatureGraph and persist a bundle artifact ref."""

    persistence: FeatureGraphPersistenceService = field(default_factory=FeatureGraphPersistenceService)

    def bundle(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        graph, reason_codes = _load_feature_graph_from_inputs(inputs)
        if graph is None:
            return {"artifact_ref": None, "reason_codes": reason_codes}
        dossier_id = _resolve_dossier_id(inputs, graph)
        artifact_id = f"bundle_{graph.graph_id}_{uuid4().hex[:8]}"
        bundle_artifact = bundle_feature_graph(
            target_graph=graph,
            available_graphs=None,
            bundle_id=artifact_id,
            created_by="agent_kernel",
            bundle_purpose="controller_loop_bundle",
        )
        saved = self.persistence.save_artifact(artifact=bundle_artifact, dossier_id=dossier_id)
        return {"artifact_ref": ArtifactRef(artifact_path=str(saved["path"])), "reason_codes": ["bundled"]}


@dataclass
class FeatureGraphGeoreferenceTool:
    """Adapt FeatureGraph artifacts into georeference service requests and persist raw results."""

    def georeference(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        graph, graph_source, reason_codes = _load_feature_graph_for_georeference(inputs)
        if graph is None:
            return {"artifact_ref": None, "reason_codes": reason_codes}

        local_coordinates = _extract_primary_local_polygon_vertices(graph)
        if local_coordinates is None:
            return _tool_refusal_result(
                "georef_missing_local_polygon_geometry",
                diagnostics={"georef_readiness": _georef_readiness_diagnostics(graph)},
            )

        plss_anchor = _extract_plss_anchor(graph)
        if plss_anchor is None:
            return _tool_refusal_result(
                "georef_missing_plss_anchor",
                missing_inputs=["plss_anchor"],
                diagnostics={"georef_readiness": _georef_readiness_diagnostics(graph)},
            )

        options = _extract_georeference_options(graph=graph)
        georef_request: dict[str, Any] = {
            "local_coordinates": local_coordinates,
            "plss_anchor": plss_anchor,
            "options": options,
        }
        tie_to_corner = _extract_tie_to_corner(graph)
        quality = _graph_mapping_quality_diagnostics(graph, tie_to_corner=tie_to_corner)
        if isinstance(tie_to_corner, dict) and tie_to_corner:
            georef_request["starting_point"] = {"tie_to_corner": tie_to_corner}

        try:
            from pipelines.mapping.georeference.georeference_service import GeoreferenceService
        except Exception as exc:
            return {
                "artifact_ref": None,
                "reason_codes": ["georef_service_import_failed"],
                "error": str(exc)[:300],
            }

        service = GeoreferenceService()
        result = service.georeference_polygon(georef_request)
        if not isinstance(result, dict):
            return _tool_refusal_result("georef_invalid_service_response")

        if not bool(result.get("success")):
            error_text = _read_str(result.get("error")) or "unknown_georef_error"
            payload = _tool_refusal_result("georef_service_failed")
            payload["error"] = error_text[:300]
            return payload
        if not isinstance(result.get("plss_anchor"), dict):
            result["plss_anchor"] = dict(plss_anchor)
        result["agent_kernel_quality"] = quality

        dossier_id = _resolve_georeference_dossier_id(inputs=inputs, graph=graph, source_ref=graph_source)
        artifact_ref = _persist_json_artifact(category="georeference", dossier_id=dossier_id, payload=result)
        return {"artifact_ref": artifact_ref, "reason_codes": ["georeferenced"]}


@dataclass
class FeatureGraphValidateTool:
    """Validate georeferenced polygons and persist durable validation artifacts."""

    def validate(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        georef_ref = _coerce_artifact_ref(inputs.get("georef_artifact_ref"))
        if georef_ref is None:
            georef_ref = _coerce_artifact_ref(inputs.get("georeference_artifact_ref"))
        if georef_ref is None:
            return {
                "validation_result": ValidationInline(
                    passed=False,
                    reason_code="validate_missing_georef_artifact_ref",
                    checks={},
                ),
                "reason_codes": ["validate_missing_georef_artifact_ref"],
            }

        georef_payload = _read_json_dict(Path(georef_ref.artifact_path))
        if georef_payload is None:
            return {
                "validation_result": ValidationInline(
                    passed=False,
                    reason_code="validate_georef_artifact_invalid_json",
                    checks={},
                ),
                "reason_codes": ["validate_georef_artifact_invalid_json"],
            }

        plss_anchor = georef_payload.get("plss_anchor")
        if not isinstance(plss_anchor, dict):
            plss_anchor = _extract_plss_anchor_from_georef_payload(georef_payload)
        geographic_polygon = georef_payload.get("geographic_polygon")
        if not isinstance(plss_anchor, dict) or not isinstance(geographic_polygon, dict):
            return {
                "validation_result": ValidationInline(
                    passed=False,
                    reason_code="validate_missing_plss_or_polygon",
                    checks={},
                ),
                "reason_codes": ["validate_missing_plss_or_polygon"],
            }

        try:
            from pipelines.mapping.georeference.validator import validate_polygon_against_plss
        except Exception as exc:
            return {
                "validation_result": ValidationInline(
                    passed=False,
                    reason_code="validate_service_import_failed",
                    checks={},
                ),
                "reason_codes": ["validate_service_import_failed"],
                "error": str(exc)[:300],
            }

        validator_result = validate_polygon_against_plss(plss_anchor, geographic_polygon)
        if not isinstance(validator_result, dict):
            validator_result = {
                "success": False,
                "error": "validator_returned_non_object",
                "issues": ["validator_returned_non_object"],
            }
        quality_issues = _mapping_quality_issues_from_georef_payload(georef_payload)
        if quality_issues:
            existing_issues = validator_result.get("issues")
            combined: list[str] = []
            if isinstance(existing_issues, list):
                combined.extend(str(item) for item in existing_issues if str(item))
            for issue in quality_issues:
                if issue not in combined:
                    combined.append(issue)
            validator_result["issues"] = combined

        if _validator_allows_tie_anchored_override(
            georef_payload=georef_payload,
            validator_result=validator_result,
        ):
            validator_result["success"] = True
            issues = validator_result.get("issues")
            if isinstance(issues, list):
                retained = [
                    str(item)
                    for item in issues
                    if str(item)
                    and not any(tok in str(item).lower() for tok in ("centroid", "section center", "near section"))
                ]
                validator_result["issues"] = retained
            checks = validator_result.get("validation_checks")
            if isinstance(checks, dict):
                checks["centroid_within_section_tolerance"] = True
                if "vertices_near_section" in checks:
                    checks["vertices_near_section"] = True
            notes = validator_result.get("recommendations")
            if isinstance(notes, list):
                if "Tie-anchored georeference override applied; centroid-proximity checks treated as advisory." not in notes:
                    notes.append("Tie-anchored georeference override applied; centroid-proximity checks treated as advisory.")
            else:
                validator_result["recommendations"] = [
                    "Tie-anchored georeference override applied; centroid-proximity checks treated as advisory."
                ]

        passed = bool(validator_result.get("success")) and not bool(validator_result.get("issues"))
        top_issues = [str(item)[:200] for item in (validator_result.get("issues") or []) if str(item)][:5]
        bounds = geographic_polygon.get("bounds") if isinstance(geographic_polygon.get("bounds"), dict) else None
        checks = validator_result.get("validation_checks") if isinstance(validator_result.get("validation_checks"), dict) else {}
        metrics = validator_result.get("accuracy_metrics") if isinstance(validator_result.get("accuracy_metrics"), dict) else {}
        validation_payload = {
            "artifact_type": "georef_validation",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "reason_code": "validation_passed" if passed else "validation_failed",
            "georef_artifact_ref": georef_ref.model_dump(mode="json"),
            "plss_anchor": plss_anchor,
            "anchor_used": georef_payload.get("anchor_info"),
            "bounds": bounds,
            "top_issues": top_issues,
            "overall_accuracy": validator_result.get("overall_accuracy"),
            "accuracy_metrics": metrics,
            "validation_checks_excerpt": _bounded_validate_checks(checks),
            "validator_result": validator_result,
            "agent_kernel_quality": georef_payload.get("agent_kernel_quality") if isinstance(georef_payload.get("agent_kernel_quality"), dict) else None,
        }
        dossier_id = _infer_dossier_id_for_agent_kernel_artifact(georef_ref.artifact_path) or "unknown"
        artifact_ref = _persist_json_artifact(
            category="georeference_validation",
            dossier_id=dossier_id,
            payload=validation_payload,
        )
        inline = ValidationInline(
            passed=passed,
            reason_code=("validation_passed" if passed else "validation_failed"),
            checks={
                "overall_accuracy": validator_result.get("overall_accuracy"),
                "top_issues": top_issues,
                "bounds": bounds,
                "passed_checks": metrics.get("passed_checks") if isinstance(metrics, dict) else None,
                "total_checks": metrics.get("total_checks") if isinstance(metrics, dict) else None,
            },
        )
        return {
            "artifact_ref": artifact_ref,
            "reason_codes": [inline.reason_code or ("validation_passed" if passed else "validation_failed")],
            "validation_result": inline.model_dump(mode="json"),
            "validate_summary": {
                "passed": passed,
                "overall_accuracy": validator_result.get("overall_accuracy"),
                "top_issues": top_issues,
            },
        }


@dataclass
class FeatureGraphRenderTool:
    """Render a simple SVG preview from a georeferenced polygon artifact."""

    def render(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        georef_ref = _coerce_artifact_ref(inputs.get("georef_artifact_ref"))
        if georef_ref is None:
            georef_ref = _coerce_artifact_ref(inputs.get("georeference_artifact_ref"))
        if georef_ref is None:
            return _tool_refusal_result("render_missing_georef_artifact_ref", missing_inputs=["georef_artifact_ref"])

        georef_payload = _read_json_dict(Path(georef_ref.artifact_path))
        if georef_payload is None:
            return _tool_refusal_result("render_georef_artifact_invalid_json")

        ring = _extract_geographic_polygon_ring_lonlat(georef_payload)
        if ring is None or len(ring) < 4:
            return _tool_refusal_result("render_missing_geographic_polygon")

        bounds = _extract_bounds_from_georef_payload(georef_payload) or _compute_ring_bounds(ring)
        if bounds is None:
            return _tool_refusal_result("render_missing_bounds")

        width = _bounded_int(inputs.get("width"), default=900, minimum=256, maximum=2400)
        height = _bounded_int(inputs.get("height"), default=700, minimum=256, maximum=2400)
        svg_text = _render_polygon_svg(
            ring=ring,
            bounds=bounds,
            width=width,
            height=height,
            title=_read_str(((georef_payload.get("anchor_info") or {}).get("plss_reference") if isinstance(georef_payload.get("anchor_info"), dict) else None))
            or "Georeferenced parcel preview",
        )

        dossier_id = _infer_dossier_id_for_agent_kernel_artifact(georef_ref.artifact_path) or "unknown"
        svg_ref = _persist_text_artifact(
            category="render_svg",
            dossier_id=dossier_id,
            text=svg_text,
            suffix=".svg",
        )
        render_payload = {
            "artifact_type": "map_render",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "georef_artifact_ref": georef_ref.model_dump(mode="json"),
            "svg_artifact_ref": svg_ref.model_dump(mode="json"),
            "width": width,
            "height": height,
            "bounds": bounds,
            "vertex_count": len(ring),
            "plss_anchor": georef_payload.get("plss_anchor"),
            "anchor_info": georef_payload.get("anchor_info"),
        }
        render_ref = _persist_json_artifact(category="render", dossier_id=dossier_id, payload=render_payload)
        return {
            "artifact_ref": render_ref,
            "reason_codes": ["rendered"],
            "render_summary": {
                "width": width,
                "height": height,
                "vertex_count": len(ring),
                "svg_artifact_path": svg_ref.artifact_path,
            },
        }


@dataclass
class RetrievalEvidenceTool:
    """Execute retrieval query packs and persist deterministic retrieval artifacts."""

    engine: RetrievalEngine = field(default_factory=RetrievalEngine)

    def retrieve_evidence(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        query = _read_str(inputs.get("query"))
        if not query:
            return {"artifact_ref": None, "reason_codes": ["retrieval_missing_query"]}
        routing = inputs.get("routing")
        options = inputs.get("options")
        routing_dict = routing if isinstance(routing, dict) else {}
        options_dict = options if isinstance(options, dict) else {}
        lanes = routing_dict.get("lanes")
        lanes_list = [str(item) for item in lanes] if isinstance(lanes, list) and lanes else ["hybrid"]
        limit = int(options_dict.get("limit", 10)) if str(options_dict.get("limit", "")).strip() else 10
        limit = max(1, min(limit, 25))
        filters = _build_retrieval_filters(routing_dict=routing_dict, inputs=inputs)
        result = self.engine.search(query, filters=filters, limit=limit, lanes=lanes_list)
        reason_code = _extract_retrieval_reason_code(result.debug)
        reason_codes = ["evidence_retrieved"]
        if reason_code is not None:
            reason_codes = [reason_code]
        payload = {
            "artifact_type": "retrieval_result",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "intent": _read_str(inputs.get("intent")),
            "lanes": lanes_list,
            "limit": limit,
            "cards_count": len(result.cards),
            "cards": [_evidence_card_to_dict(card) for card in result.cards[:25]],
            "debug": result.debug,
        }
        artifact_ref = _persist_json_artifact(
            category="retrieval",
            dossier_id=filters.dossier_id,
            payload=payload,
        )
        return {"artifact_ref": artifact_ref, "reason_codes": reason_codes}


def _resolve_deed_ref(inputs: Mapping[str, Any]) -> CorpusEntryRef | None:
    raw = inputs.get("source_entry_ref")
    ref = _parse_corpus_entry_ref(raw)
    if ref is not None:
        return ref

    raw_dossier_id = _read_str(inputs.get("dossier_id"))
    if not raw_dossier_id:
        return None
    return CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=f"final:{raw_dossier_id}",
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=raw_dossier_id,
    )


def _parse_corpus_entry_ref(raw: Any) -> CorpusEntryRef | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        try:
            return CorpusEntryRef(
                view=CorpusView(str(raw.get("view", CorpusView.EVERYTHING.value))),
                entry_id=str(raw.get("entry_id", "")),
                kind=CorpusEntryKind(str(raw.get("kind", CorpusEntryKind.TRANSCRIPT.value))),
                dossier_id=_read_str(raw.get("dossier_id")),
                transcription_id=_read_str(raw.get("transcription_id")),
                segment_id=_read_str(raw.get("segment_id")),
                draft_id=_read_str(raw.get("draft_id")),
                artifact_type=_read_str(raw.get("artifact_type")),
                artifact_id=_read_str(raw.get("artifact_id")),
                metadata=dict(raw.get("metadata") or {}),
            )
        except Exception:
            return None

    raw_str = _read_str(raw)
    if not raw_str:
        return None
    if raw_str.startswith("draft:head:"):
        parts = raw_str.split(":")
        if len(parts) == 4:
            dossier_id = parts[2]
            transcription_id = parts[3]
            return CorpusEntryRef(
                view=CorpusView.EVERYTHING,
                entry_id=raw_str,
                kind=CorpusEntryKind.TRANSCRIPT,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                draft_id=raw_str,
            )
    if raw_str.startswith("final:"):
        dossier_id = raw_str.split(":", maxsplit=1)[1].strip()
        if dossier_id:
            return CorpusEntryRef(
                view=CorpusView.FINALIZED,
                entry_id=raw_str,
                kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
                dossier_id=dossier_id,
            )
    return None


def _load_feature_graph_for_georeference(
    inputs: Mapping[str, Any],
) -> tuple[FeatureGraph | None, ArtifactRef | None, list[str]]:
    bundle_ref = _coerce_artifact_ref(inputs.get("bundle_artifact_ref"))
    if bundle_ref is not None:
        payload = _read_json_dict(Path(bundle_ref.artifact_path))
        if payload is None:
            return None, None, ["bundle_artifact_invalid_json"]
        graph_candidate = payload.get("target_graph")
        if not isinstance(graph_candidate, dict):
            return None, None, ["bundle_artifact_missing_target_graph"]
        try:
            return FeatureGraph.model_validate(graph_candidate), bundle_ref, []
        except Exception:
            return None, None, ["bundle_target_graph_validation_failed"]

    graph, reason_codes = _load_feature_graph_from_inputs(inputs)
    ir_ref = _coerce_artifact_ref(inputs.get("ir_artifact_ref")) or _coerce_artifact_ref(inputs.get("updated_ir_artifact_ref"))
    return graph, ir_ref, reason_codes


def _extract_primary_local_polygon_vertices(graph: FeatureGraph) -> list[dict[str, float]] | None:
    candidate_nodes = list(graph.nodes)
    candidate_nodes.sort(
        key=lambda node: (
            not bool(isinstance(node.metadata, dict) and node.metadata.get("primary") is True),
            0 if str(node.kind.value) == "region" else 1,
            str(node.id),
        )
    )
    for node in candidate_nodes:
        if _node_is_marked_partial_for_mapping(node):
            continue
        geometry = node.geometry if isinstance(node.geometry, dict) else None
        if geometry is None:
            continue
        if node.kind.value == "region" and str(geometry.get("type")) == "Polygon":
            ring = _extract_polygon_ring(geometry)
            if ring is not None:
                return [{"x": float(x), "y": float(y)} for x, y in ring]
        if node.kind.value == "curve" and str(geometry.get("type")) == "LineString":
            line = _extract_linestring_points(geometry)
            if line is not None and _ring_is_closed(line):
                normalized = _strip_duplicate_closing_vertex(line)
                return [{"x": float(x), "y": float(y)} for x, y in normalized]
    return None


def _node_is_marked_partial_for_mapping(node: Any) -> bool:
    kind_value = str(getattr(getattr(node, "kind", None), "value", "") or "").lower()
    if kind_value not in {"region", "curve"}:
        return False
    for text in _iter_node_text_fragments(node):
        low = text.lower()
        if any(tok in low for tok in ("stub", "truncated", "incomplete", "partial")):
            return True
    return False


def _iter_node_text_fragments(node: Any) -> list[str]:
    out: list[str] = []
    node_id = getattr(node, "id", None)
    if isinstance(node_id, str) and node_id:
        out.append(node_id)
    label = getattr(node, "label", None)
    if isinstance(label, str) and label:
        out.append(label)
    metadata = getattr(node, "metadata", None)
    if isinstance(metadata, Mapping):
        for value in metadata.values():
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out.append(item)
    return out


def _extract_polygon_ring(geometry: Mapping[str, Any]) -> list[tuple[float, float]] | None:
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return None
    first_ring = coords[0]
    if not isinstance(first_ring, list) or len(first_ring) < 3:
        return None
    points = _coerce_xy_points(first_ring)
    if points is None or len(points) < 3:
        return None
    points = _strip_duplicate_closing_vertex(points)
    return points if len(points) >= 3 else None


def _extract_linestring_points(geometry: Mapping[str, Any]) -> list[tuple[float, float]] | None:
    coords = geometry.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 4:
        return None
    return _coerce_xy_points(coords)


def _coerce_xy_points(raw_points: list[Any]) -> list[tuple[float, float]] | None:
    out: list[tuple[float, float]] = []
    for item in raw_points:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            return None
        try:
            x = float(item[0])
            y = float(item[1])
        except Exception:
            return None
        out.append((x, y))
    return out


def _ring_is_closed(points: list[tuple[float, float]]) -> bool:
    if len(points) < 4:
        return False
    first = points[0]
    last = points[-1]
    return abs(first[0] - last[0]) < 1e-9 and abs(first[1] - last[1]) < 1e-9


def _strip_duplicate_closing_vertex(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) >= 2 and abs(points[0][0] - points[-1][0]) < 1e-9 and abs(points[0][1] - points[-1][1]) < 1e-9:
        return points[:-1]
    return points


def _extract_plss_anchor(graph: FeatureGraph) -> dict[str, Any] | None:
    for node in graph.nodes:
        if node.kind.value != "frame":
            continue
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        candidate = metadata.get("plss_anchor")
        if isinstance(candidate, dict) and _plss_anchor_has_required_fields(candidate):
            return dict(candidate)
        normalized = _normalize_alt_plss_anchor_shape(metadata)
        if normalized is not None:
            return normalized
    for node in graph.nodes:
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        normalized = _normalize_alt_plss_anchor_shape(metadata)
        if normalized is not None:
            return normalized
    graph_candidate = (graph.metadata or {}).get("plss_anchor")
    if isinstance(graph_candidate, dict) and _plss_anchor_has_required_fields(graph_candidate):
        return dict(graph_candidate)
    normalized_graph = _normalize_alt_plss_anchor_shape(graph.metadata or {})
    if normalized_graph is not None:
        return normalized_graph
    return None


def _plss_anchor_has_required_fields(anchor: Mapping[str, Any]) -> bool:
    required = (
        "state",
        "township_number",
        "township_direction",
        "range_number",
        "range_direction",
        "section_number",
    )
    return all(anchor.get(key) is not None for key in required)


def _normalize_alt_plss_anchor_shape(metadata: Mapping[str, Any]) -> dict[str, Any] | None:
    # Accept a common almost-correct model output shape:
    # metadata.plss (+ optional metadata.jurisdiction.state) -> canonical plss_anchor.
    plss = metadata.get("plss")
    if not isinstance(plss, dict):
        return None
    jurisdiction = metadata.get("jurisdiction") if isinstance(metadata.get("jurisdiction"), dict) else {}
    township_raw = plss.get("township")
    township = township_raw if isinstance(township_raw, dict) else {}
    range_raw = plss.get("range")
    range_obj = range_raw if isinstance(range_raw, dict) else {}
    section_value = plss.get("section")
    if section_value is None:
        section_value = plss.get("section_number")
    township_num, township_dir = _coerce_plss_number_direction(township if township else township_raw, kind="township")
    range_num, range_dir = _coerce_plss_number_direction(range_obj if range_obj else range_raw, kind="range")
    section_number = _coerce_int_like(section_value)
    anchor = {
        # Be permissive at the kernel boundary: controller outputs may place
        # jurisdiction fields either in metadata.jurisdiction or metadata.plss.
        "state": _normalize_state_value(jurisdiction.get("state") or metadata.get("state") or plss.get("state")),
        "township_number": township_num,
        "township_direction": township_dir,
        "range_number": range_num,
        "range_direction": range_dir,
        "section_number": section_number,
        "principal_meridian": plss.get("principal_meridian"),
    }
    county = jurisdiction.get("county") or metadata.get("county") or plss.get("county")
    if county is not None:
        anchor["county"] = county
    return anchor if _plss_anchor_has_required_fields(anchor) else None


def _coerce_plss_number_direction(raw: Any, *, kind: str) -> tuple[int | None, str | None]:
    if isinstance(raw, dict):
        return _coerce_int_like(raw.get("number")), _normalize_plss_direction(raw.get("direction"), kind=kind)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw), None
    if isinstance(raw, str):
        text = raw.strip().upper()
        if not text:
            return None, None
        m = re.match(r"^(\d+)\s*([NSEW])$", text)
        if m:
            return int(m.group(1)), m.group(2)
        return _coerce_int_like(text), None
    return None, None


def _normalize_plss_direction(raw: Any, *, kind: str) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text:
        return None
    aliases = {
        "township": {"N": "N", "NORTH": "N", "S": "S", "SOUTH": "S"},
        "range": {"E": "E", "EAST": "E", "W": "W", "WEST": "W"},
    }
    return aliases.get(kind, {}).get(text, text if len(text) == 1 else None)


def _coerce_int_like(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        try:
            return int(raw)
        except Exception:
            return None
    if isinstance(raw, str):
        m = re.search(r"(\d+)", raw)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
    return None


def _normalize_state_value(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    aliases = {"WY": "Wyoming", "WYO": "Wyoming"}
    return aliases.get(text.upper(), text)


def _georef_readiness_diagnostics(graph: FeatureGraph) -> dict[str, Any]:
    local_coords = _extract_primary_local_polygon_vertices(graph)
    plss_anchor = _extract_plss_anchor(graph)
    return {
        "local_polygon_detected": isinstance(local_coords, list) and len(local_coords) >= 3,
        "local_polygon_candidates": _local_polygon_candidates(graph),
        "plss_anchor_detected": isinstance(plss_anchor, dict),
        "plss_anchor": dict(plss_anchor) if isinstance(plss_anchor, dict) else None,
        "plss_candidates": _plss_anchor_candidates(graph),
    }


def _local_polygon_candidates(graph: FeatureGraph) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in graph.nodes[:80]:
        geometry = node.geometry if isinstance(node.geometry, dict) else None
        if geometry is None:
            continue
        gtype = str(geometry.get("type") or "")
        if node.kind.value == "region" and gtype == "Polygon":
            ring = _extract_polygon_ring(geometry)
            out.append(
                {
                    "node_id": node.id,
                    "kind": node.kind.value,
                    "geometry_type": gtype,
                    "valid_local_polygon": ring is not None,
                    "vertex_count": len(ring) if isinstance(ring, list) else None,
                    "primary": bool(isinstance(node.metadata, dict) and node.metadata.get("primary") is True),
                }
            )
        elif node.kind.value == "curve" and gtype == "LineString":
            line = _extract_linestring_points(geometry)
            closed = bool(isinstance(line, list) and _ring_is_closed(line))
            out.append(
                {
                    "node_id": node.id,
                    "kind": node.kind.value,
                    "geometry_type": gtype,
                    "valid_local_polygon": bool(closed and isinstance(line, list) and len(line) >= 4),
                    "closed_ring": closed,
                    "vertex_count": len(line) if isinstance(line, list) else None,
                    "primary": bool(isinstance(node.metadata, dict) and node.metadata.get("primary") is True),
                }
            )
    return out[:8]


def _plss_anchor_candidates(graph: FeatureGraph) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in graph.nodes[:80]:
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        if not isinstance(metadata.get("plss_anchor"), dict) and not isinstance(metadata.get("plss"), dict):
            continue
        entry: dict[str, Any] = {
            "node_id": node.id,
            "kind": node.kind.value,
            "frame_type": metadata.get("frame_type") if isinstance(metadata.get("frame_type"), str) else None,
            "has_plss_anchor": isinstance(metadata.get("plss_anchor"), dict),
            "has_plss_block": isinstance(metadata.get("plss"), dict),
        }
        if isinstance(metadata.get("plss_anchor"), dict):
            anchor = metadata["plss_anchor"]
            entry["plss_anchor_valid"] = _plss_anchor_has_required_fields(anchor)
            entry["plss_anchor_fields"] = sorted(str(k) for k in list(anchor.keys())[:12])
        normalized = _normalize_alt_plss_anchor_shape(metadata)
        entry["normalized_anchor_valid"] = normalized is not None
        if normalized is not None:
            entry["normalized_anchor"] = normalized
        out.append(entry)
    graph_meta = graph.metadata or {}
    if isinstance(graph_meta.get("plss_anchor"), dict) or isinstance(graph_meta.get("plss"), dict):
        normalized = _normalize_alt_plss_anchor_shape(graph_meta)
        out.append(
            {
                "node_id": "<graph.metadata>",
                "kind": "graph_metadata",
                "has_plss_anchor": isinstance(graph_meta.get("plss_anchor"), dict),
                "has_plss_block": isinstance(graph_meta.get("plss"), dict),
                "normalized_anchor_valid": normalized is not None,
                "normalized_anchor": normalized if isinstance(normalized, dict) else None,
            }
        )
    return out[:8]


def _extract_tie_to_corner(graph: FeatureGraph) -> dict[str, Any] | None:
    for node in graph.nodes:
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        if not _metadata_likely_pob(metadata, node_id=node.id, node_label=node.label):
            continue
        tie = _normalize_tie_to_corner_shape(metadata.get("tie_to_corner"))
        if tie is not None:
            return tie
        starting_point = metadata.get("starting_point")
        if isinstance(starting_point, Mapping):
            tie = _normalize_tie_to_corner_shape(starting_point.get("tie_to_corner") or starting_point.get("tie"))
            if tie is not None:
                return tie
    graph_meta = graph.metadata or {}
    starting_point = graph_meta.get("starting_point")
    if isinstance(starting_point, Mapping):
        tie = _normalize_tie_to_corner_shape(starting_point.get("tie_to_corner") or starting_point.get("tie"))
        if tie is not None:
            return tie
        for alias_key in ("pob", "point_of_beginning", "pointOfBeginning"):
            candidate = starting_point.get(alias_key)
            if isinstance(candidate, Mapping):
                tie = _normalize_tie_to_corner_shape(candidate.get("tie_to_corner") or candidate.get("tie"))
                if tie is not None:
                    return tie
    tie = _normalize_tie_to_corner_shape(graph_meta.get("tie_to_corner") or graph_meta.get("pob_tie_to_corner"))
    if tie is not None:
        return tie
    return None


def _metadata_likely_pob(metadata: Mapping[str, Any], *, node_id: str, node_label: str | None) -> bool:
    role_text = str(metadata.get("role") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if role_text in {"pob", "point_of_beginning", "pointofbeginning", "beginning_point"}:
        return True
    for key in ("is_pob", "pob", "point_of_beginning"):
        if metadata.get(key) is True:
            return True
    haystack = " ".join(
        str(part).lower()
        for part in (
            node_id,
            node_label or "",
            metadata.get("label") or "",
            metadata.get("note") or "",
            metadata.get("description") or "",
        )
        if isinstance(part, str) and part
    )
    if not haystack:
        return False
    return ("pob" in haystack) or ("point of beginning" in haystack)


def _normalize_tie_to_corner_shape(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    src = dict(raw)
    nested_tie = src.get("tie_to_corner") or src.get("tie")
    if isinstance(nested_tie, Mapping):
        src = dict(nested_tie)

    out: dict[str, Any] = {}
    corner_label = _first_nonempty_str(
        src.get("corner_label"),
        src.get("corner"),
        src.get("corner_ref"),
        src.get("corner_name"),
        src.get("cornerLabel"),
    )
    if corner_label:
        out["corner_label"] = corner_label

    bearing_raw = _first_nonempty_str(
        src.get("bearing_raw"),
        src.get("bearing"),
        src.get("bearing_text"),
        src.get("bearing_call"),
        src.get("bearingRaw"),
    )
    if bearing_raw:
        out["bearing_raw"] = bearing_raw

    distance_value = None
    distance_units = None
    distance_obj = src.get("distance")
    if isinstance(distance_obj, Mapping):
        distance_value = _coerce_float_like(distance_obj.get("value") or distance_obj.get("distance_value"))
        distance_units = _first_nonempty_str(distance_obj.get("units"), distance_obj.get("unit"))
    if distance_value is None:
        raw_distance_fallback = src.get("distance")
        if isinstance(raw_distance_fallback, Mapping):
            raw_distance_fallback = None
        distance_value = _coerce_float_like(
            src.get("distance_value")
            or raw_distance_fallback
            or src.get("distance_feet")
            or src.get("distance_ft")
            or src.get("distanceFeet")
        )
    if distance_units is None:
        distance_units = _first_nonempty_str(
            src.get("distance_units"),
            src.get("units"),
            src.get("unit"),
            "feet" if any(k in src for k in ("distance_feet", "distance_ft", "distanceFeet")) else None,
        )
    if distance_value is not None:
        if abs(distance_value - round(distance_value)) < 1e-9:
            out["distance_value"] = int(round(distance_value))
        else:
            out["distance_value"] = float(distance_value)
    if distance_units:
        out["distance_units"] = distance_units

    tie_direction = _normalize_tie_direction(
        src.get("tie_direction")
        or src.get("bearing_direction")
        or src.get("direction_mode")
        or src.get("tieDirection")
    )
    if tie_direction:
        out["tie_direction"] = tie_direction

    project_to_boundary = src.get("project_to_boundary")
    if not isinstance(project_to_boundary, bool):
        project_to_boundary = src.get("snap_to_boundary")
    if isinstance(project_to_boundary, bool):
        out["project_to_boundary"] = project_to_boundary

    for passthrough_key in ("corner_confidence", "source_span_id", "notes"):
        if passthrough_key in src and isinstance(src.get(passthrough_key), (str, int, float, bool)):
            out[passthrough_key] = src[passthrough_key]

    return out or None


def _normalize_tie_direction(raw: Any) -> str | None:
    text = _first_nonempty_str(raw)
    if not text:
        return None
    normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "corner_bears_from_pob": "corner_bears_from_pob",
        "corner_from_pob": "corner_bears_from_pob",
        "pob_to_corner": "corner_bears_from_pob",
        "pob_bears_from_corner": "pob_bears_from_corner",
        "pob_from_corner": "pob_bears_from_corner",
        "corner_to_pob": "pob_bears_from_corner",
    }
    return aliases.get(normalized)


def _first_nonempty_str(*values: Any) -> str | None:
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def _coerce_float_like(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except Exception:
            return None
    text = str(raw).strip()
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _extract_georeference_options(*, graph: FeatureGraph) -> dict[str, Any]:
    local_units = "feet"
    screen_coords_y_down = False
    for node in graph.nodes:
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        if metadata.get("local_units") is not None:
            local_units = str(metadata.get("local_units") or "feet")
        if isinstance(metadata.get("screen_coords_y_down"), bool):
            screen_coords_y_down = bool(metadata.get("screen_coords_y_down"))
    graph_meta = graph.metadata or {}
    if graph_meta.get("local_units") is not None:
        local_units = str(graph_meta.get("local_units") or local_units)
    if isinstance(graph_meta.get("screen_coords_y_down"), bool):
        screen_coords_y_down = bool(graph_meta.get("screen_coords_y_down"))
    return {"local_units": local_units, "screen_coords_y_down": screen_coords_y_down}


def _resolve_georeference_dossier_id(
    *,
    inputs: Mapping[str, Any],
    graph: FeatureGraph,
    source_ref: ArtifactRef | None,
) -> str:
    dossier_id = _resolve_dossier_id(inputs, graph)
    if dossier_id and dossier_id != "unknown":
        return dossier_id
    if source_ref is not None:
        inferred = _infer_dossier_id_from_feature_graph_artifact_path(source_ref.artifact_path)
        if inferred:
            return inferred
    return "unknown"


def _extract_plss_anchor_from_georef_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if isinstance(payload.get("plss_anchor"), dict):
        return dict(payload["plss_anchor"])
    request = payload.get("request")
    if isinstance(request, dict) and isinstance(request.get("plss_anchor"), dict):
        return dict(request["plss_anchor"])
    return None


def _bounded_validate_checks(checks: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in list(checks.keys())[:12]:
        value = checks.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)] = value
        else:
            out[str(key)] = _summarize_text(str(value))[:120]
    return out


def _tool_refusal_result(
    reason_code: str,
    *,
    missing_inputs: list[str] | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "artifact_ref": None,
        "reason_codes": [reason_code],
        "kernel_refusal": {
            "reason_code": reason_code,
            "missing_inputs": missing_inputs or [],
            "retryable": True,
            "blocked_by_budget": False,
            "blocked_by_invariant": False,
        },
    }
    if isinstance(diagnostics, Mapping):
        out["diagnostics"] = dict(diagnostics)
    return out


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _deed_fingerprint(text: str) -> dict[str, Any]:
    return {
        "sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        "length_chars": len(text),
    }


def _fingerprint_matches_dict(*, expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    if _read_str(expected.get("sha256_12")) != _read_str(actual.get("sha256_12")):
        return False
    try:
        return int(expected.get("length_chars")) == int(actual.get("length_chars"))
    except Exception:
        return False


def _load_span_index(raw_ref: Any) -> dict[str, Any] | None:
    ref = _coerce_artifact_ref(raw_ref)
    if ref is None:
        return None
    return _read_json_dict(Path(ref.artifact_path))


def _resolve_requested_text_spans(
    *,
    inputs: Mapping[str, Any],
    deed_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    raw_spans = inputs.get("spans")
    if isinstance(raw_spans, list):
        items: list[dict[str, Any]] = []
        for raw in raw_spans:
            if not isinstance(raw, dict):
                return [], _tool_refusal_result("open_text_spans_invalid_range"), []
            start_char = raw.get("start_char")
            end_char = raw.get("end_char")
            if not isinstance(start_char, int) or not isinstance(end_char, int):
                return [], _tool_refusal_result("open_text_spans_invalid_range"), []
            items.append(
                {
                    "span_id": _read_str(raw.get("span_id")),
                    "start_char": start_char,
                    "end_char": end_char,
                    "fingerprint_ok": True,
                }
            )
        return items, None, []

    raw_anchors = inputs.get("anchors")
    if isinstance(raw_anchors, list) and raw_anchors:
        return _resolve_anchor_requested_spans(raw_anchors=raw_anchors, deed_text=deed_text)

    raw_span_ids = inputs.get("span_ids")
    if not isinstance(raw_span_ids, list) or not raw_span_ids:
        return [], _tool_refusal_result("open_text_spans_invalid_range"), []
    index = _load_span_index(inputs.get("deed_span_index_ref"))
    if not isinstance(index, dict):
        return [], _tool_refusal_result("open_text_spans_invalid_range"), []
    deed_fp = index.get("deed_fingerprint")
    if not isinstance(deed_fp, dict) or not _fingerprint_matches_dict(expected=deed_fp, actual=_deed_fingerprint(deed_text)):
        return [], _tool_refusal_result("open_text_spans_fingerprint_mismatch"), []
    spans = index.get("spans")
    if not isinstance(spans, list):
        return [], _tool_refusal_result("open_text_spans_invalid_range"), []
    span_map = {}
    for span in spans:
        if isinstance(span, dict):
            sid = _read_str(span.get("span_id"))
            if sid:
                span_map[sid] = span
    items: list[dict[str, Any]] = []
    for raw_id in raw_span_ids:
        sid = _read_str(raw_id)
        span = span_map.get(sid or "")
        if sid is None or not isinstance(span, dict):
            return [], _tool_refusal_result("open_text_spans_invalid_range"), []
        start_char = span.get("start_char")
        end_char = span.get("end_char")
        if not isinstance(start_char, int) or not isinstance(end_char, int):
            return [], _tool_refusal_result("open_text_spans_invalid_range"), []
        items.append(
            {
                "span_id": sid,
                "start_char": start_char,
                "end_char": end_char,
                "fingerprint_ok": True,
            }
        )
    return items, None, []


def _resolve_anchor_requested_spans(
    *,
    raw_anchors: list[Any],
    deed_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    # Returns (resolved_items, fatal_failure, partial_failures)
    normalized_text, norm_to_orig = _normalize_text_with_index_map(deed_text)
    items: list[dict[str, Any]] = []
    partial_failures: list[dict[str, Any]] = []
    for raw in raw_anchors:
        if not isinstance(raw, dict):
            partial_failures.append({"reason_code": "open_text_spans_anchor_not_found"})
            continue
        span_id = _read_str(raw.get("span_id"))
        start_anchor_raw = _read_str(raw.get("start_anchor"))
        end_anchor_raw = _read_str(raw.get("end_anchor"))
        if not start_anchor_raw or not end_anchor_raw:
            partial_failures.append({"span_id": span_id, "reason_code": "open_text_spans_anchor_not_found"})
            continue
        start_anchor = _normalize_text_simple(start_anchor_raw)
        end_anchor = _normalize_text_simple(end_anchor_raw)
        if not start_anchor or not end_anchor:
            partial_failures.append({"span_id": span_id, "reason_code": "open_text_spans_anchor_not_found"})
            continue
        occurrence = raw.get("occurrence")
        start_matches = _find_all_occurrences(normalized_text, start_anchor)
        if not start_matches:
            partial_failures.append({"span_id": span_id, "reason_code": "open_text_spans_anchor_not_found"})
            continue
        selected_start_match = None
        if isinstance(occurrence, int):
            idx = occurrence - 1
            if idx < 0 or idx >= len(start_matches):
                partial_failures.append({"span_id": span_id, "reason_code": "open_text_spans_anchor_not_found"})
                continue
            selected_start_match = start_matches[idx]
        elif len(start_matches) == 1:
            selected_start_match = start_matches[0]
        else:
            candidate_failure = _tool_refusal_with_candidates(
                "open_text_spans_anchor_ambiguous",
                normalized_text=normalized_text,
                norm_to_orig=norm_to_orig,
                matches=start_matches,
                match_len=len(start_anchor),
            )
            candidate_failure["span_id"] = span_id
            partial_failures.append(candidate_failure)
            continue
        assert selected_start_match is not None

        end_matches = _find_all_occurrences(normalized_text, end_anchor)
        end_after = [m for m in end_matches if m >= selected_start_match]
        if not end_after:
            partial_failures.append({"span_id": span_id, "reason_code": "open_text_spans_anchor_not_found"})
            continue
        selected_end_match = end_after[0]
        if selected_end_match < selected_start_match:
            partial_failures.append({"span_id": span_id, "reason_code": "open_text_spans_anchor_invalid_order"})
            continue

        start_char = _norm_pos_to_orig_start(norm_to_orig, selected_start_match)
        end_char_exclusive = _norm_pos_to_orig_end_exclusive(norm_to_orig, selected_end_match + len(end_anchor) - 1)
        if start_char is None or end_char_exclusive is None or end_char_exclusive <= start_char:
            partial_failures.append({"span_id": span_id, "reason_code": "open_text_spans_anchor_invalid_order"})
            continue
        items.append(
            {
                "span_id": span_id,
                "start_char": start_char,
                "end_char": end_char_exclusive,
                "fingerprint_ok": True,
            }
        )
    if items:
        return items, None, partial_failures
    if partial_failures:
        first = partial_failures[0]
        if isinstance(first, dict) and "kernel_refusal" in first:
            return [], first, partial_failures
        reason_code = _read_str(first.get("reason_code")) if isinstance(first, dict) else None
        return [], _tool_refusal_result(reason_code or "open_text_spans_anchor_not_found"), partial_failures
    return [], _tool_refusal_result("open_text_spans_anchor_not_found"), partial_failures


def _tool_refusal_with_candidates(
    reason_code: str,
    *,
    normalized_text: str,
    norm_to_orig: list[int],
    matches: list[int],
    match_len: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for idx, pos in enumerate(matches[:5], start=1):
        start_orig = _norm_pos_to_orig_start(norm_to_orig, pos)
        end_orig = _norm_pos_to_orig_end_exclusive(norm_to_orig, pos + max(0, match_len - 1))
        if start_orig is None or end_orig is None:
            continue
        preview_start = max(0, start_orig - 40)
        preview_end = min(len(normalized_text), pos + match_len + 40)
        preview = normalized_text[max(0, pos - 40) : preview_end]
        candidates.append(
            {
                "candidate_id": f"cand_{idx:02d}",
                "start_char": start_orig,
                "end_char": end_orig,
                "preview": preview[:160],
            }
        )
    result = _tool_refusal_result(reason_code)
    result["candidates"] = candidates
    return result


def _normalize_text_with_index_map(text: str) -> tuple[str, list[int]]:
    out_chars: list[str] = []
    norm_to_orig: list[int] = []
    in_ws = False
    for idx, ch in enumerate(text):
        if ch.isspace():
            if not out_chars:
                continue
            if in_ws:
                continue
            out_chars.append(" ")
            norm_to_orig.append(idx)
            in_ws = True
            continue
        out_chars.append(ch)
        norm_to_orig.append(idx)
        in_ws = False
    while out_chars and out_chars[-1] == " ":
        out_chars.pop()
        norm_to_orig.pop()
    return "".join(out_chars), norm_to_orig


def _normalize_text_simple(text: str) -> str:
    return " ".join(text.split()).strip()


def _find_all_occurrences(haystack: str, needle: str) -> list[int]:
    matches: list[int] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            break
        matches.append(idx)
        start = idx + 1
    return matches


def _norm_pos_to_orig_start(norm_to_orig: list[int], norm_pos: int) -> int | None:
    if norm_pos < 0 or norm_pos >= len(norm_to_orig):
        return None
    return int(norm_to_orig[norm_pos])


def _norm_pos_to_orig_end_exclusive(norm_to_orig: list[int], norm_pos: int) -> int | None:
    if norm_pos < 0 or norm_pos >= len(norm_to_orig):
        return None
    return int(norm_to_orig[norm_pos]) + 1


def _span_catalog_excerpt(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for span in spans[:12]:
        out.append(
            {
                "span_id": span.get("span_id"),
                "kind": span.get("kind"),
                "labels": span.get("labels", [])[:4] if isinstance(span.get("labels"), list) else [],
                "status": span.get("status"),
                "start_char": span.get("start_char"),
                "end_char": span.get("end_char"),
            }
        )
    return out


def _bounded_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, value))


def _coerce_artifact_ref(raw: Any) -> ArtifactRef | None:
    if isinstance(raw, ArtifactRef):
        return raw
    if isinstance(raw, dict):
        try:
            return ArtifactRef.model_validate(raw)
        except Exception:
            return None
    raw_str = _read_str(raw)
    if raw_str:
        return ArtifactRef(artifact_path=raw_str)
    return None


def _entry_ref_to_dict(ref: CorpusEntryRef) -> dict[str, Any]:
    return {
        "view": ref.view.value,
        "entry_id": ref.entry_id,
        "kind": ref.kind.value,
        "dossier_id": ref.dossier_id,
        "transcription_id": ref.transcription_id,
        "segment_id": ref.segment_id,
        "draft_id": ref.draft_id,
        "artifact_type": ref.artifact_type,
        "artifact_id": ref.artifact_id,
        "metadata": ref.metadata,
    }


def _persist_json_artifact(
    *,
    category: str,
    dossier_id: str | None,
    payload: dict[str, Any],
) -> ArtifactRef:
    root = agent_kernel_artifacts_root() / "tool_outputs" / category / str(dossier_id or "unknown")
    root.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}.json"
    path = root / artifact_name

    fd, tmp_path = tempfile.mkstemp(prefix="kernel_tool_", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return ArtifactRef(artifact_path=str(path))


def _persist_text_artifact(
    *,
    category: str,
    dossier_id: str | None,
    text: str,
    suffix: str,
) -> ArtifactRef:
    root = agent_kernel_artifacts_root() / "tool_outputs" / category / str(dossier_id or "unknown")
    root.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}{suffix}"
    path = root / artifact_name

    fd, tmp_path = tempfile.mkstemp(prefix="kernel_tool_", suffix=suffix, dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            path.write_text(text, encoding="utf-8", newline="\n")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return ArtifactRef(artifact_path=str(path))


def _load_feature_graph_from_inputs(inputs: Mapping[str, Any]) -> tuple[FeatureGraph | None, list[str]]:
    graph_payload = inputs.get("graph")
    if isinstance(graph_payload, dict):
        try:
            return FeatureGraph.model_validate(graph_payload), []
        except Exception:
            return None, ["invalid_graph_payload"]

    ir_ref = _coerce_artifact_ref(inputs.get("ir_artifact_ref"))
    if ir_ref is None:
        ir_ref = _coerce_artifact_ref(inputs.get("updated_ir_artifact_ref"))
    if ir_ref is None:
        ir_ref = _coerce_artifact_ref(inputs.get("ir_artifact_path"))
    if ir_ref is None:
        return None, ["missing_ir_artifact_ref_or_graph"]

    path = Path(ir_ref.artifact_path)
    if not path.exists():
        return None, ["ir_artifact_not_found"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, ["ir_artifact_invalid_json"]
    if not isinstance(payload, dict):
        return None, ["ir_artifact_payload_not_object"]
    graph_candidate = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
    if not isinstance(graph_candidate, dict):
        return None, ["ir_artifact_missing_graph"]
    try:
        return FeatureGraph.model_validate(graph_candidate), []
    except Exception:
        return None, ["ir_graph_validation_failed"]


def _resolve_dossier_id(inputs: Mapping[str, Any], graph: FeatureGraph) -> str:
    dossier_id = _read_str(inputs.get("dossier_id"))
    if dossier_id:
        return dossier_id
    inferred_from_ref = _infer_dossier_id_from_ir_ref_inputs(inputs)
    if inferred_from_ref:
        return inferred_from_ref
    graph_dossier = _read_str((graph.metadata or {}).get("dossier_id"))
    if graph_dossier:
        return graph_dossier
    return "unknown"


def _infer_dossier_id_from_ir_ref_inputs(inputs: Mapping[str, Any]) -> str | None:
    for key in ("ir_artifact_ref", "updated_ir_artifact_ref", "ir_artifact_path"):
        ref = _coerce_artifact_ref(inputs.get(key))
        if ref is None:
            continue
        dossier_id = _infer_dossier_id_from_feature_graph_artifact_path(ref.artifact_path)
        if dossier_id:
            return dossier_id
    return None


def _extract_geographic_polygon_ring_lonlat(georef_payload: Mapping[str, Any]) -> list[tuple[float, float]] | None:
    geo = georef_payload.get("geographic_polygon")
    if not isinstance(geo, dict):
        return None
    coords = geo.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return None
    outer = coords[0]
    if not isinstance(outer, list):
        return None
    ring: list[tuple[float, float]] = []
    for pt in outer:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return None
        try:
            lon = float(pt[0])
            lat = float(pt[1])
        except Exception:
            return None
        ring.append((lon, lat))
    return ring if len(ring) >= 4 else None


def _extract_bounds_from_georef_payload(georef_payload: Mapping[str, Any]) -> dict[str, float] | None:
    geo = georef_payload.get("geographic_polygon")
    if not isinstance(geo, dict):
        return None
    bounds = geo.get("bounds")
    if not isinstance(bounds, dict):
        return None
    try:
        return {
            "min_lat": float(bounds["min_lat"]),
            "max_lat": float(bounds["max_lat"]),
            "min_lon": float(bounds["min_lon"]),
            "max_lon": float(bounds["max_lon"]),
        }
    except Exception:
        return None


def _compute_ring_bounds(ring: list[tuple[float, float]]) -> dict[str, float] | None:
    if not ring:
        return None
    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    return {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }


def _render_polygon_svg(
    *,
    ring: list[tuple[float, float]],
    bounds: Mapping[str, float],
    width: int,
    height: int,
    title: str,
) -> str:
    min_lon = float(bounds["min_lon"])
    max_lon = float(bounds["max_lon"])
    min_lat = float(bounds["min_lat"])
    max_lat = float(bounds["max_lat"])
    span_lon = max(max_lon - min_lon, 1e-12)
    span_lat = max(max_lat - min_lat, 1e-12)
    pad = 40.0
    inner_w = max(1.0, float(width) - (pad * 2.0))
    inner_h = max(1.0, float(height) - (pad * 2.0))
    points: list[str] = []
    for lon, lat in ring:
        x = pad + ((lon - min_lon) / span_lon) * inner_w
        y = float(height) - pad - ((lat - min_lat) / span_lat) * inner_h
        points.append(f"{x:.2f},{y:.2f}")
    pts = " ".join(points)
    safe_title = _xml_escape(title)
    info = _xml_escape(
        f"Bounds lon[{min_lon:.8f},{max_lon:.8f}] lat[{min_lat:.8f},{max_lat:.8f}]  vertices={len(ring)}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#f7f4ec"/>\n'
        f'  <rect x="{pad}" y="{pad}" width="{inner_w:.2f}" height="{inner_h:.2f}" fill="#ffffff" stroke="#d7d0bf"/>\n'
        f'  <polygon points="{pts}" fill="#3a7d6b" fill-opacity="0.22" stroke="#1f5a4d" stroke-width="2"/>\n'
        f'  <circle cx="{points[0].split(",")[0]}" cy="{points[0].split(",")[1]}" r="4" fill="#c23b22"/>\n'
        f'  <text x="{pad}" y="24" font-family="Georgia, serif" font-size="16" fill="#222">{safe_title}</text>\n'
        f'  <text x="{pad}" y="{height - 14}" font-family="Consolas, monospace" font-size="11" fill="#555">{info}</text>\n'
        f"</svg>\n"
    )


def _xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _graph_mapping_quality_diagnostics(
    graph: FeatureGraph,
    *,
    tie_to_corner: Mapping[str, Any] | None,
) -> dict[str, Any]:
    placeholder_nodes: list[str] = []
    partial_markers: list[str] = []
    partial_non_annotation_markers: list[str] = []
    partial_annotation_stubs: list[str] = []
    explicit_tie_mentions: list[str] = []

    def _scan_text(text: str, *, node_id: str, node_kind: str | None = None) -> None:
        low = text.lower()
        if any(tok in low for tok in ("placeholder", "sketch", "not yet constructed")):
            if node_id not in placeholder_nodes:
                placeholder_nodes.append(node_id)
        if any(tok in low for tok in ("stub", "truncated", "incomplete", "partial")):
            if node_id not in partial_markers:
                partial_markers.append(node_id)
            kind_token = (node_kind or "").lower()
            if kind_token in {"annotation", "graph_metadata"}:
                if node_id not in partial_annotation_stubs:
                    partial_annotation_stubs.append(node_id)
            else:
                if node_id not in partial_non_annotation_markers:
                    partial_non_annotation_markers.append(node_id)
        if ("corner" in low and "section" in low) or "tie to" in low or "nw corner" in low:
            if node_id not in explicit_tie_mentions:
                explicit_tie_mentions.append(node_id)

    graph_meta = graph.metadata if isinstance(graph.metadata, dict) else {}
    for key, value in graph_meta.items():
        if isinstance(value, str):
            _scan_text(value, node_id=f"<graph.metadata:{key}>", node_kind="graph_metadata")

    for node in graph.nodes:
        node_kind = node.kind.value if getattr(node, "kind", None) is not None else None
        _scan_text(str(node.label or ""), node_id=node.id, node_kind=node_kind)
        meta = node.metadata if isinstance(node.metadata, dict) else {}
        for key, value in meta.items():
            if isinstance(value, str):
                _scan_text(value, node_id=node.id, node_kind=node_kind)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        _scan_text(item, node_id=node.id, node_kind=node_kind)

    return {
        "placeholder_geometry_detected": bool(placeholder_nodes),
        "placeholder_nodes": placeholder_nodes[:12],
        "partial_plot_markers_detected": bool(partial_markers),
        "partial_marker_nodes": partial_markers[:12],
        "partial_non_annotation_markers_detected": bool(partial_non_annotation_markers),
        "partial_non_annotation_marker_nodes": partial_non_annotation_markers[:12],
        "partial_annotation_stub_nodes": partial_annotation_stubs[:12],
        "explicit_tie_reference_detected": bool(explicit_tie_mentions),
        "explicit_tie_reference_nodes": explicit_tie_mentions[:12],
        "tie_to_corner_provided": bool(isinstance(tie_to_corner, Mapping) and len(dict(tie_to_corner)) > 0),
    }


def _mapping_quality_issues_from_georef_payload(georef_payload: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    quality = georef_payload.get("agent_kernel_quality")
    if not isinstance(quality, dict):
        return out

    if bool(quality.get("placeholder_geometry_detected")):
        nodes = quality.get("placeholder_nodes")
        suffix = ""
        if isinstance(nodes, list) and nodes:
            suffix = f" nodes={','.join(str(v) for v in nodes[:4])}"
        out.append(f"agent_kernel_placeholder_geometry_detected{suffix}")

    explicit_tie = bool(quality.get("explicit_tie_reference_detected"))
    tie_provided = bool(quality.get("tie_to_corner_provided"))
    anchor_info = georef_payload.get("anchor_info")
    pob_method = None
    if isinstance(anchor_info, dict):
        pob_method = _read_str(anchor_info.get("pob_method"))
    if explicit_tie and not tie_provided and pob_method == "section_centroid":
        out.append("agent_kernel_unresolved_tie_to_corner_reference")

    if pob_method == "section_centroid":
        out.append("agent_kernel_section_centroid_anchor_fallback")

    # Partial markers are informative but not necessarily completion blockers by themselves.
    if bool(quality.get("partial_non_annotation_markers_detected")):
        nodes = quality.get("partial_non_annotation_marker_nodes")
        suffix = ""
        if isinstance(nodes, list) and nodes:
            suffix = f" nodes={','.join(str(v) for v in nodes[:4])}"
        out.append(f"agent_kernel_partial_plot_markers_present{suffix}")
    return out


def _validator_allows_tie_anchored_override(
    *,
    georef_payload: Mapping[str, Any],
    validator_result: Mapping[str, Any],
) -> bool:
    anchor_info = georef_payload.get("anchor_info")
    pob_method = ""
    if isinstance(anchor_info, Mapping):
        pob_method = str(anchor_info.get("pob_method") or "").strip().lower()
    quality = georef_payload.get("agent_kernel_quality")
    tie_provided = bool(isinstance(quality, Mapping) and quality.get("tie_to_corner_provided") is True)
    if "corner_with_tie" not in pob_method and not tie_provided:
        return False

    checks = validator_result.get("validation_checks")
    if isinstance(checks, Mapping):
        allowed_false = {"centroid_within_section_tolerance", "vertices_near_section"}
        for key, value in checks.items():
            if isinstance(value, bool) and value is False and str(key) not in allowed_false:
                return False

    issues = validator_result.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            low = str(issue).lower()
            if not any(tok in low for tok in ("centroid", "section center", "near section")):
                return False
    return True


def _infer_dossier_id_from_feature_graph_artifact_path(path_value: str) -> str | None:
    try:
        path = Path(path_value).resolve()
        root = dossiers_feature_graphs_artifacts_root().resolve()
    except Exception:
        return None
    if path == root or root not in path.parents:
        return None
    try:
        rel = path.relative_to(root)
    except Exception:
        return None
    if not rel.parts:
        return None
    candidate = str(rel.parts[0]).strip()
    return candidate or None


def _infer_dossier_id_for_agent_kernel_artifact(path_value: str) -> str | None:
    try:
        path = Path(path_value).resolve()
        root = agent_kernel_artifacts_root().resolve()
    except Exception:
        return None
    if path == root or root not in path.parents:
        return None
    try:
        rel = path.relative_to(root)
    except Exception:
        return None
    parts = list(rel.parts)
    if len(parts) >= 4 and parts[0] == "tool_outputs":
        candidate = str(parts[2]).strip()
        return candidate or None
    return None


def _infer_parent_artifact_ids(inputs: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("ir_artifact_ref", "compile_artifact_ref", "judge_artifact_ref", "bundle_artifact_ref"):
        ref = _coerce_artifact_ref(inputs.get(key))
        if ref is None:
            continue
        stem = Path(ref.artifact_path).stem
        if stem:
            refs.append(stem)
    return refs


def _build_retrieval_filters(*, routing_dict: dict[str, Any], inputs: Mapping[str, Any]) -> RetrievalFilters:
    view_raw = _read_str(routing_dict.get("view")) or _read_str(inputs.get("view"))
    view = None
    if view_raw:
        normalized = view_raw.strip().lower()
        view_map = {
            "everything": CorpusView.EVERYTHING,
            "finalized": CorpusView.FINALIZED,
            "final_segments": CorpusView.FINAL_SEGMENTS,
        }
        view = view_map.get(normalized)
    filters_raw = routing_dict.get("filters")
    filters_dict = filters_raw if isinstance(filters_raw, dict) else {}
    return RetrievalFilters(
        view=view,
        dossier_id=_read_str(inputs.get("dossier_id")),
        transcription_id=_read_str(inputs.get("transcription_id")),
        artifact_type=_read_str(filters_dict.get("artifact_type")),
        extra=dict(filters_dict),
    )


def _extract_retrieval_reason_code(debug: dict[str, Any]) -> str | None:
    known = {
        "semantic_worker_unavailable",
        "semantic_worker_in_backoff",
        "semantic_worker_timeout",
        "semantic_worker_port_in_use",
        "semantic_worker_backoff",
    }
    if not isinstance(debug, dict):
        return None
    stack: list[Any] = [debug]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            reason = node.get("reason")
            if isinstance(reason, str) and reason in known:
                return reason
            reason_code = node.get("reason_code")
            if isinstance(reason_code, str) and reason_code in known:
                return reason_code
            for value in node.values():
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _evidence_card_to_dict(card: Any) -> dict[str, Any]:
    spans = []
    for span in getattr(card, "spans", []) or []:
        entry = getattr(span, "entry", None)
        chunk = getattr(span, "chunk", None)
        spans.append(
            {
                "entry": {
                    "view": getattr(getattr(entry, "view", None), "value", None),
                    "entry_id": getattr(entry, "entry_id", None),
                    "kind": getattr(getattr(entry, "kind", None), "value", None),
                    "dossier_id": getattr(entry, "dossier_id", None),
                    "segment_id": getattr(entry, "segment_id", None),
                    "transcription_id": getattr(entry, "transcription_id", None),
                    "draft_id": getattr(entry, "draft_id", None),
                },
                "chunk_id": getattr(chunk, "chunk_id", None),
                "preview": getattr(span, "preview", None),
                "start": getattr(span, "start", None),
                "end": getattr(span, "end", None),
                "metadata": getattr(span, "metadata", {}) or {},
            }
        )
    return {
        "id": getattr(card, "id", ""),
        "lane": getattr(card, "lane", ""),
        "score": float(getattr(card, "score", 0.0) or 0.0),
        "title": getattr(card, "title", None),
        "provenance": getattr(card, "provenance", {}) or {},
        "spans": spans,
    }


def _summarize_path(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return f"artifact_open_unreadable:{path.name}"
    raw = raw.strip()
    if not raw:
        return "artifact_open_empty"
    try:
        parsed = json.loads(raw)
        keys = list(parsed.keys()) if isinstance(parsed, dict) else []
        if keys:
            return f"json_keys={','.join(str(k) for k in keys[:12])}"
        return "json_value_loaded"
    except Exception:
        return _summarize_text(raw)


def _repair_view_for_json_artifact(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    artifact_type = str(payload.get("artifact_type") or "").strip().lower()
    if artifact_type == "judge":
        graph_id = payload.get("graph_id")
        report = payload.get("report")
        if not isinstance(report, dict):
            return None
        gaps = report.get("gaps")
        warnings = report.get("warnings")
        return {
            "artifact_type": "judge",
            "graph_id": graph_id if isinstance(graph_id, str) else None,
            "top_gaps": _bounded_gap_repair_view(gaps, max_items=5),
            "warnings": _bounded_warnings_view(warnings, max_items=3),
        }
    if artifact_type == "compile":
        graph_id = payload.get("graph_id")
        return {
            "artifact_type": "compile",
            "graph_id": graph_id if isinstance(graph_id, str) else None,
            "top_gaps": _bounded_gap_repair_view(payload.get("gaps"), max_items=5),
            "warnings": _bounded_warnings_view(payload.get("warnings"), max_items=3),
        }
    if artifact_type == "ir":
        graph_candidate = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
        if not isinstance(graph_candidate, dict):
            return {"artifact_type": "ir", "parse_status": "missing_graph"}
        try:
            graph = FeatureGraph.model_validate(graph_candidate)
        except Exception as exc:
            return {
                "artifact_type": "ir",
                "parse_status": "invalid_graph",
                "error": _summarize_text(str(exc))[:240],
            }
        return {
            "artifact_type": "ir",
            "graph_id": graph.graph_id,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "georef_readiness": _georef_readiness_diagnostics(graph),
        }
    return None


def _bounded_gap_repair_view(raw_gaps: Any, *, max_items: int) -> list[dict[str, Any]]:
    if not isinstance(raw_gaps, list):
        return []
    out: list[dict[str, Any]] = []
    for gap in raw_gaps[:max_items]:
        if not isinstance(gap, dict):
            continue
        op_value = gap.get("operation") or gap.get("op_name") or gap.get("operation_name")
        feature_id = gap.get("feature_id") or gap.get("node_id")
        item = {
            "kind": gap.get("kind"),
            "operation": str(op_value)[:120] if op_value is not None else None,
            "feature_id": str(feature_id)[:120] if feature_id is not None else None,
            "severity": gap.get("severity"),
            "message": _summarize_text(str(gap.get("message") or ""))[:240],
        }
        guidance = _gap_rewrite_guidance(gap)
        if guidance:
            item.update(guidance)
        out.append(item)
    return out


def _bounded_warnings_view(raw_warnings: Any, *, max_items: int) -> list[str]:
    if not isinstance(raw_warnings, list):
        return []
    return [_summarize_text(str(item or ""))[:200] for item in raw_warnings[:max_items]]


def _gap_rewrite_guidance(gap: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(gap.get("kind") or "").strip().lower()
    reason_code = str(gap.get("reason_code") or "").strip().lower()
    operation = str(
        gap.get("operation") or gap.get("op_name") or gap.get("operation_name") or ""
    ).strip()
    message = str(gap.get("message") or "").strip()

    if kind == "unsupported_operation":
        op_key = operation.lower()
        if op_key == "traverse":
            return {
                "suggested_replacement_ops": ["LineStep", "Close"],
                "rewrite_hint": (
                    "Replace Traverse with a chain of LineStep ops (bearing+distance) and "
                    "use Close after the boundary path is constructed."
                )[:240],
            }
        if op_key == "pointfromreference":
            return {
                "suggested_replacement_ops": ["FeatureRef", "Annotation"],
                "rewrite_hint": (
                    "Do not treat PointFromReference as computable geometry. Represent it as a "
                    "semantic anchor/annotation with deed citation and defer spatial resolution."
                )[:240],
            }
        if op_key == "tiedpoint":
            return {
                "suggested_replacement_ops": ["Point", "Annotation"],
                "rewrite_hint": (
                    "Replace TiedPoint with direct Point geometry (schematic/local) and store tie "
                    "description details as annotation/metadata with deed citation."
                )[:240],
            }
        if op_key == "coursetraverse":
            return {
                "suggested_replacement_ops": ["LineString", "Annotation"],
                "rewrite_hint": (
                    "Replace CourseTraverse with direct LineString geometry (schematic) and keep "
                    "the course/bearing-distance sequence in metadata/annotation until Traverse lowering exists."
                )[:240],
            }
        if op_key == "metesbounds":
            return {
                "suggested_replacement_ops": ["CourseTraverse", "Close", "Annotation"],
                "rewrite_hint": (
                    "Represent metes-and-bounds as CourseTraverse.params.courses (bearing/distance list), "
                    "then Close the resulting curve; keep narrative details in annotation metadata."
                )[:240],
            }
        if op_key == "union":
            return {
                "suggested_replacement_ops": ["Collection", "Annotation"],
                "rewrite_hint": (
                    "Do not use geometric Union yet. Use Collection for semantic parcel grouping "
                    "or annotate grouping intent until boolean geometry support is implemented."
                )[:240],
            }
        if operation:
            return {
                "suggested_replacement_ops": ["LineStep", "Close"],
                "rewrite_hint": (
                    f"Operation '{operation}' is unsupported. Rewrite using supported core ops "
                    "where possible (often LineStep chain + Close) or encode as semantic annotation."
                )[:240],
            }

    if "precondition" in kind or "precondition" in reason_code or "precondition" in message.lower():
        return {
            "rewrite_hint": (
                "Fix upstream unsupported or invalid operands first, then re-run compile/judge "
                "before using dependent ops."
            )[:240],
        }

    return {}


def _summarize_text(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[:512]


def _summarize_rejected_graph(graph: dict[str, Any], *, error: str) -> dict[str, Any]:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    graph_id = graph.get("graph_id")
    return {
        "graph_id": str(graph_id)[:120] if graph_id is not None else None,
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
        "error": _summarize_text(error),
    }


def _read_str(raw: Any) -> str | None:
    if isinstance(raw, str):
        v = raw.strip()
        return v if v else None
    return None
