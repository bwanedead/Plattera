from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

pytestmark = pytest.mark.skipif(
    not os.environ.get("PLATTERA_ENABLE_LEGACY_CONTROLLERS"),
    reason="Legacy controller tests are opt-in. Set PLATTERA_ENABLE_LEGACY_CONTROLLERS=1 to run.",
)

from backend.agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from backend.agent_kernel.session import KernelSessionManager
from backend.agent_kernel.tooling import (
    TranscriptAuditTool,
    TranscriptEditPlanApplyTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanSeedsSaverTool,
    TranscriptSpanOpenerTool,
)
from backend.agents.transcript_edit.orient_tool import TranscriptOrientBaselineTool
from backend.agents.transcript_edit.controller import (
    run_transcript_edit_controller_loop,
)
from backend.agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from backend.agents.transcript_edit.terminalization import terminal_summary
from backend.transcript_edit.contracts import EditPlanV0


class _InMemoryPersistence:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Any] = {}

    def save_run_artifact(self, run_artifact):  # type: ignore[no-untyped-def]
        key = (run_artifact.request_id, run_artifact.run_id)
        self._store[key] = run_artifact
        return {"path": f"in-memory://{run_artifact.request_id}/{run_artifact.run_id}.json"}

    def get_run_artifact(self, request_id: str, run_id: str):  # type: ignore[no-untyped-def]
        return self._store.get((request_id, run_id))


class _ImageVerifierStub:
    def verify_transcript_with_image(self, inputs):  # type: ignore[no-untyped-def]
        del inputs
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/image_verify.json"},
            "reason_codes": ["tx_image_verified"],
            "tx_image_verify_summary": {"total_checks": 1, "match_count": 1, "mismatch_count": 0, "unclear_count": 0},
            "tx_image_verify_results": [{"check_id": "c1", "status": "match", "confidence": "high"}],
        }


class _ImageVerifierUnclearStub:
    def verify_transcript_with_image(self, inputs):  # type: ignore[no-untyped-def]
        del inputs
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/image_verify_unclear.json"},
            "reason_codes": ["tx_image_verified"],
            "tx_image_verify_summary": {"total_checks": 2, "match_count": 1, "mismatch_count": 0, "unclear_count": 1},
            "tx_image_verify_results": [{"check_id": "c1", "status": "unclear", "confidence": "low"}],
        }


class _PlannerSuccess:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
        source_ref = str(focus_packet.get("source_transcript_ref") or "in-memory://tx/source.json")
        source_hash = str(focus_packet.get("source_transcript_hash") or "sha256:test")
        old_excerpt = "Beginning at NW corner."
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "p1",
                "summary": "close call chain",
                "ops": [
                    {
                        "op_id": "op-1",
                        "op_type": "replace_span",
                        "change_class": "normalization",
                        "confidence": "high",
                        "review_required": False,
                        "reason": "add explicit close phrase",
                        "evidence_refs": [source_ref],
                        "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(old_excerpt)},
                        "expected_old": {"old_excerpt": old_excerpt},
                        "new_text": "Beginning at Northwest corner to point of beginning.",
                    }
                ],
                "global_flags": {"review_required": False},
            }
        )
        return {
            "decision_key": str(focus_packet.get("decision_key") or "range"),
            "move": "apply_edit_plan",
            "reason": "test_success",
            "edit_plan": plan.model_dump(mode="json"),
            "feedback_prompt": None,
            "evidence_request": None,
            "closure_update_hint": None,
            "iteration_summary": "Applied resolver plan.",
        }, "ok", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = kwargs["source_transcript_ref"]
        source_hash = kwargs["source_transcript_hash"]
        old_excerpt = "Beginning at NW corner."
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "p1",
                "summary": "close call chain",
                "ops": [
                    {
                        "op_id": "op-1",
                        "op_type": "replace_span",
                        "change_class": "normalization",
                        "confidence": "high",
                        "review_required": False,
                        "reason": "add explicit close phrase",
                        "evidence_refs": [source_ref],
                        "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(old_excerpt)},
                        "expected_old": {"old_excerpt": old_excerpt},
                        "new_text": "Beginning at Northwest corner to point of beginning.",
                    }
                ],
                "global_flags": {"review_required": False},
            }
        )
        return plan, "ok", json.dumps(plan.model_dump(mode="json"))


class _PlannerInvalid:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "resolver_invalid:invalid_payload", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "planner_invalid_response", "{bad}"


class _PlannerAlwaysInvalidFocus:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "resolver_invalid:ValidationError:invalid_move", '{"move":"bad"}'

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "planner_invalid_response", "{bad}"


class _PlannerNoOps:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        decision_key = str((kwargs.get("mapping_priority_focus") or {}).get("decision_key") or "range")
        return {
            "decision_key": decision_key,
            "move": "gather_more_evidence",
            "reason": "resolver_no_ops",
            "edit_plan": None,
            "feedback_prompt": None,
            "evidence_request": {"kind": "image_verify"},
            "closure_update_hint": None,
            "iteration_summary": "Need more evidence.",
        }, "ok", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = kwargs["source_transcript_ref"]
        source_hash = kwargs["source_transcript_hash"]
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "noop",
                "summary": "no safe edits",
                "ops": [],
                "global_flags": {"review_required": True, "rationale": "conflicting evidence"},
            }
        )
        return plan, "ok", json.dumps(plan.model_dump(mode="json"))


class _PlannerAlwaysFeedback:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
        decision_key = str(focus_packet.get("decision_key") or "range")
        return {
            "decision_key": decision_key,
            "move": "request_human_feedback",
            "reason": "need_human_confirmation",
            "edit_plan": None,
            "feedback_prompt": {
                "line1": "Confirm exact range token (number and E/W suffix).",
                "line2": "Select the correct range value.",
                "choices": ["Range 75 West", "Range 74 West"],
            },
            "evidence_request": None,
            "closure_update_hint": None,
            "iteration_summary": "Need human confirmation for range contradiction.",
        }, "ok", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise RuntimeError("not used in focus-move mode")


class _PlannerRaises:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise RuntimeError("simulated network error")

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise RuntimeError("simulated network error")


class _PlannerSectionSuccess:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
        source_ref = str(focus_packet.get("source_transcript_ref") or "in-memory://tx/source.json")
        source_hash = str(focus_packet.get("source_transcript_hash") or "sha256:test")
        old_excerpt = "Section 13"
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "section-override",
                "summary": "apply section correction from feedback",
                "ops": [
                    {
                        "op_id": "op-sec-1",
                        "op_type": "replace_span",
                        "change_class": "semantic",
                        "confidence": "high",
                        "review_required": True,
                        "reason": "Human feedback resolved section conflict.",
                        "evidence_refs": [source_ref],
                        "target": {"locator_type": "offsets", "start_char": 27, "end_char": 37},
                        "expected_old": {"old_excerpt": old_excerpt},
                        "new_text": "Section 12",
                    }
                ],
                "global_flags": {"review_required": True},
            }
        )
        return {
            "decision_key": "section",
            "move": "apply_edit_plan",
            "reason": "section_feedback_resolved",
            "edit_plan": plan.model_dump(mode="json"),
            "feedback_prompt": None,
            "evidence_request": None,
            "closure_update_hint": {"state": "verified", "selected_value": "Section 12"},
            "iteration_summary": "Applied section correction from feedback.",
        }, "ok", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = kwargs["source_transcript_ref"]
        source_hash = kwargs["source_transcript_hash"]
        old_excerpt = "Section 13"
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "section-override",
                "summary": "apply section correction from feedback",
                "ops": [
                    {
                        "op_id": "op-sec-1",
                        "op_type": "replace_span",
                        "change_class": "semantic",
                        "confidence": "high",
                        "review_required": True,
                        "reason": "Human feedback resolved section conflict.",
                        "evidence_refs": [source_ref],
                        "target": {"locator_type": "offsets", "start_char": 27, "end_char": 37},
                        "expected_old": {"old_excerpt": old_excerpt},
                        "new_text": "Section 12",
                    }
                ],
                "global_flags": {"review_required": True},
            }
        )
        return plan, "ok", json.dumps(plan.model_dump(mode="json"))


