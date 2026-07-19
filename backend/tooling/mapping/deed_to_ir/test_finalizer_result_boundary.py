"""Boundary tests: finalizer results must not name retired prepare/publish actions."""

from __future__ import annotations

import json

from tooling.mapping.deed_to_ir.finalizer_result_boundary import (
    CANONICAL_FINALIZER_ACTION,
    SUBMIT_IR_FOR_MAPPING_ACTION,
    normalize_finalizer_agent_visible_result,
    route_finalizer_next_action,
)


def _assert_no_retired_action_ids(result: dict) -> None:
    serialized = json.dumps(result, sort_keys=True)
    assert "prepare_deed_to_ir_final_package" not in serialized
    assert "publish_deed_to_ir_output" not in serialized


def _assert_no_retired_workflow_directives(result: dict) -> None:
    """Agent-visible result must not teach prepare/publish preview workflow in prose."""
    _assert_no_retired_action_ids(result)
    serialized = json.dumps(result, sort_keys=True).lower()
    forbidden = (
        "prepare or publish",
        "prepare and publish",
        "retry publish",
        "retry prepare",
        "prepare a new final package preview",
        "same preview ref",
        "same final_package_preview_ref",
        "retry the same final_package_preview_ref",
        "publish with the same",
        "from a fresh preview",
        "prepare a preview",
        "publish a preview",
    )
    for needle in forbidden:
        assert needle not in serialized, needle


def test_route_table_covers_required_reason_classes():
    assert (
        route_finalizer_next_action(
            reason_code="missing_finalization_decisions",
            retryable=True,
        )
        == CANONICAL_FINALIZER_ACTION
    )
    assert (
        route_finalizer_next_action(
            reason_code="finalization_session_stale",
            retryable=True,
        )
        == SUBMIT_IR_FOR_MAPPING_ACTION
    )
    assert (
        route_finalizer_next_action(
            reason_code="finalization_requires_hitl",
            retryable=True,
        )
        is None
    )
    assert (
        route_finalizer_next_action(
            reason_code="finalization_requirements_capacity_exceeded",
            retryable=False,
        )
        is None
    )
    assert (
        route_finalizer_next_action(
            reason_code="some_unknown_internal_failure",
            retryable=True,
        )
        is None
    )


def test_normalize_hitl_does_not_steer_back_to_finalizer():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "finalization_requires_hitl",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "finalization_status": "pending_decisions",
            "repair_hint": "Wait for human resolution of needs_hitl correction dispositions.",
            "expected_next": "finalize_current_deed_to_ir_output",
            "next_required_action": "finalize_current_deed_to_ir_output",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert "next_required_action" not in outputs
    assert "expected_next" not in outputs
    assert "needs_hitl" in outputs["repair_hint"]
    _assert_no_retired_action_ids(result)


def test_normalize_stale_session_routes_to_submit():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "finalization_session_stale",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "repair_hint": "Finalization session is stale. Remap the latest IR, then retry.",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert outputs["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert outputs["expected_next"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert outputs["repair_hint"] == (
        f"Submit the current IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
    )
    _assert_no_retired_workflow_directives(result)


