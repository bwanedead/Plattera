"""
Tests for Feature Graph Bundle Operation
==========================================

Tests verify:
- Bundle exports IR + minimal dependency subgraph
- Dependency reasons are recorded for each included graph
- Recursive dependency discovery works correctly
- Missing dependencies are handled gracefully
- Bundle artifacts are portable and self-contained
"""

import pytest
from .models import FeatureGraph, FeatureNode, FeatureRef, FeatureKind
from .artifacts import BundleArtifact
from .bundle import bundle_feature_graph, BundleOperation


class TestBundleBasics:
    """Test basic bundle operation functionality."""

    def test_bundle_single_graph_no_dependencies(self):
        """Bundle a graph with no external dependencies."""
        # Create a simple graph with no external refs
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(id="point1", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [0, 0]}),
                FeatureNode(id="point2", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [100, 0]})
            ],
            edges=[]
        )

        # Bundle with no available graphs
        bundle = bundle_feature_graph(target, available_graphs=None, bundle_purpose="Test single graph")

        # Verify bundle structure
        assert isinstance(bundle, BundleArtifact)
        assert bundle.target_graph_id == "parcel_a"
        assert bundle.target_graph == target
        assert len(bundle.dependency_graphs) == 0
        assert len(bundle.dependency_reasons) == 0
        assert bundle.bundle_purpose == "Test single graph"
        assert bundle.metadata.version == "1.0"

    def test_bundle_with_single_dependency(self):
        """Bundle a graph that references one external graph."""
        # Create target graph with external ref
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(
                    id="origin",
                    kind=FeatureKind.POINT,
                    label="Northeast Corner",
                    feature_ref=FeatureRef(
                        feature_id="ne_corner",
                        graph_id="section_1",
                        label="NE Corner Section 1",
                        is_external=True
                    )
                ),
                FeatureNode(id="point2", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [100, 0]})
            ],
            edges=[]
        )

        # Create dependency graph
        section = FeatureGraph(
            graph_id="section_1",
            nodes=[
                FeatureNode(id="ne_corner", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [1000, 2000]})
            ],
            edges=[]
        )

        # Bundle with available dependencies
        available = {"section_1": section}
        bundle = bundle_feature_graph(target, available_graphs=available, bundle_purpose="Export parcel")

        # Verify bundle includes dependency
        assert bundle.target_graph_id == "parcel_a"
        assert len(bundle.dependency_graphs) == 1
        assert bundle.dependency_graphs[0].graph_id == "section_1"

        # Verify reason is recorded
        assert "section_1" in bundle.dependency_reasons
        reason = bundle.dependency_reasons["section_1"]
        assert "origin" in reason
        assert "parcel_a" in reason
        assert "NE Corner Section 1" in reason

    def test_bundle_with_multiple_dependencies(self):
        """Bundle a graph that references multiple external graphs."""
        # Create target with multiple external refs
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(
                    id="start",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="corner1", graph_id="section_1", is_external=True)
                ),
                FeatureNode(
                    id="end",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="marker2", graph_id="parcel_b", is_external=True)
                )
            ],
            edges=[]
        )

        # Create dependency graphs
        section = FeatureGraph(graph_id="section_1", nodes=[FeatureNode(id="corner1", kind=FeatureKind.POINT)])
        parcel_b = FeatureGraph(graph_id="parcel_b", nodes=[FeatureNode(id="marker2", kind=FeatureKind.POINT)])

        available = {"section_1": section, "parcel_b": parcel_b}
        bundle = bundle_feature_graph(target, available_graphs=available)

        # Verify both dependencies included
        assert len(bundle.dependency_graphs) == 2
        dep_ids = {g.graph_id for g in bundle.dependency_graphs}
        assert dep_ids == {"section_1", "parcel_b"}

        # Verify reasons recorded for both
        assert "section_1" in bundle.dependency_reasons
        assert "parcel_b" in bundle.dependency_reasons
        assert "start" in bundle.dependency_reasons["section_1"]
        assert "end" in bundle.dependency_reasons["parcel_b"]


