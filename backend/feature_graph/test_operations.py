"""
Tests for Feature Graph Operation Registry
===========================================

Validates operation definitions, registry queries, and unsupported operation handling.

Test coverage:
- All operation definitions are well-formed
- Registry queries return correct operation defs
- Supported/unsupported operation filtering works
- UnsupportedOperation wrapper preserves params
- Operand count validation works correctly
"""

import pytest
from .operations import (
    OperationCategory,
    OperationDef,
    ParameterSpec,
    UnsupportedOperation,
    OPERATION_REGISTRY,
    get_operation_def,
    is_supported_operation,
    get_operations_by_category,
    get_supported_operations,
    get_unsupported_operations,
    # Specific operation constants
    TRAVERSE_LINE_STEP,
    TRAVERSE_CURVE_STEP,
    DERIVE_CLOSE,
    DERIVE_BUFFER,
    CONSTRAINT_DISTANCE,
    BOOLEAN_UNION,
)


def test_operation_registry_is_populated():
    """Registry contains expected operations."""
    assert len(OPERATION_REGISTRY) >= 12, "Registry should contain at least 12 operations"

    # Check key operations are present
    expected_ops = [
        "LineStep", "CurveStep", "ConstraintStep",
        "Close", "Buffer", "Offset",
        "Distance", "Angle", "Perpendicular", "Parallel",
        "Union", "Intersection", "Difference", "SymmetricDifference"
    ]
    for op_name in expected_ops:
        assert op_name in OPERATION_REGISTRY, f"{op_name} should be in registry"


def test_get_operation_def():
    """get_operation_def retrieves correct definitions."""
    # Known operations
    line_step_def = get_operation_def("LineStep")
    assert line_step_def is not None
    assert line_step_def.name == "LineStep"
    assert line_step_def.category == OperationCategory.TRAVERSE
    assert line_step_def.supported is True

    close_def = get_operation_def("Close")
    assert close_def is not None
    assert close_def.name == "Close"
    assert close_def.category == OperationCategory.DERIVE

    # Unknown operation
    unknown_def = get_operation_def("UnknownOperation")
    assert unknown_def is None


def test_is_supported_operation():
    """is_supported_operation correctly identifies supported ops."""
    # Supported operations
    assert is_supported_operation("LineStep") is True
    assert is_supported_operation("Close") is True

    # Unsupported operations (in registry but marked unsupported)
    assert is_supported_operation("Buffer") is False
    assert is_supported_operation("CurveStep") is False
    assert is_supported_operation("Union") is False

    # Not in registry
    assert is_supported_operation("NotInRegistry") is False


def test_get_operations_by_category():
    """get_operations_by_category filters correctly."""
    traverse_ops = get_operations_by_category(OperationCategory.TRAVERSE)
    assert len(traverse_ops) >= 3
    assert all(op.category == OperationCategory.TRAVERSE for op in traverse_ops)

    derive_ops = get_operations_by_category(OperationCategory.DERIVE)
    assert len(derive_ops) >= 3
    assert all(op.category == OperationCategory.DERIVE for op in derive_ops)

    constraint_ops = get_operations_by_category(OperationCategory.CONSTRAINT)
    assert len(constraint_ops) >= 4

    boolean_ops = get_operations_by_category(OperationCategory.BOOLEAN)
    assert len(boolean_ops) >= 4


def test_get_supported_operations():
    """get_supported_operations returns only supported ops."""
    supported = get_supported_operations()
    assert "LineStep" in supported
    assert "Close" in supported
    # Ensure unsupported ops are not included
    assert "Buffer" not in supported
    assert "CurveStep" not in supported


def test_get_unsupported_operations():
    """get_unsupported_operations returns only unsupported ops."""
    unsupported = get_unsupported_operations()
    assert "Buffer" in unsupported
    assert "CurveStep" in unsupported
    assert "Union" in unsupported
    # Ensure supported ops are not included
    assert "LineStep" not in unsupported
    assert "Close" not in unsupported


def test_line_step_operation_def():
    """LineStep operation has correct structure."""
    op_def = TRAVERSE_LINE_STEP
    assert op_def.name == "LineStep"
    assert op_def.category == OperationCategory.TRAVERSE
    assert op_def.supported is True
    assert op_def.min_operands == 0
    assert op_def.max_operands == 1

    # Check parameters
    required_params = op_def.get_required_parameters()
    assert "bearing" in required_params
    assert "distance" in required_params

    optional_params = op_def.get_optional_parameters()
    assert "bearing_raw" in optional_params
    assert "distance_raw" in optional_params


