"""Controller-side contracts and local validation for tool-call step proposals."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from agent_kernel.harness_action_ids import ActionType
from .tool_specs import ToolSpec
from .transcript_edit_compatibility import (
    TRANSCRIPT_EDIT_COMPATIBILITY_ACTION_IDS,
    TX_APPLY_EDIT_PLAN,
    TX_AUDIT_TRANSCRIPT,
    TX_OPEN_TRANSCRIPT_SPANS,
    TX_ORIENT_AND_BASELINE,
    TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
    TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
    TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
)


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


class IterationSummary(BaseModel):
    action: str | None = Field(default=None, max_length=64)
    intent: str | None = Field(default=None, max_length=240)
    expected_observation: str | None = Field(default=None, max_length=240)
    actual_observation: str | None = Field(default=None, max_length=240)
    state_delta: dict[str, Any] | None = None
    open_issues: list[str] | None = Field(default=None, max_length=5)
    next_move: dict[str, Any] | None = None
    confidence: str | float | None = None
    do_not_repeat: str | None = Field(default=None, max_length=240)


class KernelStepProposal(BaseModel):
    action_type: str = Field(..., min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    why: str = Field(..., min_length=1, max_length=500)
    display_delta: Any | None = None
    semantic_ready: bool | None = None
    notes: Any | None = None
    retrieval_intent: RetrievalIntent | None = None
    declare_done: DeclareDoneJustification | None = None
    iteration_summary: Any | None = None

    @field_validator("action_type")
    @classmethod
    def _normalize_action_type(cls, value: str) -> str:
        return value.strip().lower()

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
    deed_text_artifact_ref: str | None = Field(default=None, max_length=512)
    deed_artifact_ref: str | None = Field(default=None, max_length=512)
    hydrated_deed_artifact_ref: str | None = Field(default=None, max_length=512)
    graph: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_DraftIRArgs":
        # dossier_id is optional — the tool falls back to "unknown" when absent
        # (text-only runs have no dossier_id).
        if self.graph is None:
            raise ValueError("draft_ir_requires_graph")
        return self


class _OpenTextSpansRawRange(BaseModel):
    span_id: str | None = Field(default=None, max_length=128)
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=1)


class _OpenTextSpansAnchorSpec(BaseModel):
    span_id: str | None = Field(default=None, max_length=128)
    start_anchor: str = Field(..., min_length=1, max_length=200)
    end_anchor: str = Field(..., min_length=1, max_length=200)
    occurrence: int | None = Field(default=None, ge=1, le=50)


class _OpenTextSpansArgs(BaseModel):
    deed_text_artifact_ref: str | None = Field(default=None, max_length=512)
    deed_span_index_ref: str | None = Field(default=None, max_length=512)
    span_ids: list[str] | None = Field(default=None, max_length=20)
    spans: list[_OpenTextSpansRawRange] | None = Field(default=None, max_length=20)
    anchors: list[_OpenTextSpansAnchorSpec] | None = Field(default=None, max_length=10)
    max_chars_per_span: int | None = Field(default=None, ge=1, le=5000)
    max_total_chars: int | None = Field(default=None, ge=1, le=10000)
    include_context_chars: int | None = Field(default=None, ge=0, le=500)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_OpenTextSpansArgs":
        if not self.deed_text_artifact_ref:
            raise ValueError("open_text_spans_missing_deed_ref")
        has_ids = bool(self.span_ids)
        has_spans = bool(self.spans)
        has_anchors = bool(self.anchors)
        if has_ids and not self.deed_span_index_ref:
            raise ValueError("open_text_spans_missing_span_index_ref")
        modes = sum(1 for v in (has_ids, has_spans, has_anchors) if v)
        if modes == 0:
            raise ValueError("open_text_spans_requires_span_ids_or_spans_or_anchors")
        if modes > 1:
            raise ValueError("open_text_spans_requires_exactly_one_request_mode")
        return self


class _DeedFingerprintArgs(BaseModel):
    sha256_12: str = Field(..., min_length=12, max_length=12)
    length_chars: int = Field(..., ge=0)


class _DeedSpanAnchorArgs(BaseModel):
    start_snippet: str | None = Field(default=None, max_length=200)
    end_snippet: str | None = Field(default=None, max_length=200)


class _DeedSpanAgentIntentArgs(BaseModel):
    intended_verbatim_text: str | None = Field(default=None, max_length=2000)


class _DeedSpanUpsertArgs(BaseModel):
    span_id: str = Field(..., min_length=1, max_length=128)
    kind: str = Field(..., min_length=1, max_length=64)
    labels: list[str] = Field(default_factory=list, max_length=8)
    status: str = Field(..., min_length=1, max_length=32)
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=1)
    anchor: _DeedSpanAnchorArgs | None = None
    agent_intent: _DeedSpanAgentIntentArgs | None = None

    @model_validator(mode="after")
    def _validate_range(self) -> "_DeedSpanUpsertArgs":
        if self.end_char <= self.start_char:
            raise ValueError("upsert_deed_span_index_invalid_span")
        return self


class _UpsertDeedSpanIndexArgs(BaseModel):
    deed_span_index_ref: str | None = Field(default=None, max_length=512)
    deed_text_artifact_ref: str = Field(..., min_length=1, max_length=512)
    deed_fingerprint: _DeedFingerprintArgs
    upserts: list[_DeedSpanUpsertArgs] = Field(..., min_length=1, max_length=20)
    dossier_id: str | None = Field(default=None, max_length=128)


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
    georeference_artifact_ref: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _normalize_aliases(self) -> "_ValidateArgs":
        if not self.georef_artifact_ref and self.georeference_artifact_ref:
            self.georef_artifact_ref = self.georeference_artifact_ref
        return self

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_ValidateArgs":
        if not self.georef_artifact_ref:
            raise ValueError("validate_requires_georef_artifact_ref")
        return self


class _RenderArgs(BaseModel):
    georef_artifact_ref: str | None = Field(default=None, max_length=512)
    georeference_artifact_ref: str | None = Field(default=None, max_length=512)
    width: int | None = Field(default=None, ge=128, le=2400)
    height: int | None = Field(default=None, ge=128, le=2400)

    @model_validator(mode="after")
    def _normalize_aliases(self) -> "_RenderArgs":
        if not self.georef_artifact_ref and self.georeference_artifact_ref:
            self.georef_artifact_ref = self.georeference_artifact_ref
        return self

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_RenderArgs":
        if not self.georef_artifact_ref:
            raise ValueError("render_requires_georef_artifact_ref")
        return self


class _TxAuditTranscriptArgs(BaseModel):
    dossier_id: str | None = Field(default=None, max_length=128)
    source_transcript_ref: str | None = Field(default=None, max_length=512)
    source_text: str | None = Field(default=None, max_length=120000)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_TxAuditTranscriptArgs":
        if not self.source_transcript_ref and not self.source_text:
            raise ValueError("tx_audit_requires_source_transcript_ref_or_source_text")
        return self


class _TxOpenTranscriptSpansRawRange(BaseModel):
    span_id: str | None = Field(default=None, max_length=128)
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=1)


class _TxOpenTranscriptSpansAnchorSpec(BaseModel):
    span_id: str | None = Field(default=None, max_length=128)
    start_anchor: str = Field(..., min_length=1, max_length=200)
    end_anchor: str = Field(..., min_length=1, max_length=200)
    occurrence: int | None = Field(default=None, ge=1, le=200)


class _TxOpenTranscriptSpansArgs(BaseModel):
    dossier_id: str | None = Field(default=None, max_length=128)
    source_transcript_ref: str | None = Field(default=None, max_length=512)
    source_text: str | None = Field(default=None, max_length=120000)
    spans: list[_TxOpenTranscriptSpansRawRange] | None = Field(default=None, max_length=20)
    anchors: list[_TxOpenTranscriptSpansAnchorSpec] | None = Field(default=None, max_length=20)
    max_chars_per_span: int | None = Field(default=None, ge=1, le=5000)
    max_total_chars: int | None = Field(default=None, ge=1, le=12000)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_TxOpenTranscriptSpansArgs":
        if not self.source_transcript_ref and not self.source_text:
            raise ValueError("tx_open_spans_requires_source_transcript_ref_or_source_text")
        if not self.spans and not self.anchors:
            raise ValueError("tx_open_spans_requires_spans_or_anchors")
        return self


class _TxApplyEditPlanArgs(BaseModel):
    dossier_id: str | None = Field(default=None, max_length=128)
    edit_plan: dict[str, Any]


class _TxPromoteTranscriptArgs(BaseModel):
    dossier_id: str | None = Field(default=None, max_length=128)
    transcript_ref: str | None = Field(default=None, max_length=512)
    tx_edited_transcript_ref: str | None = Field(default=None, max_length=512)
    source_transcript_hash: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_TxPromoteTranscriptArgs":
        if not self.transcript_ref and not self.tx_edited_transcript_ref:
            raise ValueError("tx_promote_requires_transcript_ref")
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


_ACTION_ARG_MODELS: dict[str, type[BaseModel]] = {
    ActionType.SET_GRAPH_REQUIREMENTS.value: _SetGraphRequirementsArgs,
    ActionType.HYDRATE_DEED.value: _HydrateDeedArgs,
    ActionType.OPEN_ARTIFACT.value: _OpenArtifactArgs,
    ActionType.OPEN_TEXT_SPANS.value: _OpenTextSpansArgs,
    ActionType.DRAFT_IR.value: _DraftIRArgs,
    ActionType.DECLARE_DONE.value: _EmptyArgs,
    ActionType.RETRIEVE_EVIDENCE.value: _RetrieveEvidenceArgs,
    ActionType.COMPILE.value: _CompileArgs,
    ActionType.JUDGE.value: _JudgeArgs,
    ActionType.BUNDLE.value: _BundleArgs,
    ActionType.GEOREFERENCE.value: _GeoreferenceArgs,
    ActionType.VALIDATE.value: _ValidateArgs,
    ActionType.RENDER.value: _RenderArgs,
    TX_AUDIT_TRANSCRIPT: _TxAuditTranscriptArgs,
    TX_OPEN_TRANSCRIPT_SPANS: _TxOpenTranscriptSpansArgs,
    TX_APPLY_EDIT_PLAN: _TxApplyEditPlanArgs,
    TX_PROMOTE_TRANSCRIPT_FOR_MAPPING: _TxPromoteTranscriptArgs,
    ActionType.PROPOSE_PATCH.value: _ProposePatchArgs,
    ActionType.SUMMARIZE_STATUS.value: _SummarizeStatusArgs,
    ActionType.UPSERT_DEED_SPAN_INDEX.value: _UpsertDeedSpanIndexArgs,
}

def coerce_action_type(action_type: str) -> str | None:
    try:
        return ActionType(action_type).value
    except Exception:
        if action_type in TRANSCRIPT_EDIT_COMPATIBILITY_ACTION_IDS:
            return action_type
        return None


def validate_action_args(
    *,
    action_type: ActionType | str,
    args: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    key = action_type.value if isinstance(action_type, ActionType) else str(action_type)
    model_cls = _ACTION_ARG_MODELS.get(key)
    if model_cls is None:
        return dict(args), None, []
    try:
        validated = model_cls.model_validate(dict(args))
        return validated.model_dump(mode="json", exclude_none=True), None, []
    except ValidationError as exc:
        reason_code = _extract_reason_code(exc, default=f"{key}_inputs_invalid")
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


def kernel_step_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="kernel_step",
        description="Propose exactly one next kernel action.",
        parameters_schema={
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "description": "Kernel action type."},
                "args": {"type": "object", "description": "Action args, preferably artifact refs."},
                "idempotency_key": {
                    "type": "string",
                    "description": "Stable key for dedupe/retry discipline.",
                },
                "why": {"type": "string", "description": "Short rationale for this move."},
                "display_delta": {
                    "type": "string",
                    "description": "Optional user-facing one-line progress update (plain language, bounded).",
                },
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
                "iteration_summary": {
                    "type": "object",
                    "description": "Optional delta-only summary for this iteration (continuity memory only).",
                },
            },
            "required": ["action_type", "args", "idempotency_key", "why"],
            "additionalProperties": False,
        },
    )


def action_tool_specs_for_menu(tool_menu: list[str]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for raw in tool_menu:
        action = coerce_action_type(str(raw))
        if action is None:
            continue
        specs.append(_tool_spec_for_action(action))
    return specs


def _tool_spec_for_action(action: str) -> ToolSpec:
    arg_model = _ACTION_ARG_MODELS.get(action)
    args_schema = _pydantic_args_schema(arg_model) if arg_model is not None else {"type": "object"}
    how_to = action_how_to_guide(action_type=action, reason_code=None, context_inputs={})
    props: dict[str, Any] = {}
    required: list[str] = []
    if isinstance(args_schema, dict):
        props.update(dict(args_schema.get("properties") or {}))
        raw_required = args_schema.get("required")
        if isinstance(raw_required, list):
            required.extend([str(v) for v in raw_required if isinstance(v, str)])
    required.extend(_TOOL_SCHEMA_REQUIRED_KEYS.get(action, []))
    props["why"] = {"type": "string", "description": "Short rationale for this move."}
    props["display_delta"] = {
        "type": "string",
        "description": "Optional user-facing one-line progress update (plain language, bounded).",
    }
    props["semantic_ready"] = {"type": "boolean"}
    props["notes"] = {"type": "string"}
    if action == ActionType.RETRIEVE_EVIDENCE.value:
        props["retrieval_intent"] = {"type": "string", "enum": [intent.value for intent in RetrievalIntent]}
    if action == ActionType.DECLARE_DONE.value:
        props["declare_done"] = {"type": "object", "description": "DECLARE_DONE justification payload."}
        required.append("declare_done")
    props["iteration_summary"] = {
        "type": "object",
        "description": "Optional Memory Docket v0 (delta-only summary; continuity only).",
    }
    description = (
        f"{action}: {how_to['iteration_summary_note']} "
        f"Required fields: {', '.join(how_to['required_fields']) if how_to['required_fields'] else 'none'}."
    )
    parameters_schema: dict[str, object] = {
        "type": "object",
        "properties": props,
        "required": sorted(set(required)),
        "additionalProperties": False,
    }
    return ToolSpec(
        name=action,
        description=description[:600],
        parameters_schema=parameters_schema,
    )


def _pydantic_args_schema(model_cls: type[BaseModel] | None) -> dict[str, Any]:
    if model_cls is None:
        return {"type": "object", "properties": {}, "required": []}
    schema = model_cls.model_json_schema()
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "required": []}
    return _inline_local_refs(schema)


def _inline_local_refs(schema: dict[str, Any]) -> dict[str, Any]:
    root = dict(schema)
    defs = root.pop("$defs", {})

    def _walk(node: object) -> object:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                key = ref.split("/")[-1]
                target = defs.get(key)
                if isinstance(target, dict):
                    merged = dict(target)
                    merged.update({k: v for k, v in node.items() if k != "$ref"})
                    return _walk(merged)
            out: dict[str, object] = {}
            for k, v in node.items():
                if k in {"title", "default"}:
                    continue
                out[k] = _walk(v)
            return out
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return node

    walked = _walk(root)
    if isinstance(walked, dict):
        walked.setdefault("type", "object")
        walked.setdefault("properties", {})
        walked.setdefault("required", [])
        return walked
    return {"type": "object", "properties": {}, "required": []}


_TOOL_REQUIRED_FIELDS: dict[str, list[str]] = {
    ActionType.OPEN_ARTIFACT.value: ["artifact_ref | artifact_path | corpus_entry_ref"],
    ActionType.OPEN_TEXT_SPANS.value: ["deed_text_artifact_ref", "span_ids+deed_span_index_ref OR spans[] OR anchors[]"],
    ActionType.HYDRATE_DEED.value: ["dossier_id | source_entry_ref"],
    ActionType.DRAFT_IR.value: [
        "dossier_id",
        "graph",
        "deed_text_artifact_ref (recommended provenance)",
    ],
    ActionType.RETRIEVE_EVIDENCE.value: ["query"],
    ActionType.COMPILE.value: ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"],
    ActionType.JUDGE.value: ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"],
    ActionType.BUNDLE.value: ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"],
    ActionType.DECLARE_DONE.value: ["declare_done (artifact_refs + evidence_links + accepted_deviations)"],
    ActionType.GEOREFERENCE.value: ["bundle_artifact_ref | ir_artifact_ref"],
    ActionType.VALIDATE.value: ["georef_artifact_ref"],
    ActionType.RENDER.value: ["georef_artifact_ref"],
    TX_AUDIT_TRANSCRIPT: ["source_transcript_ref | source_text"],
    TX_OPEN_TRANSCRIPT_SPANS: ["source_transcript_ref | source_text", "spans[] OR anchors[]"],
    TX_APPLY_EDIT_PLAN: ["edit_plan"],
    TX_PROMOTE_TRANSCRIPT_FOR_MAPPING: ["transcript_ref | tx_edited_transcript_ref"],
    ActionType.PROPOSE_PATCH.value: ["ir_artifact_ref"],
    ActionType.UPSERT_DEED_SPAN_INDEX.value: ["deed_text_artifact_ref", "deed_fingerprint", "upserts[]"],
}

_TOOL_SCHEMA_REQUIRED_KEYS: dict[str, list[str]] = {
    ActionType.DRAFT_IR.value: ["dossier_id", "graph"],
    ActionType.OPEN_TEXT_SPANS.value: ["deed_text_artifact_ref"],
    ActionType.UPSERT_DEED_SPAN_INDEX.value: ["deed_text_artifact_ref", "deed_fingerprint", "upserts"],
    ActionType.RETRIEVE_EVIDENCE.value: ["query"],
    ActionType.RENDER.value: ["georef_artifact_ref"],
    TX_APPLY_EDIT_PLAN: ["edit_plan"],
}


def tool_cheatsheet_entries(
    *,
    tool_menu: list[str],
    context_inputs: Mapping[str, Any],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in tool_menu:
        action = coerce_action_type(str(raw))
        if action is None:
            continue
        how_to = action_how_to_guide(action_type=action, reason_code=None, context_inputs=context_inputs)
        entries.append(
            {
                "action_type": action,
                "required_fields": how_to["required_fields"],
                "minimal_working_example": how_to["minimal_working_example"],
                "common_mistakes": how_to["common_mistakes"],
                "iteration_summary_note": how_to.get("iteration_summary_note"),
            }
        )
    return entries


def action_how_to_guide(
    *,
    action_type: ActionType | str,
    reason_code: str | None,
    context_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(action_type, ActionType):
        action = coerce_action_type(action_type.value)
    else:
        raw_action = getattr(action_type, "value", action_type)
        action = coerce_action_type(str(raw_action))
    if action is None:
        return {
            "required_fields": ["action_type"],
            "minimal_working_example": {},
            "common_mistakes": ["Use only actions present in tool_menu."],
        }
    example_args = _example_args_for_action(action=action, context_inputs=context_inputs)
    required_fields = list(_TOOL_REQUIRED_FIELDS.get(action, []))
    common_mistakes = _common_mistakes_for_action(action, reason_code=reason_code)
    return {
        "required_fields": required_fields,
        "minimal_working_example": example_args,
        "common_mistakes": common_mistakes[:2],
        "iteration_summary_note": (
            "Optional Memory Docket v0: delta-only this-iteration notes; do not recap memory.run_summary_log "
            "or paste deed text."
        ),
    }


def _example_args_for_action(*, action: str, context_inputs: Mapping[str, Any]) -> dict[str, Any]:
    dossier_id = _ctx_str(context_inputs.get("dossier_id")) or "<inputs.dossier_id>"
    deed_ref = _ctx_str(context_inputs.get("deed_text_artifact_ref")) or "<inputs.deed_text_artifact_ref>"
    source_entry_ref = _ctx_str(context_inputs.get("source_entry_ref")) or "<inputs.source_entry_ref>"
    initial_ir_ref = _ctx_str(context_inputs.get("initial_ir_ref"))
    latest_ir_ref = _ctx_str(context_inputs.get("latest_ir_ref"))
    ir_ref = latest_ir_ref or initial_ir_ref or "<ir-artifact-ref>"
    if action == ActionType.OPEN_ARTIFACT.value:
        return {"artifact_ref": deed_ref}
    if action == ActionType.OPEN_TEXT_SPANS.value:
        index_ref = _ctx_str(context_inputs.get("deed_span_index_ref")) or "<memory.deed_span_index_ref>"
        if _ctx_str(context_inputs.get("deed_span_index_ref")):
            return {
                "deed_text_artifact_ref": deed_ref,
                "deed_span_index_ref": index_ref,
                "span_ids": ["calls_01"],
            }
        return {
            "deed_text_artifact_ref": deed_ref,
            "anchors": [
                {
                    "span_id": "calls_01",
                    "start_anchor": "BEGINNING AT",
                    "end_anchor": "POINT OF BEGINNING",
                }
            ],
        }
    if action == ActionType.HYDRATE_DEED.value:
        return {"dossier_id": dossier_id, "source_entry_ref": source_entry_ref}
    if action == ActionType.DRAFT_IR.value:
        return {
            "dossier_id": dossier_id,
            "deed_text_artifact_ref": deed_ref,
            "graph": {
                "graph_id": "g_min_draft_001",
                "nodes": [
                    {
                        "id": "plss_frame",
                        "kind": "frame",
                        "metadata": {
                            "plss_anchor": {
                                "state": "Wyoming",
                                "township_number": 14,
                                "township_direction": "N",
                                "range_number": 75,
                                "range_direction": "W",
                                "section_number": 2,
                                "principal_meridian": "Sixth Principal Meridian",
                            }
                        },
                    },
                    {
                        "id": "pob_point",
                        "kind": "point",
                        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                        "metadata": {
                            "role": "pob",
                            "tie_to_corner": {
                                "corner_label": "NW corner Sec 2",
                                "bearing_raw": "N 4° 00' W.",
                                "distance_value": 1638,
                                "distance_units": "feet",
                                "tie_direction": "corner_bears_from_pob",
                            },
                        },
                    },
                    {
                        "id": "parcel1_boundary",
                        "kind": "curve",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0.0, 0.0], [120.0, 0.0], [40.0, 80.0], [0.0, 0.0]],
                        },
                    },
                    {
                        "id": "parcel1_region",
                        "kind": "region",
                        "op_expr": {"op_name": "Close", "operands": ["parcel1_boundary"]},
                    },
                    {
                        "id": "parcel2_stub",
                        "kind": "annotation",
                        "metadata": {"note": "Parcel 2 incomplete/truncated in deed excerpt; preserve as stub until fully stated."},
                    }
                ],
                "edges": [
                    {"source_id": "pob_point", "target_id": "parcel1_boundary", "edge_type": "anchored_to"},
                    {"source_id": "parcel1_boundary", "target_id": "parcel1_region", "edge_type": "depends_on"},
                ],
                "metadata": {"source": "deed"},
            },
        }
    if action == ActionType.RETRIEVE_EVIDENCE.value:
        return {"query": "<what you need to find>"}
    if action in {ActionType.COMPILE.value, ActionType.JUDGE.value, ActionType.BUNDLE.value}:
        return {"ir_artifact_ref": ir_ref}
    if action == ActionType.DECLARE_DONE.value:
        return {
            "declare_done": {
                "artifact_refs": {
                    "ir_ref": ir_ref,
                    "compile_ref": "<latest compile ref>",
                    "judge_ref": "<latest judge ref>",
                    "bundle_ref": "<latest bundle ref>",
                },
                "evidence_links": [],
                "accepted_deviations": [],
            }
        }
    if action == ActionType.GEOREFERENCE.value:
        return {"bundle_artifact_ref": "<bundle-artifact-ref>"}
    if action == ActionType.VALIDATE.value:
        return {"georef_artifact_ref": "<georef-artifact-ref>"}
    if action == ActionType.RENDER.value:
        return {"georef_artifact_ref": "<georef-artifact-ref>", "width": 900, "height": 700}
    if action == TX_AUDIT_TRANSCRIPT:
        return {"dossier_id": dossier_id, "source_transcript_ref": "<transcript-ref>"}
    if action == TX_OPEN_TRANSCRIPT_SPANS:
        return {
            "dossier_id": dossier_id,
            "source_transcript_ref": "<transcript-ref>",
            "anchors": [
                {
                    "span_id": "tx_01",
                    "start_anchor": "Beginning at",
                    "end_anchor": "to the point of beginning",
                }
            ],
            "max_total_chars": 4000,
        }
    if action == TX_APPLY_EDIT_PLAN:
        return {
            "dossier_id": dossier_id,
            "edit_plan": {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": "<transcript-ref>",
                "source_transcript_hash": "<sha256>",
                "plan_id": "plan-001",
                "summary": "Normalize obvious OCR punctuation spacing.",
                "ops": [],
                "global_flags": {"review_required": False},
                "plan_fingerprint": "<fingerprint>",
            },
        }
    if action == TX_PROMOTE_TRANSCRIPT_FOR_MAPPING:
        return {
            "dossier_id": dossier_id,
            "tx_edited_transcript_ref": "<edited-transcript-ref>",
        }
    if action == ActionType.PROPOSE_PATCH.value:
        return {"ir_artifact_ref": ir_ref}
    if action == ActionType.UPSERT_DEED_SPAN_INDEX.value:
        return {
            "deed_text_artifact_ref": deed_ref,
            "deed_fingerprint": {"sha256_12": "<sha256_12>", "length_chars": 0},
            "upserts": [
                {
                    "span_id": "calls_01",
                    "kind": "metes_bounds_calls",
                    "labels": ["calls"],
                    "status": "proposed",
                    "start_char": 0,
                    "end_char": 120,
                    "agent_intent": {"intended_verbatim_text": "<bounded expected text>"},
                }
            ],
        }
    return {}


def _common_mistakes_for_action(action: str, *, reason_code: str | None) -> list[str]:
    generic = [
        "Do not leave args empty when the tool requires fields.",
        "Prefer artifact refs from Context Packet inputs/progress, not inline blobs.",
    ]
    if action == ActionType.OPEN_ARTIFACT.value:
        return [
            "OPEN_ARTIFACT is for bounded summaries/debug inspection, not verbatim deed recall.",
            "For verbatim deed text, prefer OPEN_TEXT_SPANS.",
        ]
    if action == ActionType.OPEN_TEXT_SPANS.value:
        return [
            "OPEN_TEXT_SPANS is the canonical verbatim deed recall tool; OPEN_ARTIFACT is summary/debug only.",
            "Use anchors[] to capture a span first, then span_ids + deed_span_index_ref for repeat verification.",
        ]
    if action == ActionType.DRAFT_IR.value:
        return [
            "DRAFT_IR must include graph (top-level tool parameter, FeatureGraph JSON); deed refs are provenance, not auto-drafting inputs.",
            "Minimum viable graph: graph_id + at least one node + metadata.source='deed'.",
            "For georeference readiness, prefer a frame node with metadata.plss_anchor (flat canonical keys) plus explicit local Polygon/closed LineString geometry.",
            "If deed ties the POB to a PLSS corner/line, encode point.metadata.role='pob' + point.metadata.tie_to_corner using canonical keys (corner_label, bearing_raw, distance_value, distance_units, tie_direction).",
            "For partial deeds, include only fully stated parcel geometry and keep incomplete parcels as annotation stubs (do not fabricate their boundaries).",
        ]
    if action == ActionType.DECLARE_DONE.value:
        return [
            "DECLARE_DONE requires top-level declare_done payload; do not leave it empty.",
            "If claimability looks ready, include artifact_refs from progress.latest_refs.artifact_refs plus empty evidence_links/accepted_deviations if unsure.",
        ]
    if action in {ActionType.COMPILE.value, ActionType.JUDGE.value, ActionType.BUNDLE.value}:
        return [
            "Physics tools require an IR artifact ref/path.",
            "Use progress.latest_refs.artifact_refs.ir_ref (path) after a successful DRAFT_IR or IR update.",
        ]
    if action == ActionType.RENDER.value:
        return [
            "RENDER requires a georeference artifact ref (not IR/bundle refs).",
            "Use progress.latest_refs.artifact_refs.georef_ref (path) after successful GEOREFERENCE.",
        ]
    if action == ActionType.RETRIEVE_EVIDENCE.value:
        return [
            "RETRIEVE_EVIDENCE requires a non-empty query string.",
            "Use retrieval only when it helps resolve a concrete gap or ambiguity.",
        ]
    if action == TX_AUDIT_TRANSCRIPT:
        return [
            "Provide source_transcript_ref when possible; source_text is fallback only.",
            "Run transcript audit before proposing transcript edits.",
        ]
    if action == TX_OPEN_TRANSCRIPT_SPANS:
        return [
            "TX_OPEN_TRANSCRIPT_SPANS needs source_transcript_ref/source_text and spans[] or anchors[].",
            "Keep requests bounded; do not request full-document spans repeatedly.",
        ]
    if action == TX_APPLY_EDIT_PLAN:
        return [
            "TX_APPLY_EDIT_PLAN requires edit_plan at top level.",
            "Each op should include expected_old.old_excerpt for drift safety.",
        ]
    if action == TX_PROMOTE_TRANSCRIPT_FOR_MAPPING:
        return [
            "Promotion requires transcript_ref (or tx_edited_transcript_ref).",
            "Do not promote when unresolved validator errors remain.",
        ]
    if action == ActionType.UPSERT_DEED_SPAN_INDEX.value:
        return [
            "UPSERT_DEED_SPAN_INDEX requires deed_fingerprint and at least one valid span upsert.",
            "Include bounded agent_intent.intended_verbatim_text to support verification loops.",
        ]
    if reason_code and "action_not_in_tool_menu" in reason_code:
        return ["Only choose actions currently listed in tool_menu."]
    return generic


def _ctx_str(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value else None
