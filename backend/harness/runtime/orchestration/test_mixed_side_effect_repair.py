"""MAPDEP-BR-031: mixed side-effect-class repair targeting."""

from __future__ import annotations

import json
from typing import Any

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
from harness.runtime.orchestration.prompt_packet_builder import build_repair_prompt_document
from harness.runtime.orchestration.repair_instruction import REPAIR_INSTRUCTION
from harness.runtime.orchestration.repair_lane import (
    _derive_repair_context,
    _is_mixed_side_effect_class_error,
    attempt_repair,
)
from harness.runtime.orchestration.tool_batch_policy import (
    ToolBatchPolicy,
    resolve_tool_batch_policies,
)

_MIXED_DETAIL = (
    "actions failed canonical validation: action_batch cannot mix disallowed side_effect classes"
)


def _fake_policies() -> dict[str, ToolBatchPolicy]:
    return {
        "hydrate_artifact_refs": ToolBatchPolicy(
            tool_id="hydrate_artifact_refs",
            allowed=True,
            max_calls_per_batch=3,
            side_effect_class="read_only",
            can_run_parallel=True,
        ),
        "transform_artifact": ToolBatchPolicy(
            tool_id="transform_artifact",
            allowed=True,
            max_calls_per_batch=4,
            side_effect_class="derived_artifact",
        ),
        "noop_probe": ToolBatchPolicy(
            tool_id="noop_probe",
            allowed=True,
            max_calls_per_batch=2,
            side_effect_class="read_only",
        ),
    }


def _mixed_plan() -> dict[str, Any]:
    return {
        "actions": [
            {
                "alias": "read_example_token",
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["t0:raw:example_pass"], "max_refs": 2},
            },
            {
                "alias": "read_example_peer",
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["t0:raw:example_peer"], "max_refs": 1},
            },
            {
                "alias": "derive_example_window",
                "action_type": "transform_artifact",
                "action_inputs": {
                    "ref_id": "image:assoc:example-source:original",
                    "sub_action": "crop",
                    "params": {"box_norm": [0.1, 0.1, 0.2, 0.2]},
                },
            },
        ],
        "rationale": "read example evidence and derive one synthetic window",
    }


def _orch_context() -> OrchestratorContext:
    memory = LoopMemoryState()
    memory.iterations = 1
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-mixed-side-effect",
        loop_memory=memory,
        request_id_prefix="req-mixed-side-effect",
        opaque_run_context={},
    )


def test_mixed_read_only_and_derived_plan_gets_new_target_without_multi_action_preserve() -> None:
    prior = _mixed_plan()
    _obj, targets, extras = _derive_repair_context(
        json.dumps(prior),
        _MIXED_DETAIL,
        tool_batch_policies=_fake_policies(),
    )
    assert "preserve_native_actions_array" in targets
    assert "select_one_side_effect_class_group_for_this_turn" in targets
    assert "preserve_multi_action_intent" not in targets
    assert _is_mixed_side_effect_class_error(_MIXED_DETAIL) is True
    assert extras["action_side_effect_classes"] == [
        {
            "alias": "read_example_token",
            "action_type": "hydrate_artifact_refs",
            "side_effect_class": "read_only",
        },
        {
            "alias": "read_example_peer",
            "action_type": "hydrate_artifact_refs",
            "side_effect_class": "read_only",
        },
        {
            "alias": "derive_example_window",
            "action_type": "transform_artifact",
            "side_effect_class": "derived_artifact",
        },
    ]


class _StrMarker:
    def __str__(self) -> str:
        return _MIXED_DETAIL


