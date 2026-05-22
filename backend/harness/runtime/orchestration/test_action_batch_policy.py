"""Policy resolution tests for action_batch."""

from __future__ import annotations

import pytest

from domains.mapping.transcript_edit.domain_pack import build_transcript_edit_domain_pack
from harness.runtime.orchestration.action_batch import ActionBatchItem
from harness.runtime.orchestration.action_batch import validate_action_batch_policy
from harness.runtime.orchestration.action_batch import ActionBatchValidationError
from harness.runtime.orchestration.tool_batch_policy import (
    DomainActionBatchPolicy,
    ToolBatchPolicy,
    effective_tool_cap,
    policy_from_tool_spec_row,
    resolve_tool_batch_policies,
)


def _read_only_policy(tool_id: str = "hydrate_artifact_refs", *, max_calls: int = 3) -> ToolBatchPolicy:
    return ToolBatchPolicy(
        tool_id=tool_id,
        allowed=True,
        max_calls_per_batch=max_calls,
        side_effect_class="read_only",
    )


def _derived_policy(tool_id: str = "transform_artifact", *, max_calls: int = 4) -> ToolBatchPolicy:
    return ToolBatchPolicy(
        tool_id=tool_id,
        allowed=True,
        max_calls_per_batch=max_calls,
        side_effect_class="derived_artifact",
    )


def test_policy_from_tool_spec_row_requires_explicit_batching() -> None:
    assert policy_from_tool_spec_row({"tool_id": "x"}) is None
    row = {
        "tool_id": "hydrate_artifact_refs",
        "batching": {
            "allowed": True,
            "max_calls_per_batch": 3,
            "side_effect_class": "read_only",
        },
    }
    policy = policy_from_tool_spec_row(row)
    assert policy is not None
    assert policy.allowed is True
    assert policy.max_calls_per_batch == 3


def test_tool_cap_wins_over_global_cap() -> None:
    policy = _derived_policy(max_calls=2)
    cap = effective_tool_cap(
        tool_id="transform_artifact",
        tool_policy=policy,
        global_default=5,
        domain_policy=None,
    )
    assert cap == 2


def test_domain_cap_tightens_tool_and_global() -> None:
    policy = _derived_policy(max_calls=4)
    domain = DomainActionBatchPolicy(tool_caps={"transform_artifact": 2})
    cap = effective_tool_cap(
        tool_id="transform_artifact",
        tool_policy=policy,
        global_default=5,
        domain_policy=domain,
    )
    assert cap == 2


def test_missing_batch_policy_rejects() -> None:
    items = (
        ActionBatchItem(alias="a", action_type="save_workspace_artifact", action_inputs={}),
    )
    with pytest.raises(ActionBatchValidationError, match="not batchable"):
        validate_action_batch_policy(
            items,
            available_tool_ids=("save_workspace_artifact",),
            tool_batch_policies={},
            domain_batch_policy=None,
        )


def test_read_only_and_derived_allowed_separately() -> None:
    for policy in (_read_only_policy(), _derived_policy()):
        validate_action_batch_policy(
            (ActionBatchItem(alias="a", action_type=policy.tool_id, action_inputs={}),),
            available_tool_ids=(policy.tool_id,),
            tool_batch_policies={policy.tool_id: policy},
            domain_batch_policy=None,
        )


def test_mixed_side_effect_classes_rejected() -> None:
    items = (
        ActionBatchItem(alias="a", action_type="hydrate_artifact_refs", action_inputs={}),
        ActionBatchItem(alias="b", action_type="transform_artifact", action_inputs={}),
    )
    policies = {
        "hydrate_artifact_refs": _read_only_policy(),
        "transform_artifact": _derived_policy(),
    }
    with pytest.raises(ActionBatchValidationError, match="mix"):
        validate_action_batch_policy(
            items,
            available_tool_ids=tuple(policies.keys()),
            tool_batch_policies=policies,
            domain_batch_policy=None,
        )


def test_resolve_tool_batch_policies_from_surface_payloads() -> None:
    policies = resolve_tool_batch_policies({
        "transcript_edit": {
            "tool_specs": [
                {
                    "tool_id": "hydrate_artifact_refs",
                    "batching": {
                        "allowed": True,
                        "max_calls_per_batch": 3,
                        "side_effect_class": "read_only",
                    },
                },
            ],
        },
    })
    assert "hydrate_artifact_refs" in policies
    assert policies["hydrate_artifact_refs"].side_effect_class == "read_only"


def test_resolve_tool_batch_policies_finds_nested_runtime_shape() -> None:
    pack = build_transcript_edit_domain_pack()
    inner = pack.build_surface_payload()
    policies = resolve_tool_batch_policies({
        "transcript_edit": {"transcript_edit": inner},
    })
    assert "hydrate_artifact_refs" in policies
    assert "transform_artifact" in policies
    transform = policies["transform_artifact"]
    assert transform.allowed is True
    assert transform.max_calls_per_batch == 4
    assert transform.side_effect_class == "derived_artifact"
