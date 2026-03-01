"""Durable run artifact and step record models for Agent Kernel v0."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .models import ActionType

_MAX_INLINE_JSON_BYTES = 16384
_GEOMETRY_KEYS = {"geometry", "coordinates", "rings", "vertices", "polygon"}
_MAX_GEOMETRY_POINTS = 64


class ArtifactRef(BaseModel):
    """Reference to a persisted artifact, optionally scoped to evidence indices."""

    artifact_path: str = Field(..., min_length=1)
    card_index: Optional[int] = Field(default=None, ge=0)
    span_index: Optional[int] = Field(default=None, ge=0)


class ValidationInline(BaseModel):
    """Small deterministic validation output stored inline on a step record."""

    passed: bool
    reason_code: Optional[str] = None
    checks: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _enforce_small_payload(self) -> "ValidationInline":
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        if len(payload.encode("utf-8")) > _MAX_INLINE_JSON_BYTES:
            raise ValueError("validation_result exceeds inline payload limit")
        return self


class StepRecord(BaseModel):
    """Single deterministic execution step with refs and compact inline outputs."""

    step_id: str = Field(..., min_length=1)
    action: ActionType
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    reason_codes: List[str] = Field(default_factory=list)
    outputs_inline: Optional[Dict[str, Any]] = None
    validation_result: Optional[ValidationInline] = None

    @model_validator(mode="after")
    def _validate_inline_payload(self) -> "StepRecord":
        if self.outputs_inline is None:
            return self

        payload = json.dumps(self.outputs_inline, sort_keys=True, separators=(",", ":"))
        if len(payload.encode("utf-8")) > _MAX_INLINE_JSON_BYTES:
            raise ValueError("outputs_inline exceeds inline payload limit")
        if _contains_large_geometry(self.outputs_inline):
            raise ValueError("outputs_inline cannot include large geometry blobs")
        return self


class RunArtifact(BaseModel):
    """Durable run-level refs plus deterministic step execution records."""

    run_id: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    requires_global_placement: bool = False
    render_required: bool = False
    created_at_epoch_seconds: Optional[int] = None
    session_budgets: Dict[str, int] = Field(default_factory=dict)
    ir_artifact_ref: Optional[ArtifactRef] = None
    compile_artifact_ref: Optional[ArtifactRef] = None
    judge_artifact_ref: Optional[ArtifactRef] = None
    bundle_artifact_ref: Optional[ArtifactRef] = None
    georeference_artifact_ref: Optional[ArtifactRef] = None
    validate_artifact_ref: Optional[ArtifactRef] = None
    render_artifact_ref: Optional[ArtifactRef] = None
    retrieval_artifact_ref: Optional[ArtifactRef] = None
    deed_span_index_artifact_ref: Optional[ArtifactRef] = None
    tx_source_transcript_artifact_ref: Optional[ArtifactRef] = None
    tx_open_spans_artifact_ref: Optional[ArtifactRef] = None
    tx_validator_report_artifact_ref: Optional[ArtifactRef] = None
    tx_edit_plan_artifact_ref: Optional[ArtifactRef] = None
    tx_apply_report_artifact_ref: Optional[ArtifactRef] = None
    tx_edited_transcript_artifact_ref: Optional[ArtifactRef] = None
    tx_mapping_pointer_artifact_ref: Optional[ArtifactRef] = None
    tx_span_seeds_artifact_ref: Optional[ArtifactRef] = None
    idempotency_ledger: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    steps: List[StepRecord] = Field(default_factory=list)


def _contains_large_geometry(value: Any, parent_key: str = "") -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in _GEOMETRY_KEYS and _is_large_geometry_value(nested):
                return True
            if _contains_large_geometry(nested, parent_key=key_lower):
                return True
        return False

    if isinstance(value, list):
        if parent_key in _GEOMETRY_KEYS and len(value) > _MAX_GEOMETRY_POINTS:
            return True
        for nested in value:
            if _contains_large_geometry(nested, parent_key=parent_key):
                return True
        return False

    return False


def _is_large_geometry_value(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) > _MAX_GEOMETRY_POINTS
    if isinstance(value, dict):
        for nested in value.values():
            if _is_large_geometry_value(nested):
                return True
        return False
    return False