@pytest.mark.parametrize(
    "detail",
    [
        f"note: {_MIXED_DETAIL}",
        f"{_MIXED_DETAIL} (retry)",
        _MIXED_DETAIL.upper(),
        f" {_MIXED_DETAIL} ",
        f"\n{_MIXED_DETAIL}",
        _StrMarker(),
    ],
    ids=[
        "prefix",
        "suffix",
        "wrong_case",
        "surrounding_spaces",
        "leading_newline",
        "non_string_str_marker",
    ],
)
def test_nonexact_mixed_class_diagnostics_keep_existing_repair_path(detail: object) -> None:
    assert _is_mixed_side_effect_class_error(detail) is False
    prior = _mixed_plan()
    _obj, targets, extras = _derive_repair_context(
        json.dumps(prior),
        detail,
        tool_batch_policies=_fake_policies(),
    )
    assert "preserve_native_actions_array" in targets
    assert "select_one_side_effect_class_group_for_this_turn" not in targets
    assert "action_side_effect_classes" not in extras
    assert "preserve_multi_action_intent" in targets


def test_nonexact_string_diagnostic_uses_existing_model_repair() -> None:
    prior = _mixed_plan()
    selected = {
        "actions": [prior["actions"][0], prior["actions"][1]],
        "rationale": "existing multi-action repair still chooses authored rows",
    }
    wrapped = f"{_MIXED_DETAIL} (retry)"

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        marker = '"repair_targets":'
        slice_text = prompt[prompt.index(marker) : prompt.index(marker) + 400]
        assert "preserve_native_actions_array" in slice_text
        assert "preserve_multi_action_intent" in slice_text
        assert "select_one_side_effect_class_group_for_this_turn" not in slice_text
        return json.dumps(selected)

    attempt = attempt_repair(
        model_caller=caller,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text=json.dumps(prior),
        original_exc=ModelActionParseError("invalid_model_action_json", wrapped),
        available_tool_ids=("hydrate_artifact_refs", "transform_artifact"),
        tool_batch_policies=_fake_policies(),
    )
    assert attempt.repair_parse_ok is True
    assert attempt.repair_parsed_action_plan is not None
    assert [row.alias for row in attempt.repair_parsed_action_plan.actions] == [
        "read_example_token",
        "read_example_peer",
    ]


def test_repair_instruction_teaches_selecting_one_compatible_class_group() -> None:
    text = REPAIR_INSTRUCTION.lower()
    assert "select_one_side_effect_class_group_for_this_turn" in text
    assert "compatible side-effect-class group" in text
    assert "keep each retained row's action_type and action_inputs unchanged" in text
    assert "retain multiple rows when they share the selected class" in text
    assert "defer rows belonging to other classes" in text
    assert "does not pick a winner" in text
    assert "action_side_effect_classes" in text


def test_repair_selecting_either_class_parses_and_keeps_inputs_exact() -> None:
    prior = _mixed_plan()
    policies = _fake_policies()
    selected_read = {
        "actions": [prior["actions"][0], prior["actions"][1]],
        "rationale": "keep the already-authored read_only rows this turn",
    }
    selected_derive = {
        "actions": [prior["actions"][2]],
        "rationale": "keep the already-authored derived_artifact row this turn",
    }

    for selected in (selected_read, selected_derive):
        def caller(prompt: str, model: str, *, _selected: dict[str, Any] = selected, **_kwargs: Any) -> str:
            del model
            assert "select_one_side_effect_class_group_for_this_turn" in prompt
            marker = '"repair_targets":'
            slice_text = prompt[prompt.index(marker) : prompt.index(marker) + 400]
            assert "select_one_side_effect_class_group_for_this_turn" in slice_text
            assert "preserve_multi_action_intent" not in slice_text
            return json.dumps(_selected)

        attempt = attempt_repair(
            model_caller=caller,
            model_name="fake",
            prior_prompt_mode="full_choose_action",
            previous_response_text=json.dumps(prior),
            original_exc=ModelActionParseError("invalid_model_action_json", _MIXED_DETAIL),
            available_tool_ids=("hydrate_artifact_refs", "transform_artifact"),
            tool_batch_policies=policies,
        )
        assert attempt.repair_parse_ok is True
        plan = attempt.repair_parsed_action_plan
        assert plan is not None
        retained_aliases = [row.alias for row in plan.actions]
        expected_aliases = [row["alias"] for row in selected["actions"]]
        assert retained_aliases == expected_aliases
        for authored, repaired in zip(selected["actions"], plan.actions):
            assert repaired.action_type == authored["action_type"]
            assert repaired.action_inputs == authored["action_inputs"]
        unselected = {
            row["alias"] for row in prior["actions"]
        } - set(expected_aliases)
        assert unselected
        assert unselected.isdisjoint(retained_aliases)