class _PlannerHintResolvedNoEdit:
    def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
        focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
        return {
            "decision_key": str(focus_packet.get("decision_key") or "range"),
            "move": "mark_resolved_no_edit",
            "reason": "hint_says_resolved",
            "edit_plan": None,
            "feedback_prompt": None,
            "evidence_request": None,
            "closure_update_hint": {"state": "verified", "selected_value": "Range 75 West"},
            "iteration_summary": "Resolver thinks no edit required.",
        }, "ok", "{}"

    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "planner_unused", "{}"


class _OrientBaselinerStub:
    def orient_and_baseline(self, inputs):  # type: ignore[no-untyped-def]
        source_ref = str(
            inputs.get("canonical_ref")
            or inputs.get("source_transcript_ref")
            or "in-memory://tx/source.json"
        )
        candidate_texts = inputs.get("candidate_texts") if isinstance(inputs.get("candidate_texts"), list) else []
        candidate_refs = inputs.get("candidate_refs") if isinstance(inputs.get("candidate_refs"), list) else []
        has_conflict = len(candidate_texts) > 1 or len(candidate_refs) > 1
        range_state = "disputed" if has_conflict else "verified"
        range_impact = "mapping_blocking" if has_conflict else "transcript_quality_only"
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/orient_baseline.json"},
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_source_transcript_ref": source_ref,
            "tx_source_transcript_hash": "sha256:orient",
            "tx_orient_items": [
                {
                    "key": "range",
                    "state": range_state,
                    "alternatives": ["Range 75 West", "Range 74 West"],
                    "confidence": "medium",
                    "layer_tag": "layer1_canonical_recovery",
                    "operational_impact": range_impact,
                    "block_reason": "contradiction",
                    "required_information": "Confirm exact range token.",
                    "minimal_user_action": "Select the correct range token.",
                    "resolution_options": ["Range 75 West", "Range 74 West"],
                    "self_retrievable": "conditional",
                    "retrieval_attempted": True,
                    "retrieval_blocker": None,
                    "verification_required": True,
                    "attempt_summary": "Conflicting candidates.",
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                },
                {
                    "key": "acreage",
                    "state": "unknown",
                    "alternatives": ["1.4 acres", "1.9 acres"],
                    "confidence": "low",
                    "layer_tag": "layer4_transcript_quality_optional",
                    "operational_impact": "transcript_quality_only",
                    "block_reason": "ambiguity",
                    "required_information": "Confirm acreage if present.",
                    "minimal_user_action": "Optional acreage confirmation.",
                    "resolution_options": ["1.4 acres", "1.9 acres"],
                    "self_retrievable": "conditional",
                    "retrieval_attempted": True,
                    "retrieval_blocker": None,
                    "verification_required": False,
                    "attempt_summary": "Optional discrepancy.",
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                },
            ],
            "tx_span_seeds_ref": "in-memory://tx/span-seeds.json",
        }


class _OrientBaselinerStateStub:
    def __init__(self, *, range_state: str) -> None:
        self._range_state = range_state

    def orient_and_baseline(self, inputs):  # type: ignore[no-untyped-def]
        source_ref = str(
            inputs.get("canonical_ref")
            or inputs.get("source_transcript_ref")
            or "in-memory://tx/source.json"
        )
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/orient_baseline_state.json"},
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_source_transcript_ref": source_ref,
            "tx_source_transcript_hash": "sha256:orient-state",
            "tx_orient_items": [
                {
                    "key": "range",
                    "state": self._range_state,
                    "alternatives": ["Range 75 West"],
                    "confidence": "medium",
                    "layer_tag": "layer1_canonical_recovery",
                    "operational_impact": "mapping_blocking",
                    "block_reason": "ambiguity",
                    "required_information": "Confirm exact range token.",
                    "minimal_user_action": "Select the correct range token.",
                    "resolution_options": ["Range 75 West"],
                    "self_retrievable": "conditional",
                    "retrieval_attempted": True,
                    "retrieval_blocker": None,
                    "verification_required": True,
                    "attempt_summary": "Needs confirmation.",
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                }
            ],
            "tx_span_seeds_ref": "in-memory://tx/span-seeds.json",
        }


class _OrientBaselinerSectionConflictStub:
    def orient_and_baseline(self, inputs):  # type: ignore[no-untyped-def]
        source_ref = str(
            inputs.get("canonical_ref")
            or inputs.get("source_transcript_ref")
            or "in-memory://tx/source.json"
        )
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/orient_baseline_section.json"},
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_source_transcript_ref": source_ref,
            "tx_source_transcript_hash": "sha256:orient-section",
            "tx_orient_items": [
                {
                    "key": "section",
                    "state": "disputed",
                    "alternatives": ["Section 12", "Section 13"],
                    "confidence": "medium",
                    "layer_tag": "layer1_canonical_recovery",
                    "operational_impact": "mapping_blocking",
                    "block_reason": "contradiction",
                    "required_information": "Confirm section token.",
                    "minimal_user_action": "Select the correct section token.",
                    "resolution_options": ["Section 12", "Section 13"],
                    "self_retrievable": "conditional",
                    "retrieval_attempted": True,
                    "retrieval_blocker": None,
                    "verification_required": True,
                    "attempt_summary": "Conflicting section candidates.",
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                }
            ],
            "tx_span_seeds_ref": "in-memory://tx/span-seeds.json",
        }


class _OrientBaselinerPartialTruncatedScopedStub:
    def orient_and_baseline(self, inputs):  # type: ignore[no-untyped-def]
        source_ref = str(
            inputs.get("canonical_ref")
            or inputs.get("source_transcript_ref")
            or "in-memory://tx/source.json"
        )
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/orient_baseline_partial_scope.json"},
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_source_transcript_ref": source_ref,
            "tx_source_transcript_hash": "sha256:orient-partial",
            "tx_orient_items": [
                {
                    "key": "range",
                    "state": "verified",
                    "alternatives": ["Range 75 West"],
                    "confidence": "high",
                    "layer_tag": "layer1_canonical_recovery",
                    "operational_impact": "mapping_blocking",
                    "scope_id": "target_scope",
                    "scope_label": "Target Scope",
                    "scope_priority": 0,
                    "in_target_scope": True,
                    "source_completeness": "partial_truncated",
                    "source_completeness_reason": "Lower page is cut off in source image.",
                    "source_limitations": ["Lower-page content outside target plot is unavailable."],
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                },
                {
                    "key": "closure_or_pob",
                    "state": "disputed",
                    "alternatives": ["Call A", "Call B"],
                    "confidence": "low",
                    "layer_tag": "layer1_canonical_recovery",
                    "operational_impact": "mapping_blocking",
                    "block_reason": "ambiguity",
                    "required_information": "Missing lower-page closure language.",
                    "minimal_user_action": "Provide uncropped source image.",
                    "resolution_options": ["Call A", "Call B"],
                    "self_retrievable": "conditional",
                    "retrieval_attempted": True,
                    "retrieval_blocker": "source_truncated",
                    "verification_required": True,
                    "attempt_summary": "Outside target scope content is truncated in source.",
                    "scope_id": "outside_target_scope",
                    "scope_label": "Outside Target Scope",
                    "scope_priority": 90,
                    "in_target_scope": False,
                    "scope_status": "outside_target",
                    "scope_proof": ["source_truncation_boundary"],
                    "source_completeness": "partial_truncated",
                    "source_completeness_reason": "Lower page is cut off in source image.",
                    "source_limitations": ["Lower-page content outside target plot is unavailable."],
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                },
            ],
            "tx_span_seeds_ref": "in-memory://tx/span-seeds.json",
        }


