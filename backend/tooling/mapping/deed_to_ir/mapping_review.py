"""Compact mapping review packet for deed-to-IR submit and hydrate flows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from feature_graph.artifact_refs import build_feature_graph_artifact_ref, parse_feature_graph_artifact_ref
from feature_graph.artifacts import CompileArtifact, IRArtifact
from feature_graph.mapping_artifacts import MappingArtifact
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .mapping_sanity import (
    attach_sanity_review_to_mapping_review,
    compact_sanity_review_for_projection,
    render_sanity_review_timeline_lines,
)

MAX_RECOMMENDED_REVIEW_REFS = 3


def build_mapping_review(
    *,
    mapping_artifact_ref: str,
    source_ir_artifact_ref: str,
    compile_artifact_ref: str,
    judge_artifact_ref: str,
    geometry_ref: str,
    clean_render_ref: str,
    control_render_ref: str,
    coordinate_space: str,
    compiled_feature_count: int,
    rendered_feature_count: int,
    skipped_feature_count: int,
    warning_count: int,
    compile_gap_count: int,
    judge_gap_count: int,
    world_bbox: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a path-free mapping review packet for agent inspection and publish handoff."""
    recommended_publish_refs = {
        "mapping_artifact_ref": mapping_artifact_ref,
        "expected_ir_artifact_ref": source_ir_artifact_ref,
    }
    recommended_review_refs = [
        mapping_artifact_ref,
        control_render_ref,
        geometry_ref,
    ][:MAX_RECOMMENDED_REVIEW_REFS]
    review: dict[str, Any] = {
        "mapping_artifact_ref": mapping_artifact_ref,
        "source_ir_artifact_ref": source_ir_artifact_ref,
        "compile_artifact_ref": compile_artifact_ref,
        "judge_artifact_ref": judge_artifact_ref,
        "geometry_ref": geometry_ref,
        "clean_render_ref": clean_render_ref,
        "control_render_ref": control_render_ref,
        "coordinate_space": coordinate_space,
        "compiled_feature_count": compiled_feature_count,
        "rendered_feature_count": rendered_feature_count,
        "skipped_feature_count": skipped_feature_count,
        "warning_count": warning_count,
        "compile_gap_count": compile_gap_count,
        "judge_gap_count": judge_gap_count,
        "recommended_review_refs": recommended_review_refs,
        "recommended_publish_refs": recommended_publish_refs,
    }
    if isinstance(world_bbox, Mapping) and world_bbox:
        review["world_bbox"] = dict(world_bbox)
    return review


def build_mapping_review_from_mapping_artifact(
    *,
    mapping: MappingArtifact,
    mapping_artifact_ref: str,
    compiled_feature_count: int,
    rendered_feature_count: int,
    skipped_feature_count: int,
    compile_gap_count: int,
    judge_gap_count: int,
) -> dict[str, Any]:
    return build_mapping_review(
        mapping_artifact_ref=mapping_artifact_ref,
        source_ir_artifact_ref=mapping.source_ir_artifact_ref,
        compile_artifact_ref=mapping.compile_artifact_ref,
        judge_artifact_ref=mapping.judge_artifact_ref,
        geometry_ref=mapping.geometry.ref,
        clean_render_ref=mapping.clean_render.ref,
        control_render_ref=mapping.control_render.ref,
        coordinate_space=mapping.coordinate_space,
        compiled_feature_count=compiled_feature_count,
        rendered_feature_count=rendered_feature_count,
        skipped_feature_count=skipped_feature_count,
        warning_count=mapping.warning_count,
        compile_gap_count=compile_gap_count,
        judge_gap_count=judge_gap_count,
        world_bbox=mapping.world_bbox.model_dump(mode="json"),
    )


