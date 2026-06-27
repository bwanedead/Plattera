"""Draft IR lifecycle helpers: versioning, evaluation feedback, and carry-forward lanes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from feature_graph.artifact_refs import FeatureGraphArtifactRefError, parse_feature_graph_artifact_ref
from feature_graph.models import FeatureGraph, FeatureKind
from services.feature_graph.feature_graph_evaluation_service import (
    FeatureGraphEvaluationArtifacts,
    FeatureGraphEvaluationService,
    PersistedCompileOutcome,
    PersistedJudgeOutcome,
)
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

MAX_COMPILE_GAPS_IN_FEEDBACK = 8
MAX_JUDGE_FINDINGS_IN_FEEDBACK = 8
MAX_DRAFT_REPAIR_ITEMS = 12
MAX_DRAFT_NODE_SUMMARY = 24
MAX_DRAFT_EDGE_SUMMARY = 24
MAX_EVALUATION_WARNING_MESSAGE_CHARS = 240


def stable_draft_artifact_id(graph_id: str, draft_sequence_index: int) -> str:
    """Allocate a versioned draft artifact id from stable logical graph_id."""
    base = _sanitize_graph_id_for_artifact(graph_id)
    if draft_sequence_index < 0:
        draft_sequence_index = 0
    return f"{base}_v{draft_sequence_index}"


def _sanitize_graph_id_for_artifact(graph_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(graph_id or "")).strip("_")
    return (cleaned[:120] or "graph")


def load_base_draft_artifact(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    base_draft_ref: str,
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Load prior draft IR artifact from base_draft_ref; return (artifact, error_code)."""
    try:
        artifact_type, artifact_id = parse_feature_graph_artifact_ref(base_draft_ref)
    except FeatureGraphArtifactRefError:
        return None, "base_draft_ref_invalid"
    if artifact_type != "ir":
        return None, "base_draft_ref_not_ir"
    raw = persistence.get_artifact(dossier_id, artifact_id)
    if not isinstance(raw, Mapping):
        return None, "base_draft_ref_not_found"
    return raw, None


