"""MAPDEP-BR-020: nonbatchable multi-action repair + recovery tool contracts."""

from __future__ import annotations

import json
from typing import Any

import pytest

from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)
from harness.runtime.orchestration.compact_tool_contracts import project_compact_tool_contracts
from harness.runtime.orchestration.llm_prompt_builder import build_turn_recovery_prompt_document
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.repair_instruction import REPAIR_INSTRUCTION
from harness.runtime.orchestration.repair_lane import _derive_repair_context, attempt_repair
from harness.runtime.orchestration.recoverable_turn_failure import (
    POST_REPAIR_PARSE_FAILURE_STAGE,
    RecoverableTurnFailure,
)
from harness.runtime.orchestration.test_contract_turn_recovery import (
    _adapter as _base_adapter,
    _orch_context,
)


_NONBATCHABLE_DETAIL = (
    "actions failed canonical validation: action_type not batchable: save_workspace_artifact"
)


def _fake_domain_surface_payloads() -> dict[str, dict[str, Any]]:
    return {
        "fake_ops": {
            "tool_ids": [
                "save_workspace_artifact",
                "hydrate_artifact_refs",
                "noop_probe",
            ],
            "tool_specs": [
                {
                    "tool_id": "save_workspace_artifact",
                    "category": "write",
                    "purpose": "Persist one authored workspace artifact revision.",
                    "expected_request_shape": (
                        "payload: required object. "
                        "base_revision_ref: optional prior revision."
                    ),
                    "batching": {
                        "allowed": False,
                        "max_calls_per_batch": 1,
                        "side_effect_class": "workspace_write",
                    },
                    "expected_request_json_shape": {"type": "object"},
                    "example_request": {"payload": {"status": "draft"}},
                },
                {
                    "tool_id": "hydrate_artifact_refs",
                    "category": "read",
                    "purpose": "Load bounded artifact content by ref id.",
                    "expected_request_shape": (
                        "ref_ids: required non-empty array of ref_id strings. "
                        "max_refs: optional integer cap."
                    ),
                    "batching": {
                        "allowed": True,
                        "max_calls_per_batch": 3,
                        "side_effect_class": "read_only",
                        "can_run_parallel": True,
                    },
                },
                {
                    "tool_id": "noop_probe",
                    "category": "read",
                    "purpose": "No-op probe for fake-domain coverage.",
                    "expected_request_shape": "empty object",
                    "batching": {
                        "allowed": True,
                        "max_calls_per_batch": 2,
                        "side_effect_class": "read_only",
                    },
                },
            ],
            "startup_inventory": {"should_not_appear": True},
        }
    }


def _dual_save_plan(*, with_root_closure: bool = True) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "actions": [
            {
                "alias": "save_a",
                "action_type": "save_workspace_artifact",
                "action_inputs": {"payload": {"lane": "a", "text": "first save"}},
            },
            {
                "alias": "save_b",
                "action_type": "save_workspace_artifact",
                "action_inputs": {"payload": {"lane": "b", "text": "second save"}},
            },
        ],
        "rationale": "persist two authored workspace revisions in one turn",
    }
    if with_root_closure:
        plan["state_patch"] = {
            "mission": {
                "closure_state": {
                    "dimensions": [{"id": "batch_done", "status": "satisfied"}]
                }
            }
        }
        plan["complete_run"] = True
    return plan


def _composed() -> ComposedTurnInput:
    return ComposedTurnInput(
        blocks=(
            TurnBlock(
                content="fake domain doctrine must stay out of turn_recovery",
                metadata={"layer": "domain_branch"},
            ),
        ),
        surface_payloads=_fake_domain_surface_payloads(),
        tool_handlers={
            "save_workspace_artifact": lambda payload: payload,
            "hydrate_artifact_refs": lambda payload: payload,
            "noop_probe": lambda payload: payload,
        },
    )


def _adapter(caller) -> LlmTurnOrchestrationAdapter:
    return LlmTurnOrchestrationAdapter(
        composed_input=_composed(),
        text_model_caller=caller,
        model_name="fake-model",
    )


def test_dual_save_workspace_artifact_derives_nonbatchable_repair_target() -> None:
    prior = _dual_save_plan()
    _obj, targets, extras = _derive_repair_context(json.dumps(prior), _NONBATCHABLE_DETAIL)
    assert "select_one_nonbatchable_action_for_this_turn" in targets
    assert "preserve_native_actions_array" in targets
    assert "preserve_multi_action_intent" not in targets
    assert extras["nonbatchable_action_type"] == "save_workspace_artifact"
    assert extras["affected_action_aliases"] == ["save_a", "save_b"]


def test_nonbatchable_repair_instruction_splits_representation_from_cardinality() -> None:
    text = REPAIR_INSTRUCTION.lower()
    assert "preserve_native_actions_array" in text
    assert "representation only" in text
    assert "preserve_multi_action_intent" in text
    assert "select_one_nonbatchable_action_for_this_turn" in text
    assert "unambiguously requires one row" in text
    assert "do not convert another row into a different tool" in text
    assert "defer the remaining rows" in text
    # Old combined teaching that conflated representation with cardinality must be gone.
    assert "preserve_multi_action_intent or preserve_native_actions_array" not in text


