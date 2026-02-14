"""
Feature Graph IR Core Models
=============================

Universal intermediate representation models for deed meaning.
These models provide total representability - any deed assertion must be
encodable in this IR, even if compilation is not yet supported.

Design principles:
- Total representability: all deed assertions can be encoded
- No confidence scores: record facts, provenance, deterministic outcomes
- Explicit gaps: compilation failures produce typed gaps, never silent failure
- Provenance-aware: all nodes/edges can cite source evidence
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from .provenance import ProvenanceAttachment


class FeatureKind(str, Enum):
    """
    Type of geographic feature represented by a node.

    This enum is extensible - new kinds can be added as deed parsing evolves.
    """
    POINT = "point"              # Single coordinate point
    CURVE = "curve"              # Open curve (polyline, arc, etc)
    REGION = "region"            # Closed polygon/area
    FRAME = "frame"              # Coordinate reference frame (e.g., PLSS section)
    CONSTRAINT = "constraint"    # Geometric constraint (distance, angle, etc)
    ANNOTATION = "annotation"    # Textual annotation or label
    UNKNOWN = "unknown"          # Placeholder for unsupported feature types


class Literal(BaseModel):
    """
    Typed literal value (string, number, boolean, etc).

    Preserves both the raw string representation (for provenance)
    and parsed typed value (for computation).
    """
    raw: str = Field(..., description="Original string representation from source")
    value: Union[str, float, int, bool, None] = Field(..., description="Parsed typed value, or None if parse failed")
    unit: Optional[str] = Field(None, description="Unit of measurement if applicable (feet, degrees, etc)")
    value_type: str = Field("string", description="Type hint: string, number, boolean, etc")

    class Config:
        frozen = False


class OpExpr(BaseModel):
    """
    Operation expression node - represents a computation or transformation.

    Examples:
    - Traverse: sequence of line/curve steps
    - Derive: Close(curve) → region, Buffer(region, distance) → region
    - Constraint: Distance(A, B) = 100ft
    - Boolean: Union(A, B), Intersection(A, B), Difference(A, B)

    Unsupported operations can still be stored in IR with op_name and params,
    but will produce typed gaps during compilation.
    """
    op_name: str = Field(..., description="Operation name (Traverse, Close, Buffer, Union, etc)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Operation parameters as key-value pairs")
    operands: List[Union[str, OpExpr]] = Field(default_factory=list, description="Operand feature IDs or nested OpExprs")

    class Config:
        frozen = False


class FeatureRef(BaseModel):
    """
    Reference to another feature (internal or external).

    Internal refs point to nodes within the same graph.
    External refs point to features in other graphs (e.g., referenced parcels).

    Unresolved refs will produce MissingAnchor or AmbiguousChoice gaps.
    """
    feature_id: str = Field(..., description="ID of referenced feature")
    graph_id: Optional[str] = Field(None, description="Graph ID if external reference")
    label: Optional[str] = Field(None, description="Human-readable label (e.g., 'Parcel A', 'Section 1')")
    is_external: bool = Field(False, description="True if reference points to external graph")

    class Config:
        frozen = False


class FeatureNode(BaseModel):
    """
    Single node in the feature graph.

    Each node represents a geographic feature with a unique ID, kind, and optional geometry.
    Nodes can be defined by:
    - Direct geometry (coordinates, polyline, polygon)
    - Operation expression (OpExpr) that produces the feature
    - Reference to another feature (FeatureRef)

    Provenance fields (citations, evidence) are optional and added via provenance module.
    """
    id: str = Field(..., description="Unique identifier within this graph")
    kind: FeatureKind = Field(..., description="Type of feature")
    label: Optional[str] = Field(None, description="Human-readable label")

    # Geometry representation (mutually exclusive with op_expr and feature_ref)
    geometry: Optional[Dict[str, Any]] = Field(None, description="Direct geometry (GeoJSON-like or local coordinates)")

    # Operation expression (mutually exclusive with geometry and feature_ref)
    op_expr: Optional[OpExpr] = Field(None, description="Operation that produces this feature")

    # Feature reference (mutually exclusive with geometry and op_expr)
    feature_ref: Optional[FeatureRef] = Field(None, description="Reference to another feature")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata, params, or annotations")

    # Provenance (optional, added via provenance module)
    provenance: Optional[Any] = Field(None, description="ProvenanceAttachment with citations and evidence links")

    class Config:
        frozen = False

    @model_validator(mode="after")
    def validate_content_source_exclusivity(self) -> "FeatureNode":
        """Ensure geometry/op_expr/feature_ref are mutually exclusive."""
        content_fields = [self.geometry, self.op_expr, self.feature_ref]
        provided_count = sum(1 for field in content_fields if field is not None)
        if provided_count > 1:
            raise ValueError(
                "FeatureNode content is ambiguous: provide only one of "
                "geometry, op_expr, or feature_ref."
            )
        return self


class FeatureEdge(BaseModel):
    """
    Directed edge between features in the graph.

    Edges represent relationships, dependencies, or spatial constraints:
    - Sequencing: step1 → step2 in a traverse
    - Derivation: curve → Close(curve) → region
    - Constraint: A adjacent_to B
    - Anchoring: local_feature → frame_reference

    Edge types are extensible via the edge_type field.
    """
    source_id: str = Field(..., description="Source feature ID")
    target_id: str = Field(..., description="Target feature ID")
    edge_type: str = Field("depends_on", description="Relationship type (depends_on, next_step, anchored_to, etc)")
    label: Optional[str] = Field(None, description="Human-readable edge label")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Edge-specific metadata or parameters")

    # Provenance (optional, added via provenance module)
    provenance: Optional[Any] = Field(None, description="ProvenanceAttachment with citations and evidence links")

    class Config:
        frozen = False


class FeatureGraph(BaseModel):
    """
    Complete feature graph - a collection of nodes and edges representing deed meaning.

    The graph is a directed acyclic graph (DAG) in most cases, but cycles are allowed
    for constraint systems. The graph stores:
    - All feature nodes (points, curves, regions, frames, constraints)
    - All edges (dependencies, sequencing, anchoring)
    - Metadata (source document, creation time, lineage)

    Graphs can be compiled, validated, bundled, and persisted with full provenance.
    """
    graph_id: str = Field(..., description="Unique identifier for this graph")
    nodes: List[FeatureNode] = Field(default_factory=list, description="All feature nodes in the graph")
    edges: List[FeatureEdge] = Field(default_factory=list, description="All edges between features")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Graph-level metadata (source, lineage, etc)")

    class Config:
        frozen = False

    def get_node(self, node_id: str) -> Optional[FeatureNode]:
        """Retrieve a node by ID, or None if not found."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_edges_from(self, source_id: str) -> List[FeatureEdge]:
        """Retrieve all edges originating from a given node."""
        return [edge for edge in self.edges if edge.source_id == source_id]

    def get_edges_to(self, target_id: str) -> List[FeatureEdge]:
        """Retrieve all edges targeting a given node."""
        return [edge for edge in self.edges if edge.target_id == target_id]
