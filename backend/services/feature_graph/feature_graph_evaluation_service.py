"""Canonical mechanical compile/judge evaluation and artifact persistence."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from feature_graph.artifact_refs import (
    build_feature_graph_artifact_ref,
    validate_artifact_id,
)
from feature_graph.artifacts import (
    CompileArtifact,
    IRArtifact,
    JudgeArtifact,
    create_compile_artifact,
    create_judge_artifact,
)
from feature_graph.compiler import compile_graph
from feature_graph.judge import judge_graph
from feature_graph.models import FeatureGraph

from .feature_graph_persistence_service import FeatureGraphPersistenceService


@dataclass(frozen=True)
class PersistedCompileOutcome:
    artifact_id: str
    artifact_ref: str
    graph_id: str
    artifact: CompileArtifact
    compiled_feature_count: int
    gap_count: int
    warning_count: int


@dataclass(frozen=True)
class PersistedJudgeOutcome:
    artifact_id: str
    artifact_ref: str
    graph_id: str
    artifact: JudgeArtifact
    gap_count: int
    warning_count: int


@dataclass(frozen=True)
class FeatureGraphEvaluationArtifacts:
    ir_artifact_id: str
    compile_outcome: PersistedCompileOutcome
    judge_outcome: PersistedJudgeOutcome


class FeatureGraphEvaluationService:
    """Single runtime path for compile/judge artifact creation and persistence."""

    def __init__(self, persistence: FeatureGraphPersistenceService) -> None:
        self._persistence = persistence

    def compile_and_persist(
        self,
        *,
        graph: FeatureGraph,
        dossier_id: str,
        parent_artifact_ids: Sequence[str],
        artifact_id: str | None = None,
    ) -> PersistedCompileOutcome:
        if not dossier_id:
            raise ValueError("dossier_id_required")
        compile_result = compile_graph(graph)
        gap_dicts = [gap.model_dump(mode="json") for gap in compile_result.gaps]
        resolved_id = _resolve_artifact_id(
            prefix="compile",
            graph_id=graph.graph_id,
            explicit=artifact_id,
        )
        parents = _normalize_parent_ids(parent_artifact_ids)
        compile_artifact = create_compile_artifact(
            artifact_id=resolved_id,
            graph_id=graph.graph_id,
            compiled_features=compile_result.compiled_features,
            gaps=gap_dicts,
            warnings=list(compile_result.warnings),
            parent_artifact_ids=parents,
        )
        self._persistence.save_artifact(artifact=compile_artifact, dossier_id=dossier_id)
        return PersistedCompileOutcome(
            artifact_id=resolved_id,
            artifact_ref=build_feature_graph_artifact_ref("compile", resolved_id),
            graph_id=graph.graph_id,
            artifact=compile_artifact,
            compiled_feature_count=len(compile_result.compiled_features),
            gap_count=len(compile_result.gaps),
            warning_count=len(compile_result.warnings),
        )

    def judge_and_persist(
        self,
        *,
        graph: FeatureGraph,
        dossier_id: str,
        parent_artifact_ids: Sequence[str],
        artifact_id: str | None = None,
        include_warnings: bool = True,
    ) -> PersistedJudgeOutcome:
        if not dossier_id:
            raise ValueError("dossier_id_required")
        judge_report = judge_graph(graph, include_warnings=include_warnings)
        resolved_id = _resolve_artifact_id(
            prefix="judge",
            graph_id=graph.graph_id,
            explicit=artifact_id,
        )
        parents = _normalize_parent_ids(parent_artifact_ids)
        judge_artifact = create_judge_artifact(
            artifact_id=resolved_id,
            graph_id=graph.graph_id,
            report=judge_report,
            parent_artifact_ids=parents,
        )
        self._persistence.save_artifact(artifact=judge_artifact, dossier_id=dossier_id)
        return PersistedJudgeOutcome(
            artifact_id=resolved_id,
            artifact_ref=build_feature_graph_artifact_ref("judge", resolved_id),
            graph_id=graph.graph_id,
            artifact=judge_artifact,
            gap_count=len(judge_report.gaps),
            warning_count=len(judge_report.warnings),
        )

    def compile_and_judge_ir(
        self,
        *,
        ir_artifact: IRArtifact,
        dossier_id: str,
        include_warnings: bool = True,
    ) -> FeatureGraphEvaluationArtifacts:
        parent_ids = [ir_artifact.artifact_id]
        compile_outcome = self.compile_and_persist(
            graph=ir_artifact.graph,
            dossier_id=dossier_id,
            parent_artifact_ids=parent_ids,
        )
        judge_outcome = self.judge_and_persist(
            graph=ir_artifact.graph,
            dossier_id=dossier_id,
            parent_artifact_ids=parent_ids,
            include_warnings=include_warnings,
        )
        return FeatureGraphEvaluationArtifacts(
            ir_artifact_id=ir_artifact.artifact_id,
            compile_outcome=compile_outcome,
            judge_outcome=judge_outcome,
        )

    def try_load_existing_ir_evaluation(
        self,
        *,
        ir_artifact: IRArtifact,
        dossier_id: str,
    ) -> FeatureGraphEvaluationArtifacts | None:
        """Reuse latest compile/judge child artifacts for an IR when lineage matches."""
        compile_raw = _find_latest_child_artifact(
            persistence=self._persistence,
            dossier_id=dossier_id,
            parent_artifact_id=ir_artifact.artifact_id,
            artifact_type="compile",
            graph_id=ir_artifact.graph.graph_id,
        )
        judge_raw = _find_latest_child_artifact(
            persistence=self._persistence,
            dossier_id=dossier_id,
            parent_artifact_id=ir_artifact.artifact_id,
            artifact_type="judge",
            graph_id=ir_artifact.graph.graph_id,
        )
        if compile_raw is None or judge_raw is None:
            return None
        try:
            compile_artifact = CompileArtifact.model_validate(compile_raw)
            judge_artifact = JudgeArtifact.model_validate(judge_raw)
        except Exception:
            return None
        compile_outcome = PersistedCompileOutcome(
            artifact_id=compile_artifact.artifact_id,
            artifact_ref=build_feature_graph_artifact_ref("compile", compile_artifact.artifact_id),
            graph_id=compile_artifact.graph_id,
            artifact=compile_artifact,
            compiled_feature_count=len(compile_artifact.compiled_features or {}),
            gap_count=len(compile_artifact.gaps or []),
            warning_count=len(compile_artifact.warnings or []),
        )
        judge_outcome = PersistedJudgeOutcome(
            artifact_id=judge_artifact.artifact_id,
            artifact_ref=build_feature_graph_artifact_ref("judge", judge_artifact.artifact_id),
            graph_id=judge_artifact.graph_id,
            artifact=judge_artifact,
            gap_count=len(judge_artifact.report.gaps or []),
            warning_count=len(judge_artifact.report.warnings or []),
        )
        return FeatureGraphEvaluationArtifacts(
            ir_artifact_id=ir_artifact.artifact_id,
            compile_outcome=compile_outcome,
            judge_outcome=judge_outcome,
        )


def _resolve_artifact_id(*, prefix: str, graph_id: str, explicit: str | None) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return validate_artifact_id(explicit.strip())
    suffix = uuid.uuid4().hex[:8]
    base = _sanitize_graph_id(graph_id)
    return validate_artifact_id(f"{prefix}_{base}_{suffix}")


def _sanitize_graph_id(graph_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(graph_id or "")).strip("_")
    return cleaned[:96] or "graph"


def _normalize_parent_ids(parent_artifact_ids: Sequence[str]) -> list[str]:
    if not parent_artifact_ids:
        return []
    return [validate_artifact_id(str(item)) for item in parent_artifact_ids]


def _find_latest_child_artifact(
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
        if not isinstance(raw, dict):
            continue
        if _artifact_graph_id(raw) != graph_id:
            continue
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        parents = metadata.get("parent_artifact_ids")
        if isinstance(parents, list) and parent_artifact_id in [str(item) for item in parents]:
            matches.append((str(entry.get("saved_at") or ""), raw))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _artifact_graph_id(raw: dict[str, Any]) -> str:
    graph_id = raw.get("graph_id")
    if isinstance(graph_id, str) and graph_id.strip():
        return graph_id.strip()
    graph = raw.get("graph")
    if isinstance(graph, dict):
        value = graph.get("graph_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