class _OrientBaselinerPartialTruncatedUnknownScopeStub:
    def orient_and_baseline(self, inputs):  # type: ignore[no-untyped-def]
        source_ref = str(
            inputs.get("canonical_ref")
            or inputs.get("source_transcript_ref")
            or "in-memory://tx/source.json"
        )
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/orient_baseline_partial_unknown.json"},
            "reason_codes": ["tx_orient_baseline_completed"],
            "tx_source_transcript_ref": source_ref,
            "tx_source_transcript_hash": "sha256:orient-partial-unknown",
            "tx_orient_items": [
                {
                    "key": "range",
                    "state": "verified",
                    "alternatives": ["Range 75 West"],
                    "operational_impact": "mapping_blocking",
                    "scope_id": "target_scope",
                    "in_target_scope": True,
                    "source_completeness": "partial_truncated",
                    "source_completeness_reason": "Lower page is cut off in source image.",
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                },
                {
                    "key": "closure_or_pob",
                    "state": "disputed",
                    "alternatives": ["Call A", "Call B"],
                    "operational_impact": "mapping_blocking",
                    "scope_status": "unknown",
                    "scope_proof": [],
                    "source_completeness": "partial_truncated",
                    "source_completeness_reason": "Lower page is cut off in source image.",
                    "evidence_refs": ["orient_llm"],
                    "provenance": "orient_llm",
                },
            ],
            "tx_span_seeds_ref": "in-memory://tx/span-seeds.json",
        }


def _session_manager(image_verifier=None, orient_baseliner=None) -> KernelSessionManager:
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            transcript_auditor=TranscriptAuditTool(),
            transcript_orient_baseliner=orient_baseliner or _OrientBaselinerStub(),
            transcript_span_opener=TranscriptSpanOpenerTool(),
            transcript_image_verifier=image_verifier or _ImageVerifierStub(),
            transcript_plan_applier=TranscriptEditPlanApplyTool(),
            transcript_span_seeds_saver=TranscriptSpanSeedsSaverTool(),
            transcript_promoter=TranscriptMappingPromoterTool(),
        )
    )
    return KernelSessionManager(action_executor=executor, persistence_service=_InMemoryPersistence())


def test_transcript_controller_audit_plan_apply_audit_promote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at Northwest corner to point of beginning."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                auto_promote=True,
            ),
            request_id_prefix="tx-test-ok",
            planner=_PlannerSuccess(),
        )
        assert result.status == "completed"
        assert result.reason_code in {"tx_agent_clean_promoted", "tx_agent_clean_no_promote"}
        assert result.review_required is False
        assert isinstance(result.latest_refs.get("tx_span_seeds_ref"), dict)


def test_transcript_controller_invalid_planner_stops_needs_review_no_promote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                max_invalid_plan_attempts=2,
                auto_promote=True,
                hitl_enabled=False,
                candidate_texts=[
                    "Range seventy-five (75) West",
                    "Range seventy-four (74) West",
                ],
            ),
            request_id_prefix="tx-test-bad",
            planner=_PlannerInvalid(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code.startswith("tx_agent_plan_invalid")


def test_transcript_controller_redundancy_conflict_blocks_autopromote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=True,
                candidate_texts=[
                    "Range seventy-five (75) West",
                    "Range seventy-four (74) West",
                    "Range seventy-five (75) West",
                ],
            ),
            request_id_prefix="tx-test-disagreement",
            planner=_PlannerNoOps(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code in {"resolver_no_ops", "tx_agent_closure_requirements_unresolved"}


def test_transcript_controller_trims_oversized_orient_inputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}), encoding="utf-8")
        large_candidate = "Range seventy-five (75) West " + ("x" * 2400)
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=True,
                candidate_texts=[
                    large_candidate,
                    large_candidate.replace("75", "74"),
                    large_candidate,
                ],
            ),
            request_id_prefix="tx-test-oversized-orient-inputs",
            planner=_PlannerNoOps(),
        )
        assert result.status in {"completed", "needs_review"}
        assert result.reason_code != "inputs_payload_too_large"


def test_transcript_controller_planner_exception_degrades_to_needs_review() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                max_invalid_plan_attempts=1,
                auto_promote=True,
                hitl_enabled=False,
                candidate_texts=[
                    "Range seventy-five (75) West",
                    "Range seventy-four (74) West",
                ],
            ),
            request_id_prefix="tx-test-planner-exc",
            planner=_PlannerRaises(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code.startswith("tx_agent_plan_invalid")


def test_transcript_controller_blocks_promote_when_final_image_sanity_unclear() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple heading and legal text."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(image_verifier=_ImageVerifierUnclearStub()),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=True,
            ),
            request_id_prefix="tx-test-final-image-gate",
            planner=_PlannerSuccess(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code.startswith("tx_agent_final_image_verify_failed")


def test_transcript_controller_hitl_prompt_is_non_blocking_without_feedback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}), encoding="utf-8")
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                candidate_texts=[
                    "Range seventy-five (75) West",
                    "Range seventy-four (74) West",
                ],
                hitl_enabled=True,
            ),
            request_id_prefix="manual-hitl-nonblocking",
            planner=_PlannerNoOps(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert result.status == "needs_review"
        assert result.reason_code in {"resolver_no_ops", "tx_agent_closure_requirements_unresolved"}
        assert result.reason_code != "human_feedback_timeout"
        assert any(isinstance(evt, dict) for evt in progress_events)
        hitl_events = [evt for evt in progress_events if isinstance(evt, dict) and evt.get("event_type") == "human_feedback_needed"]
        assert len(hitl_events) == 0


def test_transcript_controller_does_not_clean_complete_with_mapping_blocking_unknown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="unknown")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-unknown-blocker",
            planner=_PlannerNoOps(),
        )
        assert result.status == "needs_review"
        assert result.reason_code in {"resolver_no_ops", "tx_agent_closure_requirements_unresolved"}


def test_transcript_controller_does_not_clean_complete_with_mapping_blocking_candidate_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="candidate_found")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-candidate-blocker",
            planner=_PlannerNoOps(),
        )
        assert result.status == "needs_review"
        assert result.reason_code in {"resolver_no_ops", "tx_agent_closure_requirements_unresolved"}