def build_mapping_review_from_persisted_mapping(
    *,
    mapping_raw: Mapping[str, Any],
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    operand_evidence_index: dict[str, list[str]] | None = None,
) -> dict[str, Any] | None:
    """Rebuild mapping_review from a stored mapping artifact payload."""
    if str(mapping_raw.get("artifact_type") or "") != "mapping":
        return None
    try:
        mapping = MappingArtifact.model_validate(dict(mapping_raw))
    except Exception:
        return None
    compile_gap, judge_gap, compiled = _evaluation_counts_from_mapping_artifact(
        persistence=persistence,
        dossier_id=dossier_id,
        mapping_raw=mapping_raw,
    )
    rendered = len(mapping.rendered_feature_ids)
    if rendered <= 0 and isinstance(mapping.geometry.rendered_feature_count, int):
        rendered = mapping.geometry.rendered_feature_count
    skipped = len(mapping.skipped_features)
    if skipped <= 0 and isinstance(mapping.geometry.skipped_feature_count, int):
        skipped = mapping.geometry.skipped_feature_count
    mapping_ref = build_feature_graph_artifact_ref("mapping", mapping.artifact_id)
    review = build_mapping_review_from_mapping_artifact(
        mapping=mapping,
        mapping_artifact_ref=mapping_ref,
        compiled_feature_count=compiled,
        rendered_feature_count=rendered,
        skipped_feature_count=skipped,
        compile_gap_count=compile_gap,
        judge_gap_count=judge_gap,
    )
    graph, compile_artifact = _load_graph_and_compile_for_mapping(
        persistence=persistence,
        dossier_id=dossier_id,
        mapping=mapping,
        mapping_raw=mapping_raw,
    )
    if graph is not None and compile_artifact is not None:
        attach_sanity_review_to_mapping_review(
            review,
            graph=graph,
            compile_artifact=compile_artifact,
            operand_evidence_index=operand_evidence_index,
        )
    return review