def test_repair_selecting_one_unchanged_save_row_parses() -> None:
    prior = _dual_save_plan(with_root_closure=True)
    selected = {
        "actions": [prior["actions"][0]],
        "rationale": "run the first already-authored save this turn and postpone the second",
    }

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        assert "select_one_nonbatchable_action_for_this_turn" in prompt
        assert '"nonbatchable_action_type": "save_workspace_artifact"' in prompt
        assert "Do not convert another row into a different tool" in prompt
        assert "convert save_b" not in prompt.lower()
        # Instruction text always names preserve_multi_action_intent as a rule family;
        # assert the emitted repair_targets for this failure omit it.
        marker = '"repair_targets":'
        start = prompt.index(marker)
        slice_text = prompt[start : start + 400]
        assert "select_one_nonbatchable_action_for_this_turn" in slice_text
        assert "preserve_multi_action_intent" not in slice_text
        return json.dumps(selected)

    attempt = attempt_repair(
        model_caller=caller,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text=json.dumps(prior),
        original_exc=ModelActionParseError("invalid_model_action_json", _NONBATCHABLE_DETAIL),
        available_tool_ids=("save_workspace_artifact", "hydrate_artifact_refs"),
        tool_batch_policies={},
    )
    assert attempt.repair_parse_ok is True
    assert attempt.repair_parsed_action_plan is not None
    assert len(attempt.repair_parsed_action_plan.actions) == 1
    row = attempt.repair_parsed_action_plan.actions[0]
    assert row.action_type == "save_workspace_artifact"
    assert row.action_inputs == {"payload": {"lane": "a", "text": "first save"}}


def test_repair_may_omit_root_closure_dependent_on_whole_batch() -> None:
    prior = _dual_save_plan(with_root_closure=True)
    postponed = {
        "actions": [prior["actions"][1]],
        "rationale": "one save this turn; postpone batch-dependent closure",
        "complete_run": False,
    }

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        assert "omit or defer" in prompt.lower()
        return json.dumps(postponed)

    attempt = attempt_repair(
        model_caller=caller,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text=json.dumps(prior),
        original_exc=ModelActionParseError("invalid_model_action_json", _NONBATCHABLE_DETAIL),
        available_tool_ids=("save_workspace_artifact",),
        tool_batch_policies={},
    )
    assert attempt.repair_parse_ok is True
    plan = attempt.repair_parsed_action_plan
    assert plan is not None
    assert plan.complete_run is False


