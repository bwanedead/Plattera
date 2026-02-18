"""Controller-side contracts for strict LLM step proposals."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

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


class NextStepProposal(BaseModel):
    action_type: ActionType
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    inputs: dict[str, object] = Field(default_factory=dict)
    why: str = Field(..., min_length=1, max_length=500)
    retrieval_intent: RetrievalIntent | None = None
    declare_done: DeclareDoneJustification | None = None
    notes: str | None = Field(default=None, max_length=500)
    semantic_ready: bool | None = None

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "NextStepProposal":
        if self.action_type == ActionType.RETRIEVE_EVIDENCE and self.retrieval_intent is None:
            raise ValueError("retrieval_intent_required_for_retrieve_evidence")
        if self.action_type == ActionType.DECLARE_DONE and self.declare_done is None:
            raise ValueError("declare_done_justification_required")
        return self


class ControllerEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)
    detail: str = Field(default="", max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


def next_step_json_schema() -> dict[str, object]:
    """Schema used in OpenAI structured output requests."""

    schema = NextStepProposal.model_json_schema()
    if isinstance(schema, dict):
        schema["additionalProperties"] = False
    return schema

