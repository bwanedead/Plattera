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
    _read_json_dict,
    _read_str,
    _tool_refusal_result,
)
from .tooling_corpus import _resolve_deed_ref

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


def _bounded_float(raw: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, value))
