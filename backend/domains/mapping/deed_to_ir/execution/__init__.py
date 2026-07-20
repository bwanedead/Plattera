"""Deed-to-IR execution declarations and result-view surface."""

from .result_views import (
    SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    SCHEMA_FINALIZE_CURRENT_OUTPUT,
    SCHEMA_HYDRATE_ARTIFACT_REFS,
    SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
    SCHEMA_PATCH_IR_DRAFT,
    SCHEMA_SAVE_IR_ARTIFACT,
    SCHEMA_SUBMIT_IR_FOR_MAPPING,
    attach_deed_to_ir_result_view,
    wrap_handler_with_result_view,
)
from .result_view_common import build_working_head_continuity_key
from .tool_specs import SemanticToolSpec, build_deed_to_ir_tool_specs

__all__ = [
    "SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES",
    "SCHEMA_FINALIZE_CURRENT_OUTPUT",
    "SCHEMA_HYDRATE_ARTIFACT_REFS",
    "SCHEMA_HYDRATE_DEED_TO_IR_INPUT",
    "SCHEMA_PATCH_IR_DRAFT",
    "SCHEMA_SAVE_IR_ARTIFACT",
    "SCHEMA_SUBMIT_IR_FOR_MAPPING",
    "SemanticToolSpec",
    "attach_deed_to_ir_result_view",
    "build_deed_to_ir_tool_specs",
    "build_working_head_continuity_key",
    "wrap_handler_with_result_view",
]
