from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from backend.agent_kernel.session import KernelSessionManager
from backend.agent_kernel.tooling import (
    TranscriptAuditTool,
    TranscriptOrientBaselineTool,
    TranscriptEditPlanApplyTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanSeedsSaverTool,
    TranscriptSpanOpenerTool,
)
from backend.agents.transcript_edit.controller import (
    run_transcript_edit_controller_loop,
)
from backend.agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
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
        assert result.reason_code == "tx_agent_closure_requirements_unresolved"


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
        assert result.reason_code == "tx_agent_closure_requirements_unresolved"
        assert result.reason_code != "human_feedback_timeout"
        assert any(isinstance(evt, dict) for evt in progress_events)
        hitl_events = [evt for evt in progress_events if isinstance(evt, dict) and evt.get("event_type") == "human_feedback_needed"]
        assert len(hitl_events) >= 1


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
        assert result.reason_code == "tx_agent_closure_requirements_unresolved"


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
        assert result.reason_code == "tx_agent_closure_requirements_unresolved"


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
        assert any(isinstance(evt, dict) and evt.get("event_type") == "human_feedback_needed" for evt in progress_events)
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
        assert bool(runtime_hitl_state.get("used_human_feedback")) is True
        assert int(runtime_hitl_state.get("feedback_consumed_count") or 0) >= 1


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
