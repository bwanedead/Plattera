"""Deterministic action executor scaffold for Agent Kernel v0.

Shared core owns built-in harness actions plus the generic provider contract:
provider_actions, provider_step_projectors, and terminal_success_hooks.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from .harness_action_ids import ActionType, canonical_action_id
from .run_artifact import ArtifactRef, RunArtifact, StepRecord, ValidationInline

# Provider-owned post-step seams. Shared core dispatches them mechanically; it does not interpret meaning.
ProviderStepResultProjector = Callable[[RunArtifact, StepRecord], None]
TerminalSuccessHook = Callable[[RunArtifact], None]


def _action_str(action: ActionType | str) -> str:
    return canonical_action_id(action)


def _provider_method(
    provider: object | None,
    method_names: tuple[str, ...],
) -> Callable[[Mapping[str, Any]], Any] | None:
    if provider is None:
        return None
    for method_name in method_names:
        method = getattr(provider, method_name, None)
        if callable(method):
            return method
    return None


@dataclass(frozen=True)
class RegisteredProviderAction:
    """Domain-registered execution handler (Phase 32 — not a harness built-in enum member)."""

    output_key: str
    reason_code: str
    missing_reason: str
    handler: Callable[[Mapping[str, Any]], Any]


class EvidenceRetriever(Protocol):
    """Explicit interface for RETRIEVE_EVIDENCE action execution."""

    def retrieve_evidence(self, inputs: Mapping[str, Any]) -> Any: ...


class ArtifactHydrator(Protocol):
    """Explicit interface for artifact hydration action execution."""

    def hydrate_artifact(self, inputs: Mapping[str, Any]) -> Any: ...


class ArtifactOpener(Protocol):
    """Explicit interface for OPEN_ARTIFACT action execution."""

    def open_artifact(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TextSpanOpener(Protocol):
    """Explicit interface for OPEN_TEXT_SPANS deterministic verbatim extraction."""

    def open_text_spans(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SpanIndexUpserter(Protocol):
    """Explicit interface for artifact span-index persistence."""

    def upsert_artifact_span_index(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ArtifactDraftProposer(Protocol):
    """Explicit interface for artifact draft proposal execution."""

    def draft_artifact(self, inputs: Mapping[str, Any]) -> Any: ...


class ArtifactCompiler(Protocol):
    """Explicit interface for artifact compile action execution."""

    def compile_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class ArtifactJudge(Protocol):
    """Explicit interface for artifact judge action execution."""

    def judge_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class ArtifactBundler(Protocol):
    """Explicit interface for artifact bundle action execution."""

    def bundle_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class ArtifactGeoreferencer(Protocol):
    """Explicit interface for artifact georeference action execution."""

    def georeference_artifact(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class ArtifactValidator(Protocol):
    """Explicit interface for artifact validation action execution."""

    def validate_artifact(self, inputs: Mapping[str, Any]) -> Any: ...


class ArtifactRenderer(Protocol):
    """Explicit interface for artifact render action execution."""

    def render_artifact(self, inputs: Mapping[str, Any]) -> Any: ...


class PatchProposer(Protocol):
    """Explicit interface stub for PROPOSE_PATCH."""

    def propose_patch(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class StatusSummarizer(Protocol):
    """Explicit interface stub for SUMMARIZE_STATUS."""

    def summarize_status(self, inputs: Mapping[str, Any]) -> str: ...


@dataclass(frozen=True)
class ActionExecutorDeps:
    """Dependency bundle for the shared execution/provider contract."""

    artifact_hydrator: ArtifactHydrator | None = None
    artifact_opener: ArtifactOpener | None = None
    text_span_opener: TextSpanOpener | None = None
    artifact_draft_proposer: ArtifactDraftProposer | None = None
    span_index_upserter: SpanIndexUpserter | None = None
    evidence_retriever: EvidenceRetriever | None = None
    artifact_compiler: ArtifactCompiler | None = None
    artifact_judge: ArtifactJudge | None = None
    artifact_bundler: ArtifactBundler | None = None
    artifact_georeferencer: ArtifactGeoreferencer | None = None
    artifact_validator: ArtifactValidator | None = None
    artifact_renderer: ArtifactRenderer | None = None
    patch_proposer: PatchProposer | None = None
    status_summarizer: StatusSummarizer | None = None
    provider_actions: dict[str, RegisteredProviderAction] = field(default_factory=dict)
    provider_step_projectors: dict[str, ProviderStepResultProjector] = field(default_factory=dict)
    terminal_success_hooks: tuple[TerminalSuccessHook, ...] = ()


class ActionExecutor:
    """Executes deterministic actions and explicit LLM stubs."""

    def __init__(self, deps: ActionExecutorDeps | None = None) -> None:
        self._deps = deps or ActionExecutorDeps()

    @property
    def deps(self) -> ActionExecutorDeps:
        """Configured dependency bundle (harness tools + provider registrations)."""
        return self._deps

    def available_actions(self, *, allow_stubbed: bool = False) -> tuple[str, ...]:
        """Return action ids currently available from configured dependencies."""
        actions: list[str] = [ActionType.SET_GRAPH_REQUIREMENTS.value]
        if self._deps.artifact_hydrator is not None or allow_stubbed:
            actions.append(ActionType.HYDRATE_ARTIFACT.value)
        if self._deps.artifact_opener is not None or allow_stubbed:
            actions.append(ActionType.OPEN_ARTIFACT.value)
        if self._deps.text_span_opener is not None or allow_stubbed:
            actions.append(ActionType.OPEN_TEXT_SPANS.value)
        if self._deps.artifact_draft_proposer is not None or allow_stubbed:
            actions.append(ActionType.DRAFT_ARTIFACT.value)
        if self._deps.evidence_retriever is not None or allow_stubbed:
            actions.append(ActionType.RETRIEVE_EVIDENCE.value)
        if self._deps.artifact_compiler is not None or allow_stubbed:
            actions.append(ActionType.COMPILE_ARTIFACT.value)
        if self._deps.artifact_judge is not None or allow_stubbed:
            actions.append(ActionType.JUDGE_ARTIFACT.value)
        if self._deps.artifact_bundler is not None or allow_stubbed:
            actions.append(ActionType.BUNDLE_ARTIFACT.value)
        if self._deps.artifact_georeferencer is not None or allow_stubbed:
            actions.append(ActionType.GEOREFERENCE_ARTIFACT.value)
        if self._deps.artifact_validator is not None or allow_stubbed:
            actions.append(ActionType.VALIDATE_ARTIFACT.value)
        if self._deps.artifact_renderer is not None or allow_stubbed:
            actions.append(ActionType.RENDER_ARTIFACT.value)
        if self._deps.patch_proposer is not None or allow_stubbed:
            actions.append(ActionType.PROPOSE_PATCH.value)
        if self._deps.status_summarizer is not None or allow_stubbed:
            actions.append(ActionType.SUMMARIZE_STATUS.value)
        if self._deps.span_index_upserter is not None or allow_stubbed:
            actions.append(ActionType.UPSERT_ARTIFACT_SPAN_INDEX.value)
        actions.extend(sorted(self._deps.provider_actions.keys()))
        return tuple(actions)

    def execute(self, step_id: str, action: ActionType | str, inputs: Mapping[str, Any]) -> StepRecord:
        action_str = _action_str(action)
        if action_str == ActionType.SET_GRAPH_REQUIREMENTS.value:
            return self._execute_set_graph_requirements(step_id=step_id, inputs=inputs)
        if action_str == ActionType.HYDRATE_ARTIFACT.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="hydrated_artifact_ref",
                reason_code="artifact_hydrated",
                missing_reason="missing_artifact_hydrator_interface",
                execute_fn=_provider_method(
                    self._deps.artifact_hydrator,
                    ("hydrate_artifact", "hydrate_deed"),
                ),
                inputs=inputs,
            )
        if action_str == ActionType.OPEN_ARTIFACT.value:
            return self._execute_open_artifact(step_id=step_id, inputs=inputs)
        if action_str == ActionType.OPEN_TEXT_SPANS.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="opened_text_spans_ref",
                reason_code="spans_opened",
                missing_reason="missing_text_span_opener_interface",
                execute_fn=(
                    self._deps.text_span_opener.open_text_spans
                    if self._deps.text_span_opener is not None
                    else None
                ),
                inputs=inputs,
            )
        if action_str == ActionType.DRAFT_ARTIFACT.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="ir_artifact_ref",
                reason_code="artifact_drafted",
                missing_reason="missing_artifact_draft_proposer_interface",
                execute_fn=_provider_method(
                    self._deps.artifact_draft_proposer,
                    ("draft_artifact", "draft_ir"),
                ),
                inputs=inputs,
            )
        if action_str == ActionType.RETRIEVE_EVIDENCE.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="retrieval_artifact_ref",
                reason_code="evidence_retrieved",
                missing_reason="missing_evidence_retriever_interface",
                execute_fn=(
                    self._deps.evidence_retriever.retrieve_evidence
                    if self._deps.evidence_retriever is not None
                    else None
                ),
                inputs=inputs,
            )
        if action_str == ActionType.COMPILE_ARTIFACT.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="compile_artifact_ref",
                reason_code="compiled",
                missing_reason="missing_compiler_interface",
                execute_fn=_provider_method(
                    self._deps.artifact_compiler,
                    ("compile_artifact", "compile"),
                ),
                inputs=inputs,
            )
        if action_str == ActionType.JUDGE_ARTIFACT.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="judge_artifact_ref",
                reason_code="judged",
                missing_reason="missing_judge_interface",
                execute_fn=_provider_method(
                    self._deps.artifact_judge,
                    ("judge_artifact", "judge"),
                ),
                inputs=inputs,
            )
        if action_str == ActionType.BUNDLE_ARTIFACT.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="bundle_artifact_ref",
                reason_code="bundled",
                missing_reason="missing_bundler_interface",
                execute_fn=_provider_method(
                    self._deps.artifact_bundler,
                    ("bundle_artifact", "bundle"),
                ),
                inputs=inputs,
            )
        if action_str == ActionType.GEOREFERENCE_ARTIFACT.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="georeference_artifact_ref",
                reason_code="georeferenced",
                missing_reason="missing_georeferencer_interface",
                execute_fn=_provider_method(
                    self._deps.artifact_georeferencer,
                    ("georeference_artifact", "georeference"),
                ),
                inputs=inputs,
            )
        if action_str == ActionType.VALIDATE_ARTIFACT.value:
            return self._execute_validate(step_id=step_id, inputs=inputs)
        if action_str == ActionType.RENDER_ARTIFACT.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="render_artifact_ref",
                reason_code="artifact_rendered",
                missing_reason="missing_renderer_interface",
                execute_fn=_provider_method(
                    self._deps.artifact_renderer,
                    ("render_artifact", "render"),
                ),
                inputs=inputs,
            )
        if action_str == ActionType.PROPOSE_PATCH.value:
            return self._execute_propose_patch(step_id=step_id, inputs=inputs)
        if action_str == ActionType.SUMMARIZE_STATUS.value:
            return self._execute_summarize_status(step_id=step_id, inputs=inputs)
        if action_str == ActionType.UPSERT_ARTIFACT_SPAN_INDEX.value:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key="artifact_span_index_ref",
                reason_code="artifact_span_index_saved",
                missing_reason="missing_artifact_span_index_upserter_interface",
                execute_fn=_provider_method(
                    self._deps.span_index_upserter,
                    ("upsert_artifact_span_index",),
                ),
                inputs=inputs,
            )
        spec = self._deps.provider_actions.get(action_str)
        if spec is not None:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action_str,
                output_key=spec.output_key,
                reason_code=spec.reason_code,
                missing_reason=spec.missing_reason,
                execute_fn=spec.handler,
                inputs=inputs,
            )

        return StepRecord(step_id=step_id, action=action_str, inputs=dict(inputs), reason_codes=["unsupported_action"])

    def _execute_set_graph_requirements(self, step_id: str, inputs: Mapping[str, Any]) -> StepRecord:
        graph_payload = inputs.get("graph", {})
        if not isinstance(graph_payload, dict):
            graph_payload = {}

        graph = deepcopy(graph_payload)
        metadata = graph.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            graph["metadata"] = metadata

        global_required = bool(inputs.get("global_placement_required", False))
        metadata["global_placement_required"] = global_required

        updated_ref = _resolve_ir_artifact_ref(inputs)
        reason_codes = ["graph_requirements_set"]
        if updated_ref is None:
            reason_codes.append("missing_updated_ir_ref")

        outputs: dict[str, Any] = {"graph": graph}
        if updated_ref is not None:
            outputs["ir_artifact_ref"] = updated_ref.model_dump(mode="json")

        return StepRecord(
            step_id=step_id,
            action=ActionType.SET_GRAPH_REQUIREMENTS.value,
            inputs=dict(inputs),
            outputs=outputs,
            reason_codes=reason_codes,
        )

    def _execute_artifact_action(
        self,
        step_id: str,
        action: str,
        output_key: str,
        reason_code: str,
        missing_reason: str,
        execute_fn: Any,
        inputs: Mapping[str, Any],
    ) -> StepRecord:
        if execute_fn is None:
            return StepRecord(
                step_id=step_id,
                action=action,
                inputs=dict(inputs),
                reason_codes=[missing_reason],
            )

        raw_result = execute_fn(inputs)
        artifact_ref, reason_codes, outputs_inline = _coerce_artifact_action_result(
            raw_result=raw_result,
            default_reason_code=reason_code,
        )
        outputs: dict[str, Any] = {}
        if artifact_ref is not None:
            outputs[output_key] = artifact_ref.model_dump(mode="json")
        return StepRecord(
            step_id=step_id,
            action=action,
            inputs=dict(inputs),
            outputs=outputs,
            reason_codes=reason_codes,
            outputs_inline=outputs_inline,
        )

    def _execute_validate(self, step_id: str, inputs: Mapping[str, Any]) -> StepRecord:
        if self._deps.artifact_validator is None:
            validation_result = ValidationInline(
                passed=False,
                reason_code="missing_artifact_validator_interface",
                checks={},
            )
            validate_artifact_ref = None
            reason_codes = [validation_result.reason_code or "validation_failed"]
            outputs_inline = None
        else:
            validator = _provider_method(
                self._deps.artifact_validator,
                ("validate_artifact", "validate"),
            )
            if validator is None:
                validation_result = ValidationInline(
                    passed=False,
                    reason_code="missing_artifact_validator_interface",
                    checks={},
                )
                validate_artifact_ref = None
                reason_codes = [validation_result.reason_code or "validation_failed"]
                outputs_inline = None
            else:
                raw_result = validator(inputs)
                validate_artifact_ref = None
                outputs_inline = None
                reason_codes = None
                validation_result = _coerce_validation_inline(raw_result)
                if validation_result is None:
                    validation_result = ValidationInline(
                        passed=False,
                        reason_code="validator_return_invalid",
                        checks={},
                    )
                elif isinstance(raw_result, dict):
                    raw_reason_codes = raw_result.get("reason_codes")
                    if isinstance(raw_reason_codes, list):
                        reason_codes = [str(code) for code in raw_reason_codes if str(code)]
                    outputs_inline = {
                        str(k): v
                        for k, v in raw_result.items()
                        if k not in {"artifact_ref", "reason_codes", "validation_result"}
                    } or None
                if isinstance(raw_result, dict):
                    validate_artifact_ref = _coerce_artifact_ref(raw_result.get("artifact_ref"))
                else:
                    validate_artifact_ref = None
                if reason_codes is None:
                    reason_codes = []

        reason_code = validation_result.reason_code or (
            "validation_passed" if validation_result.passed else "validation_failed"
        )
        if not reason_codes:
            reason_codes = [reason_code]
        outputs: dict[str, Any] = {"validation_ref": "inline"}
        if validate_artifact_ref is not None:
            outputs["validate_artifact_ref"] = validate_artifact_ref.model_dump(mode="json")
        return StepRecord(
            step_id=step_id,
            action=ActionType.VALIDATE_ARTIFACT.value,
            inputs=dict(inputs),
            outputs=outputs,
            reason_codes=reason_codes,
            outputs_inline=outputs_inline,
            validation_result=validation_result,
        )

    def _execute_propose_patch(self, step_id: str, inputs: Mapping[str, Any]) -> StepRecord:
        if self._deps.patch_proposer is None:
            return StepRecord(
                step_id=step_id,
                action=ActionType.PROPOSE_PATCH.value,
                inputs=dict(inputs),
                reason_codes=["missing_patch_proposer_interface"],
                outputs_inline={
                    "stubbed": True,
                    "required_interface": "PatchProposer",
                },
            )

        patch = dict(self._deps.patch_proposer.propose_patch(inputs))
        return StepRecord(
            step_id=step_id,
            action=ActionType.PROPOSE_PATCH.value,
            inputs=dict(inputs),
            reason_codes=["patch_proposed"],
            outputs_inline=patch,
        )

    def _execute_summarize_status(self, step_id: str, inputs: Mapping[str, Any]) -> StepRecord:
        if self._deps.status_summarizer is None:
            return StepRecord(
                step_id=step_id,
                action=ActionType.SUMMARIZE_STATUS.value,
                inputs=dict(inputs),
                reason_codes=["missing_status_summarizer_interface"],
                outputs_inline={
                    "stubbed": True,
                    "required_interface": "StatusSummarizer",
                },
            )

        summary = self._deps.status_summarizer.summarize_status(inputs)
        return StepRecord(
            step_id=step_id,
            action=ActionType.SUMMARIZE_STATUS.value,
            inputs=dict(inputs),
            reason_codes=["status_summarized"],
            outputs_inline={"summary": summary},
        )

    def _execute_open_artifact(self, step_id: str, inputs: Mapping[str, Any]) -> StepRecord:
        if self._deps.artifact_opener is None:
            return StepRecord(
                step_id=step_id,
                action=ActionType.OPEN_ARTIFACT.value,
                inputs=dict(inputs),
                reason_codes=["missing_artifact_opener_interface"],
            )
        payload = dict(self._deps.artifact_opener.open_artifact(inputs))
        raw_reason_codes = payload.get("reason_codes")
        reason_codes = (
            [str(code) for code in raw_reason_codes if str(code)]
            if isinstance(raw_reason_codes, list)
            else ["artifact_opened"]
        )
        raw_ref = payload.get("artifact_ref")
        artifact_ref = _coerce_artifact_ref(raw_ref)
        outputs: dict[str, Any] = {}
        if artifact_ref is not None:
            outputs["opened_artifact_ref"] = artifact_ref.model_dump(mode="json")
        outputs_inline = None
        summary = payload.get("summary")
        if isinstance(summary, str):
            outputs_inline = {"summary": summary[:512]}
        repair_view = payload.get("repair_view")
        if isinstance(repair_view, dict):
            outputs_inline = outputs_inline or {}
            outputs_inline["repair_view"] = repair_view
        return StepRecord(
            step_id=step_id,
            action=ActionType.OPEN_ARTIFACT.value,
            inputs=dict(inputs),
            outputs=outputs,
            reason_codes=reason_codes,
            outputs_inline=outputs_inline,
        )


def _resolve_ir_artifact_ref(inputs: Mapping[str, Any]) -> ArtifactRef | None:
    raw_ref = inputs.get("updated_ir_artifact_ref")
    if isinstance(raw_ref, ArtifactRef):
        return raw_ref
    if isinstance(raw_ref, dict):
        return ArtifactRef.model_validate(raw_ref)
    if isinstance(raw_ref, str) and raw_ref:
        return ArtifactRef(artifact_path=raw_ref)

    raw_path = inputs.get("updated_ir_artifact_path")
    if isinstance(raw_path, str) and raw_path:
        return ArtifactRef(artifact_path=raw_path)

    raw_path = inputs.get("ir_artifact_path")
    if isinstance(raw_path, str) and raw_path:
        return ArtifactRef(artifact_path=raw_path)

    return None


def _coerce_artifact_action_result(
    *,
    raw_result: Any,
    default_reason_code: str,
) -> tuple[ArtifactRef | None, list[str], dict[str, Any] | None]:
    if isinstance(raw_result, dict):
        raw_ref = raw_result.get("artifact_ref")
        artifact_ref = _coerce_artifact_ref(raw_ref)
        raw_reason_codes = raw_result.get("reason_codes")
        reason_codes = [default_reason_code]
        if isinstance(raw_reason_codes, list):
            coerced = [str(code) for code in raw_reason_codes if str(code)]
            if coerced:
                reason_codes = coerced
        outputs_inline = {
            str(k): v
            for k, v in raw_result.items()
            if k not in {"artifact_ref", "reason_codes"}
        } or None
        return artifact_ref, reason_codes, outputs_inline
    if isinstance(raw_result, ArtifactRef):
        return raw_result, [default_reason_code], None
    return None, [default_reason_code], None


def _coerce_artifact_ref(raw_ref: Any) -> ArtifactRef | None:
    if isinstance(raw_ref, ArtifactRef):
        return raw_ref
    if isinstance(raw_ref, dict):
        return ArtifactRef.model_validate(raw_ref)
    if hasattr(raw_ref, "model_dump"):
        dumped = raw_ref.model_dump(mode="json")
        if isinstance(dumped, dict):
            return ArtifactRef.model_validate(dumped)
    if hasattr(raw_ref, "artifact_path"):
        artifact_path = getattr(raw_ref, "artifact_path", None)
        if isinstance(artifact_path, str) and artifact_path:
            card_index = getattr(raw_ref, "card_index", None)
            span_index = getattr(raw_ref, "span_index", None)
            return ArtifactRef(artifact_path=artifact_path, card_index=card_index, span_index=span_index)
    if isinstance(raw_ref, str) and raw_ref:
        return ArtifactRef(artifact_path=raw_ref)
    return None


def _coerce_validation_inline(raw_result: Any) -> ValidationInline | None:
    if isinstance(raw_result, ValidationInline):
        return raw_result
    if hasattr(raw_result, "model_dump"):
        dumped = raw_result.model_dump(mode="json")
        if isinstance(dumped, dict):
            return _coerce_validation_inline(dumped)
    if isinstance(raw_result, dict):
        raw_validation = raw_result.get("validation_result")
        if isinstance(raw_validation, ValidationInline):
            return raw_validation
        if hasattr(raw_validation, "model_dump"):
            dumped = raw_validation.model_dump(mode="json")
            if isinstance(dumped, dict):
                return ValidationInline.model_validate(dumped)
        if isinstance(raw_validation, dict):
            return ValidationInline.model_validate(raw_validation)
        return ValidationInline(
            passed=bool(raw_result.get("passed", False)),
            reason_code=str(raw_result.get("reason_code") or "validation_failed"),
            checks={},
        )
    return None
