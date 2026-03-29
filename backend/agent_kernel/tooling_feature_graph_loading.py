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

from .tooling_artifacts import (
    _coerce_artifact_ref,
    _infer_dossier_id_for_agent_kernel_artifact,
    _infer_dossier_id_from_feature_graph_artifact_path,
    _infer_parent_artifact_ids,
    _persist_json_artifact,
    _persist_text_artifact,
    _read_str,
    _summarize_text,
    _tool_refusal_result,
)

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


def _bounded_validate_checks(checks: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in list(checks.keys())[:12]:
        value = checks.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)] = value
        else:
            out[str(key)] = _summarize_text(str(value))[:120]
    return out


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