def test_normalize_invalid_session_routes_to_submit():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "finalization_session_invalid",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "repair_hint": (
                "Persisted finalization decisions are invalid. "
                "Call prepare_deed_to_ir_final_package after remapping."
            ),
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert outputs["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert outputs["expected_next"] == SUBMIT_IR_FOR_MAPPING_ACTION
    _assert_no_retired_action_ids(result)
    assert outputs["repair_hint"] == (
        f"Submit the current IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
    )


def test_normalize_lineage_mismatch_preserves_remap_prerequisite():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "mapping_ir_lineage_mismatch",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": "mapping_ir_lineage_mismatch",
                "message": "Remap then call prepare_deed_to_ir_final_package.",
            },
            "repair_hint": (
                "Submit IR for mapping, then call prepare_deed_to_ir_final_package "
                "with use_current_mapping_lineage=true."
            ),
            "expected_next": "prepare_deed_to_ir_final_package",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    _assert_no_retired_action_ids(result)
    assert result["outputs"]["expected_next"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert result["outputs"]["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert result["outputs"]["repair_hint"] == (
        f"Submit the expected IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
    )


def test_normalize_missing_decisions_routes_to_finalizer():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "missing_finalization_decisions",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "missing": {"scope_ids": ["scope_a"]},
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert outputs["next_required_action"] == CANONICAL_FINALIZER_ACTION
    assert outputs["expected_next"] == CANONICAL_FINALIZER_ACTION
    assert outputs["missing"]["scope_ids"] == ["scope_a"]


def test_normalize_preview_ready_publication_failure_routes_to_finalizer():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "publish_posture_audit_gate",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "finalization_status": "preview_ready",
            "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
            "working_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
            "preview_ready_summary": {
                "expected_next": "publish_deed_to_ir_output",
            },
            "repair_hint": "Patch posture then retry publish_deed_to_ir_output.",
            "expected_next": "publish_deed_to_ir_output",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert outputs["final_package_preview_ref"] == "deed_to_ir:final_package_preview:rev:0001"
    assert "working_preview_ref" not in outputs
    assert "preview_ready_summary" not in outputs
    assert outputs["next_required_action"] == CANONICAL_FINALIZER_ACTION
    assert outputs["expected_next"] == CANONICAL_FINALIZER_ACTION
    assert outputs["repair_hint"] == (
        f"Patch readiness/audit posture if warranted, then retry "
        f"{CANONICAL_FINALIZER_ACTION} without decision mutations."
    )
    _assert_no_retired_workflow_directives(result)


def test_normalize_scrubs_publish_refusal_and_strips_legacy_cards():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "publish_posture_audit_gate",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "repair_hint": "Patch posture then retry publish_deed_to_ir_output.",
            "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
            "finalization_decision_card": {"required_lanes": ["scope_dispositions"]},
            "retry_package_shell": {"mapping_artifact_ref": "feature_graph:mapping:x"},
            "correction_contract_ref": "deed_to_ir:correction_contract",
            "recommended_publish_request": {
                "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001"
            },
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert "finalization_decision_card" not in outputs
    assert "retry_package_shell" not in outputs
    assert "correction_contract_ref" not in outputs
    assert "recommended_publish_request" not in outputs
    _assert_no_retired_workflow_directives(result)
    assert outputs["final_package_preview_ref"] == "deed_to_ir:final_package_preview:rev:0001"
    assert outputs["next_required_action"] == CANONICAL_FINALIZER_ACTION
    assert outputs["repair_hint"] == (
        f"Patch readiness/audit posture if warranted, then retry "
        f"{CANONICAL_FINALIZER_ACTION} without decision mutations."
    )


def test_normalize_preserves_non_retryable_invariant_without_next_action():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "finalization_requirements_capacity_exceeded",
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": "finalization_requirements_capacity_exceeded",
                "message": "Capacity exceeded.",
            },
            "next_required_action": "finalize_current_deed_to_ir_output",
            "expected_next": "finalize_current_deed_to_ir_output",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    assert result["refusal"]["retryable"] is False
    assert result["refusal"]["blocked_by_invariant"] is True
    assert "next_required_action" not in result["outputs"]
    assert "expected_next" not in result["outputs"]


def test_normalize_unknown_retryable_omits_synthetic_next_action():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "unexpected_internal_prepare_failure",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "repair_hint": "Internal prepare failed; inspect observability.",
            "expected_next": "prepare_deed_to_ir_final_package",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert "next_required_action" not in outputs
    assert "expected_next" not in outputs
    assert outputs["repair_hint"] == "Internal prepare failed; inspect observability."
    _assert_no_retired_action_ids(result)


def test_normalize_unknown_omits_connector_fragment_repair_hint():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "unexpected_internal_prepare_failure",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {"code": "unexpected_internal_prepare_failure", "message": "boom"},
            "repair_hint": (
                "Call prepare_deed_to_ir_final_package, then publish_deed_to_ir_output."
            ),
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    assert "repair_hint" not in result["outputs"]
    _assert_no_retired_workflow_directives(result)


