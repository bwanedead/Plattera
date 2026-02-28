"""Typed contracts for transcription edit loop v0."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator


def stable_json_hash(payload: dict[str, Any]) -> str:
    """Compute deterministic SHA256 over canonical JSON bytes."""
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(blob).hexdigest()}"


def transcript_text_hash(text: str) -> str:
    """Hash exact UTF-8 bytes of transcript text."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


class ChangeClass(str, Enum):
    NORMALIZATION = "normalization"
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StartMode(str, Enum):
    AUDIT_ONLY = "audit_only"
    REPAIR = "repair"
    REPAIR_THEN_PROMOTE = "repair_then_promote"


class LocatorAnchorsV0(BaseModel):
    locator_type: Literal["anchors"] = "anchors"
    start_anchor: str = Field(..., min_length=1, max_length=500)
    end_anchor: str = Field(..., min_length=1, max_length=500)
    occurrence: int = Field(default=1, ge=1, le=200)


class LocatorOffsetsV0(BaseModel):
    locator_type: Literal["offsets"] = "offsets"
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> "LocatorOffsetsV0":
        if self.end_char < self.start_char:
            raise ValueError("offset_locator_invalid_bounds")
        return self


LocatorV0 = Annotated[Union[LocatorAnchorsV0, LocatorOffsetsV0], Field(discriminator="locator_type")]


class ExpectedOldV0(BaseModel):
    old_excerpt: str = Field(..., min_length=1, max_length=4000)
    old_hash: str | None = Field(default=None, max_length=80)


class EditOpBaseV0(BaseModel):
    op_id: str = Field(..., min_length=1, max_length=128)
    change_class: ChangeClass
    confidence: Confidence
    review_required: bool
    reason: str = Field(..., min_length=1, max_length=500)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    target: LocatorV0
    expected_old: ExpectedOldV0


class ReplaceSpanOpV0(EditOpBaseV0):
    op_type: Literal["replace_span"] = "replace_span"
    new_text: str = Field(..., max_length=20000)


class ReplaceLineOpV0(EditOpBaseV0):
    op_type: Literal["replace_line"] = "replace_line"
    new_text: str = Field(..., max_length=20000)


class ReplaceClauseOpV0(EditOpBaseV0):
    op_type: Literal["replace_clause"] = "replace_clause"
    new_text: str = Field(..., max_length=20000)


class RewriteSectionOpV0(EditOpBaseV0):
    op_type: Literal["rewrite_section"] = "rewrite_section"
    new_text: str = Field(..., max_length=100000)


EditOpV0 = Annotated[
    Union[ReplaceSpanOpV0, ReplaceLineOpV0, ReplaceClauseOpV0, RewriteSectionOpV0],
    Field(discriminator="op_type"),
]


class GlobalFlagsV0(BaseModel):
    review_required: bool = False
    rationale: str | None = Field(default=None, max_length=500)


