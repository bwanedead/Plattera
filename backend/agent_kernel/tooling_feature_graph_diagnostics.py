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

from .tooling_artifacts import _read_str, _summarize_text
from .tooling_feature_graph_geometry import (
    _extract_linestring_points,
    _extract_polygon_ring,
    _extract_plss_anchor,
    _extract_primary_local_polygon_vertices,
    _extract_tie_to_corner,
    _normalize_alt_plss_anchor_shape,
    _plss_anchor_has_required_fields,
)

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
