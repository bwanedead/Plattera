"""Concrete tool dependency implementations for step-driven kernel actions."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider
from feature_graph.artifacts import create_compile_artifact, create_judge_artifact
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
        return {
            "reason_codes": ["artifact_opened"],
            "summary": summary,
            "artifact_ref": artifact_ref,
        }


@dataclass
class DraftIRFilesystemProposer:
    """Persist deterministic draft-IR stubs as durable artifact refs."""

    def draft_ir(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        dossier_id = _read_str(inputs.get("dossier_id")) or "unknown"
        inline_graph = inputs.get("graph") if isinstance(inputs.get("graph"), dict) else None
        source_ref = _coerce_artifact_ref(inputs.get("hydrated_deed_artifact_ref"))
        if source_ref is None:
            source_ref = _coerce_artifact_ref(inputs.get("deed_text_artifact_ref"))
        if source_ref is None:
            source_ref = _coerce_artifact_ref(inputs.get("deed_artifact_ref"))

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


def _summarize_text(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[:512]


def _read_str(raw: Any) -> str | None:
    if isinstance(raw, str):
        v = raw.strip()
        return v if v else None
    return None
