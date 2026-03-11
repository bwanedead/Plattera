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

from .tooling_feature_graph_diagnostics import (
    _georef_readiness_diagnostics,
    _graph_mapping_quality_diagnostics,
    _local_polygon_candidates,
    _mapping_quality_issues_from_georef_payload,
    _plss_anchor_candidates,
    _render_polygon_svg,
    _summarize_rejected_graph,
    _validator_allows_tie_anchored_override,
)
from .tooling_feature_graph_geometry import (
    _coerce_float_like,
    _coerce_int_like,
    _coerce_plss_number_direction,
    _coerce_xy_points,
    _compute_ring_bounds,
    _extract_bounds_from_georef_payload,
    _extract_geographic_polygon_ring_lonlat,
    _extract_linestring_points,
    _extract_plss_anchor,
    _extract_plss_anchor_from_georef_payload,
    _extract_polygon_ring,
    _extract_primary_local_polygon_vertices,
    _extract_tie_to_corner,
    _first_nonempty_str,
    _iter_node_text_fragments,
    _metadata_likely_pob,
    _node_is_marked_partial_for_mapping,
    _normalize_alt_plss_anchor_shape,
    _normalize_plss_direction,
    _normalize_state_value,
    _normalize_tie_direction,
    _normalize_tie_to_corner_shape,
    _plss_anchor_has_required_fields,
    _ring_is_closed,
    _strip_duplicate_closing_vertex,
)
from .tooling_feature_graph_loading import (
    _bounded_validate_checks,
    _coerce_artifact_ref,
    _extract_georeference_options,
    _infer_dossier_id_for_agent_kernel_artifact,
    _infer_dossier_id_from_feature_graph_artifact_path,
    _infer_dossier_id_from_ir_ref_inputs,
    _infer_parent_artifact_ids,
    _load_feature_graph_for_georeference,
    _load_feature_graph_from_inputs,
    _persist_json_artifact,
    _persist_text_artifact,
    _read_str,
    _resolve_dossier_id,
    _resolve_georeference_dossier_id,
    _tool_refusal_result,
)

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
