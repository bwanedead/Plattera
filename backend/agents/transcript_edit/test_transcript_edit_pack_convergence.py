from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel.actions import ActionExecutor
from backend.agent_kernel.harness_action_ids import ActionType
from backend.agents.transcript_edit.capabilities import build_transcript_edit_capability_requirements
from backend.agents.transcript_edit.capability_wiring import (
    TranscriptEditMissingCapabilityError,
    build_transcript_edit_capability_wiring,
)
from backend.agents.transcript_edit.execution_translation import compile_transcript_edit_move
from backend.agents.transcript_edit.feedback import integrate_transcript_edit_feedback
from backend.agents.transcript_edit.focus_hydration import build_focus_support_state
from backend.agents.transcript_edit.handoff import build_transcript_edit_handoff_postures
from backend.agents.transcript_edit.manifest import (
    build_transcript_edit_domain_manifest,
    build_transcript_edit_domain_pack_bundle,
)
from backend.harness.orchestration_kernel.contracts import MoveDecision, OrchestratorContext


def test_transcript_edit_manifest_surfaces_are_explicit() -> None:
    manifest = build_transcript_edit_domain_manifest()
    assert manifest.domain_id == "transcript_edit"
    assert manifest.family_id == "mapping"
    assert manifest.display_name == "Transcript Edit"
    assert manifest.compatibility_status == "compatible"

    capabilities = build_transcript_edit_capability_requirements()
    assert [item.capability_id for item in capabilities] == [
        "transcript_orientation",
        "transcript_audit",
        "span_opening",
        "image_evidence",
        "edit_application",
        "feedback_prompting",
        "transcript_promotion",
        "retrieve_evidence",
    ]
    assert [item.posture for item in build_transcript_edit_handoff_postures()] == [
        "no_handoff",
        "ready_for_downstream_domain",
        "blocked_pending_dependency",
        "waiting_on_human",
    ]

    bound = {}

    class _Pack:
        def bind_domain_bundle(self, bundle) -> None:  # type: ignore[no-untyped-def]
            bound["bundle"] = bundle

    bundle = build_transcript_edit_domain_pack_bundle(_Pack())
    assert bundle.manifest.domain_id == "transcript_edit"
    assert bundle.prompt_branch_source_ref == "agents.transcript_edit.prompt_sources"
    assert bound["bundle"] is bundle