class TestRecursiveDependencies:
    """Test recursive dependency discovery."""

    def test_bundle_with_transitive_dependencies(self):
        """Bundle follows dependency chain recursively."""
        # Create chain: parcel_a -> parcel_b -> section_1
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(
                    id="ref_to_b",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="point_b", graph_id="parcel_b", is_external=True)
                )
            ]
        )

        parcel_b = FeatureGraph(
            graph_id="parcel_b",
            nodes=[
                FeatureNode(id="point_b", kind=FeatureKind.POINT),
                FeatureNode(
                    id="ref_to_section",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="corner", graph_id="section_1", is_external=True)
                )
            ]
        )

        section = FeatureGraph(
            graph_id="section_1",
            nodes=[FeatureNode(id="corner", kind=FeatureKind.POINT)]
        )

        available = {"parcel_b": parcel_b, "section_1": section}
        bundle = bundle_feature_graph(target, available_graphs=available)

        # Verify both transitive dependencies included
        assert len(bundle.dependency_graphs) == 2
        dep_ids = {g.graph_id for g in bundle.dependency_graphs}
        assert dep_ids == {"parcel_b", "section_1"}

        # Verify reasons recorded
        assert "parcel_b" in bundle.dependency_reasons
        assert "section_1" in bundle.dependency_reasons
        assert "ref_to_b" in bundle.dependency_reasons["parcel_b"]
        assert "ref_to_section" in bundle.dependency_reasons["section_1"]

    def test_bundle_handles_circular_dependencies(self):
        """Bundle handles circular references without infinite loop."""
        # Create circular chain: a -> b -> c -> a
        graph_a = FeatureGraph(
            graph_id="graph_a",
            nodes=[
                FeatureNode(
                    id="ref_to_b",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="node_b", graph_id="graph_b", is_external=True)
                )
            ]
        )

        graph_b = FeatureGraph(
            graph_id="graph_b",
            nodes=[
                FeatureNode(id="node_b", kind=FeatureKind.POINT),
                FeatureNode(
                    id="ref_to_c",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="node_c", graph_id="graph_c", is_external=True)
                )
            ]
        )

        graph_c = FeatureGraph(
            graph_id="graph_c",
            nodes=[
                FeatureNode(id="node_c", kind=FeatureKind.POINT),
                FeatureNode(
                    id="ref_back_to_a",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="node_a", graph_id="graph_a", is_external=True)
                )
            ]
        )

        available = {"graph_b": graph_b, "graph_c": graph_c}
        bundle = bundle_feature_graph(graph_a, available_graphs=available)

        # Verify no infinite loop - each graph visited once
        assert len(bundle.dependency_graphs) == 2
        dep_ids = {g.graph_id for g in bundle.dependency_graphs}
        assert dep_ids == {"graph_b", "graph_c"}


class TestMissingDependencies:
    """Test handling of missing/unavailable dependencies."""

    def test_bundle_with_missing_dependency(self):
        """Bundle handles missing dependency gracefully."""
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(
                    id="ref_to_missing",
                    kind=FeatureKind.POINT,
                    label="Missing Reference",
                    feature_ref=FeatureRef(feature_id="corner", graph_id="missing_graph", is_external=True)
                )
            ]
        )

        # Bundle without providing the referenced graph
        available = {}
        bundle = bundle_feature_graph(target, available_graphs=available)

        # Verify bundle created but dependency not included
        assert len(bundle.dependency_graphs) == 0

        # Verify reason recorded for missing dependency
        assert "missing_graph" in bundle.dependency_reasons
        reason = bundle.dependency_reasons["missing_graph"]
        assert "ref_to_missing" in reason
        assert "not available" in reason

    def test_bundle_with_partial_dependencies(self):
        """Bundle includes only available dependencies."""
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(
                    id="ref1",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="p1", graph_id="available_graph", is_external=True)
                ),
                FeatureNode(
                    id="ref2",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="p2", graph_id="missing_graph", is_external=True)
                )
            ]
        )

        available_graph = FeatureGraph(graph_id="available_graph", nodes=[FeatureNode(id="p1", kind=FeatureKind.POINT)])
        available = {"available_graph": available_graph}

        bundle = bundle_feature_graph(target, available_graphs=available)

        # Verify only available dependency included
        assert len(bundle.dependency_graphs) == 1
        assert bundle.dependency_graphs[0].graph_id == "available_graph"

        # Verify both reasons recorded
        assert "available_graph" in bundle.dependency_reasons
        assert "missing_graph" in bundle.dependency_reasons
        assert "not available" in bundle.dependency_reasons["missing_graph"]


