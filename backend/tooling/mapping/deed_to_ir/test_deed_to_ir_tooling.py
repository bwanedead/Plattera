"""Tests for deed-to-IR foundation tooling."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from feature_graph.compiler import compile_graph
from feature_graph.models import FeatureEdge, FeatureGraph, FeatureKind, FeatureNode, FeatureRef, OpExpr
from feature_graph.operations import OPERATION_REGISTRY
from feature_graph.provenance import ProvenanceAttachment, SourceEntityLink

from tooling.mapping.deed_to_ir.artifact_hydration import (
    hydrate_artifact_refs,
    hydrate_feature_graph_artifact_refs,
    list_feature_graph_artifacts,
)
from tooling.mapping.deed_to_ir.feature_graph_capabilities import describe_feature_graph_capabilities
from tooling.mapping.deed_to_ir.input_hydration import make_hydrate_deed_to_ir_input_handler
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.feature_graph_examples import build_deed_to_ir_authoring_example
from tooling.mapping.deed_to_ir.ir_draft_patch import patch_ir_draft
from tooling.mapping.deed_to_ir.mapping_operands_projection import build_mapping_operands, build_operand_groups
from tooling.mapping.deed_to_ir.operand_suite_refs import OPERAND_SUITE_REF, build_operand_suite_ref
from tooling.mapping.deed_to_ir.resolution_state_projection import (
    build_resolution_state_index,
    build_resolution_state_selected_rows,
    mechanical_resolution_state_snapshot,
    resolution_state_counts,
)

_PRACTICE_RESOLUTION_FIXTURE = (
    Path(__file__).resolve().parents[4] / "practice_deeds" / "right_of_way" / "deed_to_ir" / "resolution_state.json"
)

_FIXTURE = Path(__file__).resolve().parents[3] / "domains" / "mapping" / "deed_to_ir" / "test_fixtures"
_HANDOFF_FIXTURE = _FIXTURE / "transcript_edit_output_handoff.json"
_RESOLUTION_FIXTURE = _FIXTURE / "resolution_state_snapshot.json"


def _handoff_context() -> dict:
    from tooling.mapping.deed_to_ir import load_transcript_edit_output_handoff

    loaded = load_transcript_edit_output_handoff(output_path=_HANDOFF_FIXTURE)
    resolution = json.loads(_RESOLUTION_FIXTURE.read_text(encoding="utf-8"))
    return {
        **loaded,
        "scope": {
            "dossier_id": "dossier-fixture",
            "run_id": "practice-row-live-20260619-76",
            "workspace_id": "ws-fixture",
            "transcription_id": "tx-fixture",
        },
        "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
        "resolution_state_snapshot": resolution,
    }


def test_describe_feature_graph_capabilities_projects_starter_contract():
    caps = describe_feature_graph_capabilities()
    assert caps.get("sections") == ["starter_contract"]
    starter = caps["starter_contract"]
    assert "feature_kinds" in starter
    assert "point" in starter["feature_kinds"]
    ops = starter["operations"]
    assert any(op["name"] == "LineStep" for op in ops)
    line_step = next(op for op in ops if op["name"] == "LineStep")
    assert line_step["compiler_support"] == "supported"
    assert "feature_graph:ir:" in starter["artifact_ref_prefixes"]["ir"]


def test_capability_projection_covers_runtime_models_without_schema_drift():
    caps = describe_feature_graph_capabilities(sections=["core_schema", "provenance"])
    core_models = caps["model_schemas"]
    assert set(core_models["FeatureGraph"]["fields"]) == set(FeatureGraph.model_fields)
    assert set(core_models["FeatureNode"]["fields"]) == set(FeatureNode.model_fields)
    assert set(core_models["FeatureEdge"]["fields"]) == set(FeatureEdge.model_fields)
    assert set(core_models["FeatureRef"]["fields"]) == set(FeatureRef.model_fields)
    assert set(core_models["OpExpr"]["fields"]) == set(OpExpr.model_fields)
    assert "SourceEntityLink" in caps["provenance_schemas"]
    assert "TextSpan" in caps["provenance_schemas"]
    assert "at most one" in caps["content_rules"]["feature_node_content"].lower()


def test_capability_operation_filter_and_examples_are_valid():
    selected = ["TiedPoint", "CourseTraverse", "Close"]
    caps = describe_feature_graph_capabilities(
        sections=["operations", "examples"],
        operation_names=selected,
    )
    assert [row["name"] for row in caps["registered_operations"]] == selected
    assert set(caps["examples"]["operation_expressions"]) == set(selected)
    assert "never copy example values" in caps["examples"]["warning"].lower()
    graph_payload = caps["examples"]["complete_supported_graph"]
    assert graph_payload["nodes"][0]["op_expr"]["op_name"] == "ReferenceFrame"
    assert graph_payload["nodes"][0]["op_expr"]["params"]["frame_type"] == "plss_example"
    boundary_links = graph_payload["nodes"][2]["provenance"]["source_entity_links"]
    assert len(boundary_links) == 8
    assert all(link["entity_type"] == "resolution_unit" for link in boundary_links)
    graph = FeatureGraph.model_validate(graph_payload)
    compiled = compile_graph(graph)
    assert {
        "example_frame",
        "example_start_anchor",
        "example_traverse",
        "example_region",
    }.issubset(compiled.compiled_features)


def test_capability_registry_projection_matches_registered_vocabulary():
    caps = describe_feature_graph_capabilities(sections=["operations"])
    assert {row["name"] for row in caps["registered_operations"]} == set(OPERATION_REGISTRY)
    line_step = next(row for row in caps["registered_operations"] if row["name"] == "LineStep")
    assert line_step["compiler_support"] == "supported"
    assert "category" in line_step
    detailed = describe_feature_graph_capabilities(
        sections=["operations"],
        operation_names=["LineStep"],
    )
    line_step_detailed = next(row for row in detailed["registered_operations"] if row["name"] == "LineStep")
    assert line_step_detailed["required_parameters"] == ["bearing", "distance"]
    examples = describe_feature_graph_capabilities(
        sections=["examples"], operation_names=["LineStep"]
    )
    assert examples["examples"]["operation_expressions"]["LineStep"]["params"]["bearing"] == 45.0


def test_canonical_validation_schema_is_explicit_opt_in():
    default = describe_feature_graph_capabilities()
    assert "canonical_feature_graph_json_schema" not in default
    assert "starter_contract" in default
    exact = describe_feature_graph_capabilities(sections=["validation_schema"])
    assert exact["canonical_feature_graph_json_schema"]["title"] == "FeatureGraph"


def test_capability_projection_rejects_unknown_sections_and_all_invalid_operations():
    with pytest.raises(ValueError, match="unknown_feature_graph_capability_sections"):
        describe_feature_graph_capabilities(sections=["mystery"])
    with pytest.raises(ValueError, match="no_valid_feature_graph_operation_names"):
        describe_feature_graph_capabilities(operation_names=["MysteryOperation"])
    with pytest.raises(ValueError, match="no_valid_feature_graph_operation_names"):
        describe_feature_graph_capabilities(operation_names=["annotation"])


def test_capability_operation_names_partial_success_with_feature_kind_warning():
    caps = describe_feature_graph_capabilities(
        sections=["operations"],
        operation_names=["ReferenceFrame", "Close", "annotation"],
    )
    assert [row["name"] for row in caps["registered_operations"]] == ["ReferenceFrame", "Close"]
    assert caps["ignored_operation_names"] == [
        {"name": "annotation", "reason": "feature_kind_not_operation"}
    ]
    starter = describe_feature_graph_capabilities(
        sections=["starter_contract"],
        operation_names=["ReferenceFrame", "annotation"],
    )
    assert "feature_kind_vs_operation_contract" in starter["starter_contract"]


def test_hydrate_deed_to_ir_input_sections_bounded_and_path_free():
    handler = make_hydrate_deed_to_ir_input_handler(handoff_context=_handoff_context())
    result = handler(
        {
            "sections": [
                "normalized_transcript",
                "parcel_metadata",
                "resolution_state",
            ]
        }
    )
    assert result["executed"] is True
    outputs = result["outputs"]
    assert "normalized_transcript" in outputs["results"]
    assert "parcel_metadata" in outputs["results"]
    assert outputs["results"]["resolution_state"]["resolution_state_ref"].startswith(
        "transcript_edit:resolution_state:"
    )
    resolution = outputs["results"]["resolution_state"]
    assert resolution["projection_mode"] == "index"
    assert isinstance(resolution, dict)
    dumped = json.dumps(outputs)
    assert "test_fixtures" not in dumped.lower()
    assert "c:\\\\" not in dumped.lower()
    assert ".json" not in dumped.lower()


def test_hydrate_resolution_state_exact_unit_filter_includes_parent():
    handler = make_hydrate_deed_to_ir_input_handler(handoff_context=_handoff_context())
    result = handler(
        {
            "sections": ["resolution_state"],
            "resolution_unit_ids": ["p1_call1_bearing"],
        }
    )
    items = result["outputs"]["results"]["resolution_state"]["items"]
    assert len(items) == 1
    unit = items[0]["units"][0]
    assert unit["unit_id"] == "p1_call1_bearing"
    assert unit["parent_item_id"] == "p1_calls_group"


def test_selected_rows_global_unit_cap_reports_truncation_and_not_found():
    units = [
        {
            "unit_id": f"unit_{index}",
            "title": f"Unit {index}",
            "status": "open",
            "value_kind": "distance",
        }
        for index in range(40)
    ]
    snapshot = {
        "items": [
            {
                "item_id": "group_a",
                "title": "Group A",
                "kind": "work_unit",
                "status": "open",
                "covered_units": units,
            }
        ],
        "relations": [],
    }
    wanted = [f"unit_{index}" for index in range(40)]
    rows, not_found, truncation = build_resolution_state_selected_rows(snapshot, wanted)
    emitted = sum(len(item.get("units") or []) for item in rows)
    assert emitted <= 32
    assert truncation.get("units_omitted", 0) >= 8
    assert not_found == []


def test_selected_rows_item_row_cap_applies_to_unit_matches_across_items():
    snapshot = {
        "items": [
            {
                "item_id": f"item_{index}",
                "title": f"Item {index}",
                "kind": "work_unit",
                "status": "open",
                "covered_units": [
                    {
                        "unit_id": f"unit_{index}",
                        "title": f"Unit {index}",
                        "status": "open",
                        "value_kind": "distance",
                    }
                ],
            }
            for index in range(20)
        ],
        "relations": [],
    }
    wanted = [f"unit_{index}" for index in range(20)]
    rows, not_found, truncation = build_resolution_state_selected_rows(snapshot, wanted)
    assert len(rows) <= 16
    assert truncation.get("items_omitted", 0) >= 4 or truncation.get("units_omitted", 0) >= 4
    assert not_found == []


def test_hydrate_resolution_state_caps_requested_unit_ids_in_filter():
    handler = make_hydrate_deed_to_ir_input_handler(
        handoff_context={
            "resolution_state_ref": "transcript_edit:resolution_state:test",
            "resolution_state_snapshot": {
                "items": [
                    {
                        "item_id": "item_0",
                        "title": "Item 0",
                        "kind": "work_unit",
                        "status": "open",
                        "covered_units": [
                            {
                                "unit_id": "unit_0",
                                "title": "Unit 0",
                                "status": "open",
                                "value_kind": "distance",
                            }
                        ],
                    }
                ],
                "relations": [],
            },
        }
    )
    requested = [f"unit_{index}" for index in range(100)]
    result = handler(
        {
            "sections": ["resolution_state"],
            "resolution_unit_ids": requested,
        }
    )
    resolution = result["outputs"]["results"]["resolution_state"]
    assert len(resolution["filter"]["resolution_unit_ids"]) == 64
    assert resolution["filter"]["resolution_unit_ids_omitted"] == 36
    assert any(e.get("reason") == "resolution_unit_ids_truncated" for e in result["outputs"]["errors"])


def test_hydrate_resolution_state_not_found_reports_error():
    handler = make_hydrate_deed_to_ir_input_handler(handoff_context=_handoff_context())
    result = handler(
        {
            "sections": ["resolution_state"],
            "resolution_unit_ids": ["missing_unit"],
        }
    )
    errors = result["outputs"]["errors"]
    assert any(e.get("resolution_unit_id") == "missing_unit" for e in errors)


def test_resolution_state_projection_mechanical_copy():
    raw = json.loads(_RESOLUTION_FIXTURE.read_text(encoding="utf-8"))
    snapshot = mechanical_resolution_state_snapshot(raw)
    assert snapshot is not None
    assert snapshot["items"][0]["determined_value"] == "100 feet"
    assert snapshot["items"][1]["covered_units"][0]["unit_id"] == "p1_call1_bearing"
    counts = resolution_state_counts(snapshot)
    assert counts["items"] == 2
    assert counts["covered_units"] == 1


def test_practice_resolution_state_index_exposes_all_items_and_units():
    raw = json.loads(_PRACTICE_RESOLUTION_FIXTURE.read_text(encoding="utf-8"))
    index = build_resolution_state_index(raw, resolution_state_ref="transcript_edit:resolution_state:practice")
    assert index["projection_mode"] == "index"
    assert isinstance(index, dict)
    assert index["totals"]["items"] == 5
    assert index["totals"]["covered_units"] == 15
    unit_ids = [
        unit["unit_id"]
        for item in index["items"]
        for unit in (item.get("units") or [])
    ]
    assert "p1_call1_distance" in unit_ids
    assert len(unit_ids) == 15
    relations = index.get("relations") or []
    assert len(relations) == 4
    assert all("source" in rel and "target" in rel for rel in relations)
    dumped = json.dumps(index)
    assert "opaque_payload" not in dumped
    assert not dumped.startswith('"{')


def test_save_ir_artifact_validates_and_persists_without_paths():
    graph = FeatureGraph(
        graph_id="parcel_1_ir",
        nodes=[
            FeatureNode(
                id="n1",
                kind=FeatureKind.POINT,
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id="p1_call1_distance",
                            entity_type="resolution_unit",
                            source_ref="transcript_edit:resolution_state:fixture-001",
                        )
                    ]
                ),
            )
        ],
        edges=[],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import (
            FeatureGraphPersistenceService,
        )

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph.model_dump(mode="json"),
            artifact_id="ir_parcel_1_test",
            persistence=service,
        )
    assert result["executed"] is True
    assert result["outputs"]["ir_artifact_ref"] == "feature_graph:ir:ir_parcel_1_test"
    assert result["outputs"]["draft_ir_ref"] == "feature_graph:ir:ir_parcel_1_test"
    assert result["outputs"]["draft_version"] == "v0"
    assert result["outputs"]["is_draft"] is True
    assert result["outputs"]["source_entity_link_count"] == 1
    assert result["outputs"]["compile_artifact_ref"]
    assert result["outputs"]["current_draft_ir"]["draft_version"] == "v0"
    assert "path" not in result["outputs"]
    dumped = json.dumps(result)
    assert tmpdir not in dumped


def test_save_ir_artifact_returns_validation_errors():
    result = save_ir_artifact(
        dossier_id="d-test",
        feature_graph={"graph_id": "bad", "nodes": "not-a-list"},
    )
    assert result["executed"] is False
    assert result["reason_codes"] == ["feature_graph_validation_failed"]
    refusal = result["refusal"]
    assert refusal["reason_code"] == "feature_graph_validation_failed"
    assert refusal["retryable"] is True
    assert refusal["blocked_by_invariant"] is False
    assert refusal["blocked_by_budget"] is False
    assert result["outputs"]["validation_errors"]
    assert result["outputs"]["ir_artifact_ref"] is None


def test_save_ir_artifact_validation_failure_is_retryable_for_invalid_kind():
    result = save_ir_artifact(
        dossier_id="d-test",
        feature_graph={
            "graph_id": "bad_kind",
            "nodes": [{"id": "n1", "kind": "semantic"}],
            "edges": [],
        },
    )
    assert result["executed"] is False
    assert result["refusal"]["retryable"] is True
    assert result["reason_codes"] == ["feature_graph_validation_failed"]
    assert any("kind" in err for err in result["outputs"]["validation_errors"])


def test_save_ir_artifact_validation_failure_does_not_persist_artifact():
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import (
            FeatureGraphPersistenceService,
        )

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        before = list(service.list_artifacts("d-test", artifact_type="ir"))
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph={"graph_id": "bad", "nodes": "not-a-list"},
            persistence=service,
        )
        after = list(service.list_artifacts("d-test", artifact_type="ir"))
    assert result["executed"] is False
    assert before == after


def test_feature_graph_contract_excludes_semantic_node_kind():
    from domains.mapping.deed_to_ir.execution.tool_specs import build_deed_to_ir_tool_specs
    from tooling.mapping.deed_to_ir.feature_graph_capabilities import describe_feature_graph_capabilities
    from tooling.mapping.deed_to_ir.feature_graph_contract_projection import (
        ALLOWED_FEATURE_NODE_KINDS,
        FEATURE_NODE_PLACEHOLDER_KIND,
        build_core_schema_projection,
        build_feature_node_kind_contract,
    )

    kinds = build_feature_node_kind_contract()
    assert FEATURE_NODE_PLACEHOLDER_KIND == "unknown"
    assert "semantic" not in ALLOWED_FEATURE_NODE_KINDS
    assert kinds["placeholder_kind"] == "unknown"
    assert "unknown" in kinds["allowed_kinds"]
    core = build_core_schema_projection()
    assert "semantic" not in json.dumps(core).lower()

    starter = describe_feature_graph_capabilities()["starter_contract"]
    assert "unknown" in starter["feature_kinds"]
    assert "semantic" not in starter["feature_kinds"]
    assert starter["feature_node_kind_contract"]["placeholder_kind"] == "unknown"
    assert "semantic" not in json.dumps(starter).lower()

    save_spec = next(s for s in build_deed_to_ir_tool_specs() if s.tool_id == "save_ir_artifact")
    node_kind_enum = (
        save_spec.expected_request_json_shape["properties"]["feature_graph"]["properties"]["nodes"]["items"]["properties"]["kind"]["enum"]
    )
    assert "unknown" in node_kind_enum
    assert "semantic" not in node_kind_enum
    assert "semantic" not in save_spec.expected_request_shape.lower()
    assert "semantic" not in save_spec.purpose.lower()


def test_mapping_operands_bounds_row_fields_and_reports_truncation():
    long_value = "x" * 500
    long_candidates = [f"candidate_{index}" for index in range(20)]
    long_refs = [f"image:derived:{index:04d}" for index in range(20)]
    snapshot = {
        "items": [
            {
                "item_id": "parcel_1_group",
                "title": "Parcel 1",
                "kind": "group",
                "status": "closed",
                "covered_units": [
                    {
                        "unit_id": "p1_call1_distance",
                        "title": "Call 1 distance",
                        "value_kind": "distance",
                        "status": "closed",
                        "determination": "earned",
                        "determined_value": long_value,
                        "candidate_values": long_candidates,
                        "evidence_refs": long_refs,
                    }
                ],
            }
        ],
        "relations": [],
    }
    payload = build_mapping_operands(snapshot)
    row = payload["operands"][0]
    assert len(row["determined_value"]) <= 320
    assert row["determined_value"].endswith("…")
    assert len(row["candidate_values"]) == 8
    assert len(row["evidence_refs"]) == 8
    truncation = payload["truncation"]
    assert truncation["determined_value_chars_truncated"] == 1
    assert truncation["candidate_values_omitted"] == 12
    assert truncation["evidence_refs_omitted"] == 12


def test_mapping_operands_projection_from_practice_fixture():
    raw = json.loads(_PRACTICE_RESOLUTION_FIXTURE.read_text(encoding="utf-8"))
    payload = build_mapping_operands(raw, resolution_state_ref="transcript_edit:resolution_state:practice")
    assert payload["projection_mode"] == "mapping_operands"
    operand_ids = {row["operand_id"] for row in payload["operands"]}
    assert "p1_call1_distance" in operand_ids
    assert "p1_pob_corner_bearing" in operand_ids
    assert "parcel_2_continuation_scope" in operand_ids
    assert "range_reference_conflict" in operand_ids
    assert "range_reference_governing_choice" in operand_ids
    blocker = next(row for row in payload["operands"] if row["operand_id"] == "parcel_2_continuation_scope")
    assert blocker.get("operand_role") == "scope_blocker"
    dumped = json.dumps(payload)
    assert "opaque_payload" not in dumped
    assert "test_fixtures" not in dumped.lower()


def test_hydrate_mapping_operands_section_returns_compact_operands():
    handler = make_hydrate_deed_to_ir_input_handler(handoff_context=_handoff_context())
    result = handler({"sections": ["mapping_operands"]})
    assert result["executed"] is True
    payload = result["outputs"]["results"]["mapping_operands"]
    assert payload["projection_mode"] == "mapping_operands"
    assert payload["operands"]
    assert payload["operand_suite_ref"].startswith("deed_to_ir:operands:run:")
    assert all("operand_id" in row for row in payload["operands"])


def test_operand_groups_mechanical_from_practice_fixture():
    raw = json.loads(_PRACTICE_RESOLUTION_FIXTURE.read_text(encoding="utf-8"))
    payload = build_mapping_operands(raw)
    groups = build_operand_groups(payload["operands"])
    parcel_1 = next(group for group in groups if group["group_id"] == "parcel_1_calls")
    assert parcel_1["group_kind"] == "course_call_candidates"
    assert len(parcel_1["rows"]) == 3
    assert parcel_1["rows"][0]["call_index"] == 1
    assert "bearing_operand_id" in parcel_1["rows"][0]
    assert "distance_operand_id" in parcel_1["rows"][0]
    blockers = [group for group in groups if group["group_kind"] == "scope_blocker"]
    assert blockers
    assert blockers[0]["rows"][0]["operand_id"] == "parcel_2_continuation_scope"


def test_operand_groups_omitted_when_ids_not_parseable():
    operands = [
        {
            "operand_id": "mystery_bearing",
            "value_kind": "bearing",
            "determined_value": "N 45 E",
        }
    ]
    assert build_operand_groups(operands) == []


def test_hydrate_operand_suite_ref_returns_operand_rows():
    handoff = _handoff_context()
    ref = build_operand_suite_ref(run_id=handoff["scope"]["run_id"])
    hydrated = hydrate_feature_graph_artifact_refs(
        dossier_id="d-fixture",
        ref_ids=[ref, OPERAND_SUITE_REF],
        handoff_context=handoff,
        run_id=handoff["scope"]["run_id"],
    )
    assert hydrated["outputs"]["hydrated_count"] == 2
    row = hydrated["outputs"]["results"][0]
    assert row["artifact_type"] == "deed_to_ir_operand_suite"
    assert row["operands"]
    assert row["operand_suite_ref"] == ref
    assert "operand_groups" in row
    dumped = json.dumps(hydrated)
    assert "test_fixtures" not in dumped.lower()


def test_patch_ir_draft_modifies_target_nodes_and_increments_version():
    base_graph = FeatureGraph(
        graph_id="patch_graph",
        nodes=[
            FeatureNode(
                id="parcel_1_anchor",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
                provenance=ProvenanceAttachment(
                    source_entity_links=[
                        SourceEntityLink(
                            entity_id="p1_pob",
                            entity_type="resolution_unit",
                            source_ref="transcript_edit:resolution_state:example",
                        )
                    ]
                ),
            ),
            FeatureNode(
                id="parcel_1_traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(op_name="CourseTraverse", operands=["parcel_1_anchor"], params={"courses": []}),
            ),
            FeatureNode(
                id="parcel_1_region",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["parcel_1_traverse"]),
            ),
        ],
        edges=[],
        metadata={"note": "keep"},
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        saved = save_ir_artifact(
            dossier_id="d-patch",
            feature_graph=base_graph.model_dump(mode="json"),
            persistence=service,
        )
        base_ref = saved["outputs"]["working_draft_ref"]
        patched = patch_ir_draft(
            dossier_id="d-patch",
            base_draft_ref=base_ref,
            node_upserts=[
                {
                    "id": "parcel_1_traverse",
                    "kind": "curve",
                    "op_expr": {
                        "op_name": "CourseTraverse",
                        "operands": ["parcel_1_anchor"],
                        "params": {
                            "courses": [{"bearing": 68.5, "distance": 542.0}],
                        },
                    },
                },
                {
                    "id": "parcel_1_region",
                    "kind": "region",
                    "op_expr": {"op_name": "Close", "operands": ["parcel_1_traverse"]},
                },
            ],
            edge_upserts=[
                {
                    "source_id": "parcel_1_traverse",
                    "target_id": "parcel_1_region",
                    "edge_type": "derived_from",
                }
            ],
            persistence=service,
        )
        assert patched["executed"] is True
        assert patched["outputs"]["draft_version"] == "v1"
        assert patched["outputs"]["working_draft_ref"] != base_ref
        assert patched["outputs"]["current_draft_ir"]
        assert patched["outputs"].get("draft_repair_items") is not None

        hydrated = hydrate_feature_graph_artifact_refs(
            dossier_id="d-patch",
            ref_ids=[patched["outputs"]["working_draft_ref"], base_ref],
            persistence=service,
        )
        by_ref = {row["ref_id"]: row for row in hydrated["outputs"]["results"]}
        v0 = by_ref[base_ref]["graph"]
        v1 = by_ref[patched["outputs"]["working_draft_ref"]]["graph"]
        anchor_v0 = next(node for node in v0["nodes"] if node["id"] == "parcel_1_anchor")
        anchor_v1 = next(node for node in v1["nodes"] if node["id"] == "parcel_1_anchor")
        assert anchor_v0["provenance"] == anchor_v1["provenance"]
        traverse_v1 = next(node for node in v1["nodes"] if node["id"] == "parcel_1_traverse")
        assert traverse_v1["op_expr"]["params"]["courses"]
        assert v1["metadata"]["note"] == "keep"
        assert any(edge["edge_type"] == "derived_from" for edge in v1["edges"])


def test_patch_ir_draft_refuses_malformed_base_draft_missing_graph():
    base_graph = FeatureGraph(
        graph_id="malformed_patch_graph",
        nodes=[
            FeatureNode(
                id="anchor",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
        ],
        edges=[],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        saved = save_ir_artifact(
            dossier_id="d-malformed",
            feature_graph=base_graph.model_dump(mode="json"),
            persistence=service,
        )
        base_ref = saved["outputs"]["working_draft_ref"]
        artifact_id = saved["outputs"]["artifact_id"]
        artifact_path = Path(tmpdir) / "artifacts" / "d-malformed" / f"{artifact_id}.json"
        raw = json.loads(artifact_path.read_text(encoding="utf-8"))
        del raw["graph"]
        artifact_path.write_text(json.dumps(raw), encoding="utf-8")

        result = patch_ir_draft(
            dossier_id="d-malformed",
            base_draft_ref=base_ref,
            node_upserts=[{"id": "anchor", "kind": "point"}],
            persistence=service,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "base_draft_graph_missing"
        assert result["refusal"]["retryable"] is True
        assert "graph" in result["outputs"]["message"].lower()


def test_deed_to_ir_authoring_example_is_schema_valid_with_provenance():
    example = build_deed_to_ir_authoring_example()
    graph_payload = example["graph"]
    graph = FeatureGraph.model_validate(graph_payload)
    origin = next(node for node in graph.nodes if node.id == "example_start_anchor")
    assert origin.provenance is not None
    assert origin.provenance.source_entity_links
    blocked = next(node for node in graph.nodes if node.id == "example_blocked_scope")
    assert blocked.kind.value == "annotation"
    assert blocked.provenance is not None
    assert "semantic" not in json.dumps(example).lower()
    caps = describe_feature_graph_capabilities(sections=["examples"])
    assert "deed_to_ir_authoring" in caps["examples"]
    assert FeatureGraph.model_validate(caps["examples"]["deed_to_ir_authoring"]["graph"])


def test_feature_graph_examples_use_generic_authoring_pattern_without_practice_tokens():
    from tooling.mapping.deed_to_ir.feature_graph_examples import (
        build_complete_supported_graph_example,
        build_deed_to_ir_authoring_example,
        example_forbidden_tokens,
    )

    payloads = [
        build_complete_supported_graph_example(),
        build_deed_to_ir_authoring_example(),
        build_deed_to_ir_authoring_example()["graph"],
    ]
    caps = describe_feature_graph_capabilities(sections=["examples"])
    payloads.append(caps["examples"]["complete_supported_graph"])
    payloads.append(caps["examples"]["deed_to_ir_authoring"]["graph"])

    combined = json.dumps(payloads).lower()
    op_names = {
        node.get("op_expr", {}).get("op_name")
        for payload in payloads
        if isinstance(payload, dict)
        for node in payload.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("op_expr"), dict)
    }
    node_kinds = {
        node.get("kind")
        for payload in payloads
        if isinstance(payload, dict)
        for node in payload.get("nodes", [])
        if isinstance(node, dict)
    }
    assert op_names >= {"ReferenceFrame", "TiedPoint", "CourseTraverse", "Close"}
    assert "annotation" in node_kinds
    for token in example_forbidden_tokens():
        assert token not in combined
    assert "deed_call_sequence" not in combined
    assert "public_land_survey_frame" not in combined


def test_save_placeholder_only_graph_reports_structural_readiness_false():
    graph = FeatureGraph(
        graph_id="placeholder_scaffold",
        nodes=[
            FeatureNode(id="parcel_1_scope", kind=FeatureKind.UNKNOWN, label="Parcel 1 scope"),
            FeatureNode(id="parcel_2_scope", kind=FeatureKind.UNKNOWN, label="Parcel 2 scope"),
            FeatureNode(
                id="parcel_2_blocker",
                kind=FeatureKind.UNKNOWN,
                label="Parcel 2 continuation blocked",
            ),
        ],
        edges=[],
        metadata={"notes": "Deed prose parked in metadata instead of graph entities."},
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph.model_dump(mode="json"),
            persistence=service,
        )
    outputs = result["outputs"]
    assert outputs["placeholder_only_graph"] is True
    assert outputs["renderable_feature_count"] == 0
    assert outputs["unknown_node_count"] == 3
    assert outputs["mapping_submission_ready_candidate"] is False
    assert outputs["working_draft_ref"] == outputs["draft_ir_ref"] == outputs["ir_artifact_ref"]


def test_save_renderable_draft_can_report_mapping_submission_ready_candidate():
    graph = FeatureGraph(
        graph_id="parcel_1_ir",
        nodes=[
            FeatureNode(
                id="start",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="LineStep",
                    operands=["start"],
                    params={"bearing": 0.0, "distance": 100.0},
                ),
            ),
        ],
        edges=[],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        result = save_ir_artifact(
            dossier_id="d-test",
            feature_graph=graph.model_dump(mode="json"),
            persistence=service,
        )
    outputs = result["outputs"]
    assert outputs["renderable_feature_count"] == 2
    assert outputs["placeholder_only_graph"] is False
    assert "mapping_submission_ready_candidate" in outputs
    if outputs["mechanically_mappable_candidate"]:
        assert outputs["mapping_submission_ready_candidate"] is True


def test_mixed_parent_and_child_resolution_ids_do_not_false_not_found():
    snapshot = {
        "items": [
            {
                "item_id": "parcel_1_group",
                "title": "Parcel 1 group",
                "kind": "group",
                "status": "partial",
                "covered_units": [
                    {
                        "unit_id": "p1_call1_distance",
                        "title": "Call 1 distance",
                        "status": "open",
                        "value_kind": "distance",
                    },
                    {
                        "unit_id": "p1_call1_bearing",
                        "title": "Call 1 bearing",
                        "status": "open",
                        "value_kind": "bearing",
                    },
                    {
                        "unit_id": "p1_acreage",
                        "title": "Acreage",
                        "status": "open",
                        "value_kind": "area",
                    },
                ],
            }
        ],
        "relations": [],
    }
    requested = [
        "parcel_1_group",
        "p1_call1_distance",
        "p1_call1_bearing",
        "p1_acreage",
    ]
    rows, not_found, truncation = build_resolution_state_selected_rows(snapshot, requested)
    assert not_found == []
    item_ids = {row.get("item_id") for row in rows}
    assert "parcel_1_group" in item_ids
    handler = make_hydrate_deed_to_ir_input_handler(
        handoff_context={
            "resolution_state_ref": "transcript_edit:resolution_state:test",
            "resolution_state_snapshot": snapshot,
        }
    )
    result = handler({"sections": ["resolution_state"], "resolution_unit_ids": requested})
    errors = result["outputs"]["errors"]
    assert not any(e.get("reason") == "not_found" for e in errors)
    resolution = result["outputs"]["results"]["resolution_state"]
    assert resolution["projection_mode"] == "selected_rows"
    assert resolution["items"]


def test_mixed_parent_and_explicit_children_prioritize_children_over_implicit_cap():
    units = [
        {
            "unit_id": f"u{index}",
            "title": f"Unit {index}",
            "status": "open",
            "value_kind": "distance",
        }
        for index in range(12)
    ]
    snapshot = {
        "items": [
            {
                "item_id": "parcel_1_group",
                "title": "Parcel 1 group",
                "kind": "group",
                "status": "partial",
                "covered_units": units,
            }
        ],
        "relations": [],
    }
    requested = ["parcel_1_group", *[f"u{index}" for index in range(12)]]
    rows, not_found, truncation = build_resolution_state_selected_rows(snapshot, requested)
    assert not_found == []
    assert truncation.get("units_omitted", 0) == 0
    parent_rows = [row for row in rows if row.get("item_id") == "parcel_1_group"]
    assert len(parent_rows) == 1
    emitted_ids = [unit["unit_id"] for unit in parent_rows[0].get("units") or []]
    assert emitted_ids == [f"u{index}" for index in range(12)]


def test_save_ir_artifact_rejects_blank_source_entity_links():
    result = save_ir_artifact(
        dossier_id="d-test",
        feature_graph={
            "graph_id": "blank_links",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "point",
                    "provenance": {
                        "source_entity_links": [
                            {
                                "entity_id": " ",
                                "entity_type": "resolution_unit",
                                "source_ref": "transcript_edit:resolution_state:x",
                            }
                        ],
                    },
                }
            ],
            "edges": [],
        },
    )
    assert result["executed"] is False
    assert result["outputs"]["validation_errors"]


def test_save_ir_artifact_rejects_malformed_source_entity_links():
    result = save_ir_artifact(
        dossier_id="d-test",
        feature_graph={
            "graph_id": "bad_links",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "point",
                    "provenance": {
                        "source_entity_links": [
                            {"entity_type": "resolution_unit", "source_ref": "transcript_edit:resolution_state:x"}
                        ],
                    },
                }
            ],
            "edges": [],
        },
    )
    assert result["executed"] is False
    assert result["outputs"]["validation_errors"]
    assert any("entity_id" in err for err in result["outputs"]["validation_errors"])


def test_resolution_state_ref_and_snapshot_must_be_paired():
    from domains.mapping.deed_to_ir.payloads import DeedToIrScope
    from tooling.mapping.deed_to_ir.startup_handoff import startup_handoff_from_loader_dict
    from tooling.mapping.deed_to_ir import load_transcript_edit_output_handoff

    loaded = load_transcript_edit_output_handoff(output_path=_HANDOFF_FIXTURE)
    scope = DeedToIrScope(dossier_id="d1")
    with pytest.raises(Exception, match="resolution_state_ref_and_snapshot_must_be_paired"):
        startup_handoff_from_loader_dict(
            scope=scope,
            loaded=loaded,
            resolution_state_ref="transcript_edit:resolution_state:only-ref",
        )


def test_resolution_state_ref_requires_valid_prefix():
    from domains.mapping.deed_to_ir.payloads import DeedToIrScope
    from tooling.mapping.deed_to_ir.startup_handoff import startup_handoff_from_loader_dict
    from tooling.mapping.deed_to_ir import load_transcript_edit_output_handoff

    loaded = load_transcript_edit_output_handoff(output_path=_HANDOFF_FIXTURE)
    scope = DeedToIrScope(dossier_id="d1")
    snapshot = {"items": [], "relations": []}
    with pytest.raises(Exception, match="resolution_state_ref_invalid_prefix"):
        startup_handoff_from_loader_dict(
            scope=scope,
            loaded=loaded,
            resolution_state_ref="wrong:resolution_state:abc",
            resolution_state_snapshot=snapshot,
        )


def test_hydrate_non_ir_artifacts_are_bounded():
    from feature_graph.artifacts import create_compile_artifact, create_judge_artifact

    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        compile_artifact = create_compile_artifact(
            artifact_id="compile_big",
            graph_id="g1",
            compiled_features={f"node_{i}": {"ok": True} for i in range(100)},
            gaps=[{"kind": "gap", "id": i} for i in range(100)],
            warnings=[f"warn_{i}" for i in range(100)],
        )
        service.save_artifact(compile_artifact, dossier_id="d-bounds")
        hydrated = hydrate_feature_graph_artifact_refs(
            dossier_id="d-bounds",
            ref_ids=["feature_graph:compile:compile_big"],
            persistence=service,
        )
        row = hydrated["outputs"]["results"][0]
        assert len(row["compiled_features"]) <= 64
        assert len(row["gaps"]) <= 64
        assert len(row["warnings"]) <= 32
        assert row.get("truncated")


def test_list_and_hydrate_feature_graph_artifacts_path_free():
    graph = FeatureGraph(graph_id="g_list", nodes=[], edges=[])
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import (
            FeatureGraphPersistenceService,
        )

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        save_ir_artifact(
            dossier_id="d-list",
            feature_graph=graph.model_dump(mode="json"),
            artifact_id="ir_list_test",
            persistence=service,
        )
        listed = list_feature_graph_artifacts(dossier_id="d-list", persistence=service)
        rows = listed["outputs"]["artifacts"]
        ir_rows = [row for row in rows if row.get("artifact_type") == "ir"]
        assert ir_rows
        assert ir_rows[0]["artifact_ref"] == "feature_graph:ir:ir_list_test"
        assert ir_rows[0].get("draft_version") == "v0"
        assert "artifact_path" not in ir_rows[0]
        hydrated = hydrate_feature_graph_artifact_refs(
            dossier_id="d-list",
            ref_ids=["feature_graph:ir:ir_list_test"],
            persistence=service,
        )
        row = hydrated["outputs"]["results"][0]
        assert row["graph_id"] == "g_list"
        dumped = json.dumps(hydrated)
        assert "artifact_path" not in dumped
        assert tmpdir not in dumped


def _mappable_graph() -> FeatureGraph:
    return FeatureGraph(
        graph_id="parcel_tool_submit",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            ),
            FeatureNode(
                id="traverse",
                kind=FeatureKind.CURVE,
                op_expr=OpExpr(
                    op_name="CourseTraverse",
                    operands=["pob"],
                    params={
                        "courses": [
                            {"bearing": 90.0, "distance": 100.0},
                            {"bearing": 0.0, "distance": 50.0},
                        ]
                    },
                ),
            ),
            FeatureNode(
                id="parcel",
                kind=FeatureKind.REGION,
                op_expr=OpExpr(op_name="Close", operands=["traverse"]),
            ),
        ],
        edges=[],
    )


def test_submit_ir_for_mapping_end_to_end_persists_all_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        saved = save_ir_artifact(
            dossier_id="d-submit",
            feature_graph=_mappable_graph().model_dump(mode="json"),
            artifact_id="ir_tool_submit",
            persistence=service,
        )
        ir_ref = saved["outputs"]["ir_artifact_ref"]
        result = submit_ir_for_mapping(
            dossier_id="d-submit",
            ir_artifact_ref=ir_ref,
            persistence=service,
        )
        assert result["executed"] is True
        outputs = result["outputs"]
        assert outputs["mapping_artifact_ref"].startswith("feature_graph:mapping:")
        assert outputs["compile_artifact_ref"].startswith("feature_graph:compile:")
        assert outputs["judge_artifact_ref"].startswith("feature_graph:judge:")
        assert outputs["rendered_feature_count"] >= 1
        assert isinstance(result.get("image_evidence"), list)
        assert len(result["image_evidence"]) == 2
        assert "image_evidence" not in outputs
        assert "b64" not in json.dumps(outputs)
        mapping_id = outputs["mapping_artifact_ref"].split(":", 2)[2]
        sidecar_dir = Path(tmpdir) / "artifacts" / "d-submit" / "mappings" / mapping_id
        assert (sidecar_dir / "geometry.geojson").exists()
        assert (sidecar_dir / "clean.png").exists()
        assert (sidecar_dir / "control.png").exists()
        compile_id = outputs["compile_artifact_ref"].split(":", 2)[2]
        compile_raw = service.get_artifact("d-submit", compile_id)
        assert compile_raw is not None
        assert compile_raw["metadata"]["parent_artifact_ids"] == ["ir_tool_submit"]
        dumped = json.dumps(result)
        assert tmpdir not in dumped


def test_submit_ir_for_mapping_repeated_ids_are_distinct() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        saved = save_ir_artifact(
            dossier_id="d-repeat",
            feature_graph=_mappable_graph().model_dump(mode="json"),
            artifact_id="ir_repeat_tool",
            persistence=service,
        )
        ir_ref = saved["outputs"]["ir_artifact_ref"]
        first = submit_ir_for_mapping(dossier_id="d-repeat", ir_artifact_ref=ir_ref, persistence=service)
        second = submit_ir_for_mapping(dossier_id="d-repeat", ir_artifact_ref=ir_ref, persistence=service)
        assert first["outputs"]["mapping_artifact_ref"] != second["outputs"]["mapping_artifact_ref"]
        assert first["outputs"]["compile_artifact_ref"] == second["outputs"]["compile_artifact_ref"]
        assert first["outputs"]["judge_artifact_ref"] == second["outputs"]["judge_artifact_ref"]


def test_submit_ir_for_mapping_partial_compile_still_maps_valid_features() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        graph = FeatureGraph(
            graph_id="partial_tool",
            nodes=[
                FeatureNode(
                    id="good",
                    kind=FeatureKind.POINT,
                    geometry={"type": "Point", "coordinates": [0.0, 0.0]},
                ),
                FeatureNode(
                    id="bad",
                    kind=FeatureKind.POINT,
                    geometry={"type": "Point", "coordinates": ["north", 0.0]},
                ),
            ],
            edges=[],
        )
        saved = save_ir_artifact(
            dossier_id="d-partial",
            feature_graph=graph.model_dump(mode="json"),
            artifact_id="ir_partial_tool",
            persistence=service,
        )
        result = submit_ir_for_mapping(
            dossier_id="d-partial",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
        )
        assert result["executed"] is True
        assert result["outputs"]["rendered_feature_count"] >= 1
        assert result["outputs"]["skipped_feature_count"] >= 1


@pytest.mark.parametrize(
    ("ir_ref", "dossier_id", "expected_code"),
    [
        ("feature_graph:compile:compile_only", "d-refuse", "ir_artifact_ref_invalid"),
        ("feature_graph:ir:missing_ir", "d-refuse", "ir_artifact_not_found"),
        ("not-a-ref", "d-refuse", "ir_artifact_ref_invalid"),
    ],
)
def test_submit_ir_for_mapping_refuses_invalid_refs(
    ir_ref: str,
    dossier_id: str,
    expected_code: str,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        result = submit_ir_for_mapping(
            dossier_id=dossier_id,
            ir_artifact_ref=ir_ref,
            persistence=service,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == expected_code


def test_submit_ir_for_mapping_refuses_cross_dossier_ir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        saved = save_ir_artifact(
            dossier_id="d-owner",
            feature_graph=_mappable_graph().model_dump(mode="json"),
            artifact_id="ir_owner_only",
            persistence=service,
        )
        result = submit_ir_for_mapping(
            dossier_id="d-other",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "ir_artifact_not_found"


def test_hydrate_artifact_refs_supports_mapping_and_sidecars_path_free() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        saved = save_ir_artifact(
            dossier_id="d-hydrate-map",
            feature_graph=_mappable_graph().model_dump(mode="json"),
            artifact_id="ir_hydrate_map",
            persistence=service,
        )
        submitted = submit_ir_for_mapping(
            dossier_id="d-hydrate-map",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
        )
        mapping_ref = submitted["outputs"]["mapping_artifact_ref"]
        geo_ref = submitted["outputs"]["geometry_ref"]
        clean_ref = submitted["outputs"]["clean_render_ref"]
        hydrated = hydrate_artifact_refs(
            dossier_id="d-hydrate-map",
            ref_ids=[mapping_ref, geo_ref, clean_ref],
            persistence=service,
        )
        assert hydrated["executed"] is True
        assert hydrated["outputs"]["hydrated_count"] == 3
        mapping_row = next(row for row in hydrated["outputs"]["results"] if row["artifact_type"] == "mapping")
        assert mapping_row["source_ir_artifact_ref"] == saved["outputs"]["ir_artifact_ref"]
        assert "path" not in json.dumps(hydrated).lower() or "artifact_path" not in json.dumps(hydrated)
        assert tmpdir not in json.dumps(hydrated)
        assert isinstance(hydrated.get("image_evidence"), list)
        assert hydrated["image_evidence"][0]["ref_id"] == clean_ref
        assert "b64" in hydrated["image_evidence"][0]
        assert "b64" not in json.dumps(hydrated["outputs"])


def test_hydrate_geojson_sidecar_is_feature_bounded() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_mapping_sidecar_service import (
            FeatureGraphMappingSidecarService,
        )
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        sidecars = FeatureGraphMappingSidecarService(artifacts_root=service.artifacts_root)
        mapping_id = "mapping_geo_bounds"
        features = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [i, i]},
                    "properties": {},
                }
                for i in range(100)
            ],
        }
        mapping_dir = Path(tmpdir) / "artifacts" / "d-geo" / "mappings" / mapping_id
        mapping_dir.mkdir(parents=True)
        (mapping_dir / "geometry.geojson").write_text(json.dumps(features), encoding="utf-8")
        geo_ref = f"artifact://dossiers/feature_graphs/d-geo/mappings/{mapping_id}/geometry.geojson"
        hydrated = hydrate_artifact_refs(
            dossier_id="d-geo",
            ref_ids=[geo_ref],
            persistence=service,
        )
        row = hydrated["outputs"]["results"][0]
        assert len(row["feature_collection"]["features"]) <= 64
        assert row.get("truncated") is True


def test_list_feature_graph_artifacts_includes_mapping_type() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        saved = save_ir_artifact(
            dossier_id="d-list-map",
            feature_graph=_mappable_graph().model_dump(mode="json"),
            artifact_id="ir_list_map",
            persistence=service,
        )
        submit_ir_for_mapping(
            dossier_id="d-list-map",
            ir_artifact_ref=saved["outputs"]["ir_artifact_ref"],
            persistence=service,
        )
        listed = list_feature_graph_artifacts(
            dossier_id="d-list-map",
            artifact_type="mapping",
            persistence=service,
        )
        rows = listed["outputs"]["artifacts"]
        assert len(rows) == 1
        assert rows[0]["artifact_type"] == "mapping"


def test_malformed_geojson_sidecar_does_not_abort_mixed_hydration_batch() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        graph = FeatureGraph(graph_id="g_mixed", nodes=[], edges=[])
        save_ir_artifact(
            dossier_id="d-mixed",
            feature_graph=graph.model_dump(mode="json"),
            artifact_id="ir_mixed_ok",
            persistence=service,
        )
        mapping_dir = Path(tmpdir) / "artifacts" / "d-mixed" / "mappings" / "mapping_bad_geo"
        mapping_dir.mkdir(parents=True)
        (mapping_dir / "geometry.geojson").write_text("{not-json", encoding="utf-8")
        bad_geo_ref = "artifact://dossiers/feature_graphs/d-mixed/mappings/mapping_bad_geo/geometry.geojson"
        hydrated = hydrate_artifact_refs(
            dossier_id="d-mixed",
            ref_ids=[bad_geo_ref, "feature_graph:ir:ir_mixed_ok"],
            persistence=service,
        )
        assert hydrated["executed"] is True
        assert hydrated["outputs"]["hydrated_count"] == 1
        assert len(hydrated["outputs"]["errors"]) == 1
        assert hydrated["outputs"]["errors"][0]["reason"] == "geojson_sidecar_invalid"
        assert hydrated["outputs"]["results"][0]["ref_id"] == "feature_graph:ir:ir_mixed_ok"


def test_mapping_hydration_truncation_uses_named_lanes() -> None:
    from feature_graph.mapping_artifacts import (
        GeometryArtifactDescriptor,
        RenderArtifactDescriptor,
        SkippedFeatureRecord,
        WorldBBox,
        create_mapping_artifact,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

        service = FeatureGraphPersistenceService(
            root=Path(tmpdir) / "artifacts",
            state_dir=Path(tmpdir) / "state",
        )
        bbox = WorldBBox(min_x=0.0, min_y=0.0, max_x=1.0, max_y=1.0)
        sidecar_ref = (
            "artifact://dossiers/feature_graphs/d-trunc/mappings/mapping_trunc_lanes/geometry.geojson"
        )
        geometry = GeometryArtifactDescriptor(
            ref=sidecar_ref,
            byte_count=1,
            sha256="a" * 64,
            world_bbox=bbox,
            rendered_feature_count=100,
            skipped_feature_count=100,
        )
        render = RenderArtifactDescriptor(
            ref="artifact://dossiers/feature_graphs/d-trunc/mappings/mapping_trunc_lanes/clean.png",
            profile="clean",
            byte_count=1,
            sha256="b" * 64,
            width=100,
            height=100,
            world_bbox=bbox,
        )
        control = RenderArtifactDescriptor(
            ref="artifact://dossiers/feature_graphs/d-trunc/mappings/mapping_trunc_lanes/control.png",
            profile="control",
            byte_count=1,
            sha256="c" * 64,
            width=100,
            height=100,
            world_bbox=bbox,
        )
        artifact = create_mapping_artifact(
            artifact_id="mapping_trunc_lanes",
            graph_id="g_trunc",
            source_ir_artifact_id="ir_trunc",
            source_ir_artifact_ref="feature_graph:ir:ir_trunc",
            compile_artifact_id="compile_trunc",
            compile_artifact_ref="feature_graph:compile:compile_trunc",
            judge_artifact_id="judge_trunc",
            judge_artifact_ref="feature_graph:judge:judge_trunc",
            geometry=geometry,
            clean_render=render,
            control_render=control,
            coordinate_space="world",
            world_bbox=bbox,
            rendered_feature_ids=[f"rendered_{i}" for i in range(100)],
            skipped_features=[
                SkippedFeatureRecord(
                    node_id=f"skip_{i}",
                    graph_id="g_trunc",
                    kind="point",
                    reason="test",
                )
                for i in range(100)
            ],
        )
        service.save_artifact(artifact, dossier_id="d-trunc")
        hydrated = hydrate_artifact_refs(
            dossier_id="d-trunc",
            ref_ids=["feature_graph:mapping:mapping_trunc_lanes"],
            persistence=service,
        )
        row = hydrated["outputs"]["results"][0]
        trunc = row["truncated"]
        assert trunc["rendered_feature_ids"]["total"] == 100
        assert trunc["skipped_features"]["total"] == 100
        assert trunc["rendered_feature_ids"]["truncated"] is True
        assert trunc["skipped_features"]["truncated"] is True