def test_transcript_edit_capability_wiring_is_explicit_and_complete() -> None:
    wiring = build_transcript_edit_capability_wiring(
        transcript_auditor=SimpleNamespace(audit_transcript=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/audit.json"}}),
        transcript_orient_baseliner=SimpleNamespace(orient_and_baseline=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/orient.json"}}),
        transcript_span_opener=SimpleNamespace(open_transcript_spans=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/spans.json"}}),
        transcript_image_verifier=SimpleNamespace(verify_transcript_with_image=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/image.json"}}),
        transcript_plan_applier=SimpleNamespace(apply_edit_plan=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/apply.json"}}),
        transcript_span_seeds_saver=SimpleNamespace(save_transcript_span_seeds=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/seeds.json"}}),
        transcript_promoter=SimpleNamespace(promote_transcript_for_mapping=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/promote.json"}}),
        evidence_retriever=SimpleNamespace(retrieve_evidence=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/retrieve.json"}}),
    )

    assert wiring.capability_to_action_ids["transcript_orientation"] == ("tx_orient_and_baseline",)
    assert wiring.capability_to_action_ids["transcript_audit"] == ("tx_audit_transcript",)
    assert wiring.capability_to_action_ids["retrieve_evidence"] == (ActionType.RETRIEVE_EVIDENCE.value,)
    assert wiring.missing_required_capabilities == ()

    bindings = {item.capability_id: item for item in wiring.capability_bindings}
    assert bindings["transcript_orientation"].satisfied is True
    assert bindings["transcript_orientation"].wiring_kind == "provider_action"
    assert bindings["retrieve_evidence"].wiring_kind == "executor_interface"
    assert bindings["feedback_prompting"].wiring_kind == "runtime_seam"
    assert bindings["feedback_prompting"].satisfied is True

    executor = ActionExecutor(deps=wiring.action_executor_deps)
    available_actions = set(executor.available_actions())
    assert ActionType.RETRIEVE_EVIDENCE.value in available_actions
    assert "tx_audit_transcript" in available_actions
    assert "tx_orient_and_baseline" in available_actions
    assert "tx_apply_edit_plan" in available_actions


def test_transcript_edit_capability_wiring_fails_fast_for_missing_required_capability() -> None:
    with pytest.raises(TranscriptEditMissingCapabilityError) as excinfo:
        build_transcript_edit_capability_wiring(
            transcript_auditor=SimpleNamespace(audit_transcript=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/audit.json"}}),
            transcript_orient_baseliner=SimpleNamespace(orient_and_baseline=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/orient.json"}}),
            transcript_span_opener=SimpleNamespace(open_transcript_spans=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/spans.json"}}),
            transcript_image_verifier=SimpleNamespace(verify_transcript_with_image=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/image.json"}}),
            transcript_plan_applier=SimpleNamespace(apply_edit_plan=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/apply.json"}}),
            transcript_span_seeds_saver=SimpleNamespace(save_transcript_span_seeds=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/seeds.json"}}),
            transcript_promoter=SimpleNamespace(promote_transcript_for_mapping=lambda inputs: {"artifact_ref": {"artifact_path": "in-memory://tx/promote.json"}}),
            evidence_retriever=None,
        )

    assert "retrieve_evidence" in str(excinfo.value)


def test_focus_hydration_builds_support_state_without_packet_assembly() -> None:
    support_state = build_focus_support_state(
        decision_key="range",
        ledger_item={
            "key": "range",
            "state": "disputed",
            "label": "Range",
            "mapping_blocking": True,
            "closure_requirement": {
                "mapping_blocking": True,
                "scope_status": "unknown",
                "required_information": "Resolve the range conflict.",
                "minimal_user_action": "Choose the correct range value.",
            },
        },
        closure_requirement={
            "mapping_blocking": True,
            "scope_status": "unknown",
            "required_information": "Resolve the range conflict.",
            "minimal_user_action": "Choose the correct range value.",
        },
        recent_attempts=[{"decision_key": "range", "move": "audit", "outcome": "ok"}],
        span_context=[],
        image_verification={},
        visual_evidence={},
        feedback=None,
        source_completeness="unknown",
        evidence_repeat_guard={"range|repeat": {"count": 1, "last_signal_counter": 0}},
        evidence_signal_counter=0,
        board_item={"materiality": "high", "state": "blocked"},
    )

    brief = support_state["item_context"]
    continuity = support_state["continuity_context"]
    evidence = support_state["evidence_context"]
    posture = support_state["blocker_posture"]

    assert brief["role"] == "sticky_note"
    assert continuity["role"] == "continuity_context"
    assert evidence["role"] == "evidence_context"
    assert posture["understanding_strength"] in {"weak", "moderate", "narrow"}
    assert "support_state" not in support_state
    assert support_state["blocker_posture"]["needs_inventory"] in {True, False}


def test_execution_translation_compiles_apply_edit_plan() -> None:
    request = SimpleNamespace(dossier_id="dossier-1", source_image_refs=[])
    state = SimpleNamespace(
        current_transcript_ref="in-memory://working.json",
        apply_reaudit_baseline_blocking_count=None,
        apply_reaudit_baseline_blocking_signature=None,
        continuity_log=[],
        visual_evidence_by_decision_key={},
        latest_refs={},
        llm_call_seq=0,
        evidence_signal_counter=0,
    )
    pack = SimpleNamespace(
        _request=request,
        _request_id_prefix="req:test",
        _state=state,
        _iter_blocking_count=4,
        _iter_blocking_signature="sig-4",
        _awaiting_apply_outcome=False,
        _pending_lineage_meta=None,
        _loop_model="gpt-5.2",
        _progress_cb=None,
        _iter_planning_findings=[],
        _iter_source_hash="sha256:test",
    )
    context = OrchestratorContext(
        session_manager=SimpleNamespace(),
        session_id="session:test",
        loop_memory=SimpleNamespace(iterations=3, pending_refresh=False),
        request_id_prefix="req:test",
        dossier_id="dossier-1",
    )
    move = MoveDecision(
        move_type="apply_edit_plan",
        focus_key="range",
        rationale="apply",
        domain_move_payload={"edit_plan": {"plan_version": "edit_plan_v0"}, "reason": "apply"},
    )

    plan = compile_transcript_edit_move(pack, context, move)

    assert plan.action_type == "tx_apply_edit_plan"
    assert plan.action_inputs["decision_key"] == "range"
    assert pack._awaiting_apply_outcome is True
    assert pack._pending_lineage_meta["focus_key"] == "range"
    assert state.apply_reaudit_baseline_blocking_count == 4


def test_feedback_integration_marks_pending_feedback_consumed() -> None:
    state = SimpleNamespace(
        pending_feedback_decision_key="range",
        pending_feedback_prompt_id="prompt_range",
        blocker_registry={"rows": []},
        decision_ledger={"items": []},
        latest_feedback=None,
        evidence_signal_counter=0,
        used_human_feedback=False,
        pending_feedback_prompt={"prompt_id": "prompt_range"},
        feedback_received_count=0,
        feedback_consumed_count=0,
        feedback_stale_count=0,
        feedback_superseded_count=0,
        superseded_feedback_prompt_ids=set(),
        hitl_lifecycle_log=[],
        convention_context={},
        current_transcript_ref="in-memory://working.json",
    )
    pack = SimpleNamespace(_state=state)
    context = SimpleNamespace()

    result = integrate_transcript_edit_feedback(
        pack,
        context,  # type: ignore[arg-type]
        {
            "decision_key": "range",
            "prompt_id": "prompt_range",
            "selected_value": "Range 75 West",
            "summary": "feedback integrated",
        },
    )

    assert result.integrated is True
    assert result.integration_summary == "feedback integrated"
    assert state.latest_feedback["selected_value"] == "Range 75 West"
    assert state.pending_feedback_decision_key is None
    assert state.pending_feedback_prompt_id is None
    assert state.used_human_feedback is True
