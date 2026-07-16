"""Procedural guidance for deed-to-IR foundation tools."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID

DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/procedural_guidance.py"
)
DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION = "v34"

DEED_TO_IR_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to orient deed-to-IR work. This is **guidance**, not a hard script.

## Startup orientation
- Read `inherited_handoff_conditions` first — it is the high-salience mechanical copy of upstream parcel metadata, issues, HITL decisions, evidence refs, and transcript lane excerpts.
- Treat inherited resolution rows as **input/provenance**, not as local work inventory to recreate.
- Treat the operand suite as a **core deed-to-IR anchor**. It is acceptable for `operand_suite_ref` / `mapping_operands` to remain available across the run. Do not spend turns managing pin lifecycle unless the suite is clearly stale or harmful.
- Use `hydrate_deed_to_ir_input` section `mapping_operands` or hydrate `operand_suite_ref` via `hydrate_artifact_refs` for compact upstream determined values and scope blockers before rereading nested resolution-state rows.
- If a `mapping_operands`-only hydration defers `inherited_handoff_conditions`, that is intentional operand-lane protection, not missing context. Do not spend a turn rehydrating inherited handoff just because the operand-focused packet kept it out of the way.

## Draft-first orientation
- After startup orientation, hydrate the operand suite and the minimal feature-graph authoring contract (`starter_contract.first_draft_authoring_card`). Once those are visible, **draft the IR**. Do not keep rereading upstream lanes or repeat focused capability reads just to gain more confidence.
- If you have already hydrated the operand suite and the same focused operation contract, do not reread them again just to feel safer. Save the draft and use compile/judge/mapping feedback. Reread the contract only when a new primitive, unknown parameter, or concrete validation error requires it.
- A saved draft is the working checkpoint; compile/judge feedback and mapping review are the right way to discover concrete defects.
- If the first draft may be imperfect, save a bounded supported draft anyway rather than spinning in pre-draft reading. Repair from draft feedback.
- A compile-clean graph with zero `source_entity_links` is not a good first draft. It may be mechanically mappable, but it is weak deed-to-IR work. For every node or edge derived from upstream deed meaning, attach exact `source_entity_links` when the operand suite or inherited handoff provides a source entity id.
- `source_entity_links` belong on graph entities, not only graph metadata. Use upstream `operand_id` / resolution item ids as `entity_id`; set `entity_type` to the available upstream entity type (`resolution_unit`, `resolution_item`, or equivalent); set `source_ref` to the inherited resolution state ref when applicable.
- The first draft does not need perfect provenance, but zero provenance links should be treated as a repair signal before finalization — use `draft_quality_flags` and counts, not guesswork.

## Draft IR lifecycle
- Before authoring or repairing supported operation nodes, use the FeatureGraph authoring guide as the layer map: deed meaning, node kind, compiler operation, params, operands, and rendered geometry are distinct.
- `graph_id` is the **stable logical graph id** — do not embed draft version numbers in `graph_id` (avoid `right_of_way_v1` as graph_id).
- To continue a working draft, pass `base_draft_ref` from the prior save; the tool allocates versioned artifact refs (`feature_graph:ir:right_of_way_v0`, `..._v1`, ...).
- `save_ir_artifact` saves a **draft checkpoint** (`draft_version` such as v0, v1, v2) — not final publication.
- Use `patch_ir_draft` for surgical repair when `draft_repair_items` are directly actionable and operands are already available; use full `save_ir_artifact` for first draft or major rewrite. For CourseTraverse row field fixes, see Mapping sanity repair.
- Keep the current draft ref and repair feedback active while drafting; keep operand values visible via `mapping_operands` / `operand_suite_ref` as needed.
- Use `outputs.working_draft_ref` (alias of `draft_ir_ref` / `ir_artifact_ref`) for `@this.result.working_draft_ref` hydrate-next on the same turn batch.
- Compile/judge feedback on draft save is expected mechanical feedback — use `current_draft_ir.draft_repair_items`, `draft_quality_flags`, and node-precise `compile_gaps` to repair the **same graph_id** and save the next draft version; do not reread operation contracts unless a new primitive is genuinely needed.
- `placeholder_only_graph`, `renderable_feature_count`, and `mapping_submission_ready_candidate` distinguish schema-valid scaffolds from map-useful IR.
- `mechanically_mappable_candidate` means only that no blocking mechanical compile/judge gaps were detected; it is **not** deed-correctness, closure truth, or submission readiness by itself.
- Use `unknown` only when the feature kind itself is unknown. A known blocked, partial, or dependency-pending scope is not unknown; represent it as an `annotation` with source/provenance links and handoff notes. Do not fabricate geometry for blocked scope.
- Do not treat `unknown` nodes with deed prose parked in `graph.metadata` as sufficient map IR.
- `submit_ir_for_mapping` is the deliberate mapping attempt once structural readiness is honest enough for inspection.
- After mapping review is honest enough for scoped handoff, call `finalize_current_deed_to_ir_output` — the finalizer prepares and publishes the durable package internally.

## Canonical finalization
- Preferred endgame: inspect mapping review → repair current IR if necessary → submit the repaired IR for mapping → call `finalize_current_deed_to_ir_output` with only unresolved semantic decision maps → `complete_run`.
- Treat the lineage-bound finalization session from a successful remap as the current finalization candidate. Do not track mapping/IR pairs, preview refs, closure arrays, or strict package rows manually.
- Author only semantic conclusions the active session still needs:
  - scope statuses: `handoffable` or `blocked`;
  - correction dispositions: `confirmed_source_repair`, `ir_only_exception`, or `needs_hitl`;
  - dependency dispositions: `include` or `not_applicable`;
  - rationales only for exceptional cases required by the session (`ir_only_exception`, `not_applicable`).
- When `correction_posture` is active, choose dispositions from evidence: source-confirmed repaired value used by current IR → `confirmed_source_repair`; intentional IR-only difference → `ir_only_exception` plus rationale; unresolved human question → `needs_hitl`. Do not invent strict correction rows — the finalizer expands dispositions mechanically.
- A blocked scope alone is not a dependency disposition. Use dependency dispositions only for explicit external-dependency candidates on the session.
- Exact request grammar and known IDs live on the finalizer tool spec and the active finalization session projection — do not invent IDs or reconstruct package shells.
- If `missing_finalization_decisions` is returned, supply only the reported missing IDs (reuse `prompt_carry_forward` / session projection when present). Previously persisted decisions need not be repeated.
- If correction disposition is `needs_hitl`, wait for human resolution; do not treat that as approval or publication.
- If the session is `preview_ready`, retry the same finalizer with **no decision mutations** — publication retries the stored immutable preview.
- If the result is `published` with `next_required_action=complete_run`, call `complete_run`. Do not hydrate output/preview/IR/mapping just to restate what the finalizer already returned.
- Reopen IR only for a material defect in the current IR/mapping/final handoff — not to polish bookkeeping or restate already accepted decisions.
- Mapping review before finalization remains required. Rendered output is not semantic correctness by itself.
- Never treat mechanical mapping facts (compile/judge counts, renders, lineage_current) as semantic closure.
- Corrections used by final IR must be disclosed via correction dispositions. Blocked scopes and external dependencies must remain explicit. Dependency and correction candidates are evidence, not deterministic conclusions.
- IR patched after mapping must be remapped before finalization. Published output is the durable closeout package.

## Mapping review and hydration discipline
- After `submit_ir_for_mapping`, inspect `outputs.mapping_review` first — mapping review is not just compile/judge pass/fail. Inspect mechanical geometry behavior in `mapping_review.sanity_review` (endpoint displacement, course leg tables, source evidence handles). When present, inspect `mapping_review.correction_posture` for mechanical IR-vs-inherited operand deltas and use the compact finalizer correction dispositions above.
- Prefer `outputs.mapping_review.recommended_review_refs` over `@this.result.artifact_refs[]` for ordinary mapping review — do not bulk-hydrate every returned ref by habit. Copyable `*_ref` fields must be full canonical refs; never use truncated display fragments as refs.
- Large unexplained endpoint displacement is a **source-sanity trigger**, not automatically a deed defect. Do not declare an open traverse limitation until you consider whether the deed description expected closure or a boundary return.
- If one course leg looks suspicious, hydrate targeted source evidence for that leg (from `sanity_review.recommended_source_evidence_refs` or course leg `evidence_refs`) before finalizing an upstream correction or limitation.
- Station chains, centerlines, routes, strips, and intentionally open alignments may not close — endpoint displacement is a mechanical fact to interpret, not a universal failure.
- Hydrate specific refs only when needed: control render for visual map review (leg/gap annotations), geometry ref for feature/coordinate inspection, mapping ref for compact lineage, counts, sanity_review, and draft_patch_targets.
- For upstream source repair, hydrate targeted transcript-edit evidence refs (`image:derived:*`, `image:assoc:*`) via `hydrate_artifact_refs` — do not bulk-hydrate the entire transcript-edit artifact universe.
- After a successful remap via `submit_ir_for_mapping`, use `mapping_review.active_handoff_context` (or `current_mapping_lineage` / compatibility `lineage_lock`) as the **sole hot mapping/IR candidate** for the next finalization — do not treat older mappings in `latest_refs` as equally eligible, and do not mix a newer IR ref with an older mapping ref (or vice versa). When hydrating a mapping ref, inspect `lineage_status` (`current` vs `superseded`); a superseded historical mapping remains auditable but is not the finalization candidate.
- Work items whose explicit `evidence_refs` cite only superseded mapping/IR refs are **historical lineage context**: auditable, but they do not establish a defect in the current mapping and must not reopen otherwise accepted current handoff work.
- When a source limitation is represented in current IR/mapping as a scoped blocked continuation, treat it as a **durable package limitation** — not an instruction to reopen otherwise accepted current work. Do not create or preserve a global `blocks → final_handoff` relation solely because a source continuation is unavailable. A material defect in current lineage may still block handoff; that distinction remains agent-authored.
- If any `patch_ir_draft` occurs after mapping, resubmit the patched draft for mapping before finalization — stale mapping lineage is refused retryably.

## Mapping sanity repair (surgical course patch)
- Normal path: inspect `mapping_review.sanity_review` → use `mapping_review.draft_patch_targets` (and `correction_posture.matching_patch_target_id` / `patch_update_shells` when present) → `patch_ir_draft` with `course_updates` → remap → finalize.
- Prefer `course_updates` over reconstructing full `courses[]` for a simple bearing/distance fix. Shells may include placeholders; the agent authors the corrected `value`. Deterministic code does not choose deed truth.
- Do **not** use `delegate_subtask` to locate IR patch targets — the parent already owns the draft/mapping surfaces and the mechanical bridges (`draft_patch_targets` / shells); delegation adds no bounded observation gain for this repair.

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
  - author scoped IR (cite `operand_suite_ref` / `mapping_operands` — do not recopy every operand row)
  - represent blocked/partial scopes explicitly
  - encode governing range or frame decisions in IR/provenance
  - submit IR for mapping
  - inspect map/compile/judge artifacts
  - repair IR when mapping exposes a real defect
  - finalize the current lineage-bound package
  - complete the run after published output
- Inherited upstream values are **starting inputs**, not blind truth. If mapping/compile/judge exposes a real defect, self-heal by correcting IR and provenance — do not silently trust transcript-edit when earned evidence contradicts it.

## Foundation workflow (bound)
- Bound tool contracts live in tool specs — treat those as authoritative; this guidance does not duplicate exact tool IDs or request shapes.
- Typical flow: hydrate `mapping_operands` and feature-graph capabilities; save a draft early; repair placeholder-only drafts into real op/geometry/feature-ref structure with provenance; submit saved IR for mapping when `mapping_submission_ready_candidate` is true enough for inspection; inspect returned mapping review; finalize with unresolved semantic decisions; complete after published output.
- Attach exact upstream links through `ProvenanceAttachment.source_entity_links` on graph entities — not only graph metadata.
- Do not guess schema, operation parameters, units, operand shapes, support status, or provenance contracts. Hydrate capability details in the same orientation batch before the first non-trivial IR save when details are not already in context.

## What not to do
- Do not rebuild transcript-edit's resolution graph as local deed-to-IR inventory.
- Do not parse deed text into IR in bulk prose without durable IR artifacts.
- Do not treat startup handoff or resolution summary as closure or earned geometry truth.
- Do not expect deterministic code to infer atom-to-feature associations or source-entity links.
- Do not unpin or shrink operand-suite visibility by default after drafting — the operand suite is core reference material, not disposable context.
- Do not manage preview refs, closure arrays, strict package rows, or package shells as agent bookkeeping — the finalizer owns that realization.
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
