"""
Feature Graph IR Models Tests
==============================

Tests JSON round-trip serialization and basic functionality for core IR models.
These tests validate the weight-bearing invariants:
- Models serialize to JSON and deserialize without loss
- IDs are stable and deterministic
- Graph query methods work correctly
- Edge cases (empty graphs, missing nodes) are handled safely
"""

import pytest
import json
from backend.feature_graph.models import (
    FeatureKind,
    FeatureNode,
    FeatureEdge,
    FeatureRef,
    OpExpr,
    Literal,
    FeatureGraph,
)


def test_literal_json_roundtrip():
    """Test Literal serialization and deserialization."""
    lit = Literal(raw="100.5", value=100.5, unit="feet", value_type="number")

    # Serialize to JSON
    json_str = lit.model_dump_json()
    data = json.loads(json_str)

    # Deserialize back
    lit2 = Literal(**data)

    assert lit2.raw == "100.5"
    assert lit2.value == 100.5
    assert lit2.unit == "feet"
    assert lit2.value_type == "number"


def test_op_expr_json_roundtrip():
    """Test OpExpr serialization with nested operands."""
    op = OpExpr(
        op_name="Buffer",
        params={"distance": 10.0, "unit": "feet"},
        operands=["region_1"]
    )

    # Serialize
    json_str = op.model_dump_json()
    data = json.loads(json_str)

    # Deserialize
    op2 = OpExpr(**data)

    assert op2.op_name == "Buffer"
    assert op2.params["distance"] == 10.0
    assert op2.operands == ["region_1"]


def test_feature_ref_json_roundtrip():
    """Test FeatureRef serialization for internal and external refs."""
    # Internal ref
    ref1 = FeatureRef(feature_id="point_1", label="Starting Point", is_external=False)
    json_str = ref1.model_dump_json()
    ref1_restored = FeatureRef(**json.loads(json_str))
    assert ref1_restored.feature_id == "point_1"
    assert ref1_restored.is_external is False

    # External ref
    ref2 = FeatureRef(
        feature_id="parcel_A",
        graph_id="graph_123",
        label="Adjacent Parcel A",
        is_external=True
    )
    json_str = ref2.model_dump_json()
    ref2_restored = FeatureRef(**json.loads(json_str))
    assert ref2_restored.graph_id == "graph_123"
    assert ref2_restored.is_external is True


def test_feature_node_json_roundtrip():
    """Test FeatureNode with different content types."""
    # Node with direct geometry
    node1 = FeatureNode(
        id="point_1",
        kind=FeatureKind.POINT,
        label="NE Corner",
        geometry={"type": "Point", "coordinates": [100.0, 200.0]}
    )
    json_str = node1.model_dump_json()
    node1_restored = FeatureNode(**json.loads(json_str))
    assert node1_restored.id == "point_1"
    assert node1_restored.kind == FeatureKind.POINT
    assert node1_restored.geometry["coordinates"] == [100.0, 200.0]

    # Node with operation expression
    node2 = FeatureNode(
        id="region_1",
        kind=FeatureKind.REGION,
        label="Main Parcel",
        op_expr=OpExpr(op_name="Close", operands=["curve_1"])
    )
    json_str = node2.model_dump_json()
    node2_restored = FeatureNode(**json.loads(json_str))
    assert node2_restored.op_expr.op_name == "Close"

    # Node with feature reference
    node3 = FeatureNode(
        id="anchor_1",
        kind=FeatureKind.FRAME,
        label="Section 1",
        feature_ref=FeatureRef(feature_id="section_1_T1N_R1W", is_external=True)
    )
    json_str = node3.model_dump_json()
    node3_restored = FeatureNode(**json.loads(json_str))
    assert node3_restored.feature_ref.feature_id == "section_1_T1N_R1W"


def test_feature_edge_json_roundtrip():
    """Test FeatureEdge serialization."""
    edge = FeatureEdge(
        source_id="step_1",
        target_id="step_2",
        edge_type="next_step",
        label="Step 1 to Step 2",
        metadata={"sequence": 1}
    )

    json_str = edge.model_dump_json()
    edge_restored = FeatureEdge(**json.loads(json_str))

    assert edge_restored.source_id == "step_1"
    assert edge_restored.target_id == "step_2"
    assert edge_restored.edge_type == "next_step"
    assert edge_restored.metadata["sequence"] == 1