def test_same_class_rows_can_remain_together() -> None:
    prior = _mixed_plan()
    selected = {
        "actions": [prior["actions"][0], prior["actions"][1]],
        "rationale": "retain both authored read_only rows",
    }

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del prompt, model
        return json.dumps(selected)

    attempt = attempt_repair(
        model_caller=caller,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text=json.dumps(prior),
        original_exc=ModelActionParseError("invalid_model_action_json", _MIXED_DETAIL),
        available_tool_ids=("hydrate_artifact_refs", "transform_artifact"),
        tool_batch_policies=_fake_policies(),
    )
    assert attempt.repair_parse_ok is True
    assert attempt.repair_parsed_action_plan is not None
    assert [row.alias for row in attempt.repair_parsed_action_plan.actions] == [
        "read_example_token",
        "read_example_peer",
    ]


def test_missing_or_malformed_policies_are_not_guessed() -> None:
    prior = _mixed_plan()
    _, no_policy_targets, no_policy_extras = _derive_repair_context(
        json.dumps(prior),
        _MIXED_DETAIL,
        tool_batch_policies=None,
    )
    assert "select_one_side_effect_class_group_for_this_turn" not in no_policy_targets
    assert "preserve_multi_action_intent" not in no_policy_targets
    assert "action_side_effect_classes" not in no_policy_extras

    incomplete = {"hydrate_artifact_refs": _fake_policies()["hydrate_artifact_refs"]}
    _, incomplete_targets, incomplete_extras = _derive_repair_context(
        json.dumps(prior),
        _MIXED_DETAIL,
        tool_batch_policies=incomplete,
    )
    assert "select_one_side_effect_class_group_for_this_turn" not in incomplete_targets
    assert "action_side_effect_classes" not in incomplete_extras

    broken = dict(prior)
    broken["actions"] = [
        {**prior["actions"][0], "alias": 12},
        prior["actions"][2],
    ]
    _, broken_targets, broken_extras = _derive_repair_context(
        json.dumps(broken),
        _MIXED_DETAIL,
        tool_batch_policies=_fake_policies(),
    )
    assert "select_one_side_effect_class_group_for_this_turn" not in broken_targets
    assert "action_side_effect_classes" not in broken_extras


def test_repair_metadata_is_json_native_and_bounded() -> None:
    good_rows = [
        {
            "alias": "read_example_token",
            "action_type": "hydrate_artifact_refs",
            "side_effect_class": "read_only",
        },
        {
            "alias": "derive_example_window",
            "action_type": "transform_artifact",
            "side_effect_class": "derived_artifact",
        },
    ]
    good = build_repair_prompt_document(
        available_tool_ids=("hydrate_artifact_refs", "transform_artifact"),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail=_MIXED_DETAIL,
        previous_response_text="{}",
        repair_targets=["select_one_side_effect_class_group_for_this_turn"],
        repair_context_extras={"action_side_effect_classes": good_rows},
    )
    assert good.prompt_body["repair_context"]["action_side_effect_classes"] == good_rows

    oversized = build_repair_prompt_document(
        available_tool_ids=("hydrate_artifact_refs",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail=_MIXED_DETAIL,
        previous_response_text="{}",
        repair_context_extras={
            "action_side_effect_classes": [
                {
                    "alias": f"row_{index}",
                    "action_type": "hydrate_artifact_refs",
                    "side_effect_class": "read_only",
                }
                for index in range(17)
            ]
        },
    )
    assert "action_side_effect_classes" not in oversized.prompt_body["repair_context"]

    guessed_class = build_repair_prompt_document(
        available_tool_ids=("hydrate_artifact_refs",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail=_MIXED_DETAIL,
        previous_response_text="{}",
        repair_context_extras={
            "action_side_effect_classes": [
                {
                    "alias": "read_example_token",
                    "action_type": "hydrate_artifact_refs",
                    "side_effect_class": "maybe_read",
                }
            ]
        },
    )
    assert "action_side_effect_classes" not in guessed_class.prompt_body["repair_context"]
    assert "maybe_read" not in guessed_class.prompt_text


def test_same_class_multi_action_repair_still_preserves_intent() -> None:
    prior = {
        "actions": [
            {
                "alias": "read_example_token",
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["t0:raw:example_pass"]},
            },
            {
                "alias": "read_example_peer",
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["t0:raw:example_peer"]},
            },
        ],
        "rationale": "two same-class reads",
    }
    _, targets, extras = _derive_repair_context(
        json.dumps(prior),
        "actions failed canonical validation: some other structural fault",
        tool_batch_policies=_fake_policies(),
    )
    assert "preserve_native_actions_array" in targets
    assert "preserve_multi_action_intent" in targets
    assert "select_one_side_effect_class_group_for_this_turn" not in targets
    assert "action_side_effect_classes" not in extras