def test_close_operation_def():
    """Close operation has correct structure."""
    op_def = DERIVE_CLOSE
    assert op_def.name == "Close"
    assert op_def.category == OperationCategory.DERIVE
    assert op_def.supported is True
    assert op_def.min_operands == 1
    assert op_def.max_operands == 1
    assert len(op_def.parameters) == 0  # No parameters needed


def test_buffer_operation_def():
    """Buffer operation has correct structure (unsupported)."""
    op_def = DERIVE_BUFFER
    assert op_def.name == "Buffer"
    assert op_def.category == OperationCategory.DERIVE
    assert op_def.supported is False  # Not yet implemented
    assert op_def.min_operands == 1
    assert op_def.max_operands == 1

    required_params = op_def.get_required_parameters()
    assert "distance" in required_params


def test_operand_count_validation():
    """OperationDef.validate_operand_count works correctly."""
    # LineStep: 0-1 operands
    line_step = get_operation_def("LineStep")
    assert line_step.validate_operand_count(0) is True
    assert line_step.validate_operand_count(1) is True
    assert line_step.validate_operand_count(2) is False

    # Close: exactly 1 operand
    close = get_operation_def("Close")
    assert close.validate_operand_count(0) is False
    assert close.validate_operand_count(1) is True
    assert close.validate_operand_count(2) is False

    # Union: 2+ operands (unlimited)
    union = get_operation_def("Union")
    assert union.validate_operand_count(0) is False
    assert union.validate_operand_count(1) is False
    assert union.validate_operand_count(2) is True
    assert union.validate_operand_count(10) is True


def test_unsupported_operation_wrapper():
    """UnsupportedOperation can store arbitrary operations."""
    unsupported_op = UnsupportedOperation(
        op_name="CustomDeedOperation",
        params={"custom_param": "value", "distance": 100.0},
        operands=["feature_1", "feature_2"],
        reason="Not yet implemented in compiler"
    )

    assert unsupported_op.op_name == "CustomDeedOperation"
    assert unsupported_op.params["custom_param"] == "value"
    assert len(unsupported_op.operands) == 2

    # Convert to OpExpr format
    op_expr_dict = unsupported_op.to_op_expr()
    assert op_expr_dict["op_name"] == "CustomDeedOperation"
    assert op_expr_dict["params"]["custom_param"] == "value"
    assert op_expr_dict["params"]["_unsupported"] is True
    assert op_expr_dict["params"]["_reason"] == "Not yet implemented in compiler"
    assert op_expr_dict["operands"] == ["feature_1", "feature_2"]


def test_parameter_spec_structure():
    """ParameterSpec contains required fields."""
    param = ParameterSpec(
        name="distance",
        param_type="number",
        required=True,
        unit="feet",
        description="Distance parameter"
    )

    assert param.name == "distance"
    assert param.param_type == "number"
    assert param.required is True
    assert param.unit == "feet"
    assert param.description == "Distance parameter"


def test_all_operations_have_valid_categories():
    """All operations in registry have valid categories."""
    for op_name, op_def in OPERATION_REGISTRY.items():
        assert isinstance(op_def.category, OperationCategory)
        assert op_def.category != OperationCategory.UNKNOWN


def test_all_operations_have_descriptions():
    """All operations have non-empty descriptions."""
    for op_name, op_def in OPERATION_REGISTRY.items():
        assert op_def.description, f"{op_name} should have a description"


def test_json_serialization_roundtrip():
    """OperationDef can be serialized to JSON and back."""
    op_def = TRAVERSE_LINE_STEP
    json_dict = op_def.model_dump()

    # Verify key fields are present
    assert json_dict["name"] == "LineStep"
    assert json_dict["category"] == "traverse"
    assert json_dict["supported"] is True
    assert len(json_dict["parameters"]) >= 2

    # Reconstruct from JSON
    reconstructed = OperationDef(**json_dict)
    assert reconstructed.name == op_def.name
    assert reconstructed.category == op_def.category
    assert reconstructed.supported == op_def.supported
    assert len(reconstructed.parameters) == len(op_def.parameters)


def test_boolean_operations_allow_multiple_operands():
    """Boolean operations support 2+ operands."""
    union_def = get_operation_def("Union")
    assert union_def.min_operands == 2
    assert union_def.max_operands is None  # Unlimited

    intersection_def = get_operation_def("Intersection")
    assert intersection_def.min_operands == 2
    assert intersection_def.max_operands is None


def test_constraint_operations_have_correct_operand_counts():
    """Constraint operations have appropriate operand counts."""
    distance_def = get_operation_def("Distance")
    assert distance_def.min_operands == 2
    assert distance_def.max_operands == 2  # Exactly 2 features

    angle_def = get_operation_def("Angle")
    assert angle_def.min_operands == 3
    assert angle_def.max_operands == 3  # Three points define an angle
