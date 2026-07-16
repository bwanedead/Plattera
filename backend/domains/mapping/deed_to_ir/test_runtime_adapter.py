"""Runtime adapter tests for deed_to_ir foundation tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from domains.mapping.deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter
from harness.runtime.composition import TurnSurface

_FIXTURE = Path(__file__).resolve().parent / "test_fixtures" / "transcript_edit_output_handoff.json"
_RESOLUTION = Path(__file__).resolve().parent / "test_fixtures" / "resolution_state_snapshot.json"

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


def _launch_context(**overrides: object) -> dict:
    base = {
        "dossier_id": "dossier-fixture",
        "transcript_edit_output_path": str(_FIXTURE),
        "transcription_id": "tx-fixture",
        "workspace_id": "ws-fixture",
        "run_id": "practice-row-live-20260619-76",
        "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
        "resolution_state_snapshot": json.loads(_RESOLUTION.read_text(encoding="utf-8")),
    }
    base.update(overrides)
    return base


def test_runtime_adapter_builds_turn_surface_with_eight_tools() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())

    assert isinstance(surface, TurnSurface)
    assert surface.surface_id == "deed_to_ir"
    assert [b.tool_id for b in surface.tool_bindings] == list(_EXPECTED_TOOL_IDS)

    payload = surface.payload["deed_to_ir"]
    assert payload["tool_ids"] == list(_EXPECTED_TOOL_IDS)
    assert len(payload["tool_specs"]) == 8

    handoff = surface.payload["deed_to_ir_startup_handoff"]
    assert handoff["resolution_state_ref"] == "transcript_edit:resolution_state:fixture-001"
    assert handoff["operand_suite_ref"].startswith("deed_to_ir:operands:run:")
    assert handoff["resolution_state_counts"]["items"] == 2
    assert "resolution_state_snapshot" not in handoff
    assert handoff["resolution_state_summary"]
    assert "transcript_edit_output_path" not in handoff["source"]
    assert str(_FIXTURE) not in surface.blocks[3].content


def test_runtime_adapter_requires_transcript_edit_output_path() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    with pytest.raises(ValueError, match="transcript_edit_output_path_required"):
        adapter.build_turn_surface({"dossier_id": "d1"})


def test_describe_capabilities_handler() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(b.handler for b in surface.tool_bindings if b.tool_id == "describe_feature_graph_capabilities")
    result = handler({})
    assert result["executed"] is True
    assert "starter_contract" in result["outputs"]
    assert result["outputs"]["sections"] == ["starter_contract"]


def test_describe_capabilities_handler_supports_focused_contract_packet() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(b.handler for b in surface.tool_bindings if b.tool_id == "describe_feature_graph_capabilities")
    result = handler(
        {
            "sections": ["core_schema", "operations", "examples"],
            "operation_names": ["LineStep"],
        }
    )
    assert result["executed"] is True
    assert [row["name"] for row in result["outputs"]["registered_operations"]] == ["LineStep"]
    assert set(result["outputs"]["examples"]["operation_expressions"]) == {"LineStep"}


def test_describe_capabilities_handler_rejects_all_invalid_operation_names() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(b.handler for b in surface.tool_bindings if b.tool_id == "describe_feature_graph_capabilities")
    result = handler({"operation_names": ["MysteryOperation"]})
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "no_valid_feature_graph_operation_names"


def test_describe_capabilities_handler_partial_succeeds_with_feature_kind_warning() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(b.handler for b in surface.tool_bindings if b.tool_id == "describe_feature_graph_capabilities")
    result = handler(
        {
            "sections": ["operations"],
            "operation_names": ["ReferenceFrame", "Close", "annotation"],
        }
    )
    assert result["executed"] is True
    names = [row["name"] for row in result["outputs"]["registered_operations"]]
    assert names == ["ReferenceFrame", "Close"]
    ignored = result["outputs"]["ignored_operation_names"]
    assert ignored == [{"name": "annotation", "reason": "feature_kind_not_operation"}]


def test_describe_capabilities_handler_refuses_annotation_only() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(b.handler for b in surface.tool_bindings if b.tool_id == "describe_feature_graph_capabilities")
    result = handler({"operation_names": ["annotation"]})
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "no_valid_feature_graph_operation_names"


def test_hydrate_input_handler_via_bindings() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(b.handler for b in surface.tool_bindings if b.tool_id == "hydrate_deed_to_ir_input")
    result = handler({"sections": ["issues", "resolution_state"]})
    assert result["executed"] is True
    assert "issues" in result["outputs"]["results"]
    assert result["outputs"]["results"]["resolution_state"]["items"]


def test_save_ir_handler_sanitizes_exception_paths() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(b.handler for b in surface.tool_bindings if b.tool_id == "save_ir_artifact")
    secret_path = r"C:\secret\dossiers_data\artifacts\feature_graphs\d1\ir.json"
    with patch(
        "domains.mapping.deed_to_ir.runtime_adapter.composition.save_ir_artifact",
        side_effect=OSError(f"Failed to write {secret_path}"),
    ):
        result = handler({"feature_graph": {"graph_id": "g", "nodes": [], "edges": []}})
    assert result["executed"] is False
    dumped = json.dumps(result)
    assert secret_path not in dumped
    assert "C:\\\\secret" not in dumped
    assert result["outputs"]["error"]["code"] == "deed_to_ir_tool_error"
    assert result["refusal"]["reason_code"] == "deed_to_ir_tool_error"


def test_finalize_handler_passes_malformed_maps_through() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(
        b.handler for b in surface.tool_bindings if b.tool_id == "finalize_current_deed_to_ir_output"
    )
    captured: dict[str, object] = {}

    def _fake_finalize(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "executed": False,
            "refusal": {
                "reason_code": "finalization_decision_invalid",
                "retryable": True,
                "blocked_by_invariant": False,
                "blocked_by_budget": False,
                "missing_inputs": [],
            },
            "outputs": {
                "error": {
                    "code": "finalization_decision_invalid",
                    "message": "scope_statuses must be an object map",
                }
            },
        }

    with patch(
        "domains.mapping.deed_to_ir.runtime_adapter.composition.finalize_current_deed_to_ir_output",
        side_effect=_fake_finalize,
    ):
        list_result = handler({"scope_statuses": ["parcel_1"]})
        assert captured["scope_statuses"] == ["parcel_1"]
        assert list_result["refusal"]["reason_code"] == "finalization_decision_invalid"
        assert list_result["refusal"]["retryable"] is True

        scalar_result = handler({"rationales": 42})
        assert captured["rationales"] == 42
        assert scalar_result["refusal"]["retryable"] is True


def test_error_code_accepts_machine_safe_value_error_codes() -> None:
    from domains.mapping.deed_to_ir.runtime_adapter.composition import _error_code_for_exception

    assert _error_code_for_exception(ValueError("dossier_id_required")) == "dossier_id_required"
    assert (
        _error_code_for_exception(ValueError("resolution_state_ref_invalid_prefix"))
        == "resolution_state_ref_invalid_prefix"
    )
    assert _error_code_for_exception(ValueError("/tmp/secret/file.json missing")) == "deed_to_ir_tool_error"
    assert _error_code_for_exception(ValueError(r"C:\secret\file.json")) == "deed_to_ir_tool_error"