class EditPlanV0(BaseModel):
    plan_version: Literal["edit_plan_v0"] = "edit_plan_v0"
    source_transcript_ref: str = Field(..., min_length=1, max_length=1024)
    source_transcript_hash: str = Field(..., min_length=8, max_length=80)
    plan_id: str = Field(..., min_length=1, max_length=128)
    summary: str = Field(..., min_length=1, max_length=500)
    ops: list[EditOpV0] = Field(default_factory=list, max_length=500)
    global_flags: GlobalFlagsV0 = Field(default_factory=GlobalFlagsV0)
    plan_fingerprint: str | None = Field(default=None, max_length=80)

    def payload_for_fingerprint(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("plan_fingerprint", None)
        return payload

    def computed_plan_fingerprint(self) -> str:
        return stable_json_hash(self.payload_for_fingerprint())

    @model_validator(mode="after")
    def _validate_fingerprint(self) -> "EditPlanV0":
        if self.plan_fingerprint is None:
            self.plan_fingerprint = self.computed_plan_fingerprint()
            return self
        if self.plan_fingerprint != self.computed_plan_fingerprint():
            raise ValueError("plan_fingerprint_mismatch")
        return self


class EditLoopStartRequestV0(BaseModel):
    start_version: Literal["edit_loop_start_v0"] = "edit_loop_start_v0"
    dossier_id: str | None = Field(default=None, max_length=128)
    source_transcript_ref: str | None = Field(default=None, max_length=1024)
    source_text: str | None = Field(default=None, max_length=2_000_000)
    source_image_refs: list[str] = Field(default_factory=list, max_length=200)
    mode: StartMode = StartMode.REPAIR

    @model_validator(mode="after")
    def _validate_one_of_source(self) -> "EditLoopStartRequestV0":
        has_ref = bool(self.source_transcript_ref and self.source_transcript_ref.strip())
        has_text = bool(self.source_text and self.source_text.strip())
        if has_ref == has_text:
            raise ValueError("start_request_requires_exactly_one_of_source_transcript_ref_or_source_text")
        return self


class CanonicalTranscriptInputV0(BaseModel):
    source_transcript_ref: str
    source_transcript_hash: str
    transcript_text: str
    transcript_sections: list["TranscriptSectionV0"] = Field(default_factory=list)
    source_image_refs: list[str] = Field(default_factory=list)
    dossier_id: str | None = None
    mode: StartMode = StartMode.REPAIR


class TranscriptSectionV0(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    body: str = Field(default="", max_length=2_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptDocumentV0(BaseModel):
    transcript_version: Literal["transcript_v0"] = "transcript_v0"
    source_transcript_ref: str | None = Field(default=None, max_length=1024)
    source_transcript_hash: str | None = Field(default=None, max_length=80)
    sections: list[TranscriptSectionV0] = Field(default_factory=list, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidatorFindingV0(BaseModel):
    finding_id: str = Field(..., min_length=1, max_length=128)
    finding_type: str = Field(..., min_length=1, max_length=64)
    severity: Literal["info", "warning", "error"] = "warning"
    message: str = Field(..., min_length=1, max_length=500)
    section_id: str | None = Field(default=None, max_length=128)
    span: dict[str, int] | None = None


class ValidatorReportV0(BaseModel):
    report_version: Literal["validator_report_v0"] = "validator_report_v0"
    source_transcript_ref: str
    source_transcript_hash: str
    findings: list[ValidatorFindingV0] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class TranscriptionEditRunRequestV0(BaseModel):
    run_version: Literal["transcription_edit_run_v0"] = "transcription_edit_run_v0"
    start: EditLoopStartRequestV0
    plan: EditPlanV0 | None = None
    promote_for_mapping: bool = False


class TranscriptionEditRunSnapshotV0(BaseModel):
    run_id: str
    dossier_id: str
    status: Literal["completed", "failed"]
    mode: StartMode
    source_transcript_ref: str
    source_transcript_hash: str
    validator_report_ref: str | None = None
    edit_plan_ref: str | None = None
    apply_report_ref: str | None = None
    edited_transcript_ref: str | None = None
    latest_mapping_pointer_ref: str | None = None
    review_required: bool = False
    error: str | None = None


class ApplyOpResultV0(BaseModel):
    op_id: str
    status: Literal["applied", "refused"]
    reason_code: str | None = None
    locator_span: dict[str, int] | None = None


class ApplyReportV0(BaseModel):
    report_version: Literal["apply_report_v0"] = "apply_report_v0"
    plan_id: str
    source_transcript_ref: str
    source_transcript_hash_expected: str
    source_transcript_hash_actual: str
    root_status: Literal["applied", "refused"]
    root_reason_code: str | None = None
    applied_count: int
    refused_count: int
    op_results: list[ApplyOpResultV0] = Field(default_factory=list)
    output_transcript_ref: str | None = None
    output_transcript_text: str
    output_transcript_hash: str
