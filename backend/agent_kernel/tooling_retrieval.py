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
from tooling.mapping.transcription_edit.apply import (
    apply_plan_to_sections,
    materialize_canonical_input,
)
from tooling.mapping.transcription_edit.contracts import (
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
from services.workflows.mapping.transcription_edit.persistence import TranscriptionEditPersistenceService
from tooling.mapping.transcription_edit.span_seeds import (
    build_transcript_span_seeds_artifact,
    load_transcript_text_for_seeds,
)
from tooling.mapping.transcription_edit.validators import run_validators
from services.llm.openai import OpenAIService

from .run_artifact import ArtifactRef, ValidationInline

logger = logging.getLogger(__name__)

from .tooling_artifacts import _persist_json_artifact, _read_str, _tool_refusal_result

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




