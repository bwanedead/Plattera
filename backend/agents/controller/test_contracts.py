from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel.harness_action_ids import ActionType
from backend.agents.transcript_edit.execution_action_ids import (
    TX_APPLY_EDIT_PLAN,
    TX_OPEN_TRANSCRIPT_SPANS,
)
from backend.agents.controller.contracts import (
    KernelStepProposal,
    action_how_to_guide,
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
    props = params.get("properties")
    assert isinstance(props, dict)
    assert "display_delta" in props


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


def test_kernel_step_proposal_allows_missing_declare_done_for_controller_refusal_path() -> None:
    payload = {
        "action_type": "declare_done",
        "idempotency_key": "k1",
        "why": "done",
        "args": {},
    }
    proposal = KernelStepProposal.model_validate(payload)
    assert proposal.action_type == "declare_done"
    assert proposal.declare_done is None


def test_kernel_step_proposal_allows_untrusted_display_delta_any_shape() -> None:
    proposal = KernelStepProposal.model_validate(
        {
            "action_type": "open_artifact",
            "idempotency_key": "k1",
            "why": "inspect",
            "args": {"artifact_ref": "artifacts/deed/d1.json"},
            "display_delta": {"weird": ["shape", 1]},
        }
    )
    assert isinstance(proposal.display_delta, dict)


def test_action_how_to_guide_declare_done_has_concrete_minimal_example() -> None:
    guide = action_how_to_guide(
        action_type=ActionType.DECLARE_DONE,
        reason_code=None,
        context_inputs={
            "latest_ir_ref": "artifacts/ir/ir-001.json",
        },
    )
    example = guide["minimal_working_example"]
    assert isinstance(example, dict)
    assert "declare_done" in example
    dd = example["declare_done"]
    assert isinstance(dd, dict)
    assert isinstance(dd.get("artifact_refs"), dict)


def test_coerce_action_type_returns_none_for_unknown_value() -> None:
    assert coerce_action_type("not_a_real_action") is None
    assert coerce_action_type("compile") == ActionType.COMPILE


def test_validate_action_args_compile_requires_ir_ref() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.COMPILE.value,
        args={},
    )
    assert cleaned is None
    assert reason_code == "compile_requires_ir_artifact_ref_or_updated_ir_artifact_ref_or_ir_artifact_path"
    assert missing == []


def test_validate_action_args_retrieve_evidence_requires_query() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.RETRIEVE_EVIDENCE.value,
        args={},
    )
    assert cleaned is None
    assert reason_code == "retrieve_evidence_inputs_invalid"
    assert missing == ["query"]


def test_validate_action_args_returns_cleaned_payload() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.HYDRATE_DEED.value,
        args={"dossier_id": "abc", "source_entry_ref": None},
    )
    assert reason_code is None
    assert missing == []
    assert cleaned == {"dossier_id": "abc"}


def test_validate_action_args_draft_ir_requires_graph_even_with_deed_ref() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=ActionType.DRAFT_IR.value,
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
        action_type=ActionType.DRAFT_IR.value,
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


def test_validate_action_args_tx_open_transcript_spans_requires_source_and_query_shape() -> None:
    cleaned, reason_code, missing = validate_action_args(
        action_type=TX_OPEN_TRANSCRIPT_SPANS,
        args={"anchors": [{"start_anchor": "Beginning", "end_anchor": "P.O.B."}]},
    )
    assert cleaned is None
    assert reason_code == "tx_open_spans_requires_source_transcript_ref_or_source_text"
    assert missing == []


def test_action_tool_specs_for_menu_tx_apply_edit_plan_requires_edit_plan() -> None:
    specs = action_tool_specs_for_menu([TX_APPLY_EDIT_PLAN])
    assert len(specs) == 1
    params = specs[0].parameters_schema
    required = params.get("required")
    assert isinstance(required, list)
    assert "edit_plan" in required