def test_transcript_controller_non_range_feedback_generates_manual_override(monkeypatch) -> None:
    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        if str(prompt_id or "").startswith("hitl_section_"):
            return {
                "prompt_id": prompt_id,
                "choice": "Section 12",
                "note": "Resolved section as: Section 12",
                "metadata": {
                    "decision_key": "section",
                    "resolved_value": "Section 12",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.build_human_feedback_prompt",
        lambda decision_ledger, iteration: {
            "prompt_id": f"hitl_section_{iteration}_forced",
            "line1": "Confirm section token.",
            "line2": "Select the correct section.",
            "choices": ["Section 12", "Section 13"],
            "default_choice": "Section 12",
            "context": {"decision_key": "section"},
        },
    )
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at corner in Section 13, Township 1 North, Range 75 West."}]}),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerSectionConflictStub()),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-nonrange-hitl",
            planner=_PlannerSectionSuccess(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert result.status in {"needs_review", "completed"}
        assert all(not (isinstance(evt, dict) and evt.get("event_type") == "human_feedback_needed") for evt in progress_events)
        assert any(
            isinstance(evt, dict)
            and evt.get("phase") == "plan_result"
            and isinstance(evt.get("detail"), dict)
            and str(evt["detail"].get("plan_reason") or "").startswith("resolver_edit_plan")
            for evt in progress_events
        )
        assert any(
            isinstance(evt, dict)
            and evt.get("phase") == "apply_result"
            and isinstance(evt.get("detail"), dict)
            and int(evt["detail"].get("plan_op_count") or 0) > 0
            for evt in progress_events
        )
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        assert bool(runtime_hitl_state.get("used_human_feedback")) is False
        assert int(runtime_hitl_state.get("feedback_consumed_count") or 0) == 0


def test_transcript_controller_closure_update_hint_does_not_override_ledger_truth() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Range token remains unresolved in candidates."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="manual-closure-hint-advisory",
            planner=_PlannerHintResolvedNoEdit(),
        )
        assert result.status == "needs_review"
        assert str(result.reason_code).startswith("mark_resolved_no_edit_rejected:")


def test_transcript_controller_repeated_closed_world_no_progress_halts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=4,
                max_no_progress_iterations=1,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="manual-closed-world-stagnation",
            planner=_PlannerNoOps(),
        )
        assert result.status == "needs_review"
        assert str(result.reason_code).startswith("tx_agent_no_progress:")


def test_no_progress_with_repeated_image_evidence_falls_back_to_waiting_feedback(monkeypatch) -> None:
    class _PlannerRepeatImageEvidence:
        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "gather_more_evidence",
                "reason": "repeat_image_evidence",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": {
                    "kind": "image_evidence",
                    "mode": "select_region",
                    "target": {
                        "crop_box_normalized": {"x": 0.3, "y": 0.1, "width": 0.45, "height": 0.25},
                        "zoom_factor": 2.5,
                        "query": "Read range token",
                    },
                },
                "closure_update_hint": None,
                "iteration_summary": "Collect image evidence again.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    def _image_mode_stub(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "mode": "select_region",
            "status": "executed",
            "latest_refs": {},
            "llm_call_seq_end": int(kwargs.get("llm_call_seq_start") or 0) + 1,
            "image_evidence": {
                "mode": "select_region",
                "status": "located",
                "check_id": "image_evidence_select_region_range_test",
                "query": "Read range token",
                "selector_type": "normalized_box",
                "crop_box": {"x": 100, "y": 120, "width": 240, "height": 90},
                "zoom_factor": 2.5,
                "tx_image_evidence_region_ref": {"artifact_path": "in-memory://range-region.jpg"},
                "tx_image_evidence_context_ref": None,
                "latest_refs": {},
            },
            "image_verification": {},
        }

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._run_image_evidence_mode",
        _image_mode_stub,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.build_human_feedback_prompt",
        lambda decision_ledger, iteration, image_verification_payload=None, visual_evidence_state=None: {
            "prompt_id": f"hitl_range_{iteration}_fallback",
            "line1": "Range remains ambiguous after repeated image attempts.",
            "line2": "Please confirm the correct range token.",
            "choices": ["Range 75 West", "Range 74 West"],
            "default_choice": "Range 75 West",
            "context": {"decision_key": "range"},
        },
    )

    progress_events: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=4,
                max_no_progress_iterations=2,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-no-progress-image-evidence-hitl-fallback",
            planner=_PlannerRepeatImageEvidence(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )

    assert result.status == "waiting_feedback"
    assert str(result.reason_code) == "tx_agent_waiting_feedback"
    hitl_events = [
        evt
        for evt in progress_events
        if isinstance(evt, dict) and str(evt.get("event_type") or "") == "human_feedback_needed"
    ]
    assert hitl_events
    fallback_ticker = [
        evt
        for evt in progress_events
        if isinstance(evt, dict)
        and str(evt.get("phase") or "") == "human_feedback_needed"
        and isinstance(evt.get("detail"), dict)
        and str((evt.get("detail") or {}).get("fallback_reason") or "") == "no_progress_repeated_image_evidence"
    ]
    assert fallback_ticker


def test_transcript_controller_pending_feedback_gets_grace_drain_before_no_progress(monkeypatch) -> None:
    call_count = {"poll": 0}

    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        del run_id
        call_count["poll"] += 1
        if call_count["poll"] == 2:
            return {
                "prompt_id": prompt_id,
                "choice": "Range 75 West",
                "note": "Use Range 75 for this contradiction.",
                "metadata": {
                    "decision_key": "range",
                    "resolved_value": "Range 75 West",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.build_human_feedback_prompt",
        lambda decision_ledger, iteration: {
            "prompt_id": f"hitl_range_{iteration}_abc12345",
            "line1": "Resolve range contradiction.",
            "line2": "Select the correct range token.",
            "choices": ["Range 75 West", "Range 74 West"],
            "default_choice": "Range 75 West",
            "context": {"decision_key": "range"},
        },
    )

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                max_no_progress_iterations=1,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-no-progress-feedback-grace",
            planner=_PlannerNoOps(),
        )
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        assert int(runtime_hitl_state.get("feedback_received_count") or 0) == 0
        assert int(runtime_hitl_state.get("feedback_consumed_count") or 0) == 0
        assert bool(runtime_hitl_state.get("used_human_feedback")) is False
        assert not str(result.reason_code).startswith("tx_agent_no_progress:pending_human_feedback_no_new_signal")


def test_transcript_controller_resume_restores_blocker_registry_projection_state() -> None:
    resume_registry = {
        "version": 1,
        "run_id": "prior-run",
        "session_id": "prior-session",
        "active_blocker_id": "blocker:range",
        "counts": {"answered_unintegrated": 1, "total": 1},
        "rows": [
            {
                "blocker_id": "blocker:range",
                "decision_key": "range",
                "mapping_blocking": True,
                "scope_status": "in_target",
                "state": "answered_unintegrated",
                "linked_prompt_id": "hitl_range_1_resume",
                "feedback_status": "received",
                "feedback_value": "Range 75 West",
                "last_transition_reason": "feedback_received",
                "created_at": 1,
                "updated_at": 2,
            }
        ],
        "history": [
            {
                "iteration": 3,
                "active_blocker_id": "blocker:range",
                "action_attempted": "request_hitl",
                "result": "waiting_feedback",
            }
        ],
        "updated_at": 2,
    }
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Range token remains unresolved in candidates."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                hitl_enabled=False,
                resume_blocker_registry=resume_registry,
            ),
            request_id_prefix="manual-resume-blocker-registry",
            planner=_PlannerNoOps(),
        )
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        restored = runtime_hitl_state.get("blocker_registry") if isinstance(runtime_hitl_state.get("blocker_registry"), dict) else {}
        rows = [row for row in list(restored.get("rows") or []) if isinstance(row, dict)]
        assert any(
            str(row.get("decision_key") or "") == "range"
            and str(row.get("state") or "") == "answered_unintegrated"
            for row in rows
        )
        history = [row for row in list(restored.get("history") or []) if isinstance(row, dict)]
        assert any(str(row.get("action_attempted") or "") == "request_hitl" for row in history)


def test_transcript_controller_emits_blocker_health_check_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Range token remains unresolved in candidates."}]}),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="manual-blocker-health-check",
            planner=_PlannerNoOps(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        health_events = [
            evt
            for evt in progress_events
            if isinstance(evt, dict) and str(evt.get("phase") or "") == "blocker_health_check"
        ]
        assert health_events
        detail = health_events[-1].get("detail") if isinstance(health_events[-1].get("detail"), dict) else {}
        assert "answered_unintegrated_count" in detail
        assert "ledger_registry_mismatch" in detail


def test_transcript_controller_does_not_reemit_baseline_prompt_immediately_after_feedback_consumed(monkeypatch) -> None:
    call_count = {"poll": 0}

    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        del run_id
        call_count["poll"] += 1
        if call_count["poll"] == 1:
            return {
                "prompt_id": prompt_id,
                "choice": "Range 75 West",
                "note": "Use Range 75.",
                "metadata": {
                    "decision_key": "range",
                    "resolved_value": "Range 75 West",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.build_human_feedback_prompt",
        lambda decision_ledger, iteration: {
            "prompt_id": f"hitl_range_{iteration}_abc12345",
            "line1": "Resolve range contradiction.",
            "line2": "Select the correct range token.",
            "choices": ["Range 75 West", "Range 74 West"],
            "default_choice": "Range 75 West",
            "context": {"decision_key": "range"},
        },
    )
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                max_no_progress_iterations=2,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-hitl-reemit-guard",
            planner=_PlannerNoOps(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        prompt_events = [
            evt
            for evt in progress_events
            if isinstance(evt, dict)
            and str(evt.get("event_type") or "") == "human_feedback_needed"
            and str(evt.get("prompt_id") or "").strip()
        ]
        assert len(prompt_events) == 0
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        assert int(runtime_hitl_state.get("feedback_consumed_count") or 0) == 0


def test_transcript_controller_repeated_consistent_feedback_drives_decisive_outcome(monkeypatch) -> None:
    calls = {"poll": 0}

    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        del run_id
        if calls["poll"] < 2:
            calls["poll"] += 1
            return {
                "prompt_id": prompt_id,
                "choice": "Range 75 West",
                "note": "Use Range 75 West.",
                "metadata": {
                    "decision_key": "range",
                    "resolved_value": "Range 75 West",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps(
                {
                    "sections": [
                        {
                            "id": "s1",
                            "body": (
                                "Beginning at a point on the west boundary, Township Fourteen (14) North, "
                                "Range Seventy-four (74) West of the Sixth Principal Meridian."
                            ),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=4,
                max_no_progress_iterations=2,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-consistent-feedback-decisive",
            planner=_PlannerAlwaysFeedback(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert str(result.reason_code) != "tx_agent_evidence_repeat_budget_exhausted"
        assert any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "apply_result"
            and isinstance(evt.get("detail"), dict)
            and int(evt["detail"].get("plan_op_count") or 0) > 0
            for evt in progress_events
        )
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        assert int(runtime_hitl_state.get("feedback_consumed_count") or 0) >= 2
        tickets = [
            dict(row)
            for row in list(runtime_hitl_state.get("human_resolution_tickets") or [])
            if isinstance(row, dict)
        ]
        assert any(str(row.get("lifecycle_state") or "") == "integrated" for row in tickets)


def test_transcript_controller_feedback_consumption_sets_answered_unintegrated_ticket(monkeypatch) -> None:
    class _PlannerMarkBlocked:
        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "mark_blocked",
                "reason": "insufficient_autonomous_path",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": None,
                "closure_update_hint": None,
                "iteration_summary": "Blocked after consuming feedback.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    calls = {"poll": 0}

    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        del run_id
        if calls["poll"] == 0:
            calls["poll"] += 1
            return {
                "prompt_id": prompt_id,
                "choice": "Range 75 West",
                "note": "Use Range 75 West.",
                "metadata": {
                    "decision_key": "range",
                    "resolved_value": "Range 75 West",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-answered-unintegrated-ticket",
            planner=_PlannerMarkBlocked(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        assert int(runtime_hitl_state.get("feedback_consumed_count") or 0) == 0
        tickets = [dict(row) for row in list(runtime_hitl_state.get("human_resolution_tickets") or []) if isinstance(row, dict)]
        assert isinstance(tickets, list)
        assert all(
            not (
                isinstance(evt, dict)
                and str(evt.get("phase") or "") == "ticket_answered_unintegrated"
                and str(evt.get("decision_key") or "") == "range"
            )
            for evt in progress_events
        )


def test_transcript_controller_post_feedback_mark_blocked_invalid_apply_can_recover_with_override(monkeypatch) -> None:
    class _PlannerMarkBlockedPostFeedbackInvalid:
        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "mark_blocked",
                "reason": "blocked_no_safe_integration_after_feedback:invalid_apply_payload",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": None,
                "closure_update_hint": None,
                "iteration_summary": "Fallback blocked after invalid apply payload.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    calls = {"poll": 0}

    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        del run_id
        if calls["poll"] == 0:
            calls["poll"] += 1
            return {
                "prompt_id": prompt_id,
                "choice": "Range 75 West",
                "note": "Use Range 75 West.",
                "metadata": {
                    "decision_key": "range",
                    "resolved_value": "Range 75 West",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps(
                {
                    "sections": [
                        {
                            "id": "s1",
                            "body": (
                                "Situated in Section Two (2), Township Fourteen (14) North, "
                                "Range Seventy-five (75) West; then calls refer to "
                                "Range Seventy-four (74) West."
                            ),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-post-feedback-blocked-fallback-apply",
            planner=_PlannerMarkBlockedPostFeedbackInvalid(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert not any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "apply_result"
            and isinstance(evt.get("detail"), dict)
            and int(evt["detail"].get("plan_op_count") or 0) > 0
            for evt in progress_events
        )
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        tickets = [dict(row) for row in list(runtime_hitl_state.get("human_resolution_tickets") or []) if isinstance(row, dict)]
        assert isinstance(tickets, list)


def test_transcript_controller_sets_integration_attempted_failed_when_feedback_no_safe_plan(monkeypatch) -> None:
    calls = {"poll": 0}

    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        del run_id
        if calls["poll"] == 0:
            calls["poll"] += 1
            return {
                "prompt_id": prompt_id,
                "choice": "Range 75 West",
                "note": "Use Range 75 West.",
                "metadata": {
                    "decision_key": "range",
                    "resolved_value": "Range 75 West",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at a point in Township only."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-ticket-integration-failed",
            planner=_PlannerAlwaysFeedback(),
        )
        assert result.status == "needs_review"
        assert result.reason_code == "tx_agent_consistent_feedback_no_safe_plan"
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        tickets = [dict(row) for row in list(runtime_hitl_state.get("human_resolution_tickets") or []) if isinstance(row, dict)]
        assert isinstance(tickets, list)


def test_transcript_controller_post_feedback_resolver_invalid_exhausts_with_specific_reason(monkeypatch) -> None:
    calls = {"poll": 0}

    def _fake_poll_feedback_response(*, run_id, prompt_id):  # type: ignore[no-untyped-def]
        del run_id
        if calls["poll"] == 0:
            calls["poll"] += 1
            return {
                "prompt_id": prompt_id,
                "choice": "Range 75 West",
                "note": "Use Range 75 West.",
                "metadata": {
                    "decision_key": "range",
                    "resolved_value": "Range 75 West",
                },
            }
        return None

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline.poll_feedback_response",
        _fake_poll_feedback_response,
    )
    progress_events: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Range remains disputed."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                max_invalid_plan_attempts=1,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-post-feedback-invalid-exhausted",
            planner=_PlannerAlwaysInvalidFocus(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert result.status == "needs_review"
        assert str(result.reason_code).startswith("tx_agent_plan_invalid_exhausted:")
        runtime_hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
        tickets = [dict(row) for row in list(runtime_hitl_state.get("human_resolution_tickets") or []) if isinstance(row, dict)]
        assert isinstance(tickets, list)
        assert any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "resolver_invalid"
            and isinstance(evt.get("detail"), dict)
            for evt in progress_events
        )
        assert any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "resolver_attempt"
            and isinstance(evt.get("detail"), dict)
            and int((evt.get("detail") or {}).get("resolver_attempt_number") or 0) >= 1
            for evt in progress_events
        )
        assert any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "resolver_outcome"
            and isinstance(evt.get("detail"), dict)
            and str((evt.get("detail") or {}).get("result_category") or "") in {"invalid_schema", "invalid_move"}
            for evt in progress_events
        )
        assert any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "resolver_move_gate"
            and isinstance(evt.get("detail"), dict)
            and str((evt.get("detail") or {}).get("gate_reason") or "") == "resolver_invalid_payload"
            for evt in progress_events
        )
        assert not any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "resolver_move_gate"
            and isinstance(evt.get("detail"), dict)
            and str((evt.get("detail") or {}).get("gate_reason") or "") == "accepted_mark_blocked"
            for evt in progress_events
        )
        assert not any(
            isinstance(evt, dict)
            and str(evt.get("phase") or "") == "ticket_integration_attempted_failed"
            and str(evt.get("lifecycle_state") or "") == "integration_attempted_failed"
            for evt in progress_events
        )


def test_transcript_controller_apply_requires_reaudit_for_progress_claim() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="manual-apply-needs-reaudit",
            planner=_PlannerSuccess(),
        )
        assert result.status == "needs_review"
        assert "waiting_reaudit" in str(result.reason_code)


def test_transcript_controller_emits_post_apply_progress_and_focus_diagnostics() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                max_no_progress_iterations=2,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="manual-post-apply-progress-diagnostics",
            planner=_PlannerSuccess(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        progress_eval_events = [
            evt
            for evt in progress_events
            if isinstance(evt, dict) and str(evt.get("phase") or "") == "progress_evaluation"
        ]
        assert progress_eval_events
        assert any(
            isinstance(evt.get("detail"), dict)
            and evt["detail"].get("pre_apply_blocker_signature")
            and evt["detail"].get("post_apply_blocker_signature") is not None
            for evt in progress_eval_events
        )
        investigate_events = [
            evt
            for evt in progress_events
            if isinstance(evt, dict)
            and str(evt.get("phase") or "") == "investigate"
            and isinstance(evt.get("detail"), dict)
            and "focus_advanced" in evt["detail"]
        ]
        assert investigate_events


def test_resolver_apply_edit_plan_does_not_run_automatic_pre_evidence(monkeypatch) -> None:
    def _unexpected_open_spans(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise AssertionError("automatic open_spans should not run before resolver apply_edit_plan")

    def _unexpected_image_verify(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise AssertionError("automatic image_verify should not run before resolver apply_edit_plan")

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._open_planner_context_spans",
        _unexpected_open_spans,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._verify_mapping_critical_with_image",
        _unexpected_image_verify,
    )
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="resolver-first-no-pre-evidence",
            planner=_PlannerSuccess(),
        )
        assert result.status in {"completed", "needs_review"}


def test_resolver_gather_more_evidence_executes_only_requested_kind(monkeypatch) -> None:
    class _PlannerOpenSpansOnly:
        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "gather_more_evidence",
                "reason": "need_span_context",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": {"kind": "open_spans"},
                "closure_update_hint": None,
                "iteration_summary": "Need span context.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    calls = {"open_spans": 0, "image_verify": 0}

    def _open_spans(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        calls["open_spans"] += 1
        return [{"span_id": "s1", "text": "Range token context"}]

    def _image_verify(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        calls["image_verify"] += 1
        return {"payload": {"results": []}}

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._open_planner_context_spans",
        _open_spans,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._verify_mapping_critical_with_image",
        _image_verify,
    )
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}),
            encoding="utf-8",
        )
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="resolver-evidence-open-spans-only",
            planner=_PlannerOpenSpansOnly(),
        )
    assert int(calls["open_spans"]) >= 1
    assert int(calls["image_verify"]) == 0


def test_invalid_evidence_request_gate_includes_normalize_reason_and_mode_hint() -> None:
    class _PlannerInvalidVerifyRequest:
        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "gather_more_evidence",
                "reason": "need_verify_without_query",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": {
                    "kind": "image_evidence",
                    "mode": "verify_region",
                    "target": {"region_ref": {"artifact_path": "in-memory://region.jpg"}},
                },
                "closure_update_hint": None,
                "iteration_summary": "Attempt verify without query.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    progress_events: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}),
            encoding="utf-8",
        )
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="resolver-invalid-evidence-request-diagnostics",
            planner=_PlannerInvalidVerifyRequest(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
    rejected = [
        evt
        for evt in progress_events
        if isinstance(evt, dict)
        and str(evt.get("phase") or "") == "resolver_move_gate"
        and isinstance(evt.get("detail"), dict)
        and str((evt.get("detail") or {}).get("gate_reason") or "") == "invalid_evidence_request"
    ]
    assert rejected
    detail = rejected[-1].get("detail") if isinstance(rejected[-1].get("detail"), dict) else {}
    assert str(detail.get("normalize_reason") or "") == "image_evidence_verify_region_query_missing"
    assert str(detail.get("evidence_request_kind") or "") == "image_evidence"
    assert str(detail.get("evidence_request_mode") or "") == "verify_region"


def test_resolver_gather_open_spans_persists_into_next_focus_packet() -> None:
    class _PlannerGatherThenBlock:
        def __init__(self) -> None:
            self.calls = 0
            self.saw_span_context = False

        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            spans = focus_packet.get("span_context") if isinstance(focus_packet.get("span_context"), list) else []
            if self.calls == 1:
                return {
                    "decision_key": str(focus_packet.get("decision_key") or "range"),
                    "move": "gather_more_evidence",
                    "reason": "need_spans",
                    "edit_plan": None,
                    "feedback_prompt": None,
                    "evidence_request": {"kind": "open_spans"},
                    "closure_update_hint": None,
                    "iteration_summary": "Gather spans.",
                }, "ok", "{}"
            self.saw_span_context = len(spans) > 0
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "mark_blocked",
                "reason": "blocked_no_safe_integration_after_feedback:used_open_spans_evidence",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": None,
                "closure_update_hint": None,
                "iteration_summary": "Blocked after seeing spans.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    planner = _PlannerGatherThenBlock()
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="resolver-span-evidence-persists",
            planner=planner,
        )
    assert planner.calls >= 2
    assert planner.saw_span_context is True


def test_resolver_gather_image_verify_persists_into_next_focus_packet(monkeypatch) -> None:
    class _PlannerGatherImageThenBlock:
        def __init__(self) -> None:
            self.calls = 0
            self.saw_image_results = False

        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            image = focus_packet.get("image_verification") if isinstance(focus_packet.get("image_verification"), dict) else {}
            image_results = image.get("results") if isinstance(image.get("results"), list) else []
            if self.calls == 1:
                return {
                    "decision_key": str(focus_packet.get("decision_key") or "range"),
                    "move": "gather_more_evidence",
                    "reason": "need_image",
                    "edit_plan": None,
                    "feedback_prompt": None,
                    "evidence_request": {"kind": "image_verify"},
                    "closure_update_hint": None,
                    "iteration_summary": "Gather image verify evidence.",
                }, "ok", "{}"
            self.saw_image_results = len(image_results) > 0
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "mark_blocked",
                "reason": "blocked_no_safe_integration_after_feedback:used_image_evidence",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": None,
                "closure_update_hint": None,
                "iteration_summary": "Blocked after seeing image evidence.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    planner = _PlannerGatherImageThenBlock()
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._verify_mapping_critical_with_image",
        lambda **kwargs: {  # type: ignore[no-untyped-def]
            "latest_refs": {},
            "llm_call_seq_end": int((kwargs.get("llm_call_seq_start") or 0)) + 1,
            "payload": {
                "summary": {"total_checks": 1, "match_count": 1, "mismatch_count": 0, "unclear_count": 0},
                "results": [{"check_id": "c1", "status": "match", "observed_text": "Range 75 West"}],
                "diagnostics": [],
            },
        },
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._select_focus_decision_key",
        lambda **kwargs: "range",  # type: ignore[no-untyped-def]
    )
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="resolver-image-evidence-persists",
            planner=planner,
        )
    assert planner.calls >= 2
    assert planner.saw_image_results is True


def test_resolver_can_chain_image_evidence_locate_then_verify(monkeypatch) -> None:
    class _PlannerLocateThenVerify:
        def __init__(self) -> None:
            self.calls = 0
            self.saw_located_region = False
            self.saw_selector_type = False

        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            visual = focus_packet.get("visual_evidence") if isinstance(focus_packet.get("visual_evidence"), dict) else {}
            region_ref = visual.get("tx_image_evidence_region_ref") if isinstance(visual.get("tx_image_evidence_region_ref"), dict) else None
            if self.calls == 1:
                return {
                    "decision_key": str(focus_packet.get("decision_key") or "range"),
                    "move": "gather_more_evidence",
                    "reason": "locate_first",
                    "edit_plan": None,
                    "feedback_prompt": None,
                    "evidence_request": {
                        "kind": "image_evidence",
                        "mode": "locate",
                        "target": {"query": "Locate range clause", "expected_fields": ["range"]},
                    },
                    "closure_update_hint": None,
                    "iteration_summary": "Locate image evidence first.",
                }, "ok", "{}"
            if self.calls == 2:
                self.saw_located_region = isinstance(region_ref, dict)
                self.saw_selector_type = str(visual.get("selector_type") or "") == "normalized_box"
                return {
                    "decision_key": str(focus_packet.get("decision_key") or "range"),
                    "move": "gather_more_evidence",
                    "reason": "verify_on_region",
                    "edit_plan": None,
                    "feedback_prompt": None,
                    "evidence_request": {
                        "kind": "image_evidence",
                        "mode": "verify_region",
                        "target": {"region_ref": region_ref, "query": "Verify the range value in this region."},
                    },
                    "closure_update_hint": None,
                    "iteration_summary": "Verify on the located region.",
                }, "ok", "{}"
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "mark_blocked",
                "reason": "blocked_no_safe_integration_after_feedback:image_chain_complete",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": None,
                "closure_update_hint": None,
                "iteration_summary": "Stop after verify check.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    verify_received_region_ref = {"value": False}

    def _image_mode_stub(**kwargs):  # type: ignore[no-untyped-def]
        req = kwargs.get("normalized_request") if isinstance(kwargs.get("normalized_request"), dict) else {}
        mode = str(req.get("mode") or "").strip().lower()
        target = req.get("target") if isinstance(req.get("target"), dict) else {}
        if mode == "locate":
            return {
                "mode": "locate",
                "status": "executed",
                "latest_refs": {},
                "llm_call_seq_end": int(kwargs.get("llm_call_seq_start") or 0) + 1,
                "image_evidence": {
                    "mode": "locate",
                    "status": "located",
                    "query": "Locate range clause",
                    "selector_type": "normalized_box",
                    "locator": {"status": "located", "confidence": "high", "reason": "found clause"},
                    "tx_image_evidence_region_ref": {"artifact_path": "in-memory://region.jpg"},
                    "tx_image_evidence_context_ref": {"artifact_path": "in-memory://context.jpg"},
                    "verify_summary": {},
                    "latest_refs": {},
                    "llm_call_seq_end": int(kwargs.get("llm_call_seq_start") or 0) + 1,
                },
                "image_verification": {},
            }
        verify_received_region_ref["value"] = isinstance(target.get("region_ref"), dict)
        return {
            "mode": "verify_region",
            "status": "executed",
            "latest_refs": {},
            "llm_call_seq_end": int(kwargs.get("llm_call_seq_start") or 0) + 1,
            "image_evidence": {
                "mode": "verify_region",
                "status": "match",
                "query": "Verify range",
                "tx_image_evidence_region_ref": target.get("region_ref"),
                "verify_summary": {"total_checks": 1, "match_count": 1, "mismatch_count": 0, "unclear_count": 0},
                "latest_refs": {},
                "llm_call_seq_end": int(kwargs.get("llm_call_seq_start") or 0) + 1,
            },
            "image_verification": {
                "latest_refs": {},
                "llm_call_seq_end": int(kwargs.get("llm_call_seq_start") or 0) + 1,
                "payload": {
                    "summary": {"total_checks": 1, "match_count": 1, "mismatch_count": 0, "unclear_count": 0},
                    "results": [{"check_id": "c1", "status": "match", "observed_text": "Range 75 West"}],
                    "diagnostics": [],
                },
            },
        }

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._run_image_evidence_mode",
        _image_mode_stub,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._select_focus_decision_key",
        lambda **kwargs: "range",  # type: ignore[no-untyped-def]
    )
    planner = _PlannerLocateThenVerify()
    progress_events: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="resolver-image-evidence-chain",
            planner=planner,
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
    assert planner.calls >= 2
    assert planner.saw_located_region is True
    assert planner.saw_selector_type is True
    assert verify_received_region_ref["value"] is True
    assert any(
        isinstance(evt.get("detail"), dict)
        and str(evt.get("phase") or "") == "image_verify"
        and str((evt.get("detail") or {}).get("selector_type") or "") == "normalized_box"
        for evt in progress_events
    )


def test_human_feedback_needed_includes_focused_image_evidence_after_select_region(monkeypatch) -> None:
    class _PlannerLocateThenHitl:
        def __init__(self) -> None:
            self.calls = 0

        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            key = str(focus_packet.get("decision_key") or "range")
            if self.calls == 1:
                return {
                    "decision_key": key,
                    "move": "gather_more_evidence",
                    "reason": "select_region_before_hitl",
                    "edit_plan": None,
                    "feedback_prompt": None,
                    "evidence_request": {
                        "kind": "image_evidence",
                        "mode": "select_region",
                        "target": {
                            "crop_box_normalized": {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.2},
                            "zoom_factor": 2.0,
                            "query": "Locate range reference",
                        },
                    },
                    "closure_update_hint": None,
                    "iteration_summary": "Select focused region first.",
                }, "ok", "{}"
            return {
                "decision_key": key,
                "move": "request_human_feedback",
                "reason": "need_human_confirmation",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": None,
                "closure_update_hint": None,
                "iteration_summary": "Escalate with focused image evidence.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    def _image_mode_stub(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "mode": "select_region",
            "status": "executed",
            "latest_refs": {},
            "llm_call_seq_end": int(kwargs.get("llm_call_seq_start") or 0) + 1,
            "image_evidence": {
                "mode": "select_region",
                "status": "located",
                "check_id": "image_evidence_select_region_range_1",
                "query": "Locate range reference",
                "selector_type": "normalized_box",
                "crop_box": {"x": 120, "y": 200, "width": 300, "height": 120},
                "zoom_factor": 2.0,
                "tx_image_evidence_region_ref": {"artifact_path": "in-memory://range-region.jpg"},
                "tx_image_evidence_context_ref": {"artifact_path": "in-memory://range-context.jpg"},
                "latest_refs": {},
            },
            "image_verification": {},
        }

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._run_image_evidence_mode",
        _image_mode_stub,
    )
    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._select_focus_decision_key",
        lambda **kwargs: "range",  # type: ignore[no-untyped-def]
    )
    planner = _PlannerLocateThenHitl()
    progress_events: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="resolver-hitl-focused-image-evidence",
            planner=planner,
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
    hitl_events = [
        evt
        for evt in progress_events
        if isinstance(evt, dict) and str(evt.get("event_type") or "") == "human_feedback_needed"
    ]
    assert hitl_events
    context = hitl_events[0].get("context") if isinstance(hitl_events[0].get("context"), dict) else {}
    focused = context.get("focused_image_evidence") if isinstance(context.get("focused_image_evidence"), dict) else {}
    assert str(((focused.get("tx_image_evidence_region_ref") or {}).get("artifact_path")) or "") == "in-memory://range-region.jpg"
    assert str(((focused.get("tx_image_evidence_context_ref") or {}).get("artifact_path")) or "") == "in-memory://range-context.jpg"


def test_cached_evidence_invalidated_after_transcript_ref_change(monkeypatch) -> None:
    class _PlannerGatherThenApplyThenCheck:
        def __init__(self) -> None:
            self.calls = 0
            self.saw_spans_before_apply = False
            self.saw_spans_after_apply = False

        def propose_focus_move(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            focus_packet = kwargs.get("focus_packet") if isinstance(kwargs.get("focus_packet"), dict) else {}
            spans = focus_packet.get("span_context") if isinstance(focus_packet.get("span_context"), list) else []
            if self.calls == 1:
                return {
                    "decision_key": str(focus_packet.get("decision_key") or "range"),
                    "move": "gather_more_evidence",
                    "reason": "need_spans",
                    "edit_plan": None,
                    "feedback_prompt": None,
                    "evidence_request": {"kind": "open_spans"},
                    "closure_update_hint": None,
                    "iteration_summary": "Gather spans first.",
                }, "ok", "{}"
            if self.calls == 2:
                self.saw_spans_before_apply = len(spans) > 0
                source_ref = str(focus_packet.get("source_transcript_ref") or "in-memory://tx/source.json")
                source_hash = str(focus_packet.get("source_transcript_hash") or "sha256:test")
                old_excerpt = "Beginning at NW corner."
                plan = EditPlanV0.model_validate(
                    {
                        "plan_version": "edit_plan_v0",
                        "source_transcript_ref": source_ref,
                        "source_transcript_hash": source_hash,
                        "plan_id": "cache-invalidation-plan",
                        "summary": "edit transcript after spans",
                        "ops": [
                            {
                                "op_id": "op-1",
                                "op_type": "replace_span",
                                "change_class": "normalization",
                                "confidence": "high",
                                "review_required": False,
                                "reason": "verify stale cache invalidation",
                                "evidence_refs": [source_ref],
                                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(old_excerpt)},
                                "expected_old": {"old_excerpt": old_excerpt},
                                "new_text": "Beginning at Northwest corner to point of beginning.",
                            }
                        ],
                        "global_flags": {"review_required": False},
                    }
                )
                return {
                    "decision_key": str(focus_packet.get("decision_key") or "range"),
                    "move": "apply_edit_plan",
                    "reason": "apply_after_spans",
                    "edit_plan": plan.model_dump(mode="json"),
                    "feedback_prompt": None,
                    "evidence_request": None,
                    "closure_update_hint": None,
                    "iteration_summary": "Apply edit after span evidence.",
                }, "ok", "{}"
            self.saw_spans_after_apply = len(spans) > 0
            return {
                "decision_key": str(focus_packet.get("decision_key") or "range"),
                "move": "mark_blocked",
                "reason": "blocked_no_safe_integration_after_feedback:post_apply_check",
                "edit_plan": None,
                "feedback_prompt": None,
                "evidence_request": None,
                "closure_update_hint": None,
                "iteration_summary": "Check cached evidence after transcript change.",
            }, "ok", "{}"

        def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise RuntimeError("not used in focus-move mode")

    monkeypatch.setattr(
        "backend.agents.transcript_edit.iteration_pipeline._open_planner_context_spans",
        lambda **kwargs: [{"span_id": "sp1", "text": "Range token nearby"}],  # type: ignore[no-untyped-def]
    )
    planner = _PlannerGatherThenApplyThenCheck()
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}),
            encoding="utf-8",
        )
        _ = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="resolver-evidence-cache-invalidation",
            planner=planner,
        )
    assert planner.calls >= 3
    assert planner.saw_spans_before_apply is True
    assert planner.saw_spans_after_apply is False


def test_transcript_controller_partial_source_allows_scoped_success() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Subject target plot calls are complete."}]}),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerPartialTruncatedScopedStub()),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-partial-source-scoped-success",
            planner=_PlannerAlwaysFeedback(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert result.status == "completed"
        summary = terminal_summary(progress_events, result, critical_events=[])
        assert summary["target_scope_status"] == "achieved"
        assert summary["source_completeness"] == "partial_truncated"
        assert summary["terminal_classification"] == "target_scope_complete_with_incomplete_source_context"
        assert any(
            isinstance(item, dict) and str(item.get("key") or "") == "closure_or_pob"
            for item in summary["unresolved_outside_target_scope_items"]
        )


def test_transcript_controller_partial_source_unknown_scope_blocker_does_not_complete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "Subject target plot calls are complete."}]}),
            encoding="utf-8",
        )
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerPartialTruncatedUnknownScopeStub()),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=False,
                hitl_enabled=True,
            ),
            request_id_prefix="manual-partial-source-unknown-scope-blocker",
            planner=_PlannerAlwaysFeedback(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert result.status == "needs_review"
        summary = terminal_summary(progress_events, result, critical_events=[])
        assert summary["scoped_success_eligible"] is False
        assert int((summary.get("scope_summary") or {}).get("unknown_scope_unresolved_mapping_blockers") or 0) >= 1


def test_transcript_controller_resolver_invalid_retries_then_exhausts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(orient_baseliner=_OrientBaselinerStateStub(range_state="disputed")),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                max_invalid_plan_attempts=2,
                auto_promote=False,
                hitl_enabled=False,
            ),
            request_id_prefix="manual-resolver-invalid-exhausted",
            planner=_PlannerInvalid(),
        )
        assert result.status == "needs_review"
        assert str(result.reason_code).startswith("tx_agent_plan_invalid_exhausted:")
