from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel.models import ActionType
from backend.agents.controller.contracts import (
    KernelStepProposal,
    coerce_action_type,
    kernel_step_tool_schema,
    validate_action_args,
)


def test_kernel_step_tool_schema_has_required_minimal_fields() -> None:
    schema = kernel_step_tool_schema()
    function = schema.get("function")
    assert isinstance(function, dict)
    params = function.get("parameters")
    assert isinstance(params, dict)
    required = params.get("required")
    assert required == ["action_type", "args", "idempotency_key", "why"]


def test_kernel_step_proposal_requires_declare_done_justification() -> None:
    bad = {
        "action_type": "declare_done",
        "idempotency_key": "k1",
        "why": "done",
        "args": {},
    }
    try:
        KernelStepProposal.model_validate(bad)
    except Exception as exc:
        assert "declare_done_justification_required" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_coerce_action_type_returns_none_for_unknown_value() -> None:
    assert coerce_action_type("not_a_real_action") is None
    assert coerce_action_type("compile") == ActionType.COMPILE


def test_validate_action_args_compile_requires_ir_ref() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.COMPILE,
        args={},
    )
    assert cleaned is None
    assert reason_code == "compile_requires_ir_artifact_ref_or_updated_ir_artifact_ref_or_ir_artifact_path"
    assert missing == []


def test_validate_action_args_retrieve_evidence_requires_query() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.RETRIEVE_EVIDENCE,
        args={},
    )
    assert cleaned is None
    assert reason_code == "retrieve_evidence_inputs_invalid"
    assert missing == ["query"]


def test_validate_action_args_returns_cleaned_payload() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.HYDRATE_DEED,
        args={"dossier_id": "abc", "source_entry_ref": None},
    )
    assert reason_code is None
    assert missing == []
    assert cleaned == {"dossier_id": "abc"}