def test_turn_recovery_includes_compact_hydrate_contract_for_fake_domain() -> None:
    prior = json.dumps(_dual_save_plan())
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        calls.append(prompt)
        return prior

    adapter = _adapter(caller)
    ctx = _orch_context()
    with pytest.raises(RecoverableTurnFailure) as exc_info:
        adapter.choose_action(ctx, projection=None)
    failure = exc_info.value.failure_record
    assert failure["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE
    assert len(calls) == 2
    ctx.loop_memory.turn_recovery.record_failure(failure)

    doc = build_turn_recovery_prompt_document(
        composed_input=_composed(),
        opaque_launch_context={"startup_inventory": {"banned": True}},
        context=ctx,
        projection=None,
        journal_verbatim_keep_n=1,
    )
    body = doc.prompt_body
    blob = json.dumps(body)
    assert "doctrine_blocks" not in body
    assert "startup_inventory" not in blob
    assert prior not in doc.prompt_text
    surface = body.get("surface_packet") or {}
    assert "surface_payloads" not in surface
    run_context = body.get("run_context") or {}
    assert "contract_feedback" not in run_context
    assert "turn_recovery" in run_context
    contracts = surface.get("tool_contracts") or []
    hydrate = next(row for row in contracts if row["tool_id"] == "hydrate_artifact_refs")
    assert "ref_ids" in hydrate["expected_request_shape"]
    assert hydrate["batching"]["allowed"] is True
    save = next(row for row in contracts if row["tool_id"] == "save_workspace_artifact")
    assert save["batching"]["allowed"] is False
    assert doc.prompt_budget is not None
    tool_bucket = doc.prompt_budget["buckets"]["tool_specs_or_surface_payloads"]
    assert tool_bucket >= len(json.dumps({"tool_contracts": contracts}))


def test_compact_tool_contract_projection_is_generic_and_bounded() -> None:
    contracts = project_compact_tool_contracts(
        _fake_domain_surface_payloads(),
        available_tool_ids=("hydrate_artifact_refs", "save_workspace_artifact"),
    )
    ids = [row["tool_id"] for row in contracts]
    assert ids == ["hydrate_artifact_refs", "save_workspace_artifact"]
    assert "noop_probe" not in ids
    for row in contracts:
        assert "tool_id" in row
        assert "expected_request_json_shape" not in row
        assert "example_request" not in row
        assert "startup_inventory" not in row
        if "expected_request_shape" in row:
            assert type(row["expected_request_shape"]) is str
            assert len(row["expected_request_shape"]) <= 320


def test_oversized_transcript_edit_transform_contract_is_not_silently_truncated() -> None:
    from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs

    transform = next(
        spec for spec in build_transcript_edit_tool_specs() if spec.tool_id == "transform_artifact"
    )
    shape = transform.expected_request_shape
    assert len(shape) > 320
    # Production-shaped surface row as composed payloads expose it.
    payloads = {
        "transcript_edit": {
            "tool_specs": [
                {
                    "tool_id": transform.tool_id,
                    "category": transform.category,
                    "purpose": transform.purpose,
                    "expected_request_shape": shape,
                    "batching": transform.batching,
                }
            ]
        }
    }
    contracts = project_compact_tool_contracts(
        payloads,
        available_tool_ids=("transform_artifact",),
    )
    assert len(contracts) == 1
    row = contracts[0]
    assert row["tool_id"] == "transform_artifact"
    assert "expected_request_shape" not in row
    assert row["expected_request_shape_omitted"] is True
    assert row["expected_request_shape_char_count"] == len(shape)
    preview = row["expected_request_shape_preview"]
    assert preview.endswith("...[omitted]")
    assert preview.startswith(shape[:160])
    # The old silent truncate-at-320 path cut mid-token ("reference_overl"); that
    # partial must never appear under the canonical expected_request_shape key.
    assert shape[:320] not in json.dumps({"expected_request_shape": row.get("expected_request_shape")})
    assert "expected_request_shape" not in row


def test_repair_prompt_builder_omits_malformed_or_oversized_extras() -> None:
    from harness.runtime.orchestration.prompt_packet_builder import build_repair_prompt_document

    huge_type = "x" * 10_000
    huge_alias = "a" * 10_000
    doc = build_repair_prompt_document(
        available_tool_ids=("save_workspace_artifact",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail=_NONBATCHABLE_DETAIL,
        previous_response_text="{}",
        repair_targets=["select_one_nonbatchable_action_for_this_turn"],
        repair_context_extras={
            "nonbatchable_action_type": huge_type,
            "affected_action_aliases": [huge_alias, "ok"],
            "sneaky_doctrine": "should never appear",
        },
    )
    body = doc.prompt_body
    repair_context = body["repair_context"]
    assert "nonbatchable_action_type" not in repair_context
    assert "affected_action_aliases" not in repair_context
    assert "sneaky_doctrine" not in repair_context
    blob = doc.prompt_text
    assert huge_type not in blob
    assert huge_alias not in blob
    assert "should never appear" not in blob

    good = build_repair_prompt_document(
        available_tool_ids=("save_workspace_artifact",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail=_NONBATCHABLE_DETAIL,
        previous_response_text="{}",
        repair_targets=["select_one_nonbatchable_action_for_this_turn"],
        repair_context_extras={
            "nonbatchable_action_type": "save_workspace_artifact",
            "affected_action_aliases": ["save_a", "save_b"],
        },
    )
    repair_ok = good.prompt_body["repair_context"]
    assert repair_ok["nonbatchable_action_type"] == "save_workspace_artifact"
    assert repair_ok["affected_action_aliases"] == ["save_a", "save_b"]

    bad_types = build_repair_prompt_document(
        available_tool_ids=("save_workspace_artifact",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail=_NONBATCHABLE_DETAIL,
        previous_response_text="{}",
        repair_context_extras={
            "nonbatchable_action_type": {"nested": True},
            "affected_action_aliases": ("save_a", "save_b"),
        },
    )
    repair_bad = bad_types.prompt_body["repair_context"]
    assert "nonbatchable_action_type" not in repair_bad
    assert "affected_action_aliases" not in repair_bad

    oversized_list = build_repair_prompt_document(
        available_tool_ids=("save_workspace_artifact",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail=_NONBATCHABLE_DETAIL,
        previous_response_text="{}",
        repair_context_extras={
            "affected_action_aliases": [f"alias_{i}" for i in range(20)],
        },
    )
    assert "affected_action_aliases" not in oversized_list.prompt_body["repair_context"]


def test_parser_still_rejects_dual_nonbatchable_saves() -> None:
    with pytest.raises(ModelActionParseError, match="not batchable"):
        parse_action_plan_response(
            json.dumps(_dual_save_plan(with_root_closure=False)),
            available_tool_ids=("save_workspace_artifact",),
            tool_batch_policies={},
        )


def test_existing_truncation_recovery_path_still_usable() -> None:
    # Smoke: base adapter helper from BR-019 suite remains importable/callable.
    adapter = _base_adapter(lambda prompt, model, **_kwargs: prompt)
    assert adapter is not None
