"""Procedural guidance for deed-to-IR foundation tools."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID

DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/procedural_guidance.py"
)
DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION = "v24"

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
- The first draft does not need perfect provenance, but zero provenance links should be treated as a repair signal before preview/publish — use `draft_quality_flags` and counts, not guesswork.

## Draft IR lifecycle
- Before authoring or repairing supported operation nodes, use the FeatureGraph authoring guide as the layer map: deed meaning, node kind, compiler operation, params, operands, and rendered geometry are distinct.
- `graph_id` is the **stable logical graph id** — do not embed draft version numbers in `graph_id` (avoid `right_of_way_v1` as graph_id).
- To continue a working draft, pass `base_draft_ref` from the prior save; the tool allocates versioned artifact refs (`feature_graph:ir:right_of_way_v0`, `..._v1`, ...).
- `save_ir_artifact` saves a **draft checkpoint** (`draft_version` such as v0, v1, v2) — not final publication.
- Use `patch_ir_draft` for surgical repair when `draft_repair_items` are directly actionable and operands are already available; use full `save_ir_artifact` for first draft or major rewrite.
- Keep the current draft ref and repair feedback active while drafting; keep operand values visible via `mapping_operands` / `operand_suite_ref` as needed.
- Use `outputs.working_draft_ref` (alias of `draft_ir_ref` / `ir_artifact_ref`) for `@this.result.working_draft_ref` hydrate-next on the same turn batch.
- Compile/judge feedback on draft save is expected mechanical feedback — use `current_draft_ir.draft_repair_items`, `draft_quality_flags`, and node-precise `compile_gaps` to repair the **same graph_id** and save the next draft version; do not reread operation contracts unless a new primitive is genuinely needed.
- `placeholder_only_graph`, `renderable_feature_count`, and `mapping_submission_ready_candidate` distinguish schema-valid scaffolds from map-useful IR.
- `mechanically_mappable_candidate` means only that no blocking mechanical compile/judge gaps were detected; it is **not** deed-correctness, closure truth, or submission readiness by itself.
- Use `unknown` only when the feature kind itself is unknown. A known blocked, partial, or dependency-pending scope is not unknown; represent it as an `annotation` with source/provenance links and handoff notes. Do not fabricate geometry for blocked scope.
- Do not treat `unknown` nodes with deed prose parked in `graph.metadata` as sufficient map IR.
- `submit_ir_for_mapping` is the deliberate mapping attempt once structural readiness is honest enough for inspection.
- `prepare_deed_to_ir_final_package` builds a confirmable preview checkpoint — agent-authored rows plus mechanically derived lineage.
- `publish_deed_to_ir_output` is final scoped handoff only; prefer publishing with `final_package_preview_ref` from the preview.

## Final package preview flow
- Normal end flow: save/patch draft IR → submit for mapping → inspect mapping review → prepare final package preview → publish from preview → complete (with final state patch only if still needed).
- A ready preview is a **publish launchpad**. When `prepare_deed_to_ir_final_package` returns `publish_ready_candidate=true` with valid lineage, scope counts, dependency count, and closure statuses, normally publish from `recommended_publish_request` on the next artifact-writing turn.
- Do not hydrate the preview just to reread the same summary. Use `working_preview_ref` only when targeted preview hydration is genuinely needed.
- Do not use `@this.result.derived_ref_id` after `prepare_deed_to_ir_final_package` — that tool does not emit `derived_ref_id`. Publish from `recommended_publish_request`; hydrate with `@this.result.working_preview_ref` only when necessary.
- State alignment is useful but should be **economical**:
  - patch obvious closure/work-item state in the same turn as preview when already known,
  - or patch final state in the same turn as `complete_run`,
  - do not spend separate turns on posture-only repair before publish unless publish depends on it or local state would materially mislead downstream handoff.
- If a state patch fails, do not keep repairing posture before publish unless the failure affects the package, lineage, scope posture, dependency posture, or final handoff truth.
- Before calling publish, posture alignment means the local state says what the preview already showed: mapping reviewed, final package preview accepted, scoped output ready to publish. Do not use publish as the probe for whether readiness posture is aligned.
- If publish is refused only by readiness/audit posture (`publish_gate_category=publish_posture_audit_gate`, `preview_still_valid=true`), do **not** rebuild or rehydrate the preview — patch mission/closure posture if warranted and retry the same `final_package_preview_ref`.
- If the IR is patched after preview, submit mapping again and prepare a new preview before publish.
- After a successful preview, only reopen IR for material defects: wrong geometry, wrong source value, stale mapping lineage, missing blocked scope/dependency, failed compile/judge/render, or preview does not match intended final handoff.
- Do not reopen IR for provenance wording polish or speculative improvement.
- Publish with the preview ref — do not manually reconstruct compile/judge/render refs or re-copy row payloads at publish time. To change rows, prepare a new preview.

## Publish and completion
- After successful `publish_deed_to_ir_output` with `final_output_summary.ready_for_completion_candidate=true`, normally call `complete_run`. Do not hydrate output/preview/IR/mapping just to restate what publish already returned.
- Do not patch the local work graph merely to make posture mirror final package rows — the published output is the durable closeout package and its closure rows are authoritative.
- Mission `closure_state.dimensions` mirroring is optional after publish. If you patch dimensions, each row requires `dimension_id`, `title`, and `status`. Final package closure rows use `dimension_id` + `status` only — do not mirror them verbatim without `title`.
- If `closure_dimension_validation_failed` appears on a late `complete_run` patch while publish already succeeded, treat it as repair noise unless it affects package identity; the published output remains authoritative.
- Continue only for a material defect: wrong IR/mapping lineage, wrong scope/dependency/closure metadata, map review defect, user/HITL correction, or publish result not completion-ready.
- Mapping review before preview/publish is still required — the completion anchor applies only after publish succeeds.
- Use `outputs.final_output_summary` and compact publish counts/refs to close when sufficient — hydrating `deed_to_ir:output` is optional unless you need deeper inspection of persisted rows.
- Do not default to `hydrate_next: ["@this.result.output_ref"]` after successful publish unless a specific unresolved question remains about the persisted package.
- Publish refusals include `publish_gate_category` and `repair_hint` — distinguish preview invalidity from mapping lineage, storage failure, and posture/audit gates before rebuilding artifacts.

## Final package rows
- `scope_results`: one row per scope/parcel/object being handed off.
  - Required: `scope_id`, `status`
  - Optional: `title`, `summary`, `basis_refs`, `blocker_refs`, `dependency_refs`
  - Use `dependency_refs` / `blocker_refs` to point at `external_dependencies[].dependency_id`
- `external_dependencies`: one row per missing external source/dependency.
  - Required: `dependency_id`, `affected_scope`, `description`, `status`
  - Optional: `available_refs`
  - Use `description`, not `summary`. `affected_scope` is the impacted scope id/name.
  - Do not put `title` on dependency rows.
- `closure_dimensions`: one row per closure layer.
  - Required: `dimension_id`, `status`
  - Optional: `title`, `summary`, `basis_refs`
  - Use the supported closure dimension ids from the schema (all four layers required in the preview).
- `notes`: non-blocking handoff commentary only — **notes are not the correction lane**.
  - Required: `note_id`, `summary`
  - Optional: `basis_refs`
  - Use notes for context that does not report an upstream value delta the final IR relied on.
- When prepare validation fails, inspect `rejected_payload_summary`, `row_contract_summary`, and `preserve_sections` — repair the invalid section without dropping valid sections.

## Upstream correction report (final package only)
- Trust transcript-edit as the normal starting point. Do not trigger transcript-edit repair repeatedly during drafting.
- If map/geometry/deed logic exposes a concrete upstream handoff defect, investigate with targeted source evidence refs (`image:derived:*`, `image:assoc:*` via `hydrate_artifact_refs`) and transcript lanes while continuing to solve the IR/map.
- During drafting, keep working notes local. Do not emit `upstream_corrections` as a live repair trigger.
- **`upstream_corrections` are the machine-readable correction lane** for upstream handoff/transcript/resolution deltas the final IR actually relied on.
- If final IR uses a value different from inherited `mapping_operands`, selected resolution rows, or transcript-edit output — and that difference is intentional — put it in **`upstream_corrections`**, not only in `notes`.
- Do not duplicate the same correction as both a note and an upstream correction unless the note carries separate non-corrective context.
- If the correction is merely suspected and not used by IR: `posture="suspected"` and `resolution_used_by_ir=false`.
- If the correction was used by IR: set `resolution_used_by_ir=true` and include source/evidence basis in `basis_refs`.
- If final IR/map **relies on a correction** to the inherited handoff, include one or more `upstream_corrections` rows in the final package preview.
- `upstream_corrections` are **final reports for later targeted transcript-edit amendment**, not automatic transcript mutation and not live repair runs.
- Do not emit correction rows for ordinary blocked external dependencies — use `external_dependencies` for that.
- Do not emit correction rows just because IR chose a normalized value already supported by the handoff.
- Final published output may be correct and usable even before a later transcript-edit amendment exists.

## Mapping review and hydration discipline
- After `submit_ir_for_mapping`, inspect `outputs.mapping_review` first — mapping review is not just compile/judge pass/fail. Inspect mechanical geometry behavior in `mapping_review.sanity_review` (endpoint displacement, course leg tables, source evidence handles).
- Prefer `outputs.mapping_review.recommended_review_refs` over `@this.result.artifact_refs[]` for ordinary mapping review — do not bulk-hydrate every returned ref by habit. Copyable `*_ref` fields must be full canonical refs; never use truncated display fragments as refs.
- Large unexplained endpoint displacement is a **source-sanity trigger**, not automatically a deed defect. Do not declare an open traverse limitation until you consider whether the deed description expected closure or a boundary return.
- If one course leg looks suspicious, hydrate targeted source evidence for that leg (from `sanity_review.recommended_source_evidence_refs` or course leg `evidence_refs`) before finalizing an upstream correction or limitation.
- Station chains, centerlines, routes, strips, and intentionally open alignments may not close — endpoint displacement is a mechanical fact to interpret, not a universal failure.
- Hydrate specific refs only when needed: control render for visual map review (leg/gap annotations), geometry ref for feature/coordinate inspection, mapping ref for compact lineage, counts, and sanity_review.
- For upstream source repair, hydrate targeted transcript-edit evidence refs (`image:derived:*`, `image:assoc:*`) via `hydrate_artifact_refs` — do not bulk-hydrate the entire transcript-edit artifact universe.
- When publishing, set `mapping_artifact_ref` and `expected_ir_artifact_ref` from `outputs.mapping_review.recommended_publish_refs` (or the same fields on a hydrated mapping row), then prepare final package preview before publish.
- If any `patch_ir_draft` occurs after mapping, resubmit the patched draft for mapping before publishing — stale mapping lineage is refused retryably when `expected_ir_artifact_ref` does not match.

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
  - prepare final package preview
  - publish final output from preview ref
- Inherited upstream values are **starting inputs**, not blind truth. If mapping/compile/judge exposes a real defect, self-heal by correcting IR and provenance — do not silently trust transcript-edit when earned evidence contradicts it.

## Foundation workflow (bound)
- Bound tool contracts live in tool specs — treat those as authoritative; this guidance does not duplicate exact tool IDs or request shapes.
- Typical flow: hydrate `mapping_operands` and feature-graph capabilities; save a draft early; repair placeholder-only drafts into real op/geometry/feature-ref structure with provenance; submit saved IR for mapping when `mapping_submission_ready_candidate` is true enough for inspection; inspect returned mapping review; prepare final package preview; align posture; publish from preview ref.
- Attach exact upstream links through `ProvenanceAttachment.source_entity_links` on graph entities — not only graph metadata.
- Do not guess schema, operation parameters, units, operand shapes, support status, or provenance contracts. Hydrate capability details in the same orientation batch before the first non-trivial IR save when details are not already in context.

## What not to do
- Do not rebuild transcript-edit's resolution graph as local deed-to-IR inventory.
- Do not parse deed text into IR in bulk prose without durable IR artifacts.
- Do not treat startup handoff or resolution summary as closure or earned geometry truth.
- Do not expect deterministic code to infer atom-to-feature associations or source-entity links.
- Do not unpin or shrink operand-suite visibility by default after drafting — the operand suite is core reference material, not disposable context.
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
