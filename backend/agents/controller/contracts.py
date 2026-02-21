"""Controller-side contracts and local validation for tool-call step proposals."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from agent_kernel.models import ActionType


class RetrievalIntent(str, Enum):
    ANCHOR_HUNT = "ANCHOR_HUNT"
    DEPENDENCY_HUNT = "DEPENDENCY_HUNT"
    EXEMPLAR_LOOKUP = "EXEMPLAR_LOOKUP"
    TERMINOLOGY_CHECK = "TERMINOLOGY_CHECK"
    GENERAL = "GENERAL"


class EvidenceSource(str, Enum):
    DEED = "DEED"
    RAG = "RAG"


class EvidenceLink(BaseModel):
    source: EvidenceSource
    ref: str = Field(..., min_length=1, max_length=512)
    claim: str = Field(..., min_length=1, max_length=200)


class AcceptedDeviation(BaseModel):
    kind: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=200)


class DeclareDoneArtifactRefs(BaseModel):
    ir_ref: str | None = Field(default=None, max_length=512)
    compile_ref: str | None = Field(default=None, max_length=512)
    judge_ref: str | None = Field(default=None, max_length=512)
    bundle_ref: str | None = Field(default=None, max_length=512)
    georef_ref: str | None = Field(default=None, max_length=512)
    validate_ref: str | None = Field(default=None, max_length=512)
    render_ref: str | None = Field(default=None, max_length=512)


class DeclareDoneJustification(BaseModel):
    artifact_refs: DeclareDoneArtifactRefs
    evidence_links: list[EvidenceLink] = Field(default_factory=list, max_length=20)
    accepted_deviations: list[AcceptedDeviation] = Field(default_factory=list, max_length=20)


class ControllerEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)
    detail: str = Field(default="", max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class KernelStepProposal(BaseModel):
    action_type: str = Field(..., min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    why: str = Field(..., min_length=1, max_length=500)
    semantic_ready: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    retrieval_intent: RetrievalIntent | None = None
    declare_done: DeclareDoneJustification | None = None

    @field_validator("action_type")
    @classmethod
    def _normalize_action_type(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "KernelStepProposal":
        if self.action_type == ActionType.DECLARE_DONE.value and self.declare_done is None:
            raise ValueError("declare_done_justification_required")
        return self


class _EmptyArgs(BaseModel):
    pass


class _SetGraphRequirementsArgs(BaseModel):
    ir_artifact_ref: str | None = Field(default=None, max_length=512)
    updated_ir_artifact_ref: str | None = Field(default=None, max_length=512)
    global_placement_required: bool | None = None


class _HydrateDeedArgs(BaseModel):
    dossier_id: str | None = Field(default=None, max_length=128)
    source_entry_ref: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_HydrateDeedArgs":
        if not self.dossier_id and not self.source_entry_ref:
            raise ValueError("hydrate_deed_requires_dossier_id_or_source_entry_ref")
        return self


class _OpenArtifactArgs(BaseModel):
    artifact_ref: str | None = Field(default=None, max_length=512)
    artifact_path: str | None = Field(default=None, max_length=512)
    corpus_entry_ref: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_OpenArtifactArgs":
        if not self.artifact_ref and not self.artifact_path and not self.corpus_entry_ref:
            raise ValueError("open_artifact_requires_artifact_or_corpus_ref")
        return self


class _DraftIRArgs(BaseModel):
    dossier_id: str | None = Field(default=None, max_length=128)
    deed_artifact_ref: str | None = Field(default=None, max_length=512)
    hydrated_deed_artifact_ref: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_DraftIRArgs":
        if not self.dossier_id:
            raise ValueError("draft_ir_requires_dossier_id")
        return self


class _RetrievalRoutingFilters(BaseModel):
    artifact_type: str | None = Field(default=None, max_length=128)


class _RetrievalRouting(BaseModel):
    lanes: list[str] | None = Field(default=None, max_length=8)
    view: str | None = Field(default=None, max_length=64)
    filters: _RetrievalRoutingFilters | None = None


class _RetrievalOptions(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=100)


class _RetrieveEvidenceArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    routing: _RetrievalRouting | None = None
    options: _RetrievalOptions | None = None


class _CompileArgs(BaseModel):
    ir_artifact_ref: str | None = Field(default=None, max_length=512)
    updated_ir_artifact_ref: str | None = Field(default=None, max_length=512)
    ir_artifact_path: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_CompileArgs":
        if not self.ir_artifact_ref and not self.updated_ir_artifact_ref and not self.ir_artifact_path:
            raise ValueError("compile_requires_ir_artifact_ref_or_updated_ir_artifact_ref_or_ir_artifact_path")
        return self


class _JudgeArgs(BaseModel):
    ir_artifact_ref: str | None = Field(default=None, max_length=512)
    updated_ir_artifact_ref: str | None = Field(default=None, max_length=512)
    ir_artifact_path: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_JudgeArgs":
        if not self.ir_artifact_ref and not self.updated_ir_artifact_ref and not self.ir_artifact_path:
            raise ValueError("judge_requires_ir_artifact_ref_or_updated_ir_artifact_ref_or_ir_artifact_path")
        return self


class _BundleArgs(BaseModel):
    ir_artifact_ref: str | None = Field(default=None, max_length=512)
    updated_ir_artifact_ref: str | None = Field(default=None, max_length=512)
    ir_artifact_path: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_BundleArgs":
        if not self.ir_artifact_ref and not self.updated_ir_artifact_ref and not self.ir_artifact_path:
            raise ValueError("bundle_requires_ir_artifact_ref_or_updated_ir_artifact_ref_or_ir_artifact_path")
        return self


class _GeoreferenceArgs(BaseModel):
    bundle_artifact_ref: str | None = Field(default=None, max_length=512)
    ir_artifact_ref: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_GeoreferenceArgs":
        if not self.bundle_artifact_ref and not self.ir_artifact_ref:
            raise ValueError("georeference_requires_bundle_artifact_ref_or_ir_artifact_ref")
        return self


class _ValidateArgs(BaseModel):
    georef_artifact_ref: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_ValidateArgs":
        if not self.georef_artifact_ref:
            raise ValueError("validate_requires_georef_artifact_ref")
        return self


class _ProposePatchArgs(BaseModel):
    ir_artifact_ref: str | None = Field(default=None, max_length=512)
    retrieval_artifact_ref: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_ProposePatchArgs":
        if not self.ir_artifact_ref:
            raise ValueError("propose_patch_requires_ir_artifact_ref")
        return self


class _SummarizeStatusArgs(BaseModel):
    run_artifact_ref: str | None = Field(default=None, max_length=512)
    transcript_artifact_ref: str | None = Field(default=None, max_length=512)


_ACTION_ARG_MODELS: dict[ActionType, type[BaseModel]] = {
    ActionType.SET_GRAPH_REQUIREMENTS: _SetGraphRequirementsArgs,
    ActionType.HYDRATE_DEED: _HydrateDeedArgs,
    ActionType.OPEN_ARTIFACT: _OpenArtifactArgs,
    ActionType.DRAFT_IR: _DraftIRArgs,
    ActionType.DECLARE_DONE: _EmptyArgs,
    ActionType.RETRIEVE_EVIDENCE: _RetrieveEvidenceArgs,
    ActionType.COMPILE: _CompileArgs,
    ActionType.JUDGE: _JudgeArgs,
    ActionType.BUNDLE: _BundleArgs,
    ActionType.GEOREFERENCE: _GeoreferenceArgs,
    ActionType.VALIDATE: _ValidateArgs,
    ActionType.PROPOSE_PATCH: _ProposePatchArgs,
    ActionType.SUMMARIZE_STATUS: _SummarizeStatusArgs,
}


def coerce_action_type(action_type: str) -> ActionType | None:
    try:
        return ActionType(action_type)
    except Exception:
        return None


def validate_action_args(
    *,
    action_type: ActionType,
    args: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    model_cls = _ACTION_ARG_MODELS.get(action_type)
    if model_cls is None:
        return dict(args), None, []
    try:
        validated = model_cls.model_validate(dict(args))
        return validated.model_dump(mode="json", exclude_none=True), None, []
    except ValidationError as exc:
        reason_code = _extract_reason_code(exc, default=f"{action_type.value}_inputs_invalid")
        missing_inputs = _extract_missing_inputs(exc)
        return None, reason_code, missing_inputs


def _extract_reason_code(exc: ValidationError, *, default: str) -> str:
    for err in exc.errors():
        msg = err.get("msg")
        if isinstance(msg, str) and msg.startswith("Value error, "):
            value = msg.replace("Value error, ", "", 1).strip()
            if value:
                return value
    return default


def _extract_missing_inputs(exc: ValidationError) -> list[str]:
    missing: list[str] = []
    for err in exc.errors():
        if str(err.get("type", "")).endswith("missing"):
            loc = err.get("loc")
            if isinstance(loc, tuple) and loc:
                field = loc[-1]
                if isinstance(field, str) and field not in missing:
                    missing.append(field)
    return missing


def kernel_step_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "kernel_step",
            "description": "Propose exactly one next kernel action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string", "description": "Kernel action type."},
                    "args": {"type": "object", "description": "Action args, preferably artifact refs."},
                    "idempotency_key": {
                        "type": "string",
                        "description": "Stable key for dedupe/retry discipline.",
                    },
                    "why": {"type": "string", "description": "Short rationale for this move."},
                    "semantic_ready": {"type": "boolean"},
                    "notes": {"type": "string"},
                    "retrieval_intent": {
                        "type": "string",
                        "enum": [intent.value for intent in RetrievalIntent],
                    },
                    "declare_done": {
                        "type": "object",
                        "description": "Optional DECLARE_DONE justification payload.",
                    },
                },
                "required": ["action_type", "args", "idempotency_key", "why"],
                "additionalProperties": False,
            },
        },
    }
