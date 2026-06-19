"""Tests for deed-to-IR foundation tooling."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode
from feature_graph.provenance import ProvenanceAttachment, SourceEntityLink

from tooling.mapping.deed_to_ir.artifact_hydration import (
    hydrate_feature_graph_artifact_refs,
    list_feature_graph_artifacts,
)
from tooling.mapping.deed_to_ir.feature_graph_capabilities import describe_feature_graph_capabilities
from tooling.mapping.deed_to_ir.input_hydration import make_hydrate_deed_to_ir_input_handler
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.resolution_state_projection import (
    mechanical_resolution_state_snapshot,
    resolution_state_counts,
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
        "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
        "resolution_state_snapshot": resolution,
    }


def test_describe_feature_graph_capabilities_projects_registry():
    caps = describe_feature_graph_capabilities()
    assert "feature_kinds" in caps
    assert "point" in caps["feature_kinds"]
    ops = caps["registered_operations"]
    assert any(op["name"] == "LineStep" for op in ops)
    line_step = next(op for op in ops if op["name"] == "LineStep")
    assert line_step["compiler_support"] == "supported"
    assert "feature_graph:ir:" in caps["artifact_ref_prefixes"]["ir"]


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
    unit = items[0]["covered_units"][0]
    assert unit["unit_id"] == "p1_call1_bearing"
    assert unit["parent_item_id"] == "p1_calls_group"


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
    assert result["outputs"]["source_entity_link_count"] == 1
    assert "path" not in result["outputs"]
    dumped = json.dumps(result)
    assert tmpdir not in dumped


def test_save_ir_artifact_returns_validation_errors():
    result = save_ir_artifact(
        dossier_id="d-test",
        feature_graph={"graph_id": "bad", "nodes": "not-a-list"},
    )
    assert result["executed"] is False
    assert result["outputs"]["validation_errors"]


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
        assert rows[0]["artifact_ref"] == "feature_graph:ir:ir_list_test"
        assert "artifact_path" not in rows[0]
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
