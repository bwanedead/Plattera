"""Regression tests for native multi-action plans and repair preservation."""

from __future__ import annotations

import json

import pytest

from domains.mapping.transcript_edit.domain_pack import build_transcript_edit_domain_pack
from harness.execution.session import ExecutionSessionManager
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)
from harness.runtime.orchestration.contracts import OrchestratorContext
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.repair_lane import (
    _derive_repair_context,
    attempt_repair,
    count_attempted_actions_in_text,
)
from harness.runtime.orchestration.tool_batch_policy import (
    ToolBatchPolicy,
    enrich_run_context_with_tool_batch_policies,
    resolve_policies_for_action_plan_parse,
    resolve_tool_batch_policies,
)


def _transcript_edit_policies() -> dict[str, ToolBatchPolicy]:
    pack = build_transcript_edit_domain_pack()
    return resolve_tool_batch_policies({"transcript_edit": pack.build_surface_payload()})


def _live_four_crop_payload() -> dict:
    return {
        "actions": [
            {
                "alias": "crop_surname",
                "action_type": "transform_artifact",
                "action_inputs": {
                    "ref_id": "image:assoc:draft_legal_text_image:original",
                    "sub_action": "crop",
                    "params": {"box_norm": [0.53, 0.095, 0.75, 0.185]},
                },
                "hydrate_next": ["@this.result.derived_ref_id"],
                "hydrate_next_reason": "Inspect the grantor surname in a claim-local crop next turn.",
            },
            {
                "alias": "crop_p1_bearing",
                "action_type": "transform_artifact",
                "action_inputs": {
                    "ref_id": "image:assoc:draft_legal_text_image:original",
                    "sub_action": "crop",
                    "params": {"box_norm": [0.29, 0.565, 0.49, 0.645]},
                },
                "hydrate_next": ["@this.result.derived_ref_id"],
                "hydrate_next_reason": "Inspect the parcel 1 POB bearing in a focused crop next turn.",
            },
            {
                "alias": "crop_p1_acreage",
                "action_type": "transform_artifact",
                "action_inputs": {
                    "ref_id": "image:assoc:draft_legal_text_image:original",
                    "sub_action": "crop",
                    "params": {"box_norm": [0.64, 0.765, 0.84, 0.845]},
                },
                "hydrate_next": ["@this.result.derived_ref_id"],
                "hydrate_next_reason": "Inspect the parcel 1 acreage phrase in a focused crop next turn.",
            },
            {
                "alias": "crop_p2_bearing",
                "action_type": "transform_artifact",
                "action_inputs": {
                    "ref_id": "image:assoc:draft_legal_text_image:original",
                    "sub_action": "crop",
                    "params": {"box_norm": [0.03, 0.895, 0.18, 0.965]},
                },
                "hydrate_next": ["@this.result.derived_ref_id"],
                "hydrate_next_reason": "Inspect the parcel 2 corner bearing in a focused crop next turn.",
            },
        ],
        "operator_progress_message": "Creating four focused crops for the disputed source readings.",
        "rationale": (
            "Use the grid-informed page view to localize each exact reading now "
            "so the next turn can inspect claim-local evidence."
        ),
    }


def _orch_context(*, opaque_run_context: dict | None = None) -> OrchestratorContext:
    lm = LoopMemoryState()
    lm.iterations = 1
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-native",
        loop_memory=lm,
        request_id_prefix="req-native",
        opaque_run_context=opaque_run_context or {},
    )


def test_choose_action_live_four_crop_via_opaque_run_context_policies() -> None:
    """Adapter must merge ``__tool_batch_policies`` from run context into parse/repair."""
    pack = build_transcript_edit_domain_pack()
    surface = {"transcript_edit": pack.build_surface_payload()}
    policies = _transcript_edit_policies()
    run_ctx = enrich_run_context_with_tool_batch_policies({}, surface)
    calls: list[int] = []

    def caller(_prompt: str, _model: str, **_kwargs: object) -> str:
        calls.append(1)
        return json.dumps(_live_four_crop_payload())

    adapter = LlmTurnOrchestrationAdapter(
        composed_input=ComposedTurnInput(
            blocks=(TurnBlock(content="block"),),
            surface_payloads={},
            tool_handlers={tool_id: (lambda _x, tid=tool_id: _x) for tool_id in policies},
        ),
        text_model_caller=caller,
        model_name="fake",
        opaque_launch_context={},
    )
    plan = adapter.choose_action(_orch_context(opaque_run_context=run_ctx), projection=None)

    assert len(calls) == 1
    assert len(plan.actions) == 4
    assert all(a.action_type == "transform_artifact" for a in plan.actions)
    assert plan.actions[0].hydrate_next == ("@this.result.derived_ref_id",)


def test_choose_action_live_four_crop_via_surface_payload_policies() -> None:
    pack = build_transcript_edit_domain_pack()
    surface = {"transcript_edit": pack.build_surface_payload()}
    policies = _transcript_edit_policies()
    calls: list[int] = []

    def caller(_prompt: str, _model: str, **_kwargs: object) -> str:
        calls.append(1)
        return json.dumps(_live_four_crop_payload())

    adapter = LlmTurnOrchestrationAdapter(
        composed_input=ComposedTurnInput(
            blocks=(TurnBlock(content="block"),),
            surface_payloads=surface,
            tool_handlers={tool_id: (lambda _x, tid=tool_id: _x) for tool_id in policies},
        ),
        text_model_caller=caller,
        model_name="fake",
        opaque_launch_context={},
    )
    plan = adapter.choose_action(_orch_context(), projection=None)

    assert len(calls) == 1
    assert len(plan.actions) == 4


