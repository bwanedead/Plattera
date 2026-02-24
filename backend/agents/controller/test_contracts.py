from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel.models import ActionType
from backend.agents.controller.contracts import (
    KernelStepProposal,
    action_tool_specs_for_menu,
    coerce_action_type,
    kernel_step_tool_spec,
    validate_action_args,
)


def test_kernel_step_tool_spec_has_required_minimal_fields() -> None:
    spec = kernel_step_tool_spec()
    assert spec.name == "kernel_step"
    params = spec.parameters_schema
    assert isinstance(params, dict)
    required = params.get("required")
    assert required == ["action_type", "args", "idempotency_key", "why"]


def test_action_tool_specs_for_menu_draft_ir_requires_graph() -> None:
    specs = action_tool_specs_for_menu([ActionType.DRAFT_IR.value])
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == ActionType.DRAFT_IR.value
    params = spec.parameters_schema
    assert isinstance(params, dict)
    required = params.get("required")
    assert isinstance(required, list)
    assert "dossier_id" in required
    assert "graph" in required


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


def test_validate_action_args_draft_ir_requires_graph_even_with_deed_ref() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.DRAFT_IR,
        args={
            "dossier_id": "D1",
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
        },
    )
    assert cleaned is None
    assert reason_code == "draft_ir_requires_graph"
    assert missing == []


def test_validate_action_args_draft_ir_accepts_graph() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.DRAFT_IR,
        args={
            "dossier_id": "D1",
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
            "graph": {"graph_id": "g1", "nodes": [{"id": "n1", "kind": "point", "geometry": {"type": "Point", "coordinates": [0, 0]}}], "edges": [], "metadata": {"source": "deed"}},
        },
    )
    assert reason_code is None
    assert missing == []
    assert isinstance(cleaned, dict)
    assert isinstance(cleaned.get("graph"), dict)
