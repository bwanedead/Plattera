"""Tests for deterministic action executor scaffold."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import (
    ActionExecutor,
    ActionExecutorDeps,
    ArtifactOpener,
    Bundler,
    Compiler,
    DeedHydrator,
    DraftIRProposer,
    EvidenceRetriever,
    Georeferencer,
    Judge,
    PatchProposer,
    Renderer,
    StatusSummarizer,
    TranscriptAuditor,
    TranscriptOrientBaseliner,
    TranscriptImageVerifier,
    TranscriptSpanOpener,
    TranscriptPlanApplier,
    TranscriptSpanSeedsSaver,
    TranscriptPromoter,
    Validator,
)
from backend.agent_kernel.models import ActionType
from backend.agent_kernel.run_artifact import ArtifactRef, ValidationInline


class _DeterministicServices(
    DeedHydrator,
    ArtifactOpener,
    DraftIRProposer,
    EvidenceRetriever,
    Compiler,
    Judge,
    Bundler,
    Georeferencer,
    Validator,
    Renderer,
    PatchProposer,
    StatusSummarizer,
    TranscriptAuditor,
    TranscriptOrientBaseliner,
    TranscriptImageVerifier,
    TranscriptSpanOpener,
    TranscriptPlanApplier,
    TranscriptSpanSeedsSaver,
    TranscriptPromoter,
):
    def hydrate_deed(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/deed/hydrated-001.json")

    def open_artifact(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {"summary": "opened artifact summary", "reason_codes": ["artifact_opened"]}

    def draft_ir(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/ir/ir-draft-001.json")

    def retrieve_evidence(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/retrieval/retrieval-001.json")

    def compile(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/compile/compile-001.json")

    def judge(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/judge/judge-001.json")

    def bundle(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/bundle/bundle-001.json")

    def georeference(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/georef/georef-001.json")

    def validate(self, inputs: Mapping[str, Any]) -> ValidationInline:
        del inputs
        return ValidationInline(passed=True, reason_code="ok", checks={"error_count": 0})

    def render(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/render/render-001.json")

    def propose_patch(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {"patch": "noop"}

    def summarize_status(self, inputs: Mapping[str, Any]) -> str:
        del inputs
        return "stable"

    def audit_transcript(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {
            "artifact_ref": {"artifact_path": "artifacts/tx/validator-report-001.json"},
            "reason_codes": ["tx_audit_completed"],
            "tx_source_transcript_ref": "artifacts/tx/source-001.json",
            "tx_findings_count": 0,
        }

    def apply_edit_plan(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {
            "artifact_ref": {"artifact_path": "artifacts/tx/apply-report-001.json"},
            "reason_codes": ["tx_apply_completed"],
            "tx_edit_plan_ref": "artifacts/tx/edit-plan-001.json",
            "tx_edited_transcript_ref": "artifacts/tx/edited-001.json",
        }

    def orient_and_baseline(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {
            "artifact_ref": {"artifact_path": "artifacts/tx/orient-baseline-001.json"},
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_orient_items": [{"key": "range", "state": "disputed"}],
        }

    def open_transcript_spans(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {
            "artifact_ref": None,
            "reason_codes": ["tx_spans_opened"],
            "spans": [{"span_id": "s1", "start_char": 0, "end_char": 12, "text": "Beginning at"}],
        }

    def verify_transcript_with_image(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {
            "artifact_ref": {"artifact_path": "artifacts/tx/image-verify-001.json"},
            "reason_codes": ["tx_image_verified"],
            "tx_image_verify_summary": {"total_checks": 1, "mismatch_count": 0, "unclear_count": 0},
        }

    def promote_transcript_for_mapping(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        seeds_ref = inputs.get("tx_span_seeds_ref")
        return {
            "artifact_ref": {"artifact_path": "artifacts/tx/latest_transcript_for_mapping.json"},
            "reason_codes": ["tx_promote_completed"],
            "tx_span_seeds_ref": seeds_ref,
        }

    def save_transcript_span_seeds(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {
            "artifact_ref": {"artifact_path": "artifacts/tx/span-seeds-001.json"},
            "reason_codes": ["tx_span_seeds_saved"],
            "tx_span_seeds_ref": "artifacts/tx/span-seeds-001.json",
        }


def _build_executor() -> ActionExecutor:
    services = _DeterministicServices()
    deps = ActionExecutorDeps(
        deed_hydrator=services,
        artifact_opener=services,
        draft_ir_proposer=services,
        evidence_retriever=services,
        compiler=services,
        judge=services,
        bundler=services,
        georeferencer=services,
        validator=services,
        renderer=services,
        patch_proposer=services,
        status_summarizer=services,
        transcript_auditor=services,
        transcript_orient_baseliner=services,
        transcript_span_opener=services,
        transcript_image_verifier=services,
        transcript_plan_applier=services,
        transcript_span_seeds_saver=services,
        transcript_promoter=services,
    )
    return ActionExecutor(deps=deps)


def test_executor_supports_required_deterministic_actions() -> None:
    executor = _build_executor()
    actions = (
        ActionType.SET_GRAPH_REQUIREMENTS,
        ActionType.HYDRATE_DEED,
        ActionType.OPEN_ARTIFACT,
        ActionType.DRAFT_IR,
        ActionType.RETRIEVE_EVIDENCE,
        ActionType.COMPILE,
        ActionType.JUDGE,
        ActionType.BUNDLE,
        ActionType.GEOREFERENCE,
        ActionType.VALIDATE,
        ActionType.RENDER,
        ActionType.TX_AUDIT_TRANSCRIPT,
        ActionType.TX_ORIENT_AND_BASELINE,
        ActionType.TX_OPEN_TRANSCRIPT_SPANS,
        ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
        ActionType.TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
        ActionType.TX_APPLY_EDIT_PLAN,
        ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
    )

    for index, action in enumerate(actions, start=1):
        step = executor.execute(
            step_id=f"step-{index}",
            action=action,
            inputs={
                "graph": {"metadata": {}},
                "global_placement_required": True,
                "updated_ir_artifact_path": "artifacts/ir/ir-001.json",
            },
        )
        assert step.action == action


def test_set_graph_requirements_updates_metadata_and_records_ir_ref() -> None:
    executor = _build_executor()
    original_graph = {"metadata": {"global_placement_required": False}, "nodes": [{"id": "n1"}]}
    step = executor.execute(
        step_id="set-graph",
        action=ActionType.SET_GRAPH_REQUIREMENTS,
        inputs={
            "graph": original_graph,
            "global_placement_required": True,
            "updated_ir_artifact_path": "artifacts/ir/ir-updated-001.json",
        },
    )

    assert step.outputs["graph"]["metadata"]["global_placement_required"] is True
    assert step.outputs["ir_artifact_ref"]["artifact_path"] == "artifacts/ir/ir-updated-001.json"
    assert original_graph["metadata"]["global_placement_required"] is False


def test_validate_returns_inline_validation_result_only() -> None:
    executor = _build_executor()
    step = executor.execute(
        step_id="validate",
        action=ActionType.VALIDATE,
        inputs={"judge_artifact_path": "artifacts/judge/judge-001.json"},
    )

    assert step.validation_result is not None
    assert step.validation_result.passed is True
    assert step.outputs["validation_ref"] == "inline"
    assert "validation_artifact_ref" not in step.outputs


def test_validate_accepts_validator_payload_with_persisted_artifact_ref() -> None:
    class _ValidatorWithArtifact(Validator):
        def validate(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
            del inputs
            return {
                "artifact_ref": {"artifact_path": "artifacts/validate/validate-001.json"},
                "reason_codes": ["validation_failed"],
                "validation_result": {
                    "passed": False,
                    "reason_code": "validation_failed",
                    "checks": {"top_issues": ["outside section"]},
                },
                "validate_summary": {"passed": False},
            }

    executor = ActionExecutor(deps=ActionExecutorDeps(validator=_ValidatorWithArtifact()))
    step = executor.execute(
        step_id="validate-with-artifact",
        action=ActionType.VALIDATE,
        inputs={"georef_artifact_ref": "artifacts/georef/georef-001.json"},
    )

    assert step.validation_result is not None
    assert step.validation_result.passed is False
    assert step.outputs["validation_ref"] == "inline"
    assert step.outputs["validate_artifact_ref"]["artifact_path"] == "artifacts/validate/validate-001.json"
    assert step.reason_codes == ["validation_failed"]
    assert step.outputs_inline == {"validate_summary": {"passed": False}}


def test_llm_actions_are_stubbed_with_explicit_interfaces() -> None:
    executor = ActionExecutor(deps=ActionExecutorDeps())

    patch_step = executor.execute("patch", ActionType.PROPOSE_PATCH, {"request_id": "req-1"})
    status_step = executor.execute("status", ActionType.SUMMARIZE_STATUS, {"request_id": "req-1"})

    assert patch_step.reason_codes == ["missing_patch_proposer_interface"]
    assert patch_step.outputs_inline["required_interface"] == "PatchProposer"
    assert status_step.reason_codes == ["missing_status_summarizer_interface"]
    assert status_step.outputs_inline["required_interface"] == "StatusSummarizer"


def test_open_artifact_and_draft_ir_have_deterministic_handler_behavior() -> None:
    executor = _build_executor()
    opened = executor.execute(
        "open-artifact",
        ActionType.OPEN_ARTIFACT,
        {"artifact_ref": {"artifact_path": "artifacts/ir/ir-001.json"}},
    )
    drafted = executor.execute(
        "draft-ir",
        ActionType.DRAFT_IR,
        {"deed_text_ref": {"artifact_path": "artifacts/deed/hydrated-001.json"}},
    )

    assert opened.reason_codes == ["artifact_opened"]
    assert opened.outputs_inline is not None
    assert opened.outputs_inline["summary"] == "opened artifact summary"
    assert drafted.outputs["ir_artifact_ref"]["artifact_path"] == "artifacts/ir/ir-draft-001.json"


def test_retrieve_evidence_propagates_reason_codes_from_dependency_payload() -> None:
    class _ReasonCodeRetriever(EvidenceRetriever):
        def retrieve_evidence(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
            del inputs
            return {
                "artifact_ref": None,
                "reason_codes": ["semantic_worker_unavailable"],
            }

    executor = ActionExecutor(deps=ActionExecutorDeps(evidence_retriever=_ReasonCodeRetriever()))
    step = executor.execute("retrieve", ActionType.RETRIEVE_EVIDENCE, {"semantic": True})

    assert step.reason_codes == ["semantic_worker_unavailable"]
    assert step.outputs == {}


def test_new_actions_return_explicit_missing_interface_reason_codes() -> None:
    executor = ActionExecutor(deps=ActionExecutorDeps())
    hydrated = executor.execute("hydrate", ActionType.HYDRATE_DEED, {"dossier_id": "d-1"})
    opened = executor.execute(
        "open",
        ActionType.OPEN_ARTIFACT,
        {"artifact_ref": {"artifact_path": "artifacts/x.json"}},
    )
    drafted = executor.execute("draft", ActionType.DRAFT_IR, {"deed_text": "..."})
    tx_audit = executor.execute("tx-audit", ActionType.TX_AUDIT_TRANSCRIPT, {"source_text": "abc"})
    tx_apply = executor.execute("tx-apply", ActionType.TX_APPLY_EDIT_PLAN, {"edit_plan": {}})
    tx_orient = executor.execute("tx-orient", ActionType.TX_ORIENT_AND_BASELINE, {"source_text": "abc"})
    tx_spans = executor.execute(
        "tx-spans",
        ActionType.TX_OPEN_TRANSCRIPT_SPANS,
        {"source_text": "alpha beta gamma", "spans": [{"start_char": 0, "end_char": 5}]},
    )
    tx_verify = executor.execute(
        "tx-verify",
        ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
        {"source_transcript_ref": "artifacts/tx/source-001.json", "checks": [{"query": "range"}]},
    )
    tx_promote = executor.execute(
        "tx-promote",
        ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
        {"transcript_ref": "artifacts/tx/edited-001.json"},
    )
    tx_span_seeds = executor.execute(
        "tx-seeds",
        ActionType.TX_SAVE_TRANSCRIPT_SPAN_SEEDS,
        {"source_transcript_ref": "artifacts/tx/source-001.json", "source_transcript_hash": "sha256:abc"},
    )

    assert hydrated.reason_codes == ["missing_deed_hydrator_interface"]
    assert opened.reason_codes == ["missing_artifact_opener_interface"]
    assert drafted.reason_codes == ["missing_draft_ir_proposer_interface"]
    assert tx_audit.reason_codes == ["missing_transcript_auditor_interface"]
    assert tx_orient.reason_codes == ["missing_transcript_orient_baseliner_interface"]
    assert tx_spans.reason_codes == ["missing_transcript_span_opener_interface"]
    assert tx_verify.reason_codes == ["missing_transcript_image_verifier_interface"]
    assert tx_apply.reason_codes == ["missing_transcript_plan_applier_interface"]
    assert tx_span_seeds.reason_codes == ["missing_transcript_span_seeds_saver_interface"]
    assert tx_promote.reason_codes == ["missing_transcript_promoter_interface"]
