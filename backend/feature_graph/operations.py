"""
Feature Graph Operation Registry
=================================

Universal operation definitions for feature graph IR.
All operations must be representable in IR, even if not yet compilable.

Operation categories:
- Traverse: LineStep, CurveStep, ConstraintStep (build curves from measurements)
- Derive: Close, Buffer, Offset, etc (transform features)
- Constraint: Distance, Angle, Perpendicular, etc (geometric constraints)
- Boolean: Union, Intersection, Difference, SymmetricDifference (region operations)

Design principles:
- Operations are registry entries, not hard-coded classes
- Unsupported operations can be stored in IR as UnsupportedOperation
- Each operation defines required/optional parameters and operands
- No execution logic here - compiler implements supported operations separately
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Set
from enum import Enum


class OperationCategory(str, Enum):
    """
    High-level category for operation types.
    """
    TRAVERSE = "traverse"        # Build curves from measurements (LineStep, CurveStep, etc)
    DERIVE = "derive"            # Transform features (Close, Buffer, Offset, etc)
    CONSTRAINT = "constraint"    # Geometric constraints (Distance, Angle, etc)
    BOOLEAN = "boolean"          # Region boolean operations (Union, Intersection, etc)
    UNKNOWN = "unknown"          # Unsupported or not yet categorized


class ParameterSpec(BaseModel):
    """
    Specification for an operation parameter.

    Defines name, type, whether it's required, and any default value.
    """
    name: str = Field(..., description="Parameter name")
    param_type: str = Field(..., description="Parameter type hint (number, string, boolean, etc)")
    required: bool = Field(True, description="Whether this parameter is required")
    default: Optional[Any] = Field(None, description="Default value if parameter is optional")
    unit: Optional[str] = Field(None, description="Expected unit of measurement (feet, degrees, etc)")
    description: Optional[str] = Field(None, description="Human-readable parameter description")

    class Config:
        frozen = False


class OperationDef(BaseModel):
    """
    Definition of a single operation in the registry.

    Each operation specifies:
    - name: operation identifier (used in OpExpr.op_name)
    - category: operation category (traverse, derive, etc)
    - parameters: list of parameter specifications
    - min_operands: minimum number of operands required
    - max_operands: maximum number of operands allowed (None = unlimited)
    - description: human-readable description
    - supported: whether the compiler currently implements this operation
    """
    name: str = Field(..., description="Operation name (LineStep, Close, Union, etc)")
    category: OperationCategory = Field(..., description="Operation category")
    parameters: List[ParameterSpec] = Field(default_factory=list, description="Parameter specifications")
    min_operands: int = Field(0, description="Minimum number of operands required")
    max_operands: Optional[int] = Field(None, description="Maximum operands allowed (None = unlimited)")
    description: str = Field("", description="Human-readable operation description")
    supported: bool = Field(False, description="Whether compiler currently supports this operation")

    class Config:
        frozen = False

    def get_required_parameters(self) -> List[str]:
        """Return names of all required parameters."""
        return [p.name for p in self.parameters if p.required]

    def get_optional_parameters(self) -> List[str]:
        """Return names of all optional parameters."""
        return [p.name for p in self.parameters if not p.required]

    def validate_operand_count(self, operand_count: int) -> bool:
        """Check if the given operand count is valid for this operation."""
        if operand_count < self.min_operands:
            return False
        if self.max_operands is not None and operand_count > self.max_operands:
            return False
        return True


# ============================================================================
# TRAVERSE OPERATIONS
# ============================================================================

TRAVERSE_LINE_STEP = OperationDef(
    name="LineStep",
    category=OperationCategory.TRAVERSE,
    description="Straight line segment with bearing and distance",
    parameters=[
        ParameterSpec(
            name="bearing",
            param_type="number",
            required=True,
            unit="degrees",
            description="Bearing angle from north (0-360 degrees)"
        ),
        ParameterSpec(
            name="distance",
            param_type="number",
            required=True,
            unit="feet",
            description="Distance to travel along bearing"
        ),
        ParameterSpec(
            name="bearing_raw",
            param_type="string",
            required=False,
            description="Original bearing string from deed (for provenance)"
        ),
        ParameterSpec(
            name="distance_raw",
            param_type="string",
            required=False,
            description="Original distance string from deed (for provenance)"
        )
    ],
    min_operands=0,
    max_operands=1,  # Optional: previous point as operand
    supported=True
)

TRAVERSE_CURVE_STEP = OperationDef(
    name="CurveStep",
    category=OperationCategory.TRAVERSE,
    description="Curve segment with radius, arc length, and/or chord bearing",
    parameters=[
        ParameterSpec(
            name="radius",
            param_type="number",
            required=False,
            unit="feet",
            description="Curve radius"
        ),
        ParameterSpec(
            name="arc_length",
            param_type="number",
            required=False,
            unit="feet",
            description="Arc length along curve"
        ),
        ParameterSpec(
            name="chord_bearing",
            param_type="number",
            required=False,
            unit="degrees",
            description="Bearing of chord connecting arc endpoints"
        ),
        ParameterSpec(
            name="chord_distance",
            param_type="number",
            required=False,
            unit="feet",
            description="Length of chord"
        ),
        ParameterSpec(
            name="delta_angle",
            param_type="number",
            required=False,
            unit="degrees",
            description="Central angle subtended by arc"
        ),
        ParameterSpec(
            name="direction",
            param_type="string",
            required=False,
            default="right",
            description="Curve direction (left or right)"
        )
    ],
    min_operands=0,
    max_operands=1,  # Optional: previous point as operand
    supported=False  # Not yet implemented in compiler
)

TRAVERSE_CONSTRAINT_STEP = OperationDef(
    name="ConstraintStep",
    category=OperationCategory.TRAVERSE,
    description="Traverse step constrained by geometric relationships (e.g., 'to point X')",
    parameters=[
        ParameterSpec(
            name="constraint_type",
            param_type="string",
            required=True,
            description="Type of constraint (to_point, parallel_to, perpendicular_to, etc)"
        ),
        ParameterSpec(
            name="target_id",
            param_type="string",
            required=False,
            description="ID of target feature for constraint"
        )
    ],
    min_operands=1,
    max_operands=2,  # Previous point + target point/feature
    supported=False
)

TRAVERSE_COURSE_TRAVERSE = OperationDef(
    name="CourseTraverse",
    category=OperationCategory.TRAVERSE,
    description="Sequence of bearing/distance course calls compiled into a schematic LineString",
    parameters=[
        ParameterSpec(
            name="courses",
            param_type="array",
            required=True,
            description="Ordered list of course objects with bearing/distance (numeric or raw)"
        )
    ],
    min_operands=0,
    max_operands=1,
    supported=True,
)

TRAVERSE_TIED_POINT = OperationDef(
    name="TiedPoint",
    category=OperationCategory.TRAVERSE,
    description="Schematic point anchored by descriptive tie metadata (not globally resolved)",
    parameters=[],
    min_operands=0,
    max_operands=1,
    supported=True,
)

# ============================================================================
# DERIVE OPERATIONS
# ============================================================================

DERIVE_CLOSE = OperationDef(
    name="Close",
    category=OperationCategory.DERIVE,
    description="Close a curve to produce a region (only if curve endpoints meet)",
    parameters=[],
    min_operands=1,
    max_operands=1,  # Takes exactly one curve operand
    supported=True
)

DERIVE_BUFFER = OperationDef(
    name="Buffer",
    category=OperationCategory.DERIVE,
    description="Create a buffer region around a feature",
    parameters=[
        ParameterSpec(
            name="distance",
            param_type="number",
            required=True,
            unit="feet",
            description="Buffer distance"
        ),
        ParameterSpec(
            name="side",
            param_type="string",
            required=False,
            default="both",
            description="Which side to buffer (left, right, both)"
        )
    ],
    min_operands=1,
    max_operands=1,
    supported=False  # Stubbed in compiler as unsupported
)

DERIVE_OFFSET = OperationDef(
    name="Offset",
    category=OperationCategory.DERIVE,
    description="Offset a curve by a perpendicular distance",
    parameters=[
        ParameterSpec(
            name="distance",
            param_type="number",
            required=True,
            unit="feet",
            description="Offset distance"
        ),
        ParameterSpec(
            name="side",
            param_type="string",
            required=False,
            default="right",
            description="Which side to offset (left or right)"
        )
    ],
    min_operands=1,
    max_operands=1,
    supported=False
)

# ============================================================================
# CONSTRAINT OPERATIONS
# ============================================================================

CONSTRAINT_DISTANCE = OperationDef(
    name="Distance",
    category=OperationCategory.CONSTRAINT,
    description="Assert or constrain distance between two features",
    parameters=[
        ParameterSpec(
            name="distance",
            param_type="number",
            required=True,
            unit="feet",
            description="Required distance"
        )
    ],
    min_operands=2,
    max_operands=2,  # Two features: from and to
    supported=False
)

CONSTRAINT_ANGLE = OperationDef(
    name="Angle",
    category=OperationCategory.CONSTRAINT,
    description="Assert or constrain angle between features",
    parameters=[
        ParameterSpec(
            name="angle",
            param_type="number",
            required=True,
            unit="degrees",
            description="Required angle"
        )
    ],
    min_operands=3,
    max_operands=3,  # Three points: A-B-C defines angle at B
    supported=False
)

CONSTRAINT_PERPENDICULAR = OperationDef(
    name="Perpendicular",
    category=OperationCategory.CONSTRAINT,
    description="Assert two features are perpendicular",
    parameters=[],
    min_operands=2,
    max_operands=2,
    supported=False
)

CONSTRAINT_PARALLEL = OperationDef(
    name="Parallel",
    category=OperationCategory.CONSTRAINT,
    description="Assert two features are parallel",
    parameters=[],
    min_operands=2,
    max_operands=2,
    supported=False
)

# ============================================================================
# BOOLEAN OPERATIONS
# ============================================================================

BOOLEAN_UNION = OperationDef(
    name="Union",
    category=OperationCategory.BOOLEAN,
    description="Compute union of two or more regions",
    parameters=[],
    min_operands=2,
    max_operands=None,  # Unlimited operands
    supported=False
)

BOOLEAN_COLLECTION = OperationDef(
    name="Collection",
    category=OperationCategory.BOOLEAN,
    description="Semantic grouping of features without geometric boolean computation",
    parameters=[],
    min_operands=1,
    max_operands=None,
    supported=True,
)

BOOLEAN_INTERSECTION = OperationDef(
    name="Intersection",
    category=OperationCategory.BOOLEAN,
    description="Compute intersection of two or more regions",
    parameters=[],
    min_operands=2,
    max_operands=None,
    supported=False
)

BOOLEAN_DIFFERENCE = OperationDef(
    name="Difference",
    category=OperationCategory.BOOLEAN,
    description="Compute difference of two regions (A - B)",
    parameters=[],
    min_operands=2,
    max_operands=2,
    supported=False
)

BOOLEAN_SYMMETRIC_DIFFERENCE = OperationDef(
    name="SymmetricDifference",
    category=OperationCategory.BOOLEAN,
    description="Compute symmetric difference of two regions",
    parameters=[],
    min_operands=2,
    max_operands=2,
    supported=False
)

# ============================================================================
# OPERATION REGISTRY
# ============================================================================

# Global registry of all operation definitions
OPERATION_REGISTRY: Dict[str, OperationDef] = {
    # Traverse operations
    "LineStep": TRAVERSE_LINE_STEP,
    "CurveStep": TRAVERSE_CURVE_STEP,
    "ConstraintStep": TRAVERSE_CONSTRAINT_STEP,
    "CourseTraverse": TRAVERSE_COURSE_TRAVERSE,
    "TiedPoint": TRAVERSE_TIED_POINT,

    # Derive operations
    "Close": DERIVE_CLOSE,
    "Buffer": DERIVE_BUFFER,
    "Offset": DERIVE_OFFSET,

    # Constraint operations
    "Distance": CONSTRAINT_DISTANCE,
    "Angle": CONSTRAINT_ANGLE,
    "Perpendicular": CONSTRAINT_PERPENDICULAR,
    "Parallel": CONSTRAINT_PARALLEL,

    # Boolean operations
    "Union": BOOLEAN_UNION,
    "Collection": BOOLEAN_COLLECTION,
    "Intersection": BOOLEAN_INTERSECTION,
    "Difference": BOOLEAN_DIFFERENCE,
    "SymmetricDifference": BOOLEAN_SYMMETRIC_DIFFERENCE,
}


def get_operation_def(op_name: str) -> Optional[OperationDef]:
    """
    Retrieve operation definition from registry.

    Returns None if operation is not in registry (unsupported operation).
    """
    return OPERATION_REGISTRY.get(op_name)


def is_supported_operation(op_name: str) -> bool:
    """
    Check if an operation is supported by the compiler.

    Returns False if operation is not in registry or marked as unsupported.
    """
    op_def = get_operation_def(op_name)
    return op_def is not None and op_def.supported


def get_operations_by_category(category: OperationCategory) -> List[OperationDef]:
    """
    Retrieve all operations in a given category.
    """
    return [op_def for op_def in OPERATION_REGISTRY.values() if op_def.category == category]


def get_supported_operations() -> List[str]:
    """
    Retrieve names of all operations currently supported by the compiler.
    """
    return [name for name, op_def in OPERATION_REGISTRY.items() if op_def.supported]


def get_unsupported_operations() -> List[str]:
    """
    Retrieve names of all operations NOT yet supported by the compiler.
    """
    return [name for name, op_def in OPERATION_REGISTRY.items() if not op_def.supported]


class UnsupportedOperation(BaseModel):
    """
    Wrapper for unsupported operations that can still be stored in IR.

    When an operation is not in the registry or marked as unsupported,
    it can be stored as an UnsupportedOperation entry with all params preserved.
    This ensures total representability - any deed assertion can be encoded,
    even if compilation is not yet possible.
    """
    op_name: str = Field(..., description="Name of unsupported operation")
    params: Dict[str, Any] = Field(default_factory=dict, description="Operation parameters")
    operands: List[str] = Field(default_factory=list, description="Operand feature IDs")
    reason: str = Field("Not yet implemented", description="Reason operation is unsupported")

    class Config:
        frozen = False

    def to_op_expr(self) -> Dict[str, Any]:
        """
        Convert to OpExpr-compatible dict for storage in IR.
        """
        return {
            "op_name": self.op_name,
            "params": {
                **self.params,
                "_unsupported": True,
                "_reason": self.reason
            },
            "operands": self.operands
        }
