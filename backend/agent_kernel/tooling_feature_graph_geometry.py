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


def _extract_plss_anchor_from_georef_payload(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if isinstance(payload.get("plss_anchor"), dict):
        return dict(payload["plss_anchor"])
    request = payload.get("request")
    if isinstance(request, dict) and isinstance(request.get("plss_anchor"), dict):
        return dict(request["plss_anchor"])
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