def test_normalize_strips_published_complete_run_routing():
    raw = {
        "executed": True,
        "artifact_refs": ["deed_to_ir:output"],
        "outputs": {
            "finalization_status": "published",
            "next_required_action": "complete_run",
            "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
            "output_revision_ref": "deed_to_ir:output:rev:0001",
            "final_output_summary": {"ready_for_completion_candidate": True},
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    assert "next_required_action" not in result["outputs"]
    assert "expected_next" not in result["outputs"]
    _assert_no_retired_action_ids(result)


def test_missing_decisions_keeps_missing_and_session_without_carry_forward():
    session = {
        "status": "pending_decisions",
        "mapping_artifact_ref": "feature_graph:mapping:x",
        "expected_ir_artifact_ref": "feature_graph:ir:v1",
        "lineage_fingerprint": "fp-1",
    }
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "missing_finalization_decisions",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "missing": {"scope_ids": ["scope_a"], "dependency_ids": ["dep_1"]},
            "active_finalization_session": session,
            "finalization_decision_card": {"required_lanes": ["scope_dispositions"]},
            "retry_request_template": {"scope_dispositions": []},
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert outputs["missing"]["scope_ids"] == ["scope_a"]
    assert outputs["active_finalization_session"]["mapping_artifact_ref"] == (
        "feature_graph:mapping:x"
    )
    assert "prompt_carry_forward" not in outputs
    assert "finalization_decision_card" not in outputs
    assert "retry_request_template" not in outputs
    assert outputs["next_required_action"] == CANONICAL_FINALIZER_ACTION
    assert outputs["expected_next"] == CANONICAL_FINALIZER_ACTION
    _assert_no_retired_action_ids(result)


def test_remap_refusal_preserves_session_without_carry_forward():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "mapping_ir_lineage_mismatch",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "active_finalization_session": {
                "status": "stale",
                "mapping_artifact_ref": "feature_graph:mapping:x",
            },
            "repair_hint": (
                "Submit IR for mapping, then call prepare_deed_to_ir_final_package."
            ),
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert "prompt_carry_forward" not in outputs
    assert outputs["active_finalization_session"]["mapping_artifact_ref"] == (
        "feature_graph:mapping:x"
    )
    assert outputs["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert outputs["expected_next"] == SUBMIT_IR_FOR_MAPPING_ACTION
    _assert_no_retired_action_ids(result)


def test_hitl_refusal_keeps_session_and_drops_tool_next_actions():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "finalization_requires_hitl",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "active_finalization_session": {
                "status": "pending_decisions",
                "mapping_artifact_ref": "feature_graph:mapping:x",
            },
            "repair_hint": "Wait for human resolution of needs_hitl correction dispositions.",
            "next_required_action": "prepare_deed_to_ir_final_package",
            "expected_next": "publish_deed_to_ir_output",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert "prompt_carry_forward" not in outputs
    assert outputs["active_finalization_session"]["status"] == "pending_decisions"
    assert "next_required_action" not in outputs
    assert "expected_next" not in outputs
    _assert_no_retired_action_ids(result)


def test_unknown_retryable_removes_tool_next_actions_without_carry_wrapper():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "unexpected_internal_prepare_failure",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {"code": "unexpected_internal_prepare_failure", "message": "boom"},
            "next_required_action": "finalize_current_deed_to_ir_output",
            "expected_next": "submit_ir_for_mapping",
            "repair_hint": (
                "Call prepare_deed_to_ir_final_package, then publish_deed_to_ir_output."
            ),
            "finalization_decision_card": {"required_lanes": ["scope_dispositions"]},
            "retry_request_template": {"use_current_mapping_lineage": True},
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    _assert_no_retired_workflow_directives(result)
    outputs = result["outputs"]
    assert "prompt_carry_forward" not in outputs
    assert "next_required_action" not in outputs
    assert "expected_next" not in outputs
    assert "repair_hint" not in outputs
    assert "finalization_decision_card" not in outputs
    assert "retry_request_template" not in outputs


def test_non_retryable_removes_tool_next_actions_without_carry_wrapper():
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "finalization_requirements_capacity_exceeded",
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": "finalization_requirements_capacity_exceeded",
                "message": "Capacity exceeded after prepare_deed_to_ir_final_package.",
            },
            "next_required_action": "finalize_current_deed_to_ir_output",
            "expected_next": "submit_ir_for_mapping",
            "blocked_action_id": "prepare_deed_to_ir_final_package",
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    _assert_no_retired_workflow_directives(result)
    assert "prompt_carry_forward" not in result["outputs"]
    assert "next_required_action" not in result["outputs"]
    assert "expected_next" not in result["outputs"]
    assert "blocked_action_id" not in result["outputs"]


def test_prepare_compatibility_strips_decision_card_without_carry_wrapper():
    """Internal prepare may emit decision cards; finalizer boundary must strip them."""
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "missing_finalization_decisions",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "missing": {"scope_ids": ["parcel_1"]},
            "active_finalization_session": {
                "status": "pending_decisions",
                "mapping_artifact_ref": "feature_graph:mapping:m1",
            },
            "finalization_decision_card": {
                "required_lanes": ["scope_dispositions"],
                "dependency_decisions": [{"candidate_id": "dep_1"}],
            },
            "retry_request_template": {
                "use_current_mapping_lineage": True,
                "correction_decisions": [{"target_entity_id": "p1_call2_distance"}],
            },
        },
    }
    result = normalize_finalizer_agent_visible_result(raw)
    outputs = result["outputs"]
    assert outputs["missing"]["scope_ids"] == ["parcel_1"]
    assert "active_finalization_session" in outputs
    assert "finalization_decision_card" not in outputs
    assert "retry_request_template" not in outputs
    assert "prompt_carry_forward" not in outputs
    assert outputs["next_required_action"] == CANONICAL_FINALIZER_ACTION