class TestInternalReferences:
    """Test that internal references don't create dependencies."""

    def test_bundle_ignores_internal_refs(self):
        """Internal FeatureRefs (is_external=False) should not create dependencies."""
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(id="point1", kind=FeatureKind.POINT, geometry={"type": "Point", "coordinates": [0, 0]}),
                FeatureNode(
                    id="point2",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="point1", is_external=False)  # Internal ref
                )
            ]
        )

        # Create fake graph that should NOT be included
        fake_graph = FeatureGraph(graph_id="point1", nodes=[])
        available = {"point1": fake_graph}

        bundle = bundle_feature_graph(target, available_graphs=available)

        # Verify no dependencies included (internal ref ignored)
        assert len(bundle.dependency_graphs) == 0
        assert len(bundle.dependency_reasons) == 0

    def test_bundle_only_includes_external_refs(self):
        """Only external refs (is_external=True) should trigger dependency inclusion."""
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(
                    id="internal_ref",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="local_point", is_external=False)
                ),
                FeatureNode(
                    id="external_ref",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="remote_point", graph_id="other_graph", is_external=True)
                )
            ]
        )

        other_graph = FeatureGraph(graph_id="other_graph", nodes=[FeatureNode(id="remote_point", kind=FeatureKind.POINT)])
        available = {"other_graph": other_graph}

        bundle = bundle_feature_graph(target, available_graphs=available)

        # Verify only external ref created dependency
        assert len(bundle.dependency_graphs) == 1
        assert bundle.dependency_graphs[0].graph_id == "other_graph"


class TestBundleMetadata:
    """Test bundle artifact metadata and helper methods."""

    def test_bundle_includes_metadata(self):
        """Bundle artifact includes proper metadata."""
        target = FeatureGraph(graph_id="test_graph", nodes=[])
        bundle = bundle_feature_graph(
            target,
            bundle_id="custom_bundle_id",
            created_by="test_agent",
            bundle_purpose="Testing metadata"
        )

        assert bundle.artifact_id == "custom_bundle_id"
        assert bundle.artifact_type == "bundle"
        assert bundle.metadata.created_by == "test_agent"
        assert bundle.bundle_purpose == "Testing metadata"
        assert bundle.metadata.version == "1.0"
        assert bundle.metadata.created_at is not None
        assert bundle.target_graph_id in bundle.metadata.parent_artifact_ids

    def test_bundle_auto_generates_id(self):
        """Bundle auto-generates ID if not provided."""
        target = FeatureGraph(graph_id="my_graph", nodes=[])
        bundle = bundle_feature_graph(target)

        assert bundle.artifact_id is not None
        assert "bundle_" in bundle.artifact_id
        assert "my_graph" in bundle.artifact_id

    def test_get_all_graph_ids(self):
        """Bundle helper method returns all graph IDs."""
        target = FeatureGraph(
            graph_id="target",
            nodes=[
                FeatureNode(
                    id="ref1",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="p", graph_id="dep1", is_external=True)
                )
            ]
        )
        dep1 = FeatureGraph(graph_id="dep1", nodes=[])
        available = {"dep1": dep1}

        bundle = bundle_feature_graph(target, available_graphs=available)
        all_ids = bundle.get_all_graph_ids()

        assert len(all_ids) == 2
        assert "target" in all_ids
        assert "dep1" in all_ids

    def test_get_dependency_reason(self):
        """Bundle helper method retrieves dependency reason."""
        target = FeatureGraph(
            graph_id="target",
            nodes=[
                FeatureNode(
                    id="origin",
                    kind=FeatureKind.POINT,
                    label="Origin Point",
                    feature_ref=FeatureRef(feature_id="p", graph_id="dep1", label="External Point", is_external=True)
                )
            ]
        )
        dep1 = FeatureGraph(graph_id="dep1", nodes=[])
        available = {"dep1": dep1}

        bundle = bundle_feature_graph(target, available_graphs=available)
        reason = bundle.get_dependency_reason("dep1")

        assert reason is not None
        assert "origin" in reason
        assert "Origin Point" in reason or "External Point" in reason

    def test_get_dependency_reason_missing(self):
        """get_dependency_reason returns None for missing graph."""
        target = FeatureGraph(graph_id="target", nodes=[])
        bundle = bundle_feature_graph(target)

        reason = bundle.get_dependency_reason("nonexistent")
        assert reason is None


