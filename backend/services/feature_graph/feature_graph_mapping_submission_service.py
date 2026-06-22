"""Orchestrate IR submission through compile/judge evaluation and mapping creation."""

from __future__ import annotations

from dataclasses import dataclass

from feature_graph.artifact_refs import build_feature_graph_artifact_ref
from feature_graph.artifacts import IRArtifact

from .feature_graph_evaluation_service import (
    FeatureGraphEvaluationArtifacts,
    FeatureGraphEvaluationService,
)
from .feature_graph_mapping_service import FeatureGraphMappingService, MappingCreationOutcome


@dataclass(frozen=True)
class MappingSubmissionOutcome:
    ir_artifact_id: str
    ir_artifact_ref: str
    evaluation: FeatureGraphEvaluationArtifacts
    mapping: MappingCreationOutcome


class FeatureGraphMappingSubmissionService:
    """Single submission path: IR -> compile/judge -> mapping."""

    def __init__(
        self,
        evaluation: FeatureGraphEvaluationService,
        mapping: FeatureGraphMappingService,
    ) -> None:
        self._evaluation = evaluation
        self._mapping = mapping

    def submit_ir_artifact(
        self,
        *,
        ir_artifact: IRArtifact,
        dossier_id: str,
    ) -> MappingSubmissionOutcome:
        evaluation = self._evaluation.compile_and_judge_ir(
            ir_artifact=ir_artifact,
            dossier_id=dossier_id,
        )
        mapping = self._mapping.create_mapping_from_artifacts(
            ir_artifact=ir_artifact,
            compile_artifact=evaluation.compile_outcome.artifact,
            judge_artifact=evaluation.judge_outcome.artifact,
            dossier_id=dossier_id,
        )
        return MappingSubmissionOutcome(
            ir_artifact_id=ir_artifact.artifact_id,
            ir_artifact_ref=build_feature_graph_artifact_ref("ir", ir_artifact.artifact_id),
            evaluation=evaluation,
            mapping=mapping,
        )
