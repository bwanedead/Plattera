"""Surgical CourseTraverse course-row updates for patch_ir_draft (mechanical only)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SUPPORTED_COURSE_UPDATE_FIELDS = frozenset(
    {"distance", "bearing", "distance_raw", "bearing_raw"}
)
_NUMERIC_FIELDS = frozenset({"distance", "bearing"})
_RAW_FIELDS = frozenset({"distance_raw", "bearing_raw"})


def apply_course_updates(
    graph: dict[str, Any],
    course_updates: Sequence[Mapping[str, Any]] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Apply surgical course row updates.

    Returns ``(patched_graph, None)`` on success, or ``(None, refusal)`` on retryable failure.
    """
    if not course_updates:
        return graph, None

    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return None, _course_update_refusal(
            reason_code="course_update_node_missing",
            message="Base draft graph has no nodes list for course_updates.",
        )

    nodes_by_id: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        if node_id not in nodes_by_id:
            node_order.append(node_id)
        nodes_by_id[node_id] = dict(node)

    for update in course_updates:
        if not isinstance(update, Mapping):
            continue
        refusal = _apply_one_course_update(nodes_by_id, update)
        if refusal is not None:
            return None, refusal

    patched = dict(graph)
    patched["nodes"] = [nodes_by_id[node_id] for node_id in node_order if node_id in nodes_by_id]
    return patched, None


def _apply_one_course_update(
    nodes_by_id: dict[str, dict[str, Any]],
    update: Mapping[str, Any],
) -> dict[str, Any] | None:
    node_id = str(update.get("node_id") or "").strip()
    if not node_id:
        return _course_update_refusal(
            reason_code="course_update_node_missing",
            message="course_updates entry is missing node_id.",
        )
    node = nodes_by_id.get(node_id)
    if node is None:
        return _course_update_refusal(
            reason_code="course_update_node_missing",
            message=f"No node with id {node_id!r} for course_updates.",
            details={"node_id": node_id},
        )

    op_expr = node.get("op_expr")
    if not isinstance(op_expr, Mapping):
        return _course_update_refusal(
            reason_code="course_update_not_course_traverse",
            message=f"Node {node_id!r} has no op_expr; CourseTraverse required.",
            details={"node_id": node_id},
        )
    op_name = str(op_expr.get("op_name") or "").strip()
    if op_name != "CourseTraverse":
        return _course_update_refusal(
            reason_code="course_update_not_course_traverse",
            message=f"Node {node_id!r} op_name={op_name!r} is not CourseTraverse.",
            details={"node_id": node_id, "op_name": op_name},
        )

    field = str(update.get("field") or "").strip()
    if field not in SUPPORTED_COURSE_UPDATE_FIELDS:
        return _course_update_refusal(
            reason_code="course_update_field_invalid",
            message=(
                f"Unsupported course_updates field {field!r}. "
                f"Supported: {sorted(SUPPORTED_COURSE_UPDATE_FIELDS)}."
            ),
            details={"field": field, "node_id": node_id},
        )

    course_index = _parse_course_index(update.get("course_index"))
    if course_index is None:
        return _course_update_refusal(
            reason_code="course_update_index_out_of_range",
            message="course_index must be a positive 1-based integer.",
            details={"node_id": node_id, "course_index": update.get("course_index")},
        )

    params = op_expr.get("params")
    if not isinstance(params, Mapping):
        params = {}
    courses = params.get("courses")
    if not isinstance(courses, list) or not courses:
        return _course_update_refusal(
            reason_code="course_update_index_out_of_range",
            message=f"Node {node_id!r} has no courses for course_updates.",
            details={"node_id": node_id, "course_index": course_index, "course_count": 0},
        )
    if course_index < 1 or course_index > len(courses):
        return _course_update_refusal(
            reason_code="course_update_index_out_of_range",
            message=(
                f"course_index {course_index} out of range for node {node_id!r} "
                f"(course_count={len(courses)})."
            ),
            details={
                "node_id": node_id,
                "course_index": course_index,
                "course_count": len(courses),
            },
        )

    value, value_error = _coerce_course_field_value(field=field, value=update.get("value"))
    if value_error is not None:
        return value_error

    array_index = course_index - 1
    existing = courses[array_index]
    if not isinstance(existing, Mapping):
        existing = {}
    updated_course = dict(existing)
    updated_course[field] = value

    new_courses = list(courses)
    new_courses[array_index] = updated_course
    new_params = dict(params)
    new_params["courses"] = new_courses
    new_op_expr = dict(op_expr)
    new_op_expr["params"] = new_params
    new_node = dict(node)
    new_node["op_expr"] = new_op_expr
    nodes_by_id[node_id] = new_node
    return None


def _parse_course_index(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, float) and raw.is_integer():
        value = int(raw)
        return value if value >= 1 else None
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        return value if value >= 1 else None
    return None


def _coerce_course_field_value(*, field: str, value: Any) -> tuple[Any, dict[str, Any] | None]:
    if field in _NUMERIC_FIELDS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, _course_update_refusal(
                reason_code="course_update_value_invalid",
                message=f"course_updates field {field!r} requires a numeric value.",
                details={"field": field, "value": value},
            )
        return float(value), None
    if field in _RAW_FIELDS:
        if not isinstance(value, str) or not value.strip():
            return None, _course_update_refusal(
                reason_code="course_update_value_invalid",
                message=f"course_updates field {field!r} requires a non-blank string.",
                details={"field": field, "value": value},
            )
        return value.strip(), None
    return None, _course_update_refusal(
        reason_code="course_update_field_invalid",
        message=f"Unsupported course_updates field {field!r}.",
        details={"field": field},
    )


def _course_update_refusal(
    *,
    reason_code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    outputs: dict[str, Any] = {
        "message": message,
        "error": {"code": reason_code, "message": message},
        "ir_artifact_ref": None,
        "draft_ir_ref": None,
        "working_draft_ref": None,
        "draft_version": None,
        "draft_sequence_index": None,
        "is_draft": None,
        "graph_id": None,
        "validation_errors": [],
    }
    if details:
        outputs["course_update_details"] = dict(details)
    return {
        "executed": False,
        "reason_codes": [reason_code],
        "refusal": {
            "reason_code": reason_code,
            "retryable": True,
            "blocked_by_budget": False,
            "blocked_by_invariant": False,
            "missing_inputs": [],
        },
        "outputs": outputs,
    }
