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

from .tooling_transcript_image_helpers import (
    _bounded_float,
    _bounded_int,
    _build_transcript_image_verify_prompt,
    _coerce_artifact_ref,
    _coerce_crop_box,
    _coerce_image_verify_result,
    _coerce_image_verify_checks,
    _coerce_requested_crop_box,
    _create_image_evidence_artifacts,
    _encode_image_for_verification,
    _locate_image_evidence_region,
    _persist_json_artifact,
    _read_json_dict,
    _read_str,
    _resolve_transcript_source_image_path,
    _summarize_image_verify_results,
    _summarize_text,
    _tool_refusal_result,
)
from .tooling_transcript_image_runtime import _execute_explicit_image_evidence_mode

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
class TranscriptImageVerificationTool:
    """Verify transcript claims against the source deed image with optional zoom/crop."""

    service: OpenAIService = field(default_factory=OpenAIService)

    def verify_transcript_with_image(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        dossier_id = _read_str(inputs.get("dossier_id")) or "adhoc"
        source_ref = _read_str(
            inputs.get("source_transcript_ref")
            or inputs.get("tx_source_transcript_ref")
            or inputs.get("transcript_ref")
        )
        if source_ref is None:
            return _tool_refusal_result("tx_image_verify_missing_source_transcript")
        if not self.service.is_available() or getattr(self.service, "client", None) is None:
            return _tool_refusal_result("tx_image_verify_service_unavailable")

        requested_image_path = _read_str(inputs.get("image_path") or inputs.get("image_ref"))
        image_path = _resolve_transcript_source_image_path(
            dossier_id=dossier_id,
            source_transcript_ref=source_ref,
            requested_image_path=requested_image_path,
        )
        if image_path is None:
            return _tool_refusal_result("tx_image_verify_source_image_not_found")
        image_file = Path(image_path)
        if not image_file.exists():
            return _tool_refusal_result("tx_image_verify_source_image_not_found")

        model = _read_str(inputs.get("model")) or "gpt-5.2"
        mode = (_read_str(inputs.get("mode")) or "locate").strip().lower()
        if mode in {"inspection_reference", "select_region", "refine_region", "verify_region"}:
            return _execute_explicit_image_evidence_mode(
                service=self.service,
                inputs=inputs,
                dossier_id=dossier_id,
                source_ref=source_ref,
                image_file=image_file,
                model=model,
                mode=mode,
            )
        checks = _coerce_image_verify_checks(inputs)
        if not checks:
            return _tool_refusal_result("tx_image_verify_missing_checks")

        zoom_default = _bounded_float(inputs.get("zoom_factor"), default=2.2, minimum=1.0, maximum=6.0)
        results: list[dict[str, Any]] = []
        evidence_regions: list[dict[str, Any]] = []
        for index, check in enumerate(checks):
            check_id = _read_str(check.get("check_id")) or f"check_{index + 1}"
            query = _read_str(check.get("query")) or _read_str(check.get("message"))
            expected = _read_str(check.get("expected_text"))
            if not query:
                continue
            logger.info(
                "TX_IMAGE_VERIFY_CALL ► model=%s check_id=%s idx=%s expected=%s query=%s",
                model,
                check_id,
                index + 1,
                (expected or "n/a")[:80],
                query[:120],
            )
            decision_key = _read_str(check.get("decision_key"))
            zoom_factor = _bounded_float(check.get("zoom_factor"), default=zoom_default, minimum=1.0, maximum=6.0)
            expected_text = expected or None
            precomputed_region_ref = _coerce_artifact_ref(check.get("tx_image_evidence_region_ref") or check.get("image_evidence_region_ref"))
            precomputed_region_path = (
                Path(precomputed_region_ref.artifact_path)
                if isinstance(precomputed_region_ref, ArtifactRef)
                else None
            )
            locator_result = _locate_image_evidence_region(
                service=self.service,
                image_path=image_file,
                model=model,
                check_id=check_id,
                query=query,
                expected_text=expected_text,
                decision_key=decision_key,
                fallback_crop_box=_coerce_crop_box(check.get("crop_box")),
                precomputed_region_path=precomputed_region_path,
            )
            isolate = _create_image_evidence_artifacts(
                source_image_path=image_file,
                dossier_id=dossier_id,
                check_id=check_id,
                decision_key=decision_key,
                zoom_factor=zoom_factor,
                locator_result=locator_result,
            )
            evidence_regions.append(
                {
                    "check_id": check_id,
                    "decision_key": decision_key,
                    "status": str(locator_result.get("status") or "unclear"),
                    "confidence": str(locator_result.get("confidence") or "low"),
                    "reason": str(locator_result.get("reason") or "")[:240],
                    "crop_box": locator_result.get("crop_box"),
                    "context_crop_box": locator_result.get("context_crop_box"),
                    "tx_image_evidence_region_ref": (
                        isolate.get("tx_image_evidence_region_ref").model_dump(mode="json")
                        if isinstance(isolate.get("tx_image_evidence_region_ref"), ArtifactRef)
                        else None
                    ),
                    "tx_image_evidence_context_ref": (
                        isolate.get("tx_image_evidence_context_ref").model_dump(mode="json")
                        if isinstance(isolate.get("tx_image_evidence_context_ref"), ArtifactRef)
                        else None
                    ),
                }
            )
            verify_image_path = (
                Path(isolate.get("region_image_path"))
                if isinstance(isolate.get("region_image_path"), str) and str(isolate.get("region_image_path")).strip()
                else image_file
            )
            crop_box = _coerce_crop_box(locator_result.get("crop_box")) if verify_image_path == image_file else None
            verify_zoom_factor = zoom_factor if verify_image_path == image_file else 1.0
            image_b64, render_meta = _encode_image_for_verification(
                image_path=verify_image_path,
                crop_box=crop_box,
                zoom_factor=verify_zoom_factor,
            )
            prompt = _build_transcript_image_verify_prompt(
                check_id=check_id,
                query=query,
                expected_text=expected,
            )
            response = self.service.call_vision(
                prompt=prompt,
                image_data=image_b64,
                model=model,
                json_mode="relaxed",
                max_tokens=1600,
                detail="high",
            )
            result_item = _coerce_image_verify_result(
                check_id=check_id,
                query=query,
                expected_text=expected,
                response=response,
            )
            result_item["render_meta"] = render_meta
            result_item["decision_key"] = decision_key
            result_item["locator"] = locator_result
            result_item["tx_image_evidence_region_ref"] = (
                isolate.get("tx_image_evidence_region_ref").model_dump(mode="json")
                if isinstance(isolate.get("tx_image_evidence_region_ref"), ArtifactRef)
                else None
            )
            result_item["tx_image_evidence_context_ref"] = (
                isolate.get("tx_image_evidence_context_ref").model_dump(mode="json")
                if isinstance(isolate.get("tx_image_evidence_context_ref"), ArtifactRef)
                else None
            )
            results.append(result_item)
            logger.info(
                "TX_IMAGE_VERIFY_RESULT ► model=%s check_id=%s status=%s confidence=%s observed=%s",
                model,
                check_id,
                result_item.get("status"),
                result_item.get("confidence"),
                _summarize_text(str(result_item.get("observed_text") or ""))[:120],
            )

        if not results:
            return _tool_refusal_result("tx_image_verify_missing_checks")

        summary = _summarize_image_verify_results(results)
        payload = {
            "artifact_type": "transcript_image_verification",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dossier_id": dossier_id,
            "source_transcript_ref": source_ref,
            "image_path": str(image_file),
            "model": model,
            "summary": summary,
            "results": results,
            "image_evidence_regions": evidence_regions,
        }
        artifact_ref = _persist_json_artifact(
            category="transcript_image_verify",
            dossier_id=dossier_id,
            payload=payload,
        )
        first_region_ref = next(
            (
                item.get("tx_image_evidence_region_ref")
                for item in evidence_regions
                if isinstance(item, dict) and isinstance(item.get("tx_image_evidence_region_ref"), dict)
            ),
            None,
        )
        first_context_ref = next(
            (
                item.get("tx_image_evidence_context_ref")
                for item in evidence_regions
                if isinstance(item, dict) and isinstance(item.get("tx_image_evidence_context_ref"), dict)
            ),
            None,
        )
        compact_results = []
        for item in results[:8]:
            compact_results.append(
                {
                    "check_id": item.get("check_id"),
                    "status": item.get("status"),
                    "decision_key": item.get("decision_key"),
                    "confidence": item.get("confidence"),
                    "observed_text": _summarize_text(str(item.get("observed_text") or ""))[:220],
                    "reason": _summarize_text(str(item.get("reason") or ""))[:220],
                    "locator_status": str((item.get("locator") or {}).get("status") or "unclear"),
                    "tx_image_evidence_region_ref": item.get("tx_image_evidence_region_ref"),
                    "tx_image_evidence_context_ref": item.get("tx_image_evidence_context_ref"),
                }
            )
        return {
            "artifact_ref": artifact_ref,
            "reason_codes": ["tx_image_verified"],
            "tx_source_transcript_ref": source_ref,
            "tx_image_path": str(image_file),
            "tx_image_verify_summary": summary,
            "tx_image_verify_results": compact_results,
            "tx_image_evidence_regions": evidence_regions[:8],
            "tx_image_evidence_region_ref": first_region_ref,
            "tx_image_evidence_context_ref": first_context_ref,
        }