def test_publish_gate_prose_hints_normalize_without_exact_action_ids():
    from tooling.mapping.deed_to_ir.publish_gate_feedback import (
        POSTURE_AUDIT_REPAIR_HINT,
        CLOSURE_ENFORCEMENT_POSTURE_REPAIR_HINT,
        publish_gate_repair_hint,
        PUBLISH_GATE_MAPPING_LINEAGE_MISMATCH,
        PUBLISH_GATE_PREVIEW_PACKAGE_INVALID,
        PUBLISH_GATE_WORKSPACE_STORAGE_FAILURE,
    )

    posture = {
        "executed": False,
        "refusal": {
            "reason_code": "work_universe_publish_not_audited",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "repair_hint": POSTURE_AUDIT_REPAIR_HINT,
            "next_repair_action": CLOSURE_ENFORCEMENT_POSTURE_REPAIR_HINT,
            "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
        },
    }
    posture_result = normalize_finalizer_agent_visible_result(posture)
    assert posture_result["outputs"]["next_required_action"] == CANONICAL_FINALIZER_ACTION
    assert posture_result["outputs"]["repair_hint"] == (
        f"Patch readiness/audit posture if warranted, then retry "
        f"{CANONICAL_FINALIZER_ACTION} without decision mutations."
    )
    assert posture_result["outputs"]["next_repair_action"] == (
        posture_result["outputs"]["repair_hint"]
    )
    _assert_no_retired_workflow_directives(posture_result)

    lineage_hint = publish_gate_repair_hint(
        reason_code="mapping_ir_lineage_mismatch",
        publish_gate_category=PUBLISH_GATE_MAPPING_LINEAGE_MISMATCH,
    )
    assert "prepare and publish" in lineage_hint.lower()
    lineage = {
        "executed": False,
        "refusal": {
            "reason_code": "mapping_ir_lineage_mismatch",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"repair_hint": lineage_hint},
    }
    lineage_result = normalize_finalizer_agent_visible_result(lineage)
    assert lineage_result["outputs"]["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert lineage_result["outputs"]["repair_hint"] == (
        f"Submit the expected IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
    )
    _assert_no_retired_workflow_directives(lineage_result)

    stale_hint = publish_gate_repair_hint(
        reason_code="final_package_preview_stale",
        publish_gate_category=PUBLISH_GATE_MAPPING_LINEAGE_MISMATCH,
    )
    assert "prepare a new final package preview" in stale_hint.lower()
    stale = {
        "executed": False,
        "refusal": {
            "reason_code": "final_package_preview_stale",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"repair_hint": stale_hint},
    }
    stale_result = normalize_finalizer_agent_visible_result(stale)
    assert stale_result["outputs"]["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert stale_result["outputs"]["repair_hint"] == (
        f"Submit the current IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
    )
    _assert_no_retired_workflow_directives(stale_result)

    invalid_hint = publish_gate_repair_hint(
        reason_code="final_package_preview_not_found",
        publish_gate_category=PUBLISH_GATE_PREVIEW_PACKAGE_INVALID,
    )
    assert "prepare or publish" in invalid_hint.lower()
    not_found = {
        "executed": False,
        "refusal": {
            "reason_code": "final_package_preview_not_found",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"repair_hint": invalid_hint},
    }
    not_found_result = normalize_finalizer_agent_visible_result(not_found)
    assert not_found_result["outputs"]["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
    assert not_found_result["outputs"]["repair_hint"] == (
        f"Submit the current IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
    )
    _assert_no_retired_workflow_directives(not_found_result)

    for code in (
        "final_package_preview_invalid",
        "final_package_preview_not_ready",
    ):
        routed = route_finalizer_next_action(reason_code=code, retryable=True)
        assert routed == SUBMIT_IR_FOR_MAPPING_ACTION

    storage_hint = publish_gate_repair_hint(
        reason_code="publication_in_progress",
        publish_gate_category=PUBLISH_GATE_WORKSPACE_STORAGE_FAILURE,
    )
    assert "retry publish" in storage_hint.lower()
    storage = {
        "executed": False,
        "refusal": {
            "reason_code": "publication_in_progress",
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {"code": "publication_in_progress", "message": "lock held"},
            "repair_hint": storage_hint,
            "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
        },
    }
    storage_result = normalize_finalizer_agent_visible_result(storage)
    assert storage_result["refusal"]["retryable"] is True
    assert storage_result["refusal"]["blocked_by_invariant"] is False
    assert storage_result["outputs"]["next_required_action"] == CANONICAL_FINALIZER_ACTION
    assert storage_result["outputs"]["final_package_preview_ref"] == (
        "deed_to_ir:final_package_preview:rev:0001"
    )
    assert storage_result["outputs"]["error"]["code"] == "publication_in_progress"
    _assert_no_retired_workflow_directives(storage_result)


def test_production_publisher_refusal_publication_in_progress_reclassified():
    from tooling.mapping.deed_to_ir.persistence_io import refusal as publisher_refusal
    from tooling.mapping.deed_to_ir.publish_gate_feedback import enrich_publish_refusal_result

    raw = enrich_publish_refusal_result(
        publisher_refusal("publication_in_progress", "publication_in_progress")
    )
    assert raw["refusal"]["retryable"] is False
    assert raw["refusal"]["blocked_by_invariant"] is True

    result = normalize_finalizer_agent_visible_result(raw)
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert result["refusal"]["reason_code"] == "publication_in_progress"
    assert result["outputs"]["next_required_action"] == CANONICAL_FINALIZER_ACTION
    assert result["outputs"]["expected_next"] == CANONICAL_FINALIZER_ACTION
    _assert_no_retired_workflow_directives(result)


def test_production_publisher_refusal_unusable_preview_reclassified_to_remap():
    from tooling.mapping.deed_to_ir.persistence_io import refusal as publisher_refusal
    from tooling.mapping.deed_to_ir.publish_gate_feedback import enrich_publish_refusal_result

    for code, message in (
        ("final_package_preview_not_found", "final_package_preview_not_found"),
        ("final_package_preview_invalid", "Stored final package preview is invalid."),
        (
            "final_package_preview_not_ready",
            "Stored final package preview is not publish-ready.",
        ),
    ):
        raw = enrich_publish_refusal_result(publisher_refusal(code, message))
        assert raw["refusal"]["retryable"] is False
        assert raw["refusal"]["blocked_by_invariant"] is True

        result = normalize_finalizer_agent_visible_result(raw)
        assert result["refusal"]["retryable"] is True, code
        assert result["refusal"]["blocked_by_invariant"] is False, code
        assert result["refusal"]["reason_code"] == code
        assert result["outputs"]["next_required_action"] == SUBMIT_IR_FOR_MAPPING_ACTION
        assert result["outputs"]["expected_next"] == SUBMIT_IR_FOR_MAPPING_ACTION
        assert result["outputs"]["repair_hint"] == (
            f"Submit the current IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
        )
        _assert_no_retired_workflow_directives(result)


def test_non_recoverable_publication_invariant_stays_terminal():
    from tooling.mapping.deed_to_ir.persistence_io import refusal as publisher_refusal
    from tooling.mapping.deed_to_ir.publish_gate_feedback import enrich_publish_refusal_result

    raw = enrich_publish_refusal_result(
        publisher_refusal(
            "published_preview_replay_state_invalid",
            "published_preview_replay_state_invalid",
        )
    )
    assert raw["refusal"]["retryable"] is False

    result = normalize_finalizer_agent_visible_result(raw)
    assert result["refusal"]["retryable"] is False
    assert result["refusal"]["blocked_by_invariant"] is True
    assert "next_required_action" not in result["outputs"]
    assert "expected_next" not in result["outputs"]
    _assert_no_retired_workflow_directives(result)