def compact_mapping_review_for_projection(
    mapping_review: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Bounded carry-forward lane for tool-result slices / prompt projection."""
    if not isinstance(mapping_review, Mapping) or not mapping_review:
        return None
    compact: dict[str, Any] = {
        "mapping_artifact_ref": mapping_review.get("mapping_artifact_ref"),
        "source_ir_artifact_ref": mapping_review.get("source_ir_artifact_ref"),
        "control_render_ref": mapping_review.get("control_render_ref"),
        "geometry_ref": mapping_review.get("geometry_ref"),
        "compile_gap_count": mapping_review.get("compile_gap_count"),
        "judge_gap_count": mapping_review.get("judge_gap_count"),
        "skipped_feature_count": mapping_review.get("skipped_feature_count"),
        "recommended_publish_refs": mapping_review.get("recommended_publish_refs"),
    }
    sanity_compact = compact_sanity_review_for_projection(mapping_review.get("sanity_review"))
    if sanity_compact is not None:
        compact["sanity_review"] = sanity_compact
    filtered = {key: value for key, value in compact.items() if value is not None}
    return filtered or None


def render_mapping_review_timeline_lines(
    mapping_review: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(mapping_review, Mapping) or not mapping_review:
        return []
    lines = [f"{indent}mapping_review:"]
    for label, key in (
        ("mapping", "mapping_artifact_ref"),
        ("source_ir", "source_ir_artifact_ref"),
        ("control", "control_render_ref"),
        ("geometry", "geometry_ref"),
    ):
        value = mapping_review.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{indent}  {label}: {value.strip()}")
    lines.append(
        "{indent}  counts: compiled={compiled} rendered={rendered} skipped={skipped} "
        "warnings={warnings} compile_gaps={compile_gaps} judge_gaps={judge_gaps}".format(
            indent=indent,
            compiled=mapping_review.get("compiled_feature_count", 0),
            rendered=mapping_review.get("rendered_feature_count", 0),
            skipped=mapping_review.get("skipped_feature_count", 0),
            warnings=mapping_review.get("warning_count", 0),
            compile_gaps=mapping_review.get("compile_gap_count", 0),
            judge_gaps=mapping_review.get("judge_gap_count", 0),
        )
    )
    publish = mapping_review.get("recommended_publish_refs")
    if isinstance(publish, Mapping):
        mapping_ref = publish.get("mapping_artifact_ref")
        expected_ir = publish.get("expected_ir_artifact_ref")
        if mapping_ref or expected_ir:
            lines.append(
                f"{indent}  publish: mapping_artifact_ref={mapping_ref or ''} "
                f"expected_ir_artifact_ref={expected_ir or ''}"
            )
    lines.extend(render_sanity_review_timeline_lines(mapping_review.get("sanity_review"), indent=indent))
    return lines


def render_mapping_review_tool_output(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    """Render mapping_review from submit outputs or hydrate result rows."""
    if not isinstance(outputs, Mapping):
        return []
    lines: list[str] = []
    top_level = outputs.get("mapping_review")
    if isinstance(top_level, Mapping):
        lines.extend(render_mapping_review_timeline_lines(top_level, indent=indent))
    results = outputs.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, Mapping):
                continue
            nested = item.get("mapping_review")
            if not isinstance(nested, Mapping):
                continue
            ref = item.get("ref_id") or item.get("artifact_ref")
            if isinstance(ref, str) and ref.strip():
                lines.append(f"{indent}mapping_review ({ref.strip()}):")
                lines.extend(render_mapping_review_timeline_lines(nested, indent=f"{indent}  "))
            else:
                lines.extend(render_mapping_review_timeline_lines(nested, indent=indent))
    return lines


def _evaluation_counts_from_mapping_artifact(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    mapping_raw: Mapping[str, Any],
) -> tuple[int, int, int]:
    compile_gap_count = 0
    judge_gap_count = 0
    compiled_feature_count = 0
    compile_id = str(mapping_raw.get("compile_artifact_id") or "")
    judge_id = str(mapping_raw.get("judge_artifact_id") or "")
    if compile_id:
        compile_raw = persistence.get_artifact(dossier_id, compile_id)
        if isinstance(compile_raw, Mapping):
            gaps = compile_raw.get("gaps")
            if isinstance(gaps, list):
                compile_gap_count = len(gaps)
            compiled = compile_raw.get("compiled_features")
            if isinstance(compiled, Mapping):
                compiled_feature_count = len(compiled)
    if judge_id:
        judge_raw = persistence.get_artifact(dossier_id, judge_id)
        if isinstance(judge_raw, Mapping):
            report = judge_raw.get("report")
            if isinstance(report, Mapping):
                gaps = report.get("gaps")
                if isinstance(gaps, list):
                    judge_gap_count = len(gaps)
    return compile_gap_count, judge_gap_count, compiled_feature_count


def _load_graph_and_compile_for_mapping(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    mapping: MappingArtifact,
    mapping_raw: Mapping[str, Any],
) -> tuple[Any | None, CompileArtifact | None]:
    compile_id = str(mapping_raw.get("compile_artifact_id") or mapping.compile_artifact_id or "").strip()
    if compile_id.startswith("feature_graph:compile:"):
        try:
            _, compile_id = parse_feature_graph_artifact_ref(compile_id)
        except ValueError:
            compile_id = ""
    compile_raw = persistence.get_artifact(dossier_id, compile_id) if compile_id else None
    compile_artifact: CompileArtifact | None = None
    if isinstance(compile_raw, Mapping):
        try:
            compile_artifact = CompileArtifact.model_validate(dict(compile_raw))
        except Exception:
            compile_artifact = None

    source_ir_ref = str(mapping.source_ir_artifact_ref or "").strip()
    graph = None
    if source_ir_ref.startswith("feature_graph:ir:"):
        try:
            _, ir_id = parse_feature_graph_artifact_ref(source_ir_ref)
            ir_raw = persistence.get_artifact(dossier_id, ir_id)
            if isinstance(ir_raw, Mapping):
                graph = IRArtifact.model_validate(dict(ir_raw)).graph
        except Exception:
            graph = None
    return graph, compile_artifact