def test_live_four_crop_native_actions_parse_with_transcript_edit_policies() -> None:
    policies = _transcript_edit_policies()
    plan = parse_action_plan_response(
        json.dumps(_live_four_crop_payload()),
        available_tool_ids=tuple(policies.keys()),
        tool_batch_policies=policies,
    )
    assert len(plan.actions) == 4
    assert [a.alias for a in plan.actions] == [
        "crop_surname",
        "crop_p1_bearing",
        "crop_p1_acreage",
        "crop_p2_bearing",
    ]
    assert all(a.action_type == "transform_artifact" for a in plan.actions)
    assert all(a.hydrate_next == ("@this.result.derived_ref_id",) for a in plan.actions)
    assert plan.actions[0].hydrate_next_reason.startswith("Inspect the grantor surname")
    assert plan.operator_progress_message.startswith("Creating four focused crops")


def test_multi_action_rejected_without_batch_policy() -> None:
    payload = _live_four_crop_payload()
    with pytest.raises(ModelActionParseError, match="not batchable"):
        parse_action_plan_response(
            json.dumps(payload),
            available_tool_ids=("transform_artifact",),
            tool_batch_policies={},
        )


def test_multi_action_rejected_when_exceeding_transform_cap() -> None:
    policies = _transcript_edit_policies()
    payload = dict(_live_four_crop_payload())
    payload["actions"] = list(payload["actions"]) + [
        {
            "alias": "crop_extra",
            "action_type": "transform_artifact",
            "action_inputs": {
                "ref_id": "image:assoc:draft_legal_text_image:original",
                "sub_action": "crop",
                "params": {"box_norm": [0.1, 0.1, 0.2, 0.2]},
            },
        }
    ]
    with pytest.raises(ModelActionParseError, match="per-tool cap"):
        parse_action_plan_response(
            json.dumps(payload),
            available_tool_ids=tuple(policies.keys()),
            tool_batch_policies=policies,
        )


def test_single_native_non_batchable_tool_allowed_without_batch_policy() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "actions": [
                {
                    "alias": "save_row",
                    "action_type": "save_workspace_artifact",
                    "action_inputs": {"payload": {"status": "draft"}},
                }
            ],
            "rationale": "save once",
        }),
        available_tool_ids=("save_workspace_artifact",),
        tool_batch_policies={},
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].action_type == "save_workspace_artifact"


def test_resolve_policies_merges_run_context_and_surface() -> None:
    pack = build_transcript_edit_domain_pack()
    surface_policies = resolve_tool_batch_policies({"t": pack.build_surface_payload()})
    run_ctx = {"__tool_batch_policies": {
        "transform_artifact": {
            "tool_id": "transform_artifact",
            "allowed": True,
            "max_calls_per_batch": 4,
            "side_effect_class": "derived_artifact",
        }
    }}
    merged = resolve_policies_for_action_plan_parse(
        surface_payloads={},
        opaque_run_context=run_ctx,
    )
    assert "transform_artifact" in merged
    assert merged["transform_artifact"].max_calls_per_batch == surface_policies["transform_artifact"].max_calls_per_batch


def test_derive_repair_context_flags_multi_action_native_preservation() -> None:
    prior = _live_four_crop_payload()
    prior["hydrate_next"] = ["@result.derived_ref_id"]
    _, targets = _derive_repair_context(
        json.dumps(prior),
        "actions cannot be mixed with action_type, action_inputs, action_batch, or top-level hydrate_next",
    )
    assert "preserve_native_actions_array" in targets
    assert "preserve_multi_action_intent" in targets
    assert "remove_top_level_hydrate_when_using_per_action_hydrate" in targets


def test_repair_over_cap_returns_multiple_actions_not_one() -> None:
    policies = _transcript_edit_policies()
    over_cap = dict(_live_four_crop_payload())
    over_cap["actions"] = list(over_cap["actions"]) + [
        {
            "alias": "crop_extra",
            "action_type": "transform_artifact",
            "action_inputs": {
                "ref_id": "image:assoc:draft_legal_text_image:original",
                "sub_action": "crop",
                "params": {"box_norm": [0.0, 0.0, 0.1, 0.1]},
            },
        }
    ]
    prior_text = json.dumps(over_cap)
    original_exc = ModelActionParseError(
        "invalid_model_action_json",
        "actions failed canonical validation: action_batch exceeds per-tool cap for transform_artifact (4)",
    )

    def repair_caller(prompt: str, model: str, **_kwargs: object) -> str:
        del prompt, model
        return json.dumps(_live_four_crop_payload())

    attempt = attempt_repair(
        model_caller=repair_caller,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text=prior_text,
        original_exc=original_exc,
        available_tool_ids=tuple(policies.keys()),
        tool_batch_policies=policies,
    )
    assert attempt.repair_parse_ok is True
    assert attempt.repair_parsed_action_plan is not None
    assert len(attempt.repair_parsed_action_plan.actions) == 4


def test_count_attempted_actions_in_text() -> None:
    assert count_attempted_actions_in_text(json.dumps(_live_four_crop_payload())) == 4
