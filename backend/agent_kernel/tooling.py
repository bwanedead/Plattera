"""Concrete tool dependency implementations for step-driven kernel actions."""

from __future__ import annotations

import json
import os
import hashlib
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root
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

from .run_artifact import ArtifactRef


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

        requested_spans, failure = _resolve_requested_text_spans(inputs=inputs, deed_text=text)
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
        return {"artifact_ref": None, "reason_codes": ["spans_opened"], "spans": out_spans}


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


def _tool_refusal_result(reason_code: str, *, missing_inputs: list[str] | None = None) -> dict[str, Any]:
    return {
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


def _resolve_requested_text_spans(*, inputs: Mapping[str, Any], deed_text: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    raw_spans = inputs.get("spans")
    if isinstance(raw_spans, list):
        items: list[dict[str, Any]] = []
        for raw in raw_spans:
            if not isinstance(raw, dict):
                return [], _tool_refusal_result("open_text_spans_invalid_range")
            start_char = raw.get("start_char")
            end_char = raw.get("end_char")
            if not isinstance(start_char, int) or not isinstance(end_char, int):
                return [], _tool_refusal_result("open_text_spans_invalid_range")
            items.append(
                {
                    "span_id": _read_str(raw.get("span_id")),
                    "start_char": start_char,
                    "end_char": end_char,
                    "fingerprint_ok": True,
                }
            )
        return items, None

    raw_anchors = inputs.get("anchors")
    if isinstance(raw_anchors, list) and raw_anchors:
        return _resolve_anchor_requested_spans(raw_anchors=raw_anchors, deed_text=deed_text)

    raw_span_ids = inputs.get("span_ids")
    if not isinstance(raw_span_ids, list) or not raw_span_ids:
        return [], _tool_refusal_result("open_text_spans_invalid_range")
    index = _load_span_index(inputs.get("deed_span_index_ref"))
    if not isinstance(index, dict):
        return [], _tool_refusal_result("open_text_spans_invalid_range")
    deed_fp = index.get("deed_fingerprint")
    if not isinstance(deed_fp, dict) or not _fingerprint_matches_dict(expected=deed_fp, actual=_deed_fingerprint(deed_text)):
        return [], _tool_refusal_result("open_text_spans_fingerprint_mismatch")
    spans = index.get("spans")
    if not isinstance(spans, list):
        return [], _tool_refusal_result("open_text_spans_invalid_range")
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
            return [], _tool_refusal_result("open_text_spans_invalid_range")
        start_char = span.get("start_char")
        end_char = span.get("end_char")
        if not isinstance(start_char, int) or not isinstance(end_char, int):
            return [], _tool_refusal_result("open_text_spans_invalid_range")
        items.append(
            {
                "span_id": sid,
                "start_char": start_char,
                "end_char": end_char,
                "fingerprint_ok": True,
            }
        )
    return items, None


def _resolve_anchor_requested_spans(
    *,
    raw_anchors: list[Any],
    deed_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    normalized_text, norm_to_orig = _normalize_text_with_index_map(deed_text)
    items: list[dict[str, Any]] = []
    for raw in raw_anchors:
        if not isinstance(raw, dict):
            return [], _tool_refusal_result("open_text_spans_anchor_not_found")
        start_anchor_raw = _read_str(raw.get("start_anchor"))
        end_anchor_raw = _read_str(raw.get("end_anchor"))
        if not start_anchor_raw or not end_anchor_raw:
            return [], _tool_refusal_result("open_text_spans_anchor_not_found")
        start_anchor = _normalize_text_simple(start_anchor_raw)
        end_anchor = _normalize_text_simple(end_anchor_raw)
        if not start_anchor or not end_anchor:
            return [], _tool_refusal_result("open_text_spans_anchor_not_found")
        occurrence = raw.get("occurrence")
        start_matches = _find_all_occurrences(normalized_text, start_anchor)
        if not start_matches:
            return [], _tool_refusal_result("open_text_spans_anchor_not_found")
        selected_start_match = None
        if isinstance(occurrence, int):
            idx = occurrence - 1
            if idx < 0 or idx >= len(start_matches):
                return [], _tool_refusal_result("open_text_spans_anchor_not_found")
            selected_start_match = start_matches[idx]
        elif len(start_matches) == 1:
            selected_start_match = start_matches[0]
        else:
            return [], _tool_refusal_with_candidates(
                "open_text_spans_anchor_ambiguous",
                normalized_text=normalized_text,
                norm_to_orig=norm_to_orig,
                matches=start_matches,
                match_len=len(start_anchor),
            )
        assert selected_start_match is not None

        end_matches = _find_all_occurrences(normalized_text, end_anchor)
        end_after = [m for m in end_matches if m >= selected_start_match]
        if not end_after:
            return [], _tool_refusal_result("open_text_spans_anchor_not_found")
        selected_end_match = end_after[0]
        if selected_end_match < selected_start_match:
            return [], _tool_refusal_result("open_text_spans_anchor_invalid_order")

        start_char = _norm_pos_to_orig_start(norm_to_orig, selected_start_match)
        end_char_exclusive = _norm_pos_to_orig_end_exclusive(norm_to_orig, selected_end_match + len(end_anchor) - 1)
        if start_char is None or end_char_exclusive is None or end_char_exclusive <= start_char:
            return [], _tool_refusal_result("open_text_spans_anchor_invalid_order")
        items.append(
            {
                "span_id": _read_str(raw.get("span_id")),
                "start_char": start_char,
                "end_char": end_char_exclusive,
                "fingerprint_ok": True,
            }
        )
    return items, None


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
    graph_dossier = _read_str((graph.metadata or {}).get("dossier_id"))
    if graph_dossier:
        return graph_dossier
    return "unknown"


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
