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

from .tooling_artifacts import _summarize_text
from .tooling_feature_graph_diagnostics import _georef_readiness_diagnostics

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