def test_nonbatchable_repair_target_is_unchanged() -> None:
    prior = {
        "actions": [
            {
                "alias": "save_a",
                "action_type": "save_workspace_artifact",
                "action_inputs": {"payload": {"lane": "a"}},
            },
            {
                "alias": "save_b",
                "action_type": "save_workspace_artifact",
                "action_inputs": {"payload": {"lane": "b"}},
            },
        ],
        "rationale": "two saves",
    }
    _, targets, extras = _derive_repair_context(
        json.dumps(prior),
        "actions failed canonical validation: action_type not batchable: save_workspace_artifact",
        tool_batch_policies=_fake_policies(),
    )
    assert "select_one_nonbatchable_action_for_this_turn" in targets
    assert "preserve_multi_action_intent" not in targets
    assert "select_one_side_effect_class_group_for_this_turn" not in targets
    assert extras["nonbatchable_action_type"] == "save_workspace_artifact"


def test_parser_still_rejects_mixed_side_effect_classes() -> None:
    with pytest.raises(ModelActionParseError, match="cannot mix disallowed side_effect classes"):
        parse_action_plan_response(
            json.dumps(_mixed_plan()),
            available_tool_ids=("hydrate_artifact_refs", "transform_artifact"),
            tool_batch_policies=_fake_policies(),
        )


def test_production_shaped_hydrate_plus_transform_repairs_without_turn_recovery() -> None:
    pack = build_transcript_edit_domain_pack()
    surface = {"transcript_edit": pack.build_surface_payload()}
    assert "hydrate_artifact_refs" in resolve_tool_batch_policies(surface)
    assert "transform_artifact" in resolve_tool_batch_policies(surface)
    prior = _mixed_plan()
    selected = {
        "actions": [prior["actions"][0], prior["actions"][1]],
        "rationale": "continue with the already-authored read_only group",
    }
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps(prior)
        assert "select_one_side_effect_class_group_for_this_turn" in prompt
        assert "preserve_multi_action_intent" not in prompt[
            prompt.index('"repair_targets":') : prompt.index('"repair_targets":') + 400
        ]
        return json.dumps(selected)

    adapter = LlmTurnOrchestrationAdapter(
        composed_input=ComposedTurnInput(
            blocks=(TurnBlock(content="block"),),
            surface_payloads=surface,
            tool_handlers={
                "hydrate_artifact_refs": lambda payload: payload,
                "transform_artifact": lambda payload: payload,
            },
        ),
        text_model_caller=caller,
        model_name="fake",
    )
    plan = adapter.choose_action(_orch_context(), projection=None)
    assert len(calls) == 2
    assert [row.alias for row in plan.actions] == ["read_example_token", "read_example_peer"]
    assert all(row.action_type == "hydrate_artifact_refs" for row in plan.actions)
    assert plan.actions[0].action_inputs == prior["actions"][0]["action_inputs"]
    assert "choose_action_turn_recovery" not in "".join(calls)
