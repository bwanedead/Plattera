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
    batching: dict[str, Any] | None = None


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
            batching={
                "allowed": True,
                "max_calls_per_batch": 3,
                "side_effect_class": "read_only",
                "can_run_parallel": True,
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
                "Returns a new image:derived:* ref and model-visible image evidence for the next turn. "
                "Sub-actions: crop, expand, zoom, annotate, reference_overlay, render_evidence_locators, point_crops, point_crops_adjust, point_crops_view. "
                "point_crops is the ergonomic default for template pin crop packets "
                "(small|medium|large × wide|portrait|square). "
                "Returns one master overlay as immediate image_evidence (outputs.derived_ref_id); "
                "per-point crop refs persist in outputs.crop_set.points / outputs.crop_records. "
                "Use point_crops_adjust on a prior point_crops master overlay ref to revise by letter or alias "
                "(shift_norm, size, shape); creates a new revision — old refs are not mutated. "
                "Use point_crops_view to render a filtered overlay from a prior crop set; overlay view only, no new per-point crops. "
                "Letters A/B/C are visual local labels only; semantic aliases live in metadata. "
                "Use reference_overlay as a coordinate-grid fallback when explicit box_norm bounds are needed before crop/zoom "
                "or when a target is not yet pinned well enough for point_crops. "
                "Use annotate for temporary visual markup, highlighting, bounding boxes, or labels — "
                "this is visual editing, not durable evidence. "
                "Use render_evidence_locators as the DURABLE evidence path: it renders the agent-authored "
                "image_region evidence_locators that live in the work graph and explicitly summarizes "
                "text_span, log_span, code_span, table_cell, json_path, or unsupported locators. "
                "Geometry ergonomics: crop, zoom, and each annotate annotation all accept either pixel "
                "`box` OR normalized `box_norm` (provide one, never both), plus optional adjustment "
                "controls (`adjust_px` or `adjust_norm`) for fine-tuning without recomputing coordinates.  "
                "Pixel `box` and `adjust_px` are integer-only — for fractional or sub-pixel intent, use "
                "`box_norm` + `adjust_norm`.  Annotate `label` annotations require a non-empty `text` "
                "field; `bbox` and `highlight` do not."
            ),
            expected_request_shape=(
                "ref_id: source image ref (image:assoc:* or image:derived:*). "
                "sub_action: one of crop | expand | zoom | annotate | reference_overlay | render_evidence_locators | point_crops | point_crops_adjust | point_crops_view. "
                "params: sub-action-specific parameters object. "
                "GEOMETRY FORMS — two explicit forms are accepted anywhere a box is needed "
                "(crop params, zoom params, each annotate annotation): "
                "(1) box = [x1, y1, x2, y2] — absolute pixel coordinates from the top-left corner. "
                "(2) box_norm = [x1, y1, x2, y2] — normalized coordinates in [0.0, 1.0] relative "
                "to source image dimensions.  Provide ONE form, never both — both is a retryable error. "
                "x1 < x2 and y1 < y2 required.  Example box_norm: [0.0, 0.5, 1.0, 1.0] = bottom half. "
                "ADJUSTMENT CONTROLS — optional fine-tuning that nudges the box before applying it: "
                "  adjust_norm = {expand_x?, expand_y?, shift_x?, shift_y?} when using box_norm "
                "  adjust_px   = {expand_x?, expand_y?, shift_x?, shift_y?} when using box. "
                "Positive expand_x/y grows the box on both sides; negative shrinks. "
                "Positive shift_x moves right, positive shift_y moves down. "
                "Final boxes are clamped to image bounds; if adjustment collapses the box to zero "
                "or negative area, the result is a retryable error with a repair_hint. "
                "RESOLVED GEOMETRY — every transform that applies a box returns outputs.resolved_geometry "
                "(single box ops: crop, zoom-with-box) or outputs.resolved_annotations (annotate) with the "
                "input form, adjustments_applied, source_width_height, and BOTH resolved pixel `box` and "
                "normalized `box_norm`.  Use it to refine the same box on the next turn without recomputing. "
                "REFERENCE_OVERLAY — fallback coordinate grid when explicit box_norm bounds are needed before crop/zoom "
                "or when a target is not yet pinned well enough for point_crops. "
                "Draws a labeled coordinate grid over the image so you can read exact normalized bounds from the "
                "returned image evidence and use them in a subsequent crop or zoom. "
                "params: {cols: int (default 4), rows: int (default 4), "
                "line_color: [R,G,B] (default [200,200,200]), label_color: [R,G,B] (default [255,0,0])}. "
                "Each cell label shows (col,row) and its exact box_norm bounds. "
                "RENDER_EVIDENCE_LOCATORS — params: {locators: evidence_locators[]}. "
                "This is the preferred path for claim-local evidence that should survive in the work graph "
                "and UI/audit timeline; annotate is for transient visual markup only. "
                "Image_region locators whose ref_id matches ref_id are rendered as highlights/boxes; "
                "text_span, log_span, code_span, table_cell, json_path, and unknown kinds are summarized explicitly. "
                "POINT_CROPS — params: {zoom_factor?: number, points: [{alias, point_norm: [x,y], "
                "size: small|medium|large, shape: wide|portrait|square, zoom_factor?: number}, ...], "
                "show?: [pin|box|letter]}. "
                "Default show is [pin, box, letter]. Per-point zoom_factor overrides params.zoom_factor; "
                "when neither is set, default zoom by size (small 3.0, medium 2.25, large 1.5). "
                "Zoom applies to per-point crop refs only; master overlay stays unzoomed. "
                "Master overlay includes a light normalized coordinate grid and a compact template "
                "legend (size colors + wide/portrait cues) for placement review. "
                "When run on derived refs, outputs include root-source projection metadata "
                "(local_* and root_* geometry) when the parent transform chain is composable. "
                "Creates one master overlay (outputs.derived_ref_id; "
                "returned as image_evidence) plus per-point crop refs in outputs.crop_set.points / outputs.crop_records. "
                "Only the master overlay is immediate image_evidence; use individual crop refs for "
                "hydrate_artifact_refs, delegate_subtask.context_refs, and HITL evidence packets. "
                "Aliases are stored in metadata; letters are local A/B/C labels. "
                "POINT_CROPS_ADJUST — ref_id must be a prior point_crops master overlay ref (image:derived:*). "
                "params: {adjust: [{letter|alias, point_norm?, shift_norm?, size?, shape?, zoom_factor?}, ...], "
                "show?: [pin|box|letter]}. "
                "Each adjust row targets exactly one point by letter OR alias and must make a real change. "
                "Prior zoom metadata is preserved unless zoom_factor is changed on the adjust row. "
                "Use numeric shift_norm (e.g. [0.015, 0.0]) — not natural-language movement. "
                "Prior crop-set refs remain valid; adjustment mints a new master overlay and new crop refs. "
                "POINT_CROPS_VIEW — ref_id must be a prior crop-set master overlay ref. "
                "params: {filter?: {letters?: [str], aliases?: [str]}, show?: [pin|box|letter]}. "
                "Renders a filtered overlay view only; does not mint new per-point crop refs. "
                "crop_set.points preserves original crop refs for delegation/hydration."
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
                        "enum": [
                            "crop",
                            "expand",
                            "zoom",
                            "annotate",
                            "reference_overlay",
                            "render_evidence_locators",
                            "point_crops",
                            "point_crops_adjust",
                            "point_crops_view",
                        ],
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "crop: {box: [x1,y1,x2,y2]} (pixel) OR {box_norm: [x1,y1,x2,y2]} (0..1); "
                            "optional adjust_px / adjust_norm = {expand_x?, expand_y?, shift_x?, shift_y?}. "
                            "expand: {padding: [top,right,bottom,left], fill: 'white'}. "
                            "zoom: {box: [x1,y1,x2,y2]} or {box_norm: [x1,y1,x2,y2]} or {factor: 2.0}; "
                            "optional adjust_px / adjust_norm; box/box_norm may combine with factor "
                            "(crop region, then scale by factor). "
                            "annotate: {annotations: [{type: highlight|bbox|label, "
                            "box: [x1,y1,x2,y2] OR box_norm: [x1,y1,x2,y2], "
                            "color: [R,G,B], "
                            "text: str (REQUIRED when type='label', non-empty; ignored for bbox/highlight), "
                            "adjust_px?: {...}, adjust_norm?: {...}}]}. "
                            "reference_overlay: {cols: int, rows: int, line_color: [R,G,B], label_color: [R,G,B]}. "
                            "render_evidence_locators: {locators: evidence_locators[]} — the durable evidence path. "
                            "point_crops: {zoom_factor?: number, points: [{alias: str, point_norm: [x,y], "
                            "size: small|medium|large, shape: wide|portrait|square, zoom_factor?: number}], "
                            "show?: [pin|box|letter]} — template crop packets; "
                            "master overlay only in image_evidence; per-point crops are zoomed for legibility. "
                            "point_crops_adjust: {adjust: [{letter|alias, point_norm?, shift_norm?, size?, shape?, "
                            "zoom_factor?}], show?: [pin|box|letter]} — adjust an existing crop set via prior master overlay ref_id. "
                            "point_crops_view: {filter?: {letters?, aliases?}, show?: [pin|box|letter]} — filtered overlay view."
                        ),
                    },
                },
                "additionalProperties": False,
            },
            example_request={
                "ref_id": "image:assoc:tx-1:original",
                "sub_action": "point_crops",
                "params": {
                    "points": [
                        {
                            "alias": "parcel_1_tie_bearing",
                            "point_norm": [0.42, 0.58],
                            "size": "medium",
                            "shape": "wide",
                        }
                    ],
                    "show": ["pin", "box", "letter"],
                },
            },
            batching={
                "allowed": True,
                "max_calls_per_batch": 4,
                "side_effect_class": "derived_artifact",
                "can_run_parallel": True,
                "conflict_key": "source_ref_id",
            },
            expected_result_shape=(
                "outputs.derived_ref_id: new image:derived:* ref for later reuse or HITL payloads. "
                "outputs.parent_ref_id, sub_action, basename, width_height. "
                "For crop / zoom-with-box: outputs.resolved_geometry = {box: [px], box_norm: [0..1], "
                "source_width_height: [w,h], input: {original form provided}, adjustments_applied?: {...}}. "
                "Use this to refine the same region on the next turn without recomputing coordinates. "
                "For annotate: outputs.resolved_annotations = [{index, type, resolved_geometry: {...}}, ...] "
                "preserving per-annotation lineage. "
                "For zoom factor-only (no box): outputs.factor_applied. "
                "For render_evidence_locators, outputs.rendered_evidence_refs links source_ref to "
                "rendered_ref and reports locator_count/rendered_locator_count/summary_only_locator_count/"
                "unsupported_locator_count; outputs.rendered_locators, outputs.summary_only_locators, "
                "and outputs.unsupported_locators preserve per-locator lineage. "
                "For point_crops: outputs.derived_ref_id is the master overlay ref; image_evidence contains "
                "ONLY that master overlay (not every crop). Master overlay includes a light coordinate grid "
                "and template size/shape legend for point_norm/shift_norm review. "
                "outputs.crop_set and outputs.crop_records map "
                "letters/aliases/colors/geometry to individual crop refs in artifact_refs. "
                "Per-point crop refs are zoomed for legibility; geometry fields (point_norm, box_px, box_norm) "
                "remain local to the input ref. When projection_available is true, root_point_norm/root_box_norm "
                "map nested points back to the original source; false means the parent chain was not composable. "
                "Each crop point records zoom_factor, unzoomed_width_height, "
                "output_width_height, and zoom_cap_applied when relevant. "
                "Per-crop parent_ref_id is the immediate input/local source ref; root_source_ref/root_* "
                "fields map back to the original source when projection is available; "
                "crop_set_overlay_ref links back to the master. "
                "For point_crops_adjust: same result shape as point_crops plus outputs.previous_crop_set_overlay_ref, "
                "outputs.adjustment_source_ref, and outputs.adjustments_applied with prior/new point_norm/size/shape "
                "and prior/new zoom_factor when changed per adjusted target. Old master/crop refs are not mutated. "
                "For point_crops_view: outputs.derived_ref_id is a filtered overlay ref; artifact_refs contains only "
                "that overlay; crop_set.points preserves original crop refs for delegation/hydration. "
                "Filtered overlay views use the same grid/legend master rendering as point_crops. "
                "Copy crop_ref values from crop_set.points or point_crop_set_summary.delegation_lines into "
                "delegate_subtask context_refs when delegating per-crop observations. "
                "image_evidence: model-visible generated image for the next choose_action turn; "
                "a separate hydrate_artifact_refs call is not required just to inspect the new crop/overlay. "
                "On retryable param error: outputs.error.code = invalid_transform_params, "
                "outputs.error.repair_hint contains the corrected shape to use."
            ),
        ),
        SemanticToolSpec(
            tool_id="save_workspace_artifact",
            category="write",
            purpose=(
                "Append one agent-authored working draft revision to the transcript-edit workspace. "
                "Does not mutate T0 raw drafts. Use transcript_text XOR draft_payload. "
                "Transcript-edit payload note: the saved artifact is a source-faithful transcript "
                "artifact first and a handoff-metadata carrier second. Follow the domain branch's "
                "saved-artifact contract: `source_transcript_verbatim` is the first output obligation, "
                "it should cover the full visible/available source scope, and any separate downstream lane "
                "must not silently overwrite the source lane. Do not silently mutate the verbatim transcript. "
                "When refreshing a saved artifact and most long text lanes are unchanged, "
                "prefer copy_forward_save_workspace_artifact — name the base artifact, list unchanged "
                "fields to copy exactly, and author only the fields that changed."
            ),
            expected_request_shape=(
                "transcript_text XOR draft_payload: the authored content. "
                "base_revision_ref: optional prior revision ref. "
                "evidence_refs: optional list of refs grounding this revision. "
                "rationale: optional explanation. "
                "For transcript-edit working/output drafts, prefer draft_payload structured with "
                "source_transcript_verbatim plus any needed downstream lane such as "
                "`normalized_or_mapping_transcript`, and supporting metadata "
                "(`issues`, `parcel_metadata`, `hitl_decisions`, `evidence_refs`). "
                "Use the prompt-branch contract for the detailed lane rules."
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
            tool_id="copy_forward_save_workspace_artifact",
            category="write",
            purpose=(
                "Create a new working draft revision by copying named payload fields exactly from "
                "a base artifact revision and setting only the agent-authored fields that changed. "
                "Use this instead of save_workspace_artifact when most long text lanes are unchanged "
                "and only metadata, evidence, or issue fields need updating — it avoids rehydrating "
                "and re-authoring unchanged long payload lanes through prompt context. "
                "Deterministic code copies exact values at the named paths; no semantic inference. "
                "The agent must explicitly name the base ref, all paths to copy, and all paths to author."
            ),
            expected_request_shape=(
                "base_ref: required transcript_edit:working:rev:NNNN ref to copy unchanged fields from. "
                "copy_forward_paths: required non-empty list of dot-notation paths starting with 'payload.' "
                "to copy exactly from the base artifact "
                "(e.g., ['payload.source_transcript_verbatim', 'payload.normalized_or_mapping_transcript']). "
                "set_paths: required dict mapping dot-notation paths starting with 'payload.' to "
                "agent-authored values for the fields that changed "
                "(e.g., {'payload.issues': [...], 'payload.parcel_metadata': {...}}). "
                "Paths in set_paths must not overlap with copy_forward_paths — overlap is rejected. "
                "evidence_refs: optional list of refs grounding this revision. "
                "rationale: optional explanation of what changed."
            ),
            expected_request_json_shape={
                "type": "object",
                "required": ["base_ref", "copy_forward_paths", "set_paths"],
                "properties": {
                    "base_ref": {
                        "type": "string",
                        "description": "Base working revision to copy unchanged fields from (transcript_edit:working:rev:NNNN).",
                    },
                    "copy_forward_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Dot-notation paths to copy exactly from the base artifact payload (must start with 'payload.').",
                    },
                    "set_paths": {
                        "type": "object",
                        "description": "Dot-notation path → agent-authored value for fields that changed (paths must start with 'payload.').",
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
                "base_ref": "transcript_edit:working:rev:0001",
                "copy_forward_paths": [
                    "payload.source_transcript_verbatim",
                    "payload.normalized_or_mapping_transcript",
                ],
                "set_paths": {
                    "payload.issues": [{"id": "issue-1", "description": "Bearing N 4° 00' W verified."}],
                    "payload.parcel_metadata": {"parcel_count": 1},
                    "payload.evidence_refs": ["image:derived:tx:crop_001"],
                },
                "rationale": "Updated issues and evidence after zoom verification; verbatim text unchanged.",
            },
            expected_result_shape=(
                "Same shape as save_workspace_artifact: "
                "artifact_refs include new working revision ref + aggregate working ref. "
                "outputs carry revision metadata, hash/size. "
                "On error: refusal with reason_code and outputs.error; "
                "missing_copy_paths error lists which paths were absent in the base artifact; "
                "overlapping_paths error lists which paths appeared in both copy and set lists."
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
