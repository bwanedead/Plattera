"""Agent-authored deed-to-IR final package preview contract (shape validation only)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .published_output import (
    ALLOWED_CLOSURE_DIMENSION_IDS,
    ClosureDimensionRow,
    DeedToIrOutputSource,
    DeedToIrSelectedArtifacts,
    ExternalDependencyRow,
    MAX_CLOSURE_DIMENSIONS,
    MAX_EXTERNAL_DEPENDENCIES,
    MAX_NOTES,
    MAX_SCOPE_RESULTS,
    OutputNoteRow,
    ScopeResultRow,
    UpstreamCorrectionRow,
    MAX_UPSTREAM_CORRECTIONS,
    _MODEL_CONFIG,
)

PREVIEW_SCHEMA_VERSION = "1.0"


class MechanicalReviewSummary(BaseModel):
    model_config = _MODEL_CONFIG

    compile_gap_count: int = Field(..., ge=0)
    judge_finding_count: int = Field(..., ge=0)
    rendered_feature_count: int = Field(..., ge=0)
    skipped_feature_count: int = Field(..., ge=0)
    coordinate_space: str = Field(..., min_length=1)
    world_bbox: dict[str, Any] | None = None


class LineageSummary(BaseModel):
    model_config = _MODEL_CONFIG

    expected_ir_artifact_ref: str | None = None
    current_ir_artifact_ref: str = Field(..., min_length=1)
    lineage_mismatch: bool = False
    mismatch_reason_code: str | None = None


class DeedToIrFinalPackagePreview(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["1.0"] = PREVIEW_SCHEMA_VERSION
    source: DeedToIrOutputSource
    selected_artifacts: DeedToIrSelectedArtifacts
    scope_results: list[ScopeResultRow] = Field(default_factory=list, max_length=MAX_SCOPE_RESULTS)
    external_dependencies: list[ExternalDependencyRow] = Field(
        default_factory=list,
        max_length=MAX_EXTERNAL_DEPENDENCIES,
    )
    closure_dimensions: list[ClosureDimensionRow] = Field(
        default_factory=list,
        max_length=MAX_CLOSURE_DIMENSIONS,
    )
    notes: list[OutputNoteRow] = Field(default_factory=list, max_length=MAX_NOTES)
    upstream_corrections: list[UpstreamCorrectionRow] = Field(
        default_factory=list,
        max_length=MAX_UPSTREAM_CORRECTIONS,
    )
    mechanical_review_summary: MechanicalReviewSummary
    lineage_summary: LineageSummary
    publish_ready_candidate: bool

    @model_validator(mode="after")
    def _validate_uniqueness(self) -> DeedToIrFinalPackagePreview:
        scope_ids = [row.scope_id for row in self.scope_results]
        if len(scope_ids) != len(set(scope_ids)):
            raise ValueError("scope_id_not_unique")
        dependency_ids = [row.dependency_id for row in self.external_dependencies]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("dependency_id_not_unique")
        dimension_ids = [row.dimension_id for row in self.closure_dimensions]
        if len(dimension_ids) != len(set(dimension_ids)):
            raise ValueError("closure_dimension_id_not_unique")
        note_ids = [row.note_id for row in self.notes]
        if len(note_ids) != len(set(note_ids)):
            raise ValueError("note_id_not_unique")
        correction_ids = [row.correction_id for row in self.upstream_corrections]
        if len(correction_ids) != len(set(correction_ids)):
            raise ValueError("correction_id_not_unique")
        for row in self.closure_dimensions:
            if row.dimension_id not in ALLOWED_CLOSURE_DIMENSION_IDS:
                raise ValueError("closure_dimension_id_invalid")
        return self
