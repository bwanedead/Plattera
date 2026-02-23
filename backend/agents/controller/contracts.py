"""Controller-side contracts and local validation for tool-call step proposals."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from agent_kernel.models import ActionType
from .tool_specs import ToolSpec


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
    semantic_ready: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    retrieval_intent: RetrievalIntent | None = None
    declare_done: DeclareDoneJustification | None = None
    iteration_summary: Any | None = None

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
    deed_text_artifact_ref: str | None = Field(default=None, max_length=512)
    deed_artifact_ref: str | None = Field(default=None, max_length=512)
    hydrated_deed_artifact_ref: str | None = Field(default=None, max_length=512)
    graph: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_minimum_inputs(self) -> "_DraftIRArgs":
        if not self.dossier_id:
            raise ValueError("draft_ir_requires_dossier_id")
        if (
            not self.deed_text_artifact_ref
            and not self.deed_artifact_ref
            and not self.hydrated_deed_artifact_ref
            and self.graph is None
        ):
            raise ValueError("draft_ir_requires_deed_text_artifact_ref_or_deed_artifact_ref_or_hydrated_deed_artifact_ref_or_graph")
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
    ActionType.OPEN_TEXT_SPANS: _OpenTextSpansArgs,
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
    ActionType.UPSERT_DEED_SPAN_INDEX: _UpsertDeedSpanIndexArgs,
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


_TOOL_REQUIRED_FIELDS: dict[ActionType, list[str]] = {
    ActionType.OPEN_ARTIFACT: ["artifact_ref | artifact_path | corpus_entry_ref"],
    ActionType.OPEN_TEXT_SPANS: ["deed_text_artifact_ref", "span_ids+deed_span_index_ref OR spans[] OR anchors[]"],
    ActionType.HYDRATE_DEED: ["dossier_id | source_entry_ref"],
    ActionType.DRAFT_IR: [
        "dossier_id",
        "deed_text_artifact_ref | deed_artifact_ref | hydrated_deed_artifact_ref | graph",
    ],
    ActionType.RETRIEVE_EVIDENCE: ["query"],
    ActionType.COMPILE: ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"],
    ActionType.JUDGE: ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"],
    ActionType.BUNDLE: ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"],
    ActionType.GEOREFERENCE: ["bundle_artifact_ref | ir_artifact_ref"],
    ActionType.VALIDATE: ["georef_artifact_ref"],
    ActionType.PROPOSE_PATCH: ["ir_artifact_ref"],
    ActionType.UPSERT_DEED_SPAN_INDEX: ["deed_text_artifact_ref", "deed_fingerprint", "upserts[]"],
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
                "action_type": action.value,
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
    action = action_type if isinstance(action_type, ActionType) else coerce_action_type(str(action_type))
    if action is None:
        return {
            "required_fields": ["action_type"],
            "minimal_working_example": {"action_type": "unknown", "args": {}},
            "common_mistakes": ["Use only actions present in tool_menu."],
        }
    example_args = _example_args_for_action(action=action, context_inputs=context_inputs)
    required_fields = list(_TOOL_REQUIRED_FIELDS.get(action, []))
    common_mistakes = _common_mistakes_for_action(action, reason_code=reason_code)
    return {
        "required_fields": required_fields,
        "minimal_working_example": {
            "action_type": action.value,
            "args": example_args,
        },
        "common_mistakes": common_mistakes[:2],
        "iteration_summary_note": (
            "Optional Memory Docket v0: delta-only this-iteration notes; do not recap memory.run_summary_log "
            "or paste deed text."
        ),
    }


def _example_args_for_action(*, action: ActionType, context_inputs: Mapping[str, Any]) -> dict[str, Any]:
    dossier_id = _ctx_str(context_inputs.get("dossier_id")) or "<inputs.dossier_id>"
    deed_ref = _ctx_str(context_inputs.get("deed_text_artifact_ref")) or "<inputs.deed_text_artifact_ref>"
    source_entry_ref = _ctx_str(context_inputs.get("source_entry_ref")) or "<inputs.source_entry_ref>"
    initial_ir_ref = _ctx_str(context_inputs.get("initial_ir_ref"))
    latest_ir_ref = _ctx_str(context_inputs.get("latest_ir_ref"))
    ir_ref = latest_ir_ref or initial_ir_ref or "<ir-artifact-ref>"
    if action == ActionType.OPEN_ARTIFACT:
        return {"artifact_ref": deed_ref}
    if action == ActionType.OPEN_TEXT_SPANS:
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
    if action == ActionType.HYDRATE_DEED:
        return {"dossier_id": dossier_id, "source_entry_ref": source_entry_ref}
    if action == ActionType.DRAFT_IR:
        return {"dossier_id": dossier_id, "deed_text_artifact_ref": deed_ref}
    if action == ActionType.RETRIEVE_EVIDENCE:
        return {"query": "<what you need to find>"}
    if action in {ActionType.COMPILE, ActionType.JUDGE, ActionType.BUNDLE}:
        return {"ir_artifact_ref": ir_ref}
    if action == ActionType.GEOREFERENCE:
        return {"bundle_artifact_ref": "<bundle-artifact-ref>"}
    if action == ActionType.VALIDATE:
        return {"georef_artifact_ref": "<georef-artifact-ref>"}
    if action == ActionType.PROPOSE_PATCH:
        return {"ir_artifact_ref": ir_ref}
    if action == ActionType.UPSERT_DEED_SPAN_INDEX:
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


def _common_mistakes_for_action(action: ActionType, *, reason_code: str | None) -> list[str]:
    generic = [
        "Do not leave args empty when the tool requires fields.",
        "Prefer artifact refs from Context Packet inputs/progress, not inline blobs.",
    ]
    if action == ActionType.OPEN_ARTIFACT:
        return [
            "OPEN_ARTIFACT is for bounded summaries/debug inspection, not verbatim deed recall.",
            "For verbatim deed text, prefer OPEN_TEXT_SPANS.",
        ]
    if action == ActionType.OPEN_TEXT_SPANS:
        return [
            "OPEN_TEXT_SPANS is the canonical verbatim deed recall tool; OPEN_ARTIFACT is summary/debug only.",
            "Use anchors[] to capture a span first, then span_ids + deed_span_index_ref for repeat verification.",
        ]
    if action == ActionType.DRAFT_IR:
        return [
            "DRAFT_IR requires dossier_id plus a deed ref (or an inline graph).",
            "Use inputs.dossier_id and inputs.deed_text_artifact_ref when present.",
        ]
    if action in {ActionType.COMPILE, ActionType.JUDGE, ActionType.BUNDLE}:
        return [
            "Physics tools require an IR artifact ref/path.",
            "Use progress.latest_refs.ir_ref after a successful DRAFT_IR or IR update.",
        ]
    if action == ActionType.RETRIEVE_EVIDENCE:
        return [
            "RETRIEVE_EVIDENCE requires a non-empty query string.",
            "Use retrieval only when it helps resolve a concrete gap or ambiguity.",
        ]
    if action == ActionType.UPSERT_DEED_SPAN_INDEX:
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
