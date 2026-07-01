"""Agent-authored deed-to-IR published output contract (shape validation only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"
MAX_SCOPE_RESULTS = 32
MAX_EXTERNAL_DEPENDENCIES = 32
MAX_CLOSURE_DIMENSIONS = 8
MAX_NOTES = 16
MAX_UPSTREAM_CORRECTIONS = 16
MAX_ROW_REFS = 16
MAX_RATIONALE_LENGTH = 1024
MAX_CORRECTION_VALUE_LENGTH = 512
MAX_TARGET_ENTITY_TYPE_LENGTH = 64
MAX_NOTE_LENGTH = 512
MAX_SUMMARY_LENGTH = 1024
MAX_DESCRIPTION_LENGTH = 1024
MAX_ID_LENGTH = 128
MAX_REF_LENGTH = 1024
MAX_STATUS_LENGTH = 64
MAX_TITLE_LENGTH = 256

ALLOWED_CLOSURE_DIMENSION_IDS = frozenset(
    {
        "layer_1_deed_meaning_to_ir_fidelity",
        "layer_2_ir_geometry_integrity",
        "layer_3_external_dependency_representability_completeness",
        "layer_4_map_handoffability_scoped_completion",
    }
)

_MODEL_CONFIG = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _nonblank(value: str) -> str:
    if not value:
        raise ValueError("blank")
    return value


def _nonblank_ref_list(values: list[str]) -> list[str]:
    for item in values:
        text = str(item).strip()
        if not text:
            raise ValueError("blank_ref")
        if len(text) > MAX_REF_LENGTH:
            raise ValueError("ref_too_long")
    return values


class DeedToIrOutputSource(BaseModel):
    model_config = _MODEL_CONFIG

    transcript_edit_source_revision_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)
    resolution_state_ref: str | None = Field(None, max_length=MAX_REF_LENGTH)


class DeedToIrSelectedArtifacts(BaseModel):
    model_config = _MODEL_CONFIG

    ir_artifact_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)
    compile_artifact_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)
    judge_artifact_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)
    mapping_artifact_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)
    geometry_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)
    clean_render_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)
    control_render_ref: str = Field(..., min_length=1, max_length=MAX_REF_LENGTH)


class ScopeResultRow(BaseModel):
    model_config = _MODEL_CONFIG

    scope_id: str = Field(..., min_length=1, max_length=MAX_ID_LENGTH)
    status: str = Field(..., min_length=1, max_length=MAX_STATUS_LENGTH)
    title: str | None = Field(None, max_length=MAX_TITLE_LENGTH)
    summary: str | None = Field(None, max_length=MAX_SUMMARY_LENGTH)
    basis_refs: list[str] = Field(default_factory=list, max_length=MAX_ROW_REFS)
    blocker_refs: list[str] = Field(default_factory=list, max_length=MAX_ROW_REFS)
    dependency_refs: list[str] = Field(default_factory=list, max_length=MAX_ROW_REFS)

    _validate_scope_id = field_validator("scope_id")(_nonblank)
    _validate_status = field_validator("status")(_nonblank)
    _validate_basis_refs = field_validator("basis_refs")(_nonblank_ref_list)
    _validate_blocker_refs = field_validator("blocker_refs")(_nonblank_ref_list)
    _validate_dependency_refs = field_validator("dependency_refs")(_nonblank_ref_list)


class ExternalDependencyRow(BaseModel):
    model_config = _MODEL_CONFIG

    dependency_id: str = Field(..., min_length=1, max_length=MAX_ID_LENGTH)
    affected_scope: str = Field(..., min_length=1, max_length=MAX_ID_LENGTH)
    description: str = Field(..., min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    status: str = Field(..., min_length=1, max_length=MAX_STATUS_LENGTH)
    available_refs: list[str] = Field(default_factory=list, max_length=MAX_ROW_REFS)

    _validate_dependency_id = field_validator("dependency_id")(_nonblank)
    _validate_affected_scope = field_validator("affected_scope")(_nonblank)
    _validate_description = field_validator("description")(_nonblank)
    _validate_status = field_validator("status")(_nonblank)
    _validate_available_refs = field_validator("available_refs")(_nonblank_ref_list)


class ClosureDimensionRow(BaseModel):
    model_config = _MODEL_CONFIG

    dimension_id: str = Field(..., min_length=1, max_length=MAX_ID_LENGTH)
    status: str = Field(..., min_length=1, max_length=MAX_STATUS_LENGTH)
    title: str | None = Field(None, max_length=MAX_TITLE_LENGTH)
    summary: str | None = Field(None, max_length=MAX_SUMMARY_LENGTH)
    basis_refs: list[str] = Field(default_factory=list, max_length=MAX_ROW_REFS)

    _validate_dimension_id = field_validator("dimension_id")(_nonblank)
    _validate_status = field_validator("status")(_nonblank)
    _validate_basis_refs = field_validator("basis_refs")(_nonblank_ref_list)


class OutputNoteRow(BaseModel):
    model_config = _MODEL_CONFIG

    note_id: str = Field(..., min_length=1, max_length=MAX_ID_LENGTH)
    summary: str = Field(..., min_length=1, max_length=MAX_SUMMARY_LENGTH)
    basis_refs: list[str] = Field(default_factory=list, max_length=MAX_ROW_REFS)

    _validate_note_id = field_validator("note_id")(_nonblank)
    _validate_summary = field_validator("summary")(_nonblank)
    _validate_basis_refs = field_validator("basis_refs")(_nonblank_ref_list)


UpstreamCorrectionPosture = Literal["suspected", "confirmed_from_source", "needs_hitl"]
UpstreamCorrectionRecommendedAction = Literal[
    "transcript_amendment",
    "ir_only_note",
    "dependency_block",
    "hitl_review",
]


class UpstreamCorrectionRow(BaseModel):
    model_config = _MODEL_CONFIG

    correction_id: str = Field(..., min_length=1, max_length=MAX_ID_LENGTH)
    title: str | None = Field(None, max_length=MAX_TITLE_LENGTH)
    target_entity_id: str | None = Field(None, max_length=MAX_ID_LENGTH)
    target_entity_type: str | None = Field(None, max_length=MAX_TARGET_ENTITY_TYPE_LENGTH)
    upstream_value: str | None = Field(None, max_length=MAX_CORRECTION_VALUE_LENGTH)
    corrected_value: str | None = Field(None, max_length=MAX_CORRECTION_VALUE_LENGTH)
    posture: UpstreamCorrectionPosture
    resolution_used_by_ir: bool
    recommended_action: UpstreamCorrectionRecommendedAction
    basis_refs: list[str] = Field(..., min_length=1, max_length=MAX_ROW_REFS)
    rationale: str = Field(..., min_length=1, max_length=MAX_RATIONALE_LENGTH)

    _validate_correction_id = field_validator("correction_id")(_nonblank)
    _validate_basis_refs = field_validator("basis_refs")(_nonblank_ref_list)
    _validate_rationale = field_validator("rationale")(_nonblank)


class DeedToIrPublishedOutput(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["1.0"] = SCHEMA_VERSION
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

    @model_validator(mode="after")
    def _validate_uniqueness(self) -> DeedToIrPublishedOutput:
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
