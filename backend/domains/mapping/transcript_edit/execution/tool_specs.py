"""Executable shared-capability tool specs for transcript-edit.

Only tools with bound handlers appear here. Fake/spec-only/LLM-reasoning tools
are excluded — the LLM owns comparison, reconciliation, and semantic verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticToolSpec:
    tool_id: str
    category: str
    purpose: str
    expected_request_shape: str
    expected_request_json_shape: dict[str, Any]
    expected_result_shape: str
    example_request: dict[str, Any]


def build_transcript_edit_tool_specs() -> tuple[SemanticToolSpec, ...]:
    return (
        SemanticToolSpec(
            tool_id="hydrate_artifact_refs",
            category="read",
            purpose=(
                "Load full content for one or more artifact refs. "
                "Supports T0 draft refs (t0:raw:*), transcript-edit workspace refs "
                "(transcript_edit:working, transcript_edit:output, transcript_edit:working:rev:NNNN), "
                "source image refs (image:assoc:*:original), and derived image refs (image:derived:*). "
                "Startup exposes only the original captured source image as the canonical source-image ref. "
                "Comparison and reconciliation are the LLM's job after hydration."
            ),
            expected_request_shape=(
                "ref_ids: required non-empty array of ref_id strings. "
                "max_refs: optional integer cap (default 8, max 32)."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["ref_ids"],
                "properties": {
                    "ref_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Ref IDs to hydrate (t0:raw:*, transcript_edit:*, image:assoc:*, image:derived:*).",
                    },
                    "max_refs": {
                        "type": ["integer", "null"],
                        "description": "Optional cap on refs hydrated (default 8, max 32).",
                    },
                },
                "additionalProperties": False,
            },
            example_request={
                "ref_ids": ["t0:raw:gpt4o_pass1", "image:assoc:tx-1:original"],
                "max_refs": 4,
            },
            expected_result_shape=(
                "outputs.results: list of {ref_id, kind, ...kind-specific fields}. "
                "outputs.errors: list of per-ref or batch errors. "
                "outputs.cap_exceeded: bool. "
                "outputs.hydrated_count: int. "
                "Kind-specific fields: "
                "t0:raw:* → {text, metadata}. "
                "transcript_edit:* → {payload, path}. "
                "image:assoc:*:original → raw captured source image; "
                "returns {absolute_path, exists, size_bytes, width_height, basename, role} "
                "— image content is also returned as model-visible evidence (not in outputs). "
                "image:derived:* → {absolute_path, parent_ref_id, sub_action, params, basename, width_height} "
                "— derived image content also returned as model-visible evidence."
            ),
        ),
        SemanticToolSpec(
            tool_id="transform_artifact",
            category="image_transform",
            purpose=(
                "Apply a spatial or annotation transform to a source or derived image ref. "
                "Returns a new image:derived:* ref that can be hydrated on later turns. "
                "Sub-actions: crop, expand, zoom, annotate, reference_overlay. "
                "Use annotate to highlight, draw bounding boxes, or add labels. "
                "Use reference_overlay to obtain a grid-labeled version of the image so you can "
                "identify precise subregions and then supply explicit box or box_norm coordinates "
                "to a subsequent crop."
            ),
            expected_request_shape=(
                "ref_id: source image ref (image:assoc:* or image:derived:*). "
                "sub_action: one of crop | expand | zoom | annotate | reference_overlay. "
                "params: sub-action-specific parameters object. "
                "CROP GEOMETRY — two explicit forms accepted: "
                "(1) params.box = [x1, y1, x2, y2] — absolute pixel coordinates from the top-left corner. "
                "(2) params.box_norm = [x1, y1, x2, y2] — normalized coordinates in [0.0, 1.0] relative "
                "to source image dimensions (x1/x2 scale to width, y1/y2 scale to height). "
                "x1 < x2 and y1 < y2 required. "
                "Example box_norm values: [0.0, 0.5, 1.0, 1.0] = bottom half; "
                "[0.5, 0.0, 1.0, 0.5] = top-right quadrant. "
                "Vague region descriptions are NOT accepted — you must supply explicit geometry. "
                "REFERENCE_OVERLAY — draws a labeled coordinate grid over the image so you can read "
                "exact normalized bounds for any cell and use them in a subsequent crop. "
                "params: {cols: int (default 4), rows: int (default 4), "
                "line_color: [R,G,B] (default [200,200,200]), label_color: [R,G,B] (default [255,0,0])}. "
                "Each cell label shows (col,row) and its exact box_norm bounds. "
                "Typical workflow: reference_overlay → hydrate to see the grid → crop with explicit box_norm."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["ref_id", "sub_action", "params"],
                "properties": {
                    "ref_id": {
                        "type": "string",
                        "description": "Source image ref to transform.",
                    },
                    "sub_action": {
                        "type": "string",
                        "enum": ["crop", "expand", "zoom", "annotate", "reference_overlay"],
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "crop: {box: [x1,y1,x2,y2]} (pixel) OR {box_norm: [x1,y1,x2,y2]} (normalized 0..1). "
                            "expand: {padding: [top,right,bottom,left], fill: 'white'}. "
                            "zoom: {box: [x1,y1,x2,y2]} or {factor: 2.0}. "
                            "annotate: {annotations: [{type: highlight|bbox|label, box: [x1,y1,x2,y2], "
                            "color: [R,G,B], text: str}]}. "
                            "reference_overlay: {cols: int, rows: int, line_color: [R,G,B], label_color: [R,G,B]}."
                        ),
                    },
                },
                "additionalProperties": False,
            },
            example_request={
                "ref_id": "image:assoc:tx-1:original",
                "sub_action": "reference_overlay",
                "params": {"cols": 4, "rows": 6},
            },
            expected_result_shape=(
                "outputs.derived_ref_id: new image:derived:* ref for use in hydrate_artifact_refs or HITL payloads. "
                "outputs.parent_ref_id, sub_action, basename, width_height. "
                "On retryable param error: outputs.error.code = invalid_transform_params, "
                "outputs.error.repair_hint contains the corrected shape to use."
            ),
        ),
        SemanticToolSpec(
            tool_id="save_workspace_artifact",
            category="write",
            purpose=(
                "Append one agent-authored working draft revision to the transcript-edit workspace. "
                "Does not mutate T0 raw drafts. Use transcript_text XOR draft_payload."
            ),
            expected_request_shape=(
                "transcript_text XOR draft_payload: the authored content. "
                "base_revision_ref: optional prior revision ref. "
                "evidence_refs: optional list of refs grounding this revision. "
                "rationale: optional explanation."
            ),
            expected_request_json_shape={
                "type": "object",
                "properties": {
                    "transcript_text": {
                        "type": ["string", "null"],
                        "description": "Full transcript text (plain text).",
                    },
                    "draft_payload": {
                        "type": ["object", "null"],
                        "description": "Structured draft payload (XOR with transcript_text).",
                    },
                    "base_revision_ref": {
                        "type": ["string", "null"],
                        "description": "transcript_edit:working:rev:NNNN ref this revision is based on.",
                    },
                    "evidence_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Refs grounding this revision (image:*, t0:raw:*, image:derived:*).",
                    },
                    "rationale": {
                        "type": ["string", "null"],
                        "description": "Brief explanation of what changed and why.",
                    },
                },
                "additionalProperties": False,
            },
            example_request={
                "transcript_text": "Section 1: beginning at the NW corner...",
                "base_revision_ref": "transcript_edit:working:rev:0001",
                "rationale": "Corrected section 2 per image:assoc:tx-1:original.",
            },
            expected_result_shape=(
                "artifact_refs include working revision ref + aggregate working ref for harness latest_refs. "
                "outputs carry revision metadata, hash/size."
            ),
        ),
        SemanticToolSpec(
            tool_id="publish_workspace_artifact",
            category="write",
            purpose=(
                "Publish a chosen working revision to the transcript-edit output. "
                "Agent must pass an explicit source_revision_ref — no deterministic pick."
            ),
            expected_request_shape="source_revision_ref: required transcript_edit:working:rev:NNNN ref.",
            expected_request_json_shape={
                "type": "object",
                "required": ["source_revision_ref"],
                "properties": {
                    "source_revision_ref": {
                        "type": "string",
                        "description": "The working revision to publish (transcript_edit:working:rev:NNNN).",
                    },
                },
                "additionalProperties": False,
            },
            example_request={"source_revision_ref": "transcript_edit:working:rev:0003"},
            expected_result_shape=(
                "artifact_refs include output ref + source revision ref for harness latest_refs. "
                "outputs carry published_at and paths."
            ),
        ),
    )
