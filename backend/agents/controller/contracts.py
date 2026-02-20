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
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    return _normalize_openai_strict_schema(schema)


def _normalize_openai_strict_schema(schema: dict[str, Any]) -> dict[str, object]:
    normalized = _deep_clone(schema)
    normalized = _inline_root_ref(normalized)
    _enforce_closed_objects(normalized)
    return normalized


def _inline_root_ref(schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    target = _resolve_local_ref(schema, ref)
    if not isinstance(target, dict):
        return schema

    inlined = _deep_clone(target)
    for key, value in schema.items():
        if key in {"$ref", "$defs", "definitions"}:
            continue
        inlined[key] = _deep_clone(value)
    if "$defs" in schema:
        inlined["$defs"] = _deep_clone(schema["$defs"])
    if "definitions" in schema:
        inlined["definitions"] = _deep_clone(schema["definitions"])
    return inlined


def _resolve_local_ref(root: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        return None
    current: Any = root
    for part in ref[2:].split("/"):
        token = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current if isinstance(current, dict) else None


def _enforce_closed_objects(node: Any) -> None:
    if isinstance(node, dict):
        if _node_is_object_schema(node):
            node["additionalProperties"] = False
        for value in node.values():
            _enforce_closed_objects(value)
        return
    if isinstance(node, list):
        for item in node:
            _enforce_closed_objects(item)


def _node_is_object_schema(node: dict[str, Any]) -> bool:
    node_type = node.get("type")
    if node_type == "object":
        return True
    if isinstance(node_type, list):
        return "object" in node_type
    return False


def _deep_clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_clone(v) for v in value]
    return value
