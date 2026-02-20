from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.controller.contracts import (
    _node_is_object_schema,
    _normalize_openai_strict_schema,
    next_step_json_schema,
)


def _iter_schema_nodes(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_schema_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_schema_nodes(value)


def test_next_step_json_schema_root_is_object_without_top_level_ref() -> None:
    schema = next_step_json_schema()
    assert "$ref" not in schema
    assert schema.get("type") == "object"
    assert schema.get("additionalProperties") is False


def test_next_step_json_schema_all_object_nodes_are_closed() -> None:
    schema = next_step_json_schema()
    object_nodes = [
        node
        for node in _iter_schema_nodes(schema)
        if isinstance(node, dict) and _node_is_object_schema(node)
    ]
    assert object_nodes, "expected at least one object schema node"
    assert all(node.get("additionalProperties") is False for node in object_nodes)


def test_normalizer_closes_nullable_object_type_lists() -> None:
    schema = {
        "type": "object",
        "properties": {
            "maybe_obj": {
                "type": ["object", "null"],
                "properties": {
                    "x": {"type": "string"},
                },
            }
        },
        "required": [],
    }
    normalized = _normalize_openai_strict_schema(schema)
    maybe_obj = normalized["properties"]["maybe_obj"]
    assert isinstance(maybe_obj, dict)
    assert maybe_obj.get("additionalProperties") is False