def test_feature_graph_minimal_roundtrip():
    """
    Test minimal feature graph JSON round-trip.
    This is the core acceptance criterion: a minimal graph must serialize and deserialize.
    """
    # Build minimal graph: single point and single curve with one edge
    point = FeatureNode(
        id="start",
        kind=FeatureKind.POINT,
        label="Starting Point",
        geometry={"type": "Point", "coordinates": [0.0, 0.0]}
    )

    curve = FeatureNode(
        id="boundary",
        kind=FeatureKind.CURVE,
        label="Boundary Line",
        geometry={"type": "LineString", "coordinates": [[0.0, 0.0], [100.0, 0.0]]}
    )

    edge = FeatureEdge(
        source_id="start",
        target_id="boundary",
        edge_type="anchored_to",
        label="Boundary starts at point"
    )

    graph = FeatureGraph(
        graph_id="test_graph_001",
        nodes=[point, curve],
        edges=[edge],
        metadata={"source": "test", "created": "2026-02-04"}
    )

    # Serialize to JSON
    json_str = graph.model_dump_json(indent=2)
    data = json.loads(json_str)

    # Deserialize back
    graph_restored = FeatureGraph(**data)

    # Validate round-trip
    assert graph_restored.graph_id == "test_graph_001"
    assert len(graph_restored.nodes) == 2
    assert len(graph_restored.edges) == 1
    assert graph_restored.metadata["source"] == "test"

    # Validate node content preserved
    start_node = graph_restored.get_node("start")
    assert start_node is not None
    assert start_node.kind == FeatureKind.POINT
    assert start_node.geometry["coordinates"] == [0.0, 0.0]

    boundary_node = graph_restored.get_node("boundary")
    assert boundary_node is not None
    assert boundary_node.kind == FeatureKind.CURVE


def test_feature_graph_query_methods():
    """Test graph query helper methods."""
    graph = FeatureGraph(
        graph_id="test_graph_002",
        nodes=[
            FeatureNode(id="A", kind=FeatureKind.POINT, geometry={"coordinates": [0, 0]}),
            FeatureNode(id="B", kind=FeatureKind.POINT, geometry={"coordinates": [1, 1]}),
            FeatureNode(id="C", kind=FeatureKind.CURVE, geometry={"coordinates": [[0, 0], [1, 1]]}),
        ],
        edges=[
            FeatureEdge(source_id="A", target_id="C", edge_type="start"),
            FeatureEdge(source_id="B", target_id="C", edge_type="end"),
            FeatureEdge(source_id="C", target_id="A", edge_type="returns_to"),
        ]
    )

    # Test get_node
    assert graph.get_node("A") is not None
    assert graph.get_node("missing") is None

    # Test get_edges_from
    edges_from_a = graph.get_edges_from("A")
    assert len(edges_from_a) == 1
    assert edges_from_a[0].target_id == "C"

    edges_from_c = graph.get_edges_from("C")
    assert len(edges_from_c) == 1
    assert edges_from_c[0].target_id == "A"

    # Test get_edges_to
    edges_to_c = graph.get_edges_to("C")
    assert len(edges_to_c) == 2
    assert set(e.source_id for e in edges_to_c) == {"A", "B"}

    edges_to_a = graph.get_edges_to("A")
    assert len(edges_to_a) == 1
    assert edges_to_a[0].source_id == "C"


def test_empty_graph():
    """Test that empty graphs are valid and serialize correctly."""
    empty_graph = FeatureGraph(
        graph_id="empty_001",
        nodes=[],
        edges=[],
        metadata={}
    )

    json_str = empty_graph.model_dump_json()
    restored = FeatureGraph(**json.loads(json_str))

    assert restored.graph_id == "empty_001"
    assert len(restored.nodes) == 0
    assert len(restored.edges) == 0


def test_complex_nested_op_expr():
    """Test complex nested operation expressions."""
    # Example: Union(Close(Traverse1), Buffer(Close(Traverse2), 10ft))
    inner_op1 = OpExpr(op_name="Close", operands=["traverse_1"])
    inner_op2 = OpExpr(
        op_name="Buffer",
        params={"distance": 10.0, "unit": "feet"},
        operands=[OpExpr(op_name="Close", operands=["traverse_2"])]
    )
    union_op = OpExpr(
        op_name="Union",
        operands=[inner_op1, inner_op2]
    )

    node = FeatureNode(
        id="combined_region",
        kind=FeatureKind.REGION,
        label="Union of Two Parcels",
        op_expr=union_op
    )

    # Serialize and deserialize
    json_str = node.model_dump_json()
    restored = FeatureNode(**json.loads(json_str))

    # Validate structure preserved
    assert restored.op_expr.op_name == "Union"
    assert len(restored.op_expr.operands) == 2

    # First operand is OpExpr (Close)
    first_op = restored.op_expr.operands[0]
    assert isinstance(first_op, OpExpr)
    assert first_op.op_name == "Close"

    # Second operand is OpExpr (Buffer with nested Close)
    second_op = restored.op_expr.operands[1]
    assert isinstance(second_op, OpExpr)
    assert second_op.op_name == "Buffer"
    assert second_op.params["distance"] == 10.0


if __name__ == "__main__":
    # Allow direct execution for quick testing
    pytest.main([__file__, "-v"])