def prior_graph_id_from_artifact(raw: Mapping[str, Any]) -> str:
    graph = raw.get("graph")
    if isinstance(graph, Mapping):
        value = graph.get("graph_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    source_meta = raw.get("source_metadata")
    if isinstance(source_meta, Mapping):
        value = source_meta.get("graph_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _artifact_graph_id(raw)


def prior_draft_sequence_index_from_artifact(prior_artifact: Mapping[str, Any]) -> int:
    source_meta = prior_artifact.get("source_metadata")
    if isinstance(source_meta, Mapping):
        prior = source_meta.get("draft_sequence_index")
        if isinstance(prior, int) and prior >= 0:
            return prior
    return 0


def resolve_draft_sequence_from_base(
    prior_artifact: Mapping[str, Any],
) -> int:
    """Return next index after base artifact only — prefer resolve_next_draft_sequence_index."""
    return prior_draft_sequence_index_from_artifact(prior_artifact) + 1


def max_draft_sequence_index_for_graph(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    graph_id: str,
) -> int:
    """Highest draft_sequence_index persisted for graph_id, or -1 when none."""
    highest = -1
    for entry in persistence.list_artifacts(dossier_id=dossier_id, artifact_type="ir"):
        raw = persistence.get_artifact(dossier_id, str(entry.get("artifact_id") or ""))
        if not isinstance(raw, Mapping):
            continue
        if _artifact_graph_id(raw) != graph_id:
            continue
        source_meta = raw.get("source_metadata")
        if isinstance(source_meta, Mapping):
            prior = source_meta.get("draft_sequence_index")
            if isinstance(prior, int) and prior >= 0:
                highest = max(highest, prior)
                continue
        artifact_id = str(raw.get("artifact_id") or entry.get("artifact_id") or "")
        parsed = _parse_draft_sequence_index_from_artifact_id(artifact_id, graph_id)
        if parsed is not None:
            highest = max(highest, parsed)
    return highest


def resolve_next_draft_sequence_index(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    graph_id: str,
    base_prior_index: int | None = None,
) -> int:
    """Allocate the next append-only draft index, never reusing an existing sequence slot."""
    existing_max = max_draft_sequence_index_for_graph(
        persistence=persistence,
        dossier_id=dossier_id,
        graph_id=graph_id,
    )
    if base_prior_index is not None:
        return max(base_prior_index + 1, existing_max + 1)
    return existing_max + 1


def _parse_draft_sequence_index_from_artifact_id(artifact_id: str, graph_id: str) -> int | None:
    prefix = f"{_sanitize_graph_id_for_artifact(graph_id)}_v"
    if not artifact_id.startswith(prefix):
        return None
    suffix = artifact_id[len(prefix) :]
    if suffix.isdigit():
        return int(suffix)
    return None


def resolve_draft_sequence_index(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    graph_id: str,
    artifact_id: str | None = None,
) -> int:
    """Return the next draft sequence index for a dossier + graph_id (mechanical count)."""
    if artifact_id:
        existing = persistence.get_artifact(dossier_id, artifact_id)
        if isinstance(existing, Mapping):
            meta = existing.get("source_metadata")
            if isinstance(meta, Mapping):
                prior = meta.get("draft_sequence_index")
                if isinstance(prior, int) and prior >= 0:
                    return prior + 1
    count = 0
    for entry in persistence.list_artifacts(dossier_id=dossier_id, artifact_type="ir"):
        raw = persistence.get_artifact(dossier_id, str(entry.get("artifact_id") or ""))
        if not isinstance(raw, Mapping):
            continue
        graph = raw.get("graph") if isinstance(raw.get("graph"), Mapping) else {}
        if str(graph.get("graph_id") or "") != graph_id:
            continue
        if artifact_id and str(raw.get("artifact_id") or "") == artifact_id:
            continue
        count += 1
    return count


def draft_version_label(sequence_index: int) -> str:
    if sequence_index < 0:
        sequence_index = 0
    return f"v{sequence_index}"


def build_draft_source_metadata(
    *,
    graph_id: str,
    draft_sequence_index: int,
) -> dict[str, Any]:
    return {
        "graph_id": graph_id,
        "draft_sequence_index": draft_sequence_index,
        "draft_version": draft_version_label(draft_sequence_index),
        "is_draft": True,
    }


def run_draft_compile_judge(
    *,
    evaluation: FeatureGraphEvaluationService,
    ir_artifact: Any,
    dossier_id: str,
) -> tuple[FeatureGraphEvaluationArtifacts | None, dict[str, Any] | None]:
    """Run compile+judge after draft save; return artifacts or structured warning."""
    try:
        return evaluation.compile_and_judge_ir(ir_artifact=ir_artifact, dossier_id=dossier_id), None
    except Exception as exc:
        message = str(exc).strip() or "compile_judge_evaluation_failed"
        if len(message) > MAX_EVALUATION_WARNING_MESSAGE_CHARS:
            message = message[: MAX_EVALUATION_WARNING_MESSAGE_CHARS - 1].rstrip() + "…"
        return None, {
            "reason_code": "compile_judge_evaluation_failed",
            "retryable": False,
            "message": message,
        }


def compute_draft_structural_metrics(graph: FeatureGraph) -> dict[str, Any]:
    """Mechanical draft structure counts — no deed-correctness inference."""
    geometry_count = 0
    op_expr_count = 0
    feature_ref_count = 0
    renderable_count = 0
    unknown_count = 0

    for node in graph.nodes:
        if node.kind == FeatureKind.UNKNOWN:
            unknown_count += 1
        has_geometry = node.geometry is not None
        has_op_expr = node.op_expr is not None
        has_feature_ref = node.feature_ref is not None
        if has_geometry:
            geometry_count += 1
        if has_op_expr:
            op_expr_count += 1
        if has_feature_ref:
            feature_ref_count += 1
        if has_geometry or has_op_expr or has_feature_ref:
            renderable_count += 1

    link_count = _count_source_entity_links(graph)
    placeholder_only_graph = (
        len(graph.nodes) > 0
        and renderable_count == 0
        and all(node.kind == FeatureKind.UNKNOWN for node in graph.nodes)
    )
    return {
        "node_count": len(graph.nodes),
        "unknown_node_count": unknown_count,
        "renderable_feature_count": renderable_count,
        "geometry_feature_count": geometry_count,
        "op_expr_feature_count": op_expr_count,
        "feature_ref_count": feature_ref_count,
        "edge_count": len(graph.edges),
        "source_entity_link_count": link_count,
        "placeholder_only_graph": placeholder_only_graph,
    }


def build_evaluation_feedback(
    *,
    compile_outcome: PersistedCompileOutcome | None,
    judge_outcome: PersistedJudgeOutcome | None,
    structural_metrics: Mapping[str, Any] | None = None,
    graph: FeatureGraph | None = None,
) -> dict[str, Any]:
    compile_gaps = _bound_compile_gaps(compile_outcome)
    judge_findings = _bound_judge_findings(judge_outcome)
    draft_repair_items = build_draft_repair_items(
        graph=graph,
        compile_gaps=compile_gaps,
        judge_findings=judge_findings,
    ) if graph is not None else []
    evaluation_succeeded = compile_outcome is not None and judge_outcome is not None
    compile_gap_count = compile_outcome.gap_count if compile_outcome is not None else None
    judge_finding_count = judge_outcome.gap_count if judge_outcome is not None else None
    metrics = dict(structural_metrics or {})
    mechanically_mappable_candidate = (
        evaluation_succeeded
        and compile_outcome.gap_count == 0
        and judge_outcome.gap_count == 0
    )
    mapping_submission_ready_candidate = (
        evaluation_succeeded
        and compile_outcome.gap_count == 0
        and judge_outcome.gap_count == 0
        and not metrics.get("placeholder_only_graph", True)
        and int(metrics.get("renderable_feature_count") or 0) > 0
    )
    return {
        "compile_artifact_ref": compile_outcome.artifact_ref if compile_outcome else None,
        "judge_artifact_ref": judge_outcome.artifact_ref if judge_outcome else None,
        "working_compile_ref": compile_outcome.artifact_ref if compile_outcome else None,
        "working_judge_ref": judge_outcome.artifact_ref if judge_outcome else None,
        "compile_gap_count": compile_gap_count,
        "judge_finding_count": judge_finding_count,
        "compile_gaps": compile_gaps,
        "judge_findings": judge_findings,
        "draft_repair_items": draft_repair_items,
        "mechanically_mappable_candidate": mechanically_mappable_candidate,
        "mapping_submission_ready_candidate": mapping_submission_ready_candidate,
        **metrics,
    }


def build_current_draft_ir(
    *,
    graph: FeatureGraph,
    ir_artifact_ref: str,
    draft_version: str,
    draft_sequence_index: int,
    evaluation_feedback: Mapping[str, Any],
    evaluation_warning: Mapping[str, Any] | None = None,
    structural_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = dict(structural_metrics or compute_draft_structural_metrics(graph))
    payload: dict[str, Any] = {
        "draft_ir_ref": ir_artifact_ref,
        "ir_artifact_ref": ir_artifact_ref,
        "working_draft_ref": ir_artifact_ref,
        "draft_version": draft_version,
        "draft_sequence_index": draft_sequence_index,
        "is_draft": True,
        "graph_id": graph.graph_id,
        "nodes": _summarize_nodes(graph),
        "edges": _summarize_edges(graph),
        "compile_artifact_ref": evaluation_feedback.get("compile_artifact_ref"),
        "judge_artifact_ref": evaluation_feedback.get("judge_artifact_ref"),
        "compile_gap_count": evaluation_feedback.get("compile_gap_count", 0),
        "judge_finding_count": evaluation_feedback.get("judge_finding_count", 0),
        "mechanically_mappable_candidate": evaluation_feedback.get("mechanically_mappable_candidate"),
        "mapping_submission_ready_candidate": evaluation_feedback.get(
            "mapping_submission_ready_candidate"
        ),
        "compile_gaps": evaluation_feedback.get("compile_gaps") or [],
        "judge_findings": evaluation_feedback.get("judge_findings") or [],
        "draft_repair_items": evaluation_feedback.get("draft_repair_items") or [],
        **metrics,
    }
    if evaluation_warning:
        payload["evaluation_warning"] = dict(evaluation_warning)
    return payload


def compact_current_draft_ir_for_projection(
    current_draft_ir: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Bounded carry-forward lane for tool-result slices / prompt projection."""
    if not isinstance(current_draft_ir, Mapping) or not current_draft_ir:
        return None
    nodes = current_draft_ir.get("nodes")
    edges = current_draft_ir.get("edges")
    compile_gaps = current_draft_ir.get("compile_gaps")
    judge_findings = current_draft_ir.get("judge_findings")
    draft_repair_items = current_draft_ir.get("draft_repair_items")
    summary: dict[str, Any] = {
        "draft_ir_ref": current_draft_ir.get("draft_ir_ref"),
        "working_draft_ref": current_draft_ir.get("working_draft_ref")
        or current_draft_ir.get("draft_ir_ref"),
        "draft_version": current_draft_ir.get("draft_version"),
        "graph_id": current_draft_ir.get("graph_id"),
        "node_count": current_draft_ir.get("node_count"),
        "edge_count": current_draft_ir.get("edge_count"),
        "unknown_node_count": current_draft_ir.get("unknown_node_count"),
        "renderable_feature_count": current_draft_ir.get("renderable_feature_count"),
        "geometry_feature_count": current_draft_ir.get("geometry_feature_count"),
        "op_expr_feature_count": current_draft_ir.get("op_expr_feature_count"),
        "feature_ref_count": current_draft_ir.get("feature_ref_count"),
        "source_entity_link_count": current_draft_ir.get("source_entity_link_count"),
        "placeholder_only_graph": current_draft_ir.get("placeholder_only_graph"),
        "compile_artifact_ref": current_draft_ir.get("compile_artifact_ref"),
        "judge_artifact_ref": current_draft_ir.get("judge_artifact_ref"),
        "compile_gap_count": current_draft_ir.get("compile_gap_count"),
        "judge_finding_count": current_draft_ir.get("judge_finding_count"),
        "mechanically_mappable_candidate": current_draft_ir.get("mechanically_mappable_candidate"),
        "mapping_submission_ready_candidate": current_draft_ir.get(
            "mapping_submission_ready_candidate"
        ),
    }
    if isinstance(nodes, list):
        summary["nodes"] = nodes[:MAX_DRAFT_NODE_SUMMARY]
        if len(nodes) > MAX_DRAFT_NODE_SUMMARY:
            summary["nodes_truncated"] = len(nodes) - MAX_DRAFT_NODE_SUMMARY
    if isinstance(edges, list):
        summary["edges"] = edges[:MAX_DRAFT_EDGE_SUMMARY]
        if len(edges) > MAX_DRAFT_EDGE_SUMMARY:
            summary["edges_truncated"] = len(edges) - MAX_DRAFT_EDGE_SUMMARY
    if isinstance(compile_gaps, list) and compile_gaps:
        summary["compile_gaps"] = compile_gaps[:MAX_COMPILE_GAPS_IN_FEEDBACK]
    if isinstance(judge_findings, list) and judge_findings:
        summary["judge_findings"] = judge_findings[:MAX_JUDGE_FINDINGS_IN_FEEDBACK]
    if isinstance(draft_repair_items, list) and draft_repair_items:
        summary["draft_repair_items"] = draft_repair_items[:MAX_DRAFT_REPAIR_ITEMS]
    warning = current_draft_ir.get("evaluation_warning")
    if isinstance(warning, Mapping) and warning:
        summary["evaluation_warning"] = {
            "reason_code": warning.get("reason_code"),
            "message": warning.get("message"),
        }
    return summary


def render_current_draft_ir_timeline_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(outputs, Mapping):
        return []
    current = outputs.get("current_draft_ir")
    if not isinstance(current, Mapping):
        current = outputs
    summary = compact_current_draft_ir_for_projection(current if isinstance(current, Mapping) else None)
    if summary is None:
        return []
    lines = [f"{indent}draft_ir:"]
    for key in (
        "draft_version",
        "graph_id",
        "node_count",
        "edge_count",
        "unknown_node_count",
        "renderable_feature_count",
        "placeholder_only_graph",
        "mapping_submission_ready_candidate",
        "compile_gap_count",
        "judge_finding_count",
        "mechanically_mappable_candidate",
    ):
        if key in summary and summary.get(key) is not None:
            lines.append(f"{indent}  {key}: {summary.get(key)}")
    repair_items = summary.get("draft_repair_items")
    if isinstance(repair_items, list) and repair_items:
        lines.append(f"{indent}  draft_repair_items: {len(repair_items)}")
        for item in repair_items[:3]:
            if isinstance(item, Mapping):
                node_id = item.get("node_id")
                issue = item.get("issue")
                op = item.get("current_operation")
                if node_id and issue:
                    detail = f"{node_id} ({issue}"
                    if op:
                        detail += f", op={op}"
                    detail += ")"
                    lines.append(f"{indent}    - {detail}")
    if summary.get("draft_ir_ref"):
        lines.append(f"{indent}  draft_ir_ref: {summary.get('draft_ir_ref')}")
    if summary.get("working_draft_ref"):
        lines.append(f"{indent}  working_draft_ref: {summary.get('working_draft_ref')}")
    return lines


def find_latest_child_artifact(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    parent_artifact_id: str,
    artifact_type: str,
    graph_id: str,
) -> dict[str, Any] | None:
    matches: list[tuple[str, dict[str, Any]]] = []
    for entry in persistence.list_artifacts(dossier_id=dossier_id, artifact_type=artifact_type):  # type: ignore[arg-type]
        raw = persistence.get_artifact(dossier_id, str(entry.get("artifact_id") or ""))
        if not isinstance(raw, Mapping):
            continue
        if _artifact_graph_id(raw) != graph_id:
            continue
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), Mapping) else {}
        parents = metadata.get("parent_artifact_ids")
        if isinstance(parents, list) and parent_artifact_id in [str(item) for item in parents]:
            matches.append((str(entry.get("saved_at") or ""), raw))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _artifact_graph_id(raw: Mapping[str, Any]) -> str:
    graph_id = raw.get("graph_id")
    if isinstance(graph_id, str) and graph_id.strip():
        return graph_id.strip()
    graph = raw.get("graph")
    if isinstance(graph, Mapping):
        value = graph.get("graph_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _summarize_nodes(graph: FeatureGraph) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for node in graph.nodes[:MAX_DRAFT_NODE_SUMMARY]:
        kind = node.kind.value if hasattr(node.kind, "value") else str(node.kind)
        rows.append({"id": node.id, "kind": kind})
    return rows


def _summarize_edges(graph: FeatureGraph) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for edge in graph.edges[:MAX_DRAFT_EDGE_SUMMARY]:
        rows.append(
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "edge_type": edge.edge_type,
            }
        )
    return rows


def build_draft_repair_items(
    *,
    graph: FeatureGraph,
    compile_gaps: Sequence[Mapping[str, Any]],
    judge_findings: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Bounded high-priority repair handles — mechanical facts only, no semantic rewrites."""
    node_kind_by_id = {
        node.id: node.kind.value if hasattr(node.kind, "value") else str(node.kind)
        for node in graph.nodes
    }
    op_by_id = {
        node.id: node.op_expr.op_name
        for node in graph.nodes
        if node.op_expr is not None
    }
    merged: dict[tuple[str, Any, Any], dict[str, Any]] = {}
    order: list[tuple[str, Any, Any]] = []

    for source, gaps in (("compile", compile_gaps), ("judge", judge_findings)):
        for gap in gaps:
            if not isinstance(gap, Mapping):
                continue
            node_id = gap.get("node_id") or gap.get("feature_id")
            if not isinstance(node_id, str) or not node_id.strip():
                continue
            issue = gap.get("gap_kind") or gap.get("gap_type") or gap.get("kind")
            operation = gap.get("operation") or op_by_id.get(node_id)
            reason = gap.get("reason")
            if not reason and isinstance(gap.get("message"), str):
                reason = gap.get("message")
            key = (node_id, issue, operation)
            if key not in merged:
                merged[key] = {
                    "node_id": node_id,
                    "node_kind": node_kind_by_id.get(node_id, "unknown"),
                    "current_operation": operation,
                    "issue": issue,
                    "reason": reason,
                    "sources": [source],
                }
                order.append(key)
            else:
                sources = merged[key].setdefault("sources", [])
                if source not in sources:
                    sources.append(source)
            if len(order) >= MAX_DRAFT_REPAIR_ITEMS:
                break
        if len(order) >= MAX_DRAFT_REPAIR_ITEMS:
            break

    return [merged[key] for key in order[:MAX_DRAFT_REPAIR_ITEMS]]


def _bound_compile_gaps(compile_outcome: PersistedCompileOutcome | None) -> list[dict[str, Any]]:
    if compile_outcome is None:
        return []
    gaps = compile_outcome.artifact.gaps or []
    rows: list[dict[str, Any]] = []
    for gap in gaps[:MAX_COMPILE_GAPS_IN_FEEDBACK]:
        if not isinstance(gap, Mapping):
            continue
        rows.append(_normalize_gap_feedback_row(gap))
    return rows


def _bound_judge_findings(judge_outcome: PersistedJudgeOutcome | None) -> list[dict[str, Any]]:
    if judge_outcome is None:
        return []
    report = judge_outcome.artifact.report
    gaps = report.gaps if report is not None else []
    rows: list[dict[str, Any]] = []
    for gap in gaps[:MAX_JUDGE_FINDINGS_IN_FEEDBACK]:
        if hasattr(gap, "model_dump"):
            data = gap.model_dump(mode="json")
        elif isinstance(gap, Mapping):
            data = dict(gap)
        else:
            continue
        rows.append(_normalize_gap_feedback_row(data))
    return rows


def _normalize_gap_feedback_row(gap: Mapping[str, Any]) -> dict[str, Any]:
    meta = gap.get("metadata") if isinstance(gap.get("metadata"), Mapping) else {}
    feature_id = gap.get("feature_id") or gap.get("node_id")
    gap_kind = gap.get("kind") or gap.get("gap_type") or gap.get("gap_kind")
    operation = meta.get("operation") or gap.get("operation")
    reason = meta.get("reason") or meta.get("precondition") or gap.get("reason")
    row: dict[str, Any] = {
        "feature_id": feature_id,
        "node_id": feature_id,
        "gap_kind": gap_kind,
        "operation": operation,
        "reason": reason,
        "severity": gap.get("severity"),
        "message": gap.get("message"),
    }
    return row


def _count_source_entity_links(graph: FeatureGraph) -> int:
    total = 0
    for node in graph.nodes:
        provenance = node.provenance
        if provenance is None:
            continue
        links = getattr(provenance, "source_entity_links", None)
        if links is not None:
            total += len(links)
    for edge in graph.edges:
        provenance = edge.provenance
        if provenance is None:
            continue
        links = getattr(provenance, "source_entity_links", None)
        if links is not None:
            total += len(links)
    return total