class TestBundleRoundTrip:
    """Test bundle JSON serialization and rehydration."""

    def test_bundle_json_round_trip(self):
        """Bundle can be serialized to JSON and rehydrated."""
        target = FeatureGraph(
            graph_id="parcel_a",
            nodes=[
                FeatureNode(
                    id="ref1",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="corner", graph_id="section_1", is_external=True)
                )
            ]
        )
        section = FeatureGraph(graph_id="section_1", nodes=[FeatureNode(id="corner", kind=FeatureKind.POINT)])
        available = {"section_1": section}

        bundle = bundle_feature_graph(target, available_graphs=available, bundle_purpose="Test round-trip")

        # Serialize to JSON
        json_data = bundle.model_dump()
        assert isinstance(json_data, dict)

        # Rehydrate from JSON
        rehydrated = BundleArtifact.model_validate(json_data)

        # Verify structure preserved
        assert rehydrated.artifact_id == bundle.artifact_id
        assert rehydrated.target_graph_id == "parcel_a"
        assert len(rehydrated.dependency_graphs) == 1
        assert rehydrated.dependency_graphs[0].graph_id == "section_1"
        assert "section_1" in rehydrated.dependency_reasons
        assert rehydrated.bundle_purpose == "Test round-trip"

    def test_empty_bundle_serialization(self):
        """Empty bundle (no dependencies) serializes correctly."""
        target = FeatureGraph(graph_id="simple", nodes=[])
        bundle = bundle_feature_graph(target)

        json_data = bundle.model_dump()
        rehydrated = BundleArtifact.model_validate(json_data)

        assert rehydrated.target_graph_id == "simple"
        assert len(rehydrated.dependency_graphs) == 0
        assert len(rehydrated.dependency_reasons) == 0


class TestBundleEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_bundle_empty_graph(self):
        """Bundle handles empty graph (no nodes)."""
        empty = FeatureGraph(graph_id="empty", nodes=[])
        bundle = bundle_feature_graph(empty)

        assert bundle.target_graph_id == "empty"
        assert len(bundle.dependency_graphs) == 0

    def test_bundle_with_none_available_graphs(self):
        """Bundle handles None for available_graphs parameter."""
        target = FeatureGraph(
            graph_id="test",
            nodes=[
                FeatureNode(
                    id="ref",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="ext", graph_id="external", is_external=True)
                )
            ]
        )

        bundle = bundle_feature_graph(target, available_graphs=None)

        # Verify no dependencies included (nothing available)
        assert len(bundle.dependency_graphs) == 0
        assert len(bundle.dependency_reasons) == 0

    def test_bundle_with_empty_available_graphs(self):
        """Bundle handles empty dict for available_graphs."""
        target = FeatureGraph(
            graph_id="test",
            nodes=[
                FeatureNode(
                    id="ref",
                    kind=FeatureKind.POINT,
                    feature_ref=FeatureRef(feature_id="ext", graph_id="external", is_external=True)
                )
            ]
        )

        bundle = bundle_feature_graph(target, available_graphs={})

        # Verify dependency marked as missing
        assert len(bundle.dependency_graphs) == 0
        assert "external" in bundle.dependency_reasons
        assert "not available" in bundle.dependency_reasons["external"]
