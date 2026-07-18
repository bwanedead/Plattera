"""Deterministic coverage for keyless deed-to-IR read result views (BR-020)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from domains.mapping.deed_to_ir.execution.capability_result_views import (
    SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    build_describe_feature_graph_capabilities_view,
)
from domains.mapping.deed_to_ir.execution.input_result_views import (
    SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
    build_hydrate_deed_to_ir_input_view,
)
from domains.mapping.deed_to_ir.execution.result_view_common import (
    extract_action_inputs,
)
from domains.mapping.deed_to_ir.execution.result_views import (
    attach_deed_to_ir_result_view,
    wrap_handler_with_result_view,
)
from domains.mapping.deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter
from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    agent_result_view_to_wire,
    measure_agent_result_view_chars,
    normalize_agent_result_view_pair,
)
from harness.execution.contracts import ActionDispatchResult, ExecutionStepRequest
from harness.execution.executor import ExecutionExecutor
from harness.execution.wire_codec import (
    action_dispatch_result_from_wire,
    action_dispatch_result_to_wire,
)

_FIXTURE = Path(__file__).resolve().parent / "test_fixtures" / "transcript_edit_output_handoff.json"
_RESOLUTION = Path(__file__).resolve().parent / "test_fixtures" / "resolution_state_snapshot.json"

_SCOPE = {
    "dossier_id": "dossier-fixture",
    "transcription_id": "tx-fixture",
    "workspace_id": "ws-fixture",
    "run_id": "practice-row-live-20260619-76",
}

_EXPECTED_TOOL_IDS = (
    "hydrate_deed_to_ir_input",
    "describe_feature_graph_capabilities",
    "save_ir_artifact",
    "patch_ir_draft",
    "submit_ir_for_mapping",
    "finalize_current_deed_to_ir_output",
    "hydrate_artifact_refs",
    "list_feature_graph_artifacts",
)


def _measure(view) -> int:
    return measure_agent_result_view_chars(agent_result_view_to_wire(view))


def _launch_context(**overrides: object) -> dict:
    base = {
        "dossier_id": _SCOPE["dossier_id"],
        "transcript_edit_output_path": str(_FIXTURE),
        "transcription_id": _SCOPE["transcription_id"],
        "workspace_id": _SCOPE["workspace_id"],
        "run_id": _SCOPE["run_id"],
        "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
        "resolution_state_snapshot": json.loads(_RESOLUTION.read_text(encoding="utf-8")),
    }
    base.update(overrides)
    return base


@dataclass
class _TypedRequest:
    inputs: Any


def _hydrate_outputs() -> dict[str, Any]:
    return {
        "sections": ["mapping_operands", "issues", "evidence_refs"],
        "hydrated_section_count": 3,
        "mapping_operands": {
            "operand_suite_ref": "deed_to_ir:operands:run:run-1",
            "projection_mode": "mapping_operands",
            "operand_groups": [
                {
                    "group_id": "g1",
                    "group_kind": "course_call_candidates",
                    "rows": [{"call_index": 1, "bearing": "N10E"}],
                }
            ],
            "operands": [{"operand_id": "op1", "value_kind": "bearing"}],
            "totals": {"emitted": 1, "available": 1},
            "truncation": {"operands_omitted": 0},
        },
        "results": {
            "mapping_operands": {
                "operand_suite_ref": "deed_to_ir:operands:run:run-1",
                "operands": [{"operand_id": "duplicate-lane"}],
            },
            "issues": [{"id": "iss1", "message": "needs review"}],
            "evidence_refs": ["image:assoc:a:original", "image:assoc:b:original"],
        },
        "issues": [{"id": "iss1", "message": "needs review"}],
        "evidence_refs": ["image:assoc:a:original", "image:assoc:b:original"],
        "errors": [{"code": "partial", "section": "issues", "message": "ok"}],
    }


# --- Request transport ------------------------------------------------------


def test_extract_action_inputs_mapping_and_typed() -> None:
    mapping = {"sections": ["issues"]}
    assert extract_action_inputs(mapping) == mapping
    assert extract_action_inputs(_TypedRequest(inputs={"sections": ["operations"]})) == {
        "sections": ["operations"]
    }
    assert extract_action_inputs(_TypedRequest(inputs=["not-a-mapping"])) is None
    assert extract_action_inputs("bad") is None


def test_mapping_and_typed_inputs_reach_builders() -> None:
    outputs = {
        "sections": ["starter_contract"],
        "starter_contract": {
            "first_draft_authoring_card": {"normal_deed_operation_names": ["Close"]},
            "feature_kinds": ["point"],
            "operations": [{"name": "Close", "category": "geometry"}],
        },
    }
    attached_map = attach_deed_to_ir_result_view(
        {"executed": True, "outputs": outputs},
        action_id="describe_feature_graph_capabilities",
        action_inputs={"sections": ["starter_contract"], "operation_names": ["Close"]},
        **_SCOPE,
    )
    view, _ = normalize_agent_result_view_pair(attached_map["agent_result_view"], None)
    assert view is not None
    assert view.payload["requested_sections"] == ["starter_contract"]
    assert view.payload["requested_operation_names"] == ["Close"]

    wrapped = wrap_handler_with_result_view(
        lambda _r: {"executed": True, "outputs": outputs},
        action_id="describe_feature_graph_capabilities",
        **_SCOPE,
    )
    typed = wrapped(_TypedRequest(inputs={"sections": ["starter_contract"]}))
    assert typed["agent_result_view"]["payload"]["requested_sections"] == ["starter_contract"]


# --- Keylessness ------------------------------------------------------------


def test_read_views_are_keyless() -> None:
    hydrate_view, _ = build_hydrate_deed_to_ir_input_view(
        _hydrate_outputs(),
        action_inputs={"sections": ["mapping_operands", "issues"]},
    )
    caps_view, _ = build_describe_feature_graph_capabilities_view(
        {
            "sections": ["starter_contract"],
            "starter_contract": {
                "first_draft_authoring_card": {"normal_deed_operation_names": ["Close"]},
                "operations": [{"name": "Close"}],
            },
        },
        action_inputs={"sections": ["starter_contract"]},
    )
    assert hydrate_view is not None and caps_view is not None
    assert hydrate_view.schema_id == SCHEMA_HYDRATE_DEED_TO_IR_INPUT
    assert caps_view.schema_id == SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES
    assert hydrate_view.continuity_key is None
    assert caps_view.continuity_key is None
    for view in (hydrate_view, caps_view):
        wire = agent_result_view_to_wire(view)
        assert "continuity_key" not in wire
        assert "continuity_key" not in json.dumps(wire["payload"])
        assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


# --- Input hydration --------------------------------------------------------


def test_input_requested_returned_distinct_and_operand_once() -> None:
    outputs = _hydrate_outputs()
    before = copy.deepcopy(outputs)
    view, omitted = build_hydrate_deed_to_ir_input_view(
        outputs,
        action_inputs={"sections": ["mapping_operands", "issues", "evidence_refs"]},
    )
    assert omitted is None and view is not None
    assert view.payload["requested_sections"] == [
        "mapping_operands",
        "issues",
        "evidence_refs",
    ]
    assert view.payload["returned_sections"] == ["mapping_operands", "issues", "evidence_refs"]
    assert view.payload["mapping_operands"]["operand_suite_ref"] == (
        "deed_to_ir:operands:run:run-1"
    )
    assert view.payload["mapping_operands"]["operand_groups"][0]["group_kind"] == (
        "course_call_candidates"
    )
    blob = json.dumps(view.payload)
    assert blob.count("deed_to_ir:operands:run:run-1") == 1
    assert "duplicate-lane" not in blob
    assert outputs == before
    assert isinstance(before["mapping_operands"]["operand_groups"][0]["rows"][0], dict)


def test_oversized_transcript_omitted_whole() -> None:
    text = "T" * 20_000
    outputs = {
        "sections": ["normalized_transcript"],
        "hydrated_section_count": 1,
        "normalized_transcript": text,
        "results": {"normalized_transcript": text},
    }
    view, omitted = build_hydrate_deed_to_ir_input_view(
        outputs, action_inputs={"sections": ["normalized_transcript"]}
    )
    assert omitted is None and view is not None
    assert "normalized_transcript" not in view.payload
    assert view.payload["sections_omitted"][0] == {
        "section": "normalized_transcript",
        "reason": "view_budget",
        "returned_text_chars": 20_000,
    }
    assert ("T" * 40) not in json.dumps(view.payload)


def test_input_errors_fitted_after_content() -> None:
    outputs = _hydrate_outputs()
    outputs["errors"] = [
        {"code": f"e{i}", "section": "issues", "message": "M" * 300} for i in range(20)
    ]
    view, omitted = build_hydrate_deed_to_ir_input_view(
        outputs, action_inputs={"sections": ["mapping_operands", "issues"]}
    )
    assert omitted is None and view is not None
    assert "mapping_operands" in view.payload
    assert "issues" in view.payload
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_input_host_paths_stripped_and_refusals_skip_views() -> None:
    outputs = _hydrate_outputs()
    outputs["issues"] = [
        {"id": "iss1", "message": "x", "absolute_path": "C:/secret.json", "b64": "abc"}
    ]
    view, _ = build_hydrate_deed_to_ir_input_view(
        outputs, action_inputs={"sections": ["issues"]}
    )
    assert view is not None
    blob = json.dumps(view.payload)
    assert "absolute_path" not in blob
    assert "b64" not in blob
    refused = attach_deed_to_ir_result_view(
        {
            "executed": False,
            "refusal": {"reason_code": "sections_required"},
            "outputs": {"error": {"code": "sections_required"}},
        },
        action_id="hydrate_deed_to_ir_input",
        **_SCOPE,
    )
    assert "agent_result_view" not in refused


# --- Capabilities -----------------------------------------------------------


def test_capabilities_starter_once_and_explicit_operations() -> None:
    outputs = {
        "sections": ["starter_contract", "operations"],
        "starter_contract": {
            "first_draft_authoring_card": {
                "normal_deed_operation_names": ["ReferenceFrame", "Close"]
            },
            "feature_kinds": ["point", "annotation"],
            "operations": [
                {"name": "Close", "category": "geometry", "compiler_support": "supported"}
            ],
        },
        "first_draft_authoring_card": {
            "normal_deed_operation_names": ["ReferenceFrame", "Close"]
        },
        "registered_operations": [
            {
                "name": "Close",
                "category": "geometry",
                "compiler_support": "supported",
                "min_operands": 1,
                "max_operands": 1,
                "required_parameters": [],
                "optional_parameters": [],
                "parameters": [
                    {
                        "name": "tolerance",
                        "param_type": "number",
                        "required": False,
                        "description": "D" * 500,
                    }
                ],
                "description": "Closes a traverse.",
                "compile_note": "N" * 10,
            }
        ],
        "ignored_operation_names": [
            {"name": "annotation", "reason": "feature_kind_not_operation"}
        ],
        "operation_contract": {"op_name": "Exact registered name when available."},
    }
    view, omitted = build_describe_feature_graph_capabilities_view(
        outputs,
        action_inputs={
            "sections": ["starter_contract", "operations"],
            "operation_names": ["Close", "annotation"],
        },
    )
    assert omitted is None and view is not None
    assert view.continuity_key is None
    assert view.payload["ignored_operation_names"][0]["reason"] == "feature_kind_not_operation"
    starter = view.payload["starter_contract"]
    assert "first_draft_authoring_card" in starter
    assert "first_draft_authoring_card" not in view.payload  # not duplicated at top level
    ops = view.payload["operations"]["registered_operations"]
    assert ops[0]["name"] == "Close"
    assert ops[0]["parameters"][0]["description_omitted"] is True
    assert ops[0]["parameters"][0]["description_chars"] == 500
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_capabilities_unrequested_ops_use_compact_index() -> None:
    outputs = {
        "sections": ["operations"],
        "registered_operations": [
            {"name": "Close", "category": "geometry", "compiler_support": "supported"},
            {
                "name": "CourseTraverse",
                "category": "geometry",
                "compiler_support": "supported",
                "parameters": [{"name": "courses", "param_type": "array", "required": True}],
            },
        ],
    }
    view, _ = build_describe_feature_graph_capabilities_view(
        outputs, action_inputs={"sections": ["operations"]}
    )
    assert view is not None
    for row in view.payload["operations"]["registered_operations"]:
        assert "parameters" not in row


# --- Composition / BR-019 preservation --------------------------------------


def test_composition_wraps_six_actions_preserves_order() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    assert [b.tool_id for b in surface.tool_bindings] == list(_EXPECTED_TOOL_IDS)
    by_id = {b.tool_id: b.handler for b in surface.tool_bindings}

    caps = by_id["describe_feature_graph_capabilities"]({"sections": ["starter_contract"]})
    assert "agent_result_view" in caps
    assert caps["agent_result_view"].get("continuity_key") is None

    hydrate = by_id["hydrate_deed_to_ir_input"]({"sections": ["issues"]})
    assert "agent_result_view" in hydrate
    assert hydrate["agent_result_view"].get("continuity_key") is None

    with patch(
        "domains.mapping.deed_to_ir.runtime_adapter.composition.save_ir_artifact",
        return_value={
            "executed": True,
            "outputs": {
                "ir_artifact_ref": "feature_graph:ir:v1",
                "working_draft_ref": "feature_graph:ir:v1",
                "current_draft_ir": {
                    "draft_ir_ref": "feature_graph:ir:v1",
                    "working_draft_ref": "feature_graph:ir:v1",
                    "node_count": 1,
                },
            },
        },
    ):
        saved = by_id["save_ir_artifact"]({"feature_graph": {"graph_id": "g", "nodes": [], "edges": []}})
    assert "agent_result_view" in saved
    assert saved["agent_result_view"]["continuity_key"].startswith(
        "deed_to_ir.current_working_head:"
    )

    with patch(
        "domains.mapping.deed_to_ir.runtime_adapter.composition.list_feature_graph_artifacts",
        return_value={"executed": True, "outputs": {"artifacts": []}},
    ):
        listed = by_id["list_feature_graph_artifacts"]({})
    assert "agent_result_view" not in listed


def test_executor_wire_round_trip_keyless_views() -> None:
    executor = ExecutionExecutor()
    executor.register(
        "hydrate_deed_to_ir_input",
        wrap_handler_with_result_view(
            lambda _r: {"executed": True, "outputs": _hydrate_outputs()},
            action_id="hydrate_deed_to_ir_input",
            **_SCOPE,
        ),
    )
    result = executor.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_deed_to_ir_input",
            idempotency_key="h1",
            inputs={"sections": ["mapping_operands", "issues"]},
        )
    )
    assert result.agent_result_view is not None
    assert result.agent_result_view.continuity_key is None
    adr = ActionDispatchResult(
        action_id="hydrate_deed_to_ir_input",
        executed=True,
        outputs=dict(result.outputs),
        agent_result_view=result.agent_result_view,
    )
    restored = action_dispatch_result_from_wire(action_dispatch_result_to_wire(adr))
    assert restored is not None
    assert restored.agent_result_view is not None
    assert restored.agent_result_view.continuity_key is None
    assert restored.agent_result_view.schema_id == SCHEMA_HYDRATE_DEED_TO_IR_INPUT


def test_small_transcript_retained_whole() -> None:
    text = "Exact normalized transcript text"
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["normalized_transcript"],
            "hydrated_section_count": 1,
            "normalized_transcript": text,
        },
        action_inputs={"sections": ["normalized_transcript"]},
    )
    assert omitted is None and view is not None
    assert view.payload["normalized_transcript"] == text


def test_parcel_metadata_omitted_whole_under_pressure() -> None:
    huge = {f"k{i}": "V" * 800 for i in range(40)}
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["parcel_metadata", "issues"],
            "hydrated_section_count": 2,
            "parcel_metadata": huge,
            "issues": [{"id": "iss1", "message": "keep"}],
        },
        action_inputs={"sections": ["parcel_metadata", "issues"]},
    )
    assert omitted is None and view is not None
    assert "issues" in view.payload
    assert "parcel_metadata" not in view.payload
    assert any(
        row.get("section") == "parcel_metadata" and row.get("reason") == "view_budget"
        for row in view.payload.get("sections_omitted") or []
    )


def test_resolution_state_rows_fit_with_omissions() -> None:
    items = [{"unit_id": f"u{i}", "status": "open", "note": "N" * 400} for i in range(40)]
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["resolution_state"],
            "hydrated_section_count": 1,
            "resolution_state": {
                "resolution_state_ref": "transcript_edit:resolution_state:r1",
                "projection_mode": "selected_items",
                "items": items,
            },
        },
        action_inputs={
            "sections": ["resolution_state"],
            "resolution_unit_ids": ["u1", "u2"],
        },
    )
    assert omitted is None and view is not None
    state = view.payload["resolution_state"]
    assert state["resolution_state_ref"] == "transcript_edit:resolution_state:r1"
    kept = state.get("items") or []
    omitted_count = int(state.get("items_omitted_count") or 0)
    assert len(kept) + omitted_count == 40
    assert kept
    # Request IDs fit after content; they may be omitted when content saturates.
    fitted_ids = view.payload.get("requested_resolution_unit_ids") or []
    assert set(fitted_ids).issubset({"u1", "u2"})
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_capabilities_examples_and_validation_schema() -> None:
    outputs = {
        "sections": ["examples", "validation_schema"],
        "examples": {
            "warning": "Contract-shape examples, not deed evidence.",
            "complete_supported_graph": {"graph_id": "g1", "nodes": [], "edges": []},
            "huge_example": {"pad": "P" * 15_000},
        },
        "canonical_feature_graph_json_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "FeatureGraph",
            "type": "object",
            "required": ["graph_id", "nodes"],
            "properties": {"graph_id": {"type": "string"}},
            "$defs": {
                "Node": {"type": "object", "properties": {"id": {"type": "string"}}},
                "Huge": {"type": "object", "properties": {"pad": {"const": "X" * 12_000}}},
            },
        },
    }
    view, omitted = build_describe_feature_graph_capabilities_view(
        outputs, action_inputs={"sections": ["examples", "validation_schema"]}
    )
    assert omitted is None and view is not None
    examples = view.payload["examples"]
    assert "warning" in examples
    assert "complete_supported_graph" in examples or any(
        row.get("example") == "complete_supported_graph"
        for row in examples.get("examples_omitted") or []
    )
    assert any(
        row.get("example") == "huge_example" and row.get("reason") == "view_budget"
        for row in examples.get("examples_omitted") or []
    )
    schema = view.payload["validation_schema"]
    assert schema.get("title") == "FeatureGraph" or schema.get("type") == "object"
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_complementary_reads_remain_keyless() -> None:
    first = attach_deed_to_ir_result_view(
        {"executed": True, "outputs": _hydrate_outputs()},
        action_id="hydrate_deed_to_ir_input",
        action_inputs={"sections": ["mapping_operands"]},
        **_SCOPE,
    )
    second = attach_deed_to_ir_result_view(
        {"executed": True, "outputs": _hydrate_outputs()},
        action_id="hydrate_deed_to_ir_input",
        action_inputs={"sections": ["issues"]},
        **_SCOPE,
    )
    assert first["agent_result_view"].get("continuity_key") is None
    assert second["agent_result_view"].get("continuity_key") is None


def test_hydrate_artifact_refs_untouched_by_composition() -> None:
    from domains.mapping.deed_to_ir.runtime_adapter import composition as comp

    source = Path(comp.__file__).read_text(encoding="utf-8")
    # Exactly six wrap_handler_with_result_view call sites; artifact hydrate/list stay bare.
    assert source.count("wrap_handler_with_result_view(") == 6
    assert "wrap_handler_with_result_view(\n                make_hydrate_artifact_refs_handler" not in source
    assert 'HYDRATE_ARTIFACT_REFS,\n            make_hydrate_artifact_refs_handler' in source.replace(
        "\r\n", "\n"
    )


# --- Production wire-shape integration (real tooling outputs) ---------------


def _production_handoff_context(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "scope": dict(_SCOPE),
        "source": {
            "loaded_source_label": "fixture",
            "source_revision_ref": "transcript_edit:working:rev:0001",
            "published_at": "2026-06-18T19:57:40Z",
        },
        "normalized_or_mapping_transcript": "Short normalized transcript text",
        "source_transcript_verbatim": "Short verbatim transcript text",
        "issues": [],
        "hitl_decisions": [],
        "parcel_metadata": {"county": "Larimer", "state": "CO"},
        "evidence_refs": [],
        "excerpts": {},
        "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
        "resolution_state_snapshot": json.loads(_RESOLUTION.read_text(encoding="utf-8")),
        "operand_suite_ref": None,
        "inherited_handoff_conditions": {},
    }
    base.update(overrides)
    return base


def test_production_wrapped_sections_retained_and_parcel_unwrapped_once() -> None:
    from tooling.mapping.deed_to_ir.input_hydration import (
        make_hydrate_deed_to_ir_input_handler,
    )

    handler = make_hydrate_deed_to_ir_input_handler(
        handoff_context=_production_handoff_context(
            issues=[{"issue_id": "i1", "summary": "review"}],
            hitl_decisions=[{"prompt_id": "h1", "choice": "accept"}],
        )
    )
    raw = handler(
        {
            "sections": [
                "normalized_transcript",
                "verbatim_transcript",
                "issues",
                "hitl_decisions",
                "parcel_metadata",
                "evidence_refs",
            ]
        }
    )
    assert raw["executed"] is True
    results = raw["outputs"]["results"]
    assert results["normalized_transcript"] == {
        "text": "Short normalized transcript text"
    }
    assert results["issues"] == {"issues": [{"issue_id": "i1", "summary": "review"}]}
    assert results["parcel_metadata"] == {
        "parcel_metadata": {"county": "Larimer", "state": "CO"}
    }

    view, omitted = build_hydrate_deed_to_ir_input_view(
        raw["outputs"],
        action_inputs={
            "sections": [
                "normalized_transcript",
                "verbatim_transcript",
                "issues",
                "hitl_decisions",
                "parcel_metadata",
                "evidence_refs",
            ]
        },
    )
    assert omitted is None and view is not None
    assert view.payload["normalized_transcript"] == "Short normalized transcript text"
    assert view.payload["verbatim_transcript"] == "Short verbatim transcript text"
    assert view.payload["issues"] == [{"issue_id": "i1", "summary": "review"}]
    assert view.payload["hitl_decisions"] == [{"prompt_id": "h1", "choice": "accept"}]
    assert view.payload["evidence_refs"] == []
    assert view.payload["parcel_metadata"] == {"county": "Larimer", "state": "CO"}
    assert "parcel_metadata" not in view.payload["parcel_metadata"]
    assert not any(
        row.get("reason") == "view_budget"
        for row in view.payload.get("sections_omitted") or []
    )


def test_production_empty_wrappers_remain_empty_not_omitted() -> None:
    from tooling.mapping.deed_to_ir.input_hydration import (
        make_hydrate_deed_to_ir_input_handler,
    )

    handler = make_hydrate_deed_to_ir_input_handler(
        handoff_context=_production_handoff_context()
    )
    raw = handler({"sections": ["issues", "hitl_decisions", "evidence_refs"]})
    assert raw["outputs"]["results"]["issues"] == {"issues": []}
    view, omitted = build_hydrate_deed_to_ir_input_view(
        raw["outputs"],
        action_inputs={"sections": ["issues", "hitl_decisions", "evidence_refs"]},
    )
    assert omitted is None and view is not None
    assert view.payload["issues"] == []
    assert view.payload["hitl_decisions"] == []
    assert view.payload["evidence_refs"] == []
    assert "issues" in view.payload
    assert "hitl_decisions" in view.payload
    assert "evidence_refs" in view.payload


def test_production_oversized_wrapped_transcript_omitted_with_char_count() -> None:
    from tooling.mapping.deed_to_ir.input_hydration import (
        make_hydrate_deed_to_ir_input_handler,
    )

    # Tooling bounds at 12000 chars with ellipsis; view must use unwrapped length.
    long_text = "T" * 20_000
    handler = make_hydrate_deed_to_ir_input_handler(
        handoff_context=_production_handoff_context(
            normalized_or_mapping_transcript=long_text
        )
    )
    raw = handler({"sections": ["normalized_transcript"]})
    wrapped = raw["outputs"]["results"]["normalized_transcript"]
    assert isinstance(wrapped, dict) and isinstance(wrapped.get("text"), str)
    # Force an oversized wire text past the view budget while keeping wrapper shape.
    oversized = {"text": "U" * 20_000}
    outputs = dict(raw["outputs"])
    outputs["results"] = {"normalized_transcript": oversized}
    view, omitted = build_hydrate_deed_to_ir_input_view(
        outputs, action_inputs={"sections": ["normalized_transcript"]}
    )
    assert omitted is None and view is not None
    assert "normalized_transcript" not in view.payload
    assert view.payload["sections_omitted"][0] == {
        "section": "normalized_transcript",
        "reason": "view_budget",
        "returned_text_chars": 20_000,
    }


def test_invalid_wrapper_shape_is_not_view_budget() -> None:
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["issues", "normalized_transcript"],
            "results": {
                "issues": {"issues": "not-a-list"},
                "normalized_transcript": {"text": 123},
            },
        },
        action_inputs={"sections": ["issues", "normalized_transcript"]},
    )
    assert omitted is None and view is not None
    reasons = {
        row["section"]: row["reason"] for row in view.payload.get("sections_omitted") or []
    }
    assert reasons["issues"] == "invalid_shape"
    assert reasons["normalized_transcript"] == "invalid_shape"


def test_non_string_request_entries_not_stringified() -> None:
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["issues"],
            "results": {"issues": {"issues": []}},
        },
        action_inputs={
            "sections": ["issues", {"section": "parcel_metadata"}, 12, True, ""],
            "resolution_unit_ids": ["u1", {"id": "u2"}, 3, "u1", "  u3  "],
        },
    )
    assert omitted is None and view is not None
    assert view.payload["requested_sections"] == ["issues"]
    assert view.payload["requested_resolution_unit_ids"] == ["u1", "u3"]


def test_resolution_unit_ids_bounded_with_omission_count() -> None:
    ids = [f"unit-{i:03d}" for i in range(80)]
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {"sections": ["issues"], "results": {"issues": {"issues": []}}},
        action_inputs={"sections": ["issues"], "resolution_unit_ids": ids},
    )
    assert omitted is None and view is not None
    assert view.payload["requested_resolution_unit_ids"] == ids[:64]
    assert view.payload["resolution_unit_ids_omitted_count"] == 16
    # Never substring an ID.
    assert all(uid.startswith("unit-") and len(uid) == 8 for uid in view.payload["requested_resolution_unit_ids"])


def test_section_omissions_survive_full_error_budget() -> None:
    errors = [
        {"code": f"e{i}", "section": "issues", "message": "M" * 280} for i in range(40)
    ]
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["normalized_transcript", "missing_lane"],
            "results": {"normalized_transcript": {"text": "keep me"}},
            "errors": errors,
        },
        action_inputs={"sections": ["normalized_transcript", "parcel_metadata"]},
    )
    assert omitted is None and view is not None
    assert view.payload["normalized_transcript"] == "keep me"
    assert view.payload.get("sections_omitted_count", 0) >= 1
    assert any(
        row.get("section") == "parcel_metadata"
        for row in view.payload.get("sections_omitted") or []
    )


def test_production_capabilities_coursetraverse_and_ignored_ops_do_not_evict() -> None:
    from tooling.mapping.deed_to_ir.feature_graph_capabilities import (
        describe_feature_graph_capabilities,
    )

    ignored = [
        {"name": f"bogus_op_{i}", "reason": "unknown_operation"} for i in range(80)
    ]
    caps = describe_feature_graph_capabilities(
        sections=["operations"],
        operation_names=["CourseTraverse", "not_an_operation", 12, {"x": 1}],
    )
    # Tooling ignores non-strings in its own parser; inject a large ignored list
    # after the real capability payload to pressure the view builder.
    outputs = dict(caps)
    outputs["ignored_operation_names"] = ignored + list(
        outputs.get("ignored_operation_names") or []
    )
    # Non-string operation_names must not be stringified by the view layer.
    view, omitted = build_describe_feature_graph_capabilities_view(
        outputs,
        action_inputs={
            "sections": ["operations"],
            "operation_names": ["CourseTraverse", "not_an_operation", 12, {"x": 1}],
        },
    )
    assert omitted is None and view is not None
    assert view.payload["requested_operation_names"] == [
        "CourseTraverse",
        "not_an_operation",
    ]
    ops = view.payload["operations"]["registered_operations"]
    assert any(row.get("name") == "CourseTraverse" for row in ops)
    course = next(row for row in ops if row.get("name") == "CourseTraverse")
    assert "parameters" in course
    assert any(p.get("name") == "courses" for p in course["parameters"])
    ignored_fitted = view.payload.get("ignored_operation_names") or []
    assert len(ignored_fitted) <= 32
    assert view.payload.get("ignored_operation_names_omitted_count", 0) >= 48
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


# --- Envelope-pressure regressions (row-level / nested fitting) -------------


def test_oversized_issue_skips_but_keeps_small_issue() -> None:
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["issues"],
            "hydrated_section_count": 1,
            "results": {
                "issues": {
                    "issues": [
                        {"issue_id": "big", "summary": "X" * 20_000},
                        {"issue_id": "small", "summary": "keep"},
                    ]
                }
            },
        },
        action_inputs={"sections": ["issues"]},
    )
    assert omitted is None and view is not None
    assert "issues" in view.payload
    assert view.payload["issues"] == [{"issue_id": "small", "summary": "keep"}]
    assert view.payload.get("issues_omitted_count") == 1
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_oversized_hitl_skips_but_keeps_small_decision() -> None:
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["hitl_decisions"],
            "hydrated_section_count": 1,
            "results": {
                "hitl_decisions": {
                    "hitl_decisions": [
                        {"prompt_id": "big", "choice": "Y" * 20_000},
                        {"prompt_id": "small", "choice": "accept"},
                    ]
                }
            },
        },
        action_inputs={"sections": ["hitl_decisions"]},
    )
    assert omitted is None and view is not None
    assert view.payload["hitl_decisions"] == [{"prompt_id": "small", "choice": "accept"}]
    assert view.payload.get("hitl_decisions_omitted_count") == 1
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_oversized_evidence_ref_skips_but_keeps_short_ref() -> None:
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["evidence_refs"],
            "hydrated_section_count": 1,
            "results": {
                "evidence_refs": {
                    "evidence_refs": ["image:" + ("z" * 20_000), "image:assoc:a:original"]
                }
            },
        },
        action_inputs={"sections": ["evidence_refs"]},
    )
    assert omitted is None and view is not None
    assert view.payload["evidence_refs"] == ["image:assoc:a:original"]
    assert view.payload.get("evidence_refs_omitted_count") == 1
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_mapping_operands_canonical_projector_then_view_pressure() -> None:
    tooling_omitted = 2
    operands = [
        {"operand_id": "big", "value_kind": "bearing", "note": "N" * 20_000},
        {"operand_id": "small", "value_kind": "distance", "note": "ok"},
    ]
    operands.extend(
        {
            "operand_id": f"op{i}",
            "value_kind": "bearing",
            "note": f"row-{i}",
        }
        for i in range(2, 64)
    )
    assert len(operands) == 64
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["mapping_operands"],
            "hydrated_section_count": 1,
            "mapping_operands": {
                "operand_suite_ref": "deed_to_ir:operands:run:pressure",
                "projection_mode": "mapping_operands",
                "totals": {"emitted": 64, "available": 66},
                "truncation": {"operands_omitted": tooling_omitted},
                "operands": operands,
            },
        },
        action_inputs={"sections": ["mapping_operands"]},
    )
    assert omitted is None and view is not None
    ops = view.payload["mapping_operands"]
    assert ops["operand_suite_ref"] == "deed_to_ir:operands:run:pressure"
    kept = ops.get("operands") or []
    assert any(row.get("operand_id") == "small" for row in kept)
    assert not any(row.get("operand_id") == "big" for row in kept)
    # Canonical projector keeps 16 candidates from 64; view then skips oversized.
    projector_omitted = 64 - 16
    view_omitted = 16 - len(kept)
    assert int(ops.get("operands_omitted_count") or 0) == (
        tooling_omitted + projector_omitted + view_omitted
    )
    assert len(kept) + int(ops["operands_omitted_count"]) == 64 + tooling_omitted
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_resolution_index_retains_totals_and_relations() -> None:
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["resolution_state"],
            "hydrated_section_count": 1,
            "results": {
                "resolution_state": {
                    "projection_mode": "index",
                    "resolution_state_ref": "transcript_edit:resolution_state:idx",
                    "schema_version": "resolution_state.v1",
                    "active_item_id": "item-1",
                    "totals": {"items": 2, "relations": 1, "covered_units": 2},
                    "truncation": {"items_omitted": 3, "relations_omitted": 1},
                    "items": [
                        {"item_id": "item-1", "status": "open"},
                        {"item_id": "item-2", "status": "open", "pad": "P" * 15_000},
                    ],
                    "relations": [
                        {"from_id": "item-1", "to_id": "item-2", "kind": "depends"},
                        {
                            "from_id": "item-2",
                            "to_id": "item-1",
                            "kind": "depends",
                            "pad": "R" * 15_000,
                        },
                    ],
                }
            },
        },
        action_inputs={"sections": ["resolution_state"]},
    )
    assert omitted is None and view is not None
    state = view.payload["resolution_state"]
    assert state["projection_mode"] == "index"
    assert state["resolution_state_ref"] == "transcript_edit:resolution_state:idx"
    assert state["schema_version"] == "resolution_state.v1"
    assert state["active_item_id"] == "item-1"
    assert state["totals"]["items"] == 2
    assert state["truncation"]["items_omitted"] == 3
    assert any(row.get("item_id") == "item-1" for row in state.get("items") or [])
    assert any(row.get("from_id") == "item-1" for row in state.get("relations") or [])
    # Tooling truncation + view pressure accumulate.
    assert int(state.get("items_omitted_count") or 0) >= 4
    assert int(state.get("relations_omitted_count") or 0) >= 2
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_hydrated_section_count_preserved_exactly() -> None:
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["issues"],
            "hydrated_section_count": 7,
            "results": {"issues": {"issues": []}},
        },
        action_inputs={"sections": ["issues"]},
    )
    assert omitted is None and view is not None
    assert view.payload["hydrated_section_count"] == 7
    assert view.payload["issues"] == []
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_oversized_request_names_then_close_retains_close_contract() -> None:
    from tooling.mapping.deed_to_ir.feature_graph_capabilities import (
        describe_feature_graph_capabilities,
    )

    names = [f"unknown_op_{i}_" + ("Z" * 4_000) for i in range(31)] + ["Close"]
    caps = describe_feature_graph_capabilities(
        sections=["operations"],
        operation_names=names,
    )
    assert any(
        isinstance(row, dict) and row.get("name") == "Close"
        for row in caps.get("registered_operations") or []
    )
    view, omitted = build_describe_feature_graph_capabilities_view(
        caps,
        action_inputs={"sections": ["operations"], "operation_names": names},
    )
    assert omitted is None and view is not None
    assert view.payload.get("lane") == "feature_graph_capabilities"
    ops = view.payload["operations"]["registered_operations"]
    assert any(row.get("name") == "Close" for row in ops)
    close = next(row for row in ops if row.get("name") == "Close")
    assert "parameters" in close or "min_operands" in close
    requested_names = view.payload.get("requested_operation_names") or []
    assert "Close" in requested_names
    omitted_names = int(view.payload.get("operation_names_omitted_count") or 0)
    assert omitted_names >= 1
    assert len(requested_names) + omitted_names == 32
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_oversized_resolution_unit_ids_do_not_evict_selected_rows() -> None:
    selected = {
        "projection_mode": "selected_rows",
        "resolution_state_ref": "transcript_edit:resolution_state:sel",
        "filter": {"resolution_unit_ids": ["keep-me"]},
        "items": [
            {"unit_id": "keep-me", "status": "open", "note": "selected"},
        ],
    }
    huge_ids = ["ID_" + ("Q" * 900) for _ in range(40)] + ["keep-me"]
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["resolution_state"],
            "hydrated_section_count": 1,
            "results": {"resolution_state": selected},
        },
        action_inputs={
            "sections": ["resolution_state"],
            "resolution_unit_ids": huge_ids,
        },
    )
    assert omitted is None and view is not None
    state = view.payload["resolution_state"]
    assert any(row.get("unit_id") == "keep-me" for row in state.get("items") or [])
    assert "keep-me" in (view.payload.get("requested_resolution_unit_ids") or []) or (
        int(view.payload.get("resolution_unit_ids_omitted_count") or 0) >= 1
    )
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_sixty_four_moderate_resolution_ids_do_not_evict_selected_rows() -> None:
    """Ordinary (not individually oversized) request IDs must not precede content."""
    selected = {
        "projection_mode": "selected_rows",
        "resolution_state_ref": "transcript_edit:resolution_state:bulk",
        "filter": {"resolution_unit_ids": ["keep-row"]},
        "items": [
            {
                "unit_id": "keep-row",
                "status": "open",
                "note": "selected-row-must-survive-request-metadata",
                "detail": "D" * 200,
            }
        ],
    }
    # 64 moderately sized complete IDs — enough volume to matter if fitted first.
    moderate_ids = [f"resolution-unit-identifier-{i:03d}-pad-{('m' * 40)}" for i in range(64)]
    view, omitted = build_hydrate_deed_to_ir_input_view(
        {
            "sections": ["resolution_state"],
            "hydrated_section_count": 1,
            "results": {"resolution_state": selected},
        },
        action_inputs={
            "sections": ["resolution_state"],
            "resolution_unit_ids": moderate_ids,
        },
    )
    assert omitted is None and view is not None
    state = view.payload["resolution_state"]
    assert any(row.get("unit_id") == "keep-row" for row in state.get("items") or [])
    # Request IDs may be partially omitted after content, but content stays.
    fitted_ids = view.payload.get("requested_resolution_unit_ids") or []
    omitted_ids = int(view.payload.get("resolution_unit_ids_omitted_count") or 0)
    assert len(fitted_ids) + omitted_ids == 64
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS
