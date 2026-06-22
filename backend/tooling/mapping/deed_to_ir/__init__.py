"""Deed-to-IR tooling (transcript handoff, input hydration, IR persistence)."""

from .artifact_hydration import (
    hydrate_artifact_refs,
    hydrate_feature_graph_artifact_refs,
    list_feature_graph_artifacts,
    make_hydrate_artifact_refs_handler,
)
from .feature_graph_capabilities import describe_feature_graph_capabilities
from .input_hydration import make_hydrate_deed_to_ir_input_handler
from .ir_mapping_submission import submit_ir_for_mapping
from .output_persistence import publish_deed_to_ir_output
from .ir_persistence import IR_REF_PREFIX, save_ir_artifact
from .resolution_state_projection import (
    mechanical_resolution_state_snapshot,
    resolution_state_counts,
    resolution_state_startup_summary,
)
from .startup_handoff import build_deed_to_ir_startup_handoff, startup_handoff_from_loader_dict
from .transcript_handoff_loading import (
    LOADED_SOURCE_LABEL,
    TranscriptHandoffLoadError,
    load_transcript_edit_output_handoff,
)

__all__ = [
    "IR_REF_PREFIX",
    "LOADED_SOURCE_LABEL",
    "TranscriptHandoffLoadError",
    "build_deed_to_ir_startup_handoff",
    "describe_feature_graph_capabilities",
    "hydrate_artifact_refs",
    "hydrate_feature_graph_artifact_refs",
    "list_feature_graph_artifacts",
    "load_transcript_edit_output_handoff",
    "make_hydrate_artifact_refs_handler",
    "make_hydrate_deed_to_ir_input_handler",
    "mechanical_resolution_state_snapshot",
    "publish_deed_to_ir_output",
    "resolution_state_counts",
    "resolution_state_startup_summary",
    "save_ir_artifact",
    "submit_ir_for_mapping",
    "startup_handoff_from_loader_dict",
]
