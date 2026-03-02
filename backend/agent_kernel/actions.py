"""Deterministic action executor scaffold for Agent Kernel v0."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .models import ActionType
from .run_artifact import ArtifactRef, StepRecord, ValidationInline


class EvidenceRetriever(Protocol):
    """Explicit interface for RETRIEVE_EVIDENCE action execution."""

    def retrieve_evidence(self, inputs: Mapping[str, Any]) -> Any: ...


class DeedHydrator(Protocol):
    """Explicit interface for HYDRATE_DEED action execution."""

    def hydrate_deed(self, inputs: Mapping[str, Any]) -> Any: ...


class ArtifactOpener(Protocol):
    """Explicit interface for OPEN_ARTIFACT action execution."""

    def open_artifact(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TextSpanOpener(Protocol):
    """Explicit interface for OPEN_TEXT_SPANS deterministic verbatim extraction."""

    def open_text_spans(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class DeedSpanIndexUpserter(Protocol):
    """Explicit interface for UPSERT_DEED_SPAN_INDEX artifact persistence."""

    def upsert_deed_span_index(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class DraftIRProposer(Protocol):
    """Explicit interface for DRAFT_IR action execution."""

    def draft_ir(self, inputs: Mapping[str, Any]) -> Any: ...


class Compiler(Protocol):
    """Explicit interface for COMPILE action execution."""

    def compile(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class Judge(Protocol):
    """Explicit interface for JUDGE action execution."""

    def judge(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class Bundler(Protocol):
    """Explicit interface for BUNDLE action execution."""

    def bundle(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class Georeferencer(Protocol):
    """Explicit interface for GEOREFERENCE action execution."""

    def georeference(self, inputs: Mapping[str, Any]) -> ArtifactRef: ...


class Validator(Protocol):
    """Explicit interface for VALIDATE action execution."""

    def validate(self, inputs: Mapping[str, Any]) -> Any: ...


class Renderer(Protocol):
    """Explicit interface for RENDER action execution."""

    def render(self, inputs: Mapping[str, Any]) -> Any: ...


class PatchProposer(Protocol):
    """Explicit interface stub for PROPOSE_PATCH."""

    def propose_patch(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class StatusSummarizer(Protocol):
    """Explicit interface stub for SUMMARIZE_STATUS."""

    def summarize_status(self, inputs: Mapping[str, Any]) -> str: ...


class TranscriptAuditor(Protocol):
    """Explicit interface for TX_AUDIT_TRANSCRIPT action execution."""

    def audit_transcript(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TranscriptSpanOpener(Protocol):
    """Explicit interface for TX_OPEN_TRANSCRIPT_SPANS action execution."""

    def open_transcript_spans(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TranscriptImageVerifier(Protocol):
    """Explicit interface for TX_VERIFY_TRANSCRIPT_WITH_IMAGE action execution."""

    def verify_transcript_with_image(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TranscriptPlanApplier(Protocol):
    """Explicit interface for TX_APPLY_EDIT_PLAN action execution."""

    def apply_edit_plan(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TranscriptSpanSeedsSaver(Protocol):
    """Explicit interface for TX_SAVE_TRANSCRIPT_SPAN_SEEDS action execution."""

    def save_transcript_span_seeds(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TranscriptPromoter(Protocol):
    """Explicit interface for TX_PROMOTE_TRANSCRIPT_FOR_MAPPING action execution."""

    def promote_transcript_for_mapping(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ActionExecutorDeps:
    """Dependency bundle for deterministic and LLM-scaffold action execution."""

    deed_hydrator: DeedHydrator | None = None
    artifact_opener: ArtifactOpener | None = None
    text_span_opener: TextSpanOpener | None = None
    draft_ir_proposer: DraftIRProposer | None = None
    deed_span_index_upserter: DeedSpanIndexUpserter | None = None
    evidence_retriever: EvidenceRetriever | None = None
    compiler: Compiler | None = None
    judge: Judge | None = None
    bundler: Bundler | None = None
    georeferencer: Georeferencer | None = None
    validator: Validator | None = None
    renderer: Renderer | None = None
    patch_proposer: PatchProposer | None = None
    status_summarizer: StatusSummarizer | None = None
    transcript_auditor: TranscriptAuditor | None = None
    transcript_span_opener: TranscriptSpanOpener | None = None
    transcript_image_verifier: TranscriptImageVerifier | None = None
    transcript_plan_applier: TranscriptPlanApplier | None = None
    transcript_span_seeds_saver: TranscriptSpanSeedsSaver | None = None
    transcript_promoter: TranscriptPromoter | None = None


class ActionExecutor:
    """Executes deterministic actions and explicit LLM stubs."""

    def __init__(self, deps: ActionExecutorDeps | None = None) -> None:
        self._deps = deps or ActionExecutorDeps()

    def available_actions(self, *, allow_stubbed: bool = False) -> tuple[ActionType, ...]:
        """Return actions currently available from configured dependencies."""
        actions: list[ActionType] = [ActionType.SET_GRAPH_REQUIREMENTS]
        if self._deps.deed_hydrator is not None or allow_stubbed:
            actions.append(ActionType.HYDRATE_DEED)
        if self._deps.artifact_opener is not None or allow_stubbed:
            actions.append(ActionType.OPEN_ARTIFACT)
        if self._deps.text_span_opener is not None or allow_stubbed:
            actions.append(ActionType.OPEN_TEXT_SPANS)
        if self._deps.draft_ir_proposer is not None or allow_stubbed:
            actions.append(ActionType.DRAFT_IR)
        if self._deps.evidence_retriever is not None or allow_stubbed:
            actions.append(ActionType.RETRIEVE_EVIDENCE)
        if self._deps.compiler is not None or allow_stubbed:
            actions.append(ActionType.COMPILE)
        if self._deps.judge is not None or allow_stubbed:
            actions.append(ActionType.JUDGE)
        if self._deps.bundler is not None or allow_stubbed:
            actions.append(ActionType.BUNDLE)
        if self._deps.georeferencer is not None or allow_stubbed:
            actions.append(ActionType.GEOREFERENCE)
        if self._deps.validator is not None or allow_stubbed:
            actions.append(ActionType.VALIDATE)
        if self._deps.renderer is not None or allow_stubbed:
            actions.append(ActionType.RENDER)
        if self._deps.patch_proposer is not None or allow_stubbed:
            actions.append(ActionType.PROPOSE_PATCH)
        if self._deps.status_summarizer is not None or allow_stubbed:
            actions.append(ActionType.SUMMARIZE_STATUS)
        if self._deps.deed_span_index_upserter is not None or allow_stubbed:
            actions.append(ActionType.UPSERT_DEED_SPAN_INDEX)
        if self._deps.transcript_auditor is not None or allow_stubbed:
            actions.append(ActionType.TX_AUDIT_TRANSCRIPT)
        if self._deps.transcript_span_opener is not None or allow_stubbed:
            actions.append(ActionType.TX_OPEN_TRANSCRIPT_SPANS)
        if self._deps.transcript_image_verifier is not None or allow_stubbed:
            actions.append(ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE)
        if self._deps.transcript_span_seeds_saver is not None or allow_stubbed:
            actions.append(ActionType.TX_SAVE_TRANSCRIPT_SPAN_SEEDS)
        if self._deps.transcript_plan_applier is not None or allow_stubbed:
            actions.append(ActionType.TX_APPLY_EDIT_PLAN)
        if self._deps.transcript_promoter is not None or allow_stubbed:
            actions.append(ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING)
        return tuple(actions)

    def execute(self, step_id: str, action: ActionType, inputs: Mapping[str, Any]) -> StepRecord:
        if action == ActionType.SET_GRAPH_REQUIREMENTS:
            return self._execute_set_graph_requirements(step_id=step_id, inputs=inputs)
        if action == ActionType.HYDRATE_DEED:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="hydrated_deed_artifact_ref",
                reason_code="deed_hydrated",
                missing_reason="missing_deed_hydrator_interface",
                execute_fn=(
                    self._deps.deed_hydrator.hydrate_deed if self._deps.deed_hydrator is not None else None
                ),
                inputs=inputs,
            )
        if action == ActionType.OPEN_ARTIFACT:
            return self._execute_open_artifact(step_id=step_id, inputs=inputs)
        if action == ActionType.OPEN_TEXT_SPANS:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
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
        if action == ActionType.DRAFT_IR:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="ir_artifact_ref",
                reason_code="ir_drafted",
                missing_reason="missing_draft_ir_proposer_interface",
                execute_fn=(
                    self._deps.draft_ir_proposer.draft_ir
                    if self._deps.draft_ir_proposer is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.RETRIEVE_EVIDENCE:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
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
        if action == ActionType.COMPILE:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="compile_artifact_ref",
                reason_code="compiled",
                missing_reason="missing_compiler_interface",
                execute_fn=self._deps.compiler.compile if self._deps.compiler is not None else None,
                inputs=inputs,
            )
        if action == ActionType.JUDGE:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="judge_artifact_ref",
                reason_code="judged",
                missing_reason="missing_judge_interface",
                execute_fn=self._deps.judge.judge if self._deps.judge is not None else None,
                inputs=inputs,
            )
        if action == ActionType.BUNDLE:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="bundle_artifact_ref",
                reason_code="bundled",
                missing_reason="missing_bundler_interface",
                execute_fn=self._deps.bundler.bundle if self._deps.bundler is not None else None,
                inputs=inputs,
            )
        if action == ActionType.GEOREFERENCE:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="georeference_artifact_ref",
                reason_code="georeferenced",
                missing_reason="missing_georeferencer_interface",
                execute_fn=(
                    self._deps.georeferencer.georeference
                    if self._deps.georeferencer is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.VALIDATE:
            return self._execute_validate(step_id=step_id, inputs=inputs)
        if action == ActionType.RENDER:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="render_artifact_ref",
                reason_code="rendered",
                missing_reason="missing_renderer_interface",
                execute_fn=self._deps.renderer.render if self._deps.renderer is not None else None,
                inputs=inputs,
            )
        if action == ActionType.PROPOSE_PATCH:
            return self._execute_propose_patch(step_id=step_id, inputs=inputs)
        if action == ActionType.SUMMARIZE_STATUS:
            return self._execute_summarize_status(step_id=step_id, inputs=inputs)
        if action == ActionType.UPSERT_DEED_SPAN_INDEX:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="deed_span_index_ref",
                reason_code="deed_span_index_saved",
                missing_reason="missing_deed_span_index_upserter_interface",
                execute_fn=(
                    self._deps.deed_span_index_upserter.upsert_deed_span_index
                    if self._deps.deed_span_index_upserter is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.TX_AUDIT_TRANSCRIPT:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="tx_validator_report_ref",
                reason_code="tx_audit_completed",
                missing_reason="missing_transcript_auditor_interface",
                execute_fn=(
                    self._deps.transcript_auditor.audit_transcript
                    if self._deps.transcript_auditor is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.TX_OPEN_TRANSCRIPT_SPANS:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="tx_open_spans_ref",
                reason_code="tx_spans_opened",
                missing_reason="missing_transcript_span_opener_interface",
                execute_fn=(
                    self._deps.transcript_span_opener.open_transcript_spans
                    if self._deps.transcript_span_opener is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="tx_image_verify_ref",
                reason_code="tx_image_verified",
                missing_reason="missing_transcript_image_verifier_interface",
                execute_fn=(
                    self._deps.transcript_image_verifier.verify_transcript_with_image
                    if self._deps.transcript_image_verifier is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.TX_APPLY_EDIT_PLAN:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="tx_apply_report_ref",
                reason_code="tx_apply_completed",
                missing_reason="missing_transcript_plan_applier_interface",
                execute_fn=(
                    self._deps.transcript_plan_applier.apply_edit_plan
                    if self._deps.transcript_plan_applier is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.TX_SAVE_TRANSCRIPT_SPAN_SEEDS:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="tx_span_seeds_ref",
                reason_code="tx_span_seeds_saved",
                missing_reason="missing_transcript_span_seeds_saver_interface",
                execute_fn=(
                    self._deps.transcript_span_seeds_saver.save_transcript_span_seeds
                    if self._deps.transcript_span_seeds_saver is not None
                    else None
                ),
                inputs=inputs,
            )
        if action == ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING:
            return self._execute_artifact_action(
                step_id=step_id,
                action=action,
                output_key="tx_mapping_pointer_ref",
                reason_code="tx_promote_completed",
                missing_reason="missing_transcript_promoter_interface",
                execute_fn=(
                    self._deps.transcript_promoter.promote_transcript_for_mapping
                    if self._deps.transcript_promoter is not None
                    else None
                ),
                inputs=inputs,
            )

        return StepRecord(step_id=step_id, action=action, inputs=dict(inputs), reason_codes=["unsupported_action"])

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
            action=ActionType.SET_GRAPH_REQUIREMENTS,
            inputs=dict(inputs),
            outputs=outputs,
            reason_codes=reason_codes,
        )

    def _execute_artifact_action(
        self,
        step_id: str,
        action: ActionType,
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
        if self._deps.validator is None:
            validation_result = ValidationInline(
                passed=False,
                reason_code="missing_validator_interface",
                checks={},
            )
            validate_artifact_ref = None
            reason_codes = [validation_result.reason_code or "validation_failed"]
            outputs_inline = None
        else:
            raw_result = self._deps.validator.validate(inputs)
            validate_artifact_ref = None
            outputs_inline = None
            reason_codes = None
            if isinstance(raw_result, ValidationInline):
                validation_result = raw_result
            elif isinstance(raw_result, dict):
                raw_validation = raw_result.get("validation_result")
                if isinstance(raw_validation, ValidationInline):
                    validation_result = raw_validation
                elif isinstance(raw_validation, dict):
                    validation_result = ValidationInline.model_validate(raw_validation)
                else:
                    validation_result = ValidationInline(
                        passed=bool(raw_result.get("passed", False)),
                        reason_code=str(raw_result.get("reason_code") or "validation_failed"),
                        checks={},
                    )
                validate_artifact_ref = _coerce_artifact_ref(raw_result.get("artifact_ref"))
                raw_reason_codes = raw_result.get("reason_codes")
                if isinstance(raw_reason_codes, list):
                    reason_codes = [str(code) for code in raw_reason_codes if str(code)]
                outputs_inline = {
                    str(k): v
                    for k, v in raw_result.items()
                    if k not in {"artifact_ref", "reason_codes", "validation_result"}
                } or None
            else:
                validation_result = ValidationInline(
                    passed=False,
                    reason_code="validator_return_invalid",
                    checks={},
                )
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
            action=ActionType.VALIDATE,
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
                action=ActionType.PROPOSE_PATCH,
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
            action=ActionType.PROPOSE_PATCH,
            inputs=dict(inputs),
            reason_codes=["patch_proposed"],
            outputs_inline=patch,
        )

    def _execute_summarize_status(self, step_id: str, inputs: Mapping[str, Any]) -> StepRecord:
        if self._deps.status_summarizer is None:
            return StepRecord(
                step_id=step_id,
                action=ActionType.SUMMARIZE_STATUS,
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
            action=ActionType.SUMMARIZE_STATUS,
            inputs=dict(inputs),
            reason_codes=["status_summarized"],
            outputs_inline={"summary": summary},
        )

    def _execute_open_artifact(self, step_id: str, inputs: Mapping[str, Any]) -> StepRecord:
        if self._deps.artifact_opener is None:
            return StepRecord(
                step_id=step_id,
                action=ActionType.OPEN_ARTIFACT,
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
            action=ActionType.OPEN_ARTIFACT,
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
    if isinstance(raw_ref, str) and raw_ref:
        return ArtifactRef(artifact_path=raw_ref)
    return None
