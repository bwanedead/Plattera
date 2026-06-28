"""Procedural guidance for deed-to-IR foundation tools."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID

DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/procedural_guidance.py"
)
DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION = "v13"

DEED_TO_IR_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to orient deed-to-IR work. This is **guidance**, not a hard script.

## Startup orientation
- Read `inherited_handoff_conditions` first — it is the high-salience mechanical copy of upstream parcel metadata, issues, HITL decisions, evidence refs, and transcript lane excerpts.
- Treat inherited resolution rows as **input/provenance**, not as local work inventory to recreate.
- Pin the operand suite via `operand_suite_ref` (startup handoff) — cite that ref in local state instead of recopying every evidence detail.
- Use `mapping_operands` or hydrate `operand_suite_ref` for compact upstream determined values and scope blockers before rereading nested resolution-state rows.

## Draft IR lifecycle
- Before authoring or repairing supported operation nodes, use the FeatureGraph authoring guide as the layer map: deed meaning, node kind, compiler operation, params, operands, and rendered geometry are distinct.
- `graph_id` is the **stable logical graph id** — do not embed draft version numbers in `graph_id` (avoid `right_of_way_v1` as graph_id).
- To continue a working draft, pass `base_draft_ref` from the prior save; the tool allocates versioned artifact refs (`feature_graph:ir:right_of_way_v0`, `..._v1`, ...).
- `save_ir_artifact` saves a **draft checkpoint** (`draft_version` such as v0, v1, v2) — not final publication.
- Use `patch_ir_draft` for surgical repair when `draft_repair_items` are directly actionable and operands are already available; use full `save_ir_artifact` for first draft or major rewrite.
- After initial handoff/capability hydration, prefer saving a first bounded draft IR over rereading upstream lanes.
- Keep `operand_suite_ref`, the current draft ref, and repair feedback active while drafting.
- Use `outputs.working_draft_ref` (alias of `draft_ir_ref` / `ir_artifact_ref`) for `@this.result.working_draft_ref` hydrate-next on the same turn batch.
- Compile/judge feedback on draft save is expected mechanical feedback — use `current_draft_ir.draft_repair_items` and node-precise `compile_gaps` to repair the **same graph_id** and save v2; do not reread operation contracts unless a new primitive is genuinely needed.
- `placeholder_only_graph`, `renderable_feature_count`, and `mapping_submission_ready_candidate` distinguish schema-valid scaffolds from map-useful IR.
- `mechanically_mappable_candidate` means only that no blocking mechanical compile/judge gaps were detected; it is **not** deed-correctness, closure truth, or submission readiness by itself.
- Do not treat `unknown` nodes with deed prose parked in `graph.metadata` as sufficient map IR.
- `submit_ir_for_mapping` is the deliberate mapping attempt once structural readiness is honest enough for inspection.
- `publish_deed_to_ir_output` is final scoped handoff only.

## Mapping review and hydration discipline
- After `submit_ir_for_mapping`, inspect `outputs.mapping_review` first.
- Prefer `outputs.mapping_review.recommended_review_refs` over `@this.result.artifact_refs[]` for ordinary mapping review — do not bulk-hydrate every returned ref by habit.
- Hydrate specific refs only when needed: control render for visual map review, geometry ref for feature/coordinate inspection, mapping ref for compact lineage and counts.
- When publishing, set `mapping_artifact_ref` and `expected_ir_artifact_ref` from `outputs.mapping_review.recommended_publish_refs` (or the same fields on a hydrated mapping row).
- If any `patch_ir_draft` occurs after mapping, resubmit the patched draft for mapping before publishing — stale mapping lineage is refused retryably when `expected_ir_artifact_ref` does not match.
- Pin `operand_suite_ref` early when useful; once a valid IR draft exists and needed operands are encoded in draft/provenance, unpin the operand suite unless actively editing operand-derived geometry. Do not keep large reference lanes pinned out of habit.

## Supported deed-to-IR authoring pattern
- **ReferenceFrame** — survey/frame context such as PLSS, local stationing, plat grid, or other external coordinate basis (non-rendered descriptor; not invented ops like `public_land_survey_frame`).
- **TiedPoint** — local anchor / beginning point.
- **CourseTraverse** — canonical ordered deed call sequence (not invented `deed_call_sequence` ops).
- **Close** — region from a traverse; when calls are "more or less" and endpoints nearly meet, author explicit `closure_mode: snap_to_start` and `closure_tolerance` (feet) — deterministic code does not choose this policy.
- **annotation** — blocked/incomplete scopes without fake geometry.
- Unsupported invented ops may preserve meaning in prose but are **not mapping-ready** for a scope you intend to map.

## Work inventory means downstream deed-to-IR responsibilities
- Inventory **deed-to-IR responsibilities**, not transcript-edit atoms or covered units.
- Do **not** copy inherited covered units into local covered units just to look complete.
- Local work items should track downstream obligations such as:
  - author Parcel 1 IR (cite `operand_suite_ref` / `parcel_1_traverse_operands` state — do not recopy every operand row)
  - represent Parcel 2 as blocked/partial scope
  - encode governing range decision in IR/provenance
  - submit IR for mapping
  - inspect map/compile/judge artifacts
  - repair IR when mapping exposes a real defect
  - publish final output
- Inherited upstream values are **starting inputs**, not blind truth. If mapping/compile/judge exposes a real defect, self-heal by correcting IR and provenance — do not silently trust transcript-edit when earned evidence contradicts it.

## Foundation workflow (bound)
- Bound tool contracts live in tool specs — treat those as authoritative; this guidance does not duplicate exact tool IDs or request shapes.
- Typical flow: hydrate `mapping_operands` and feature-graph capabilities; save a draft early; repair placeholder-only drafts into real op/geometry/feature-ref structure with provenance; submit saved IR for mapping when `mapping_submission_ready_candidate` is true enough for inspection; inspect returned mapping, compile, judge, and sidecar artifacts through bounded listing and hydration.
- Attach exact upstream links through `ProvenanceAttachment.source_entity_links` on graph entities — not only graph metadata.
- Do not guess schema, operation parameters, units, operand shapes, support status, or provenance contracts. Hydrate capability details in the same orientation batch before the first non-trivial IR save when details are not already in context.

## What not to do
- Do not rebuild transcript-edit's resolution graph as local deed-to-IR inventory.
- Do not parse deed text into IR in bulk prose without durable IR artifacts.
- Do not treat startup handoff or resolution summary as closure or earned geometry truth.
- Do not expect deterministic code to infer atom-to-feature associations or source-entity links.
"""


def build_deed_to_ir_procedural_guidance_blocks() -> tuple[PromptBlock, ...]:
    return (
        PromptBlock(
            block_id="deed_to_ir_procedural_guidance",
            layer="domain_guidance",
            owner=DEED_TO_IR_DOMAIN_ID,
            source_path=DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF,
            version=DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION,
            text=DEED_TO_IR_PROCEDURAL_GUIDANCE_TEXT,
        ),
    )
