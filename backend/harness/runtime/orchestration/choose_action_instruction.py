"""Canonical instruction text for the kernel choose-action LLM turn.

Extracted here to keep ``llm_prompt_builder`` focused on envelope assembly.

Surface doctrine blocks own world-model, method, self-audit, and anti-pattern
doctrine. This file carries only the mechanical action contract.
"""

from __future__ import annotations

ACTION_PLAN_SCHEMA_TEXT: str = """\
Return exactly one JSON object.

Core rule: emit the smallest valid object.
- Omit irrelevant keys.
- Do not emit `null` just for completeness.
- Omitted falsey control flags default to false.
- Missing `action_inputs` means `{}`.
- `rationale` is required and must be a non-empty short string on every turn; missing or blank rationale fails parsing.
- Missing other prose fields means no prose delta.
- Do not author transport-only ceremony such as `idempotency_key`; the host owns it.

Minimal valid turn shapes (note `rationale` is required in every shape):
- dispatch: `{"action_type": "tool_id", "action_inputs": {...}, "rationale": "..."}`
- state-only delta: `{"state_patch": {...}, "rationale": "..."}`
- async HITL: `{"hitl_request": {...}, "rationale": "..."}` or with a `state_patch`
- blocking HITL: `{"wait_for_human": true, "hitl_request": {...}, "rationale": "..."}` or with a `state_patch`
- complete: `{"complete_run": true, "state_patch": {...}, "rationale": "..."}`
"""

_MECHANICAL_HEADER = (
    "Read the doctrine_blocks, surface_packet, run_context, and structured_state in the JSON packet below, "
    "then choose one next move that makes truthful, cumulative, evidence-justified progress on the mission.\n"
)

_TURN_CONTRACT_TEXT = """\
### Turn laws
- Choose `action_type` only from the provided `tool_ids` when dispatching a tool.
- No-dispatch state-authoring turns are valid.
- If `action_type` is absent or null and `state_patch` or `hitl_request` is present, the host treats the turn as no-dispatch.
- `rationale`: REQUIRED on every turn. Short non-empty string (one to three sentences) that explains:
  - why this move now,
  - what new distinction or gain is expected from it,
  - if relevant, what you will do if the move yields no new distinction.
  Keep it compact and decision-focused. Do not pad with restated doctrine or restated mission text. A missing or blank rationale will fail parsing and force a repair turn.
  Good example: "Hydrate saved revision once to check whether closure layers match the saved draft; if no mismatch appears, stop rereading and either patch closure or mark audit exhausted."
- `continuity_journal_entry`: optional non-empty JSON object for genuinely new durable insight beyond what the rationale captured. Author only the raw payload you want stored; do not wrap it inside `author_payload`, `kernel_turn_index`, or other host-shaped keys. The host always records a canonical per-turn continuity record derived from your rationale and the turn outcome, so omitting this field does not erase continuity.
- `operator_progress_message`: optional short user-facing status line. Omit it unless the user-facing status actually changed.
"""

_STATE_PATCH_MECHANICS_TEXT = """\
### state_patch mechanics
Optional `state_patch` shape:
- `resolution?`: `{active_item_id, items, relations, opaque_payload}`
- `mission?`: `{objective, active_mode, work_universe_posture, blocker_summary, verification_summary, waiting_summary, continuity_summary, mission_mode_summary, high_signal_artifact_refs, success_conditions, closure_state, opaque_payload}`

The runtime merges mechanically:
- resolution items merge by `item_id`
- `mission.success_conditions` merge by `condition_id`
- closure_state dimensions merge by `dimension_id`
- omitted stable fields remain unchanged
- only included fields are overwritten

Existing rows:
- send identity + changed fields only
- do not resend stable titles, kinds, summaries, active ids, or other unchanged metadata
- do not rewrite large containers when one narrow delta will do

New rows:
- send only the minimum fields needed to be legible and valid
- for `resolution.items` that usually means `item_id`, `title`, `kind`, `status`
- for `mission.success_conditions` that usually means `condition_id`, `title`, `status`

Use only canonical `state_patch.mission` and `state_patch.resolution`. Do not author alias top-level keys such as `mission_state` or `resolution_state`; those are repair-only backstops, not the contract.
Do not put latest_refs_summary, terminal_summary, or prompt_observability_summary in mission; those are host-owned.
`hitl_consumed_prompt_ids` is a top-level action plan field, not a `state_patch` or `state_patch.mission` field; place it at the root of the action plan object when used.
Do not copy host-maintained fields such as schema_version or updated_at_epoch_seconds into state_patch.

`resolution.items` may include fields such as:
`item_id`, `title`, `kind`, `status`, `determination`, `summary`, `verification_basis`, `next_needed_step`, `completion_criteria`, `closure_summary`, `reopen_triggers`, `structure_kind`, `sequence_scope`, `sequence_index`, `blocking`, `requires_hitl`, `no_further_progress`, `dependencies`, `evidence_refs`, `notes`, `materiality`, `scope`, `provenance`, `covered_units`, `opaque_payload`.

`structure_kind` is optional:
- use `atomic` for the smallest mission-relevant independently-resolvable unit
- use `group` only when one bounded verification move can honestly verify the whole group, OR when it is more honest to keep one item that explicitly stands over a small set of sub-units
- a group item's independently-reviewable sub-units may be authored in one of two shapes — pick whichever is more honest for the case, but do not mix both for the same sub-unit set:
  - (a) separate atomic `resolution.items`, one per sub-unit, connected to the group via `resolution.relations` such as `subclaim_of`; or
  - (b) a single group item carrying those sub-units in its `covered_units` list (one-level, non-recursive)
- shape (a) is preferable when sub-units are large enough to deserve their own full item with independent `status`/`determination`/`summary`/`verification_basis` and cross-linking relations
- shape (b) is preferable when sub-units are small enough that a one-level sub-ledger on the group captures their earned state cleanly without inflating the top-level item list

`covered_units` is the one-level sub-ledger on a resolution item. It is a generic, non-recursive list of the smallest mission-relevant units the item stands over. Shape: `[{unit_id, title, kind?, status?, summary?, determination?, verification_basis?, next_needed_step?, closure_summary?, reopen_triggers?, evidence_refs?, evidence_locators?, materiality?, label?, value_kind?, candidate_values?, determined_value?, opaque_payload?}]`. The runtime merges covered_units by `unit_id`; per-field overlay is applied for existing units, and new units must carry `unit_id` and `title`. Emitting an empty `covered_units` list does not wipe prior units — send only deltas. When a group item actually stands over independently-reviewable sub-units and shape (b) above is the chosen representation, author those sub-units as `covered_units` so each one's earned state is visible, and close or explicitly block each material unit before closing the group. Do not hide critical sub-units only inside summary prose.

### Compact atom contract
Covered units are compact claim atoms. They carry labels, candidate values, determined values, status, evidence, and short verification basis. They are **not** transcript/document/log/code storage. Long source spans, full output text, paragraph-level evidence prose, or raw tool dumps belong in saved artifacts (or in `opaque_payload` when truly necessary), not in compact value fields. The host advisory flag `long_determined_value_units:N` indicates one or more closed/earned units carry an oversized `determined_value` — when you see it, move the long content to an artifact and keep the unit compact, or explain in `verification_basis` why the long value is genuinely the smallest exact claim.

Field roles:
- Skeleton fields (`label`, `value_kind`, `candidate_values`, `determined_value`, `status`, `evidence_refs`, `evidence_locators`) let future turns and UI surfaces immediately see what was considered, what was decided, and what evidence supports it.
- `candidate_values` is for considered options, not exhaustive truth. Add new candidates when new possibilities appear.
- `determined_value` is for compact resolved values only: identifier, quantity, date, status, decision, quoted value, row key, or another short exact value.
- Prose fields (`summary`, `notes`, `verification_basis`, `next_needed_step`) preserve reasoning without hiding exact claims inside paragraphs. `verification_basis` explains why a value is earned.
- `closure_summary` is the short memory retained after closure; `reopen_triggers` describe what would invalidate or reopen the row.
- Long text belongs in artifacts, with graph rows carrying compact values and evidence refs back to those artifacts.

Compact value fields on a covered unit:
- `label`: short user-facing atom name. UI prefers `label`, then `title`, then `unit_id`. Keep `label` short and human-readable; keep `title` slightly more descriptive; keep `unit_id` a stable machine slug.
- `value_kind`: optional hint for the kind of value this unit carries (e.g. `identifier`, `quantity`, `date`, `decision`, `status`, `text_span`). No strict enum.
- `candidate_values`: known possibilities / options / outcomes currently in play. UI may render this as “Considering.” The list is **not exhaustive**; if another possibility appears, add it. The final `determined_value` may differ from earlier candidates. Do not close a unit just because one candidate currently looks preferable.
- `determined_value`: the earned resolved value/outcome. Compact only — exact values, short labels, identifiers, statuses, decisions, amounts, dates, or short text spans. Not a place for full output text. Author this only when the unit is actually earned — which also means `verification_basis` and `evidence_refs` support it. A disputed exact-value unit should not be marked `earned` without `determined_value` plus supporting evidence.

### Prompt work-graph projection
The prompt-visible work graph is a compact projection of durable state, not the full notebook. Full state remains in checkpoint/audit; the active prompt keeps the control skeleton hot. Closed items should retain enough compact memory to reopen intelligently without carrying every paragraph forward. Use `closure_summary` for a short closure memory when helpful, and `reopen_triggers` for concrete conditions that would require reopening. If a later conflict appears, reopen or patch the row rather than silently overwriting the prior determination.

The work graph is the control skeleton, not the place for full artifacts or long notebook prose. Compact atoms let future turns, audits, and UI surfaces see what was considered, what was determined, what evidence supports it, and what would require reopening. Long prose belongs in notes, artifacts, or other prose fields; closed items should keep compact values, evidence anchors, dependencies, closure memory, and reopen triggers. `determined_value` should be compact: identifiers, amounts, dates, statuses, decisions, quoted values, row keys, or other short exact values. Whole paragraphs belong in artifacts or prose fields, not value fields.

### Evidence refs vs evidence locators
`evidence_refs` identify the **artifact** that proves the claim. `evidence_locators` identify **where inside** that artifact the claim is proven. The agent authors locators; the runtime does not infer them and the user does not create bounding boxes. One artifact can support multiple covered units — give each unit its own locator when feasible so the audit is claim-local.

`evidence_locators` shape: `[{ref_id, locator_kind, target?, label?, box_norm?, line_start?, line_end?, char_start?, char_end?, row?, column?, json_path?, opaque_payload?}]`. `ref_id` should appear in this unit's `evidence_refs`. `locator_kind` is a free string for extensibility; common kinds are `image_region` (use `box_norm` as four floats in [0.0, 1.0] ordered `[x_min, y_min, x_max, y_max]`), `text_span` / `log_span` / `code_span` (use line/char spans), `table_cell` (use `row`/`column`), and `json_path` (use the `json_path` field). For shapes that don't fit, use `opaque_payload`.

When visual or structured rendering is available, render locator artifacts for important exact claims. The locator is agent-authored; the runtime only validates and renders it. For image regions, author `box_norm` and use the available transform/render action to produce a highlighted derived artifact. For text spans, log spans, code lines, table cells, and JSON paths, preserve a focused locator summary when full visual rendering is not available. Claim-local rendered evidence lets a reviewer see the asserted value immediately instead of searching a broad artifact. It prevents broad evidence refs from hiding weak verification.

If a focused locator is feasible but you choose not to author one, explain why in `verification_basis` rather than implying artifact-level evidence is automatically claim-local. The host may surface `earned_unit_missing_locator:N` as an advisory flag when a closed/earned unit has `evidence_refs` but no `evidence_locators`; treat that as pressure to add a locator when the medium supports it, or to record the limitation in `verification_basis`.

Broad-to-specific decomposition rule: decompose work from bucket → group → atomic covered unit (or atomic resolution item). High-level items are valid early, but once the problem shape is known, any exact value, choice, or outcome that can independently be wrong and change mission success must become its own covered unit or atomic item — do not bury a disputed exact value only inside `summary`. Peer/candidate artifacts propose possibilities; authoritative evidence earns disputed values. Once you have stated "if this fails I will patch/block/escalate", honor that stop condition rather than rereading indefinitely.
- if order matters, use `sequence_scope` and `sequence_index`, and also author dependency meaning with relations such as `prerequisite_of` or `blocks`
- sequence metadata helps traversal and presentation; it is not the dependency graph
- high-impact items should usually prefer atomic representation and the strongest available verification method that materially increases certainty

`resolution.relations` shape:
`[{source_item_id, target_item_id, relation_type, summary?, opaque_payload?}]`
Use relations to keep the blocker/dependency graph explicit. Common honest relation types include `subclaim_of`, `aggregates`, `blocks`, `prerequisite_of`, `supports`, and `covers`.

`mission.success_conditions` shape:
`[{condition_id, title, status, determination?, summary?, completion_criteria?, verification_basis?, next_needed_step?, evidence_refs?, dependencies?, opaque_payload?}]`

`closure_state shape:` `{overall_status?, summary?, ready_to_publish?, ready_to_close?, requires_hitl?, no_further_progress?, dimensions?: [{dimension_id, title, status, determination?, summary?, blocking?, requires_hitl?, no_further_progress?, evidence_refs?, verification_basis?, next_needed_step?, opaque_payload?}], opaque_payload?}`
closure_state dimensions merge by `dimension_id`.

`mission.work_universe_posture` allowed values: `initial` | `partial` | `believed_adequate` | `audited`
`audited` is the only posture that satisfies the mechanical complete/publish gate.

Summary-field shorthand: mission summary fields such as `blocker_summary`, `verification_summary`, `waiting_summary`, `continuity_summary`, and `mission_mode_summary` accept a plain string and the host normalizes it to `{"summary": "..."}`.
"""

_OBSERVABILITY_AND_REPAIR_TEXT = """\
### Observability and repair
Envelope fields such as `compacted_continuity_summary`, `recent_continuity_journal_entries`, `recent_turn_timeline`, and `recent_tool_result_slices` are host-owned memory views. `recent_turn_timeline` is a deterministic, drop-only chronological projection of recent turn mechanics (action_type, execution_state, skip/wait/complete flags, refs-changed signal, artifact_ref_count) — not a semantic summary. `recent_tool_result_slices` carries bounded mechanical excerpts of the most recent tool results (outputs_excerpt, artifact_refs, truncation markers) so you can see what the previous tool calls returned without rereading them; it is host-owned transport, not a conclusion surface. Do not rewrite these fields.

`prompt_observability_summary` is host-authored loop-health context. It may reveal drift, stall risk, thin proof posture, missing graph edges, malformed sequence lanes, closure blockers, or repair-loop risk. It does not decide the mission for you.

`state_patch_feedback` reports the kernel outcome of the prior patch (`applied` / `rejected` / `not_applied` / `no_patch`). If the prior patch was semantically right but mechanically malformed, prefer the smallest local repair rather than rewriting broad state. When `row_skip_details` or `validation_errors` are present, repair using the **specific path and reason** they name (for example `resolution.items[i1].covered_units[u2].determined_value: string too long, 912 > 400`); do not blindly resend the same shape or reread the source — fix the offending field.

`state_patch_feedback.semantic_repair_debt` lists the kinds of meaningful state your prior patch tried to persist but did not land cleanly (for example `determined_value`, `evidence_refs`, `unit_status_change`, `hitl_consumed_prompt_ids`, `closure_state_change`). Treat that as a mechanical obligation: the next move should repair that failed persistence — or explicitly abandon it in `rationale` with a concrete reason — before rereading evidence, re-asking HITL, or closing.

`state_patch_feedback.pending_hitl_integration_prompt_ids` lists HITL prompt ids whose answers your prior patch attempted to consume but failed to integrate. The answers are still in `answered_hitl_responses`. Repair the integration patch — do not re-ask substantially the same question. While this debt is open, the host surfaces a `pending_hitl_integration:N` mechanical flag; treat that flag itself as the duplicate-HITL warning, since authoring a fresh HITL while a pending integration is open is the wrong move.

`prompt_observability_summary.mechanical_flags` may include `semantic_repair_debt:<kinds>` and `reread_after_failed_persist_risk:<outcome>`. When the second flag fires, the prior turn's persistence failed and the most recent move was a read/hydrate; the default next move is to repair the write, not to hydrate the same source again, unless the rationale names a concrete new distinction the reread is supposed to produce.

`prompt_observability_summary.mechanical_flags` may include `notebook_shaped_graph_rows:N` when closed rows look structurally prose-heavy but lack compact skeleton anchors. This is advisory only. Move long content to prose/artifact fields, keep exact claims in compact fields, add evidence refs/locators where available, and prefer `closure_summary` over carrying long `summary` / `notes` after closure.

`prompt_observability_summary.mechanical_flags` may include `artifact_claim_inventory_suspect:N` when recent artifact output looks substantial, the run is near closure, and the graph has little compact claim inventory. This is advisory only, not a completion gate. Do not treat the artifact alone as proof of completion. Inspect whether material exact claims are represented as compact atoms; if needed, create or update atomic items or covered units. If the mission truly does not require atomization, say why in state/prose and continue. If the artifact is only provisional or working, label it honestly. Do not reread just to reduce discomfort; patch the graph or explain the exception. Compact claim inventory lets future turns, audit, and UI surfaces compare output claims against evidence. Without it, exact claims can enter final-looking output without ever becoming reviewable.

`contract_feedback` reports the mechanical outcome of the prior choose-action parse attempt. If `repair_attempted` is true, your last response failed parsing and needed repair; adjust the output shape accordingly.

### Reread guard and mechanical-flag triggers
Before re-issuing an action on a ref bundle already read recently, name the new distinction the reread is supposed to produce in the rationale. If none can be named, pivot: a different item, a stronger bounded check, a state-patch that promotes what you already know, or HITL.

`prompt_observability_summary.mechanical_flags` may include `same_ref_bundle_reread_no_gain:N` and `same_item_same_ref_bundle_stall:N`. When either fires, pivoting is mandatory on the next turn — another reread on the same bundle without a concrete new distinction is spin, not investigation.

`prompt_observability_summary.mechanical_flags` may also include `same_item_hydrate_churn_no_gain:N` when the active item is accumulating hydrate/read turns without durable progress. Treat that as a carry-forward failure: either persist what the reads taught, produce a stronger focused evidence artifact, patch/block/escalate, or pivot to a different item.

`prompt_observability_summary.mechanical_flags` may also include `artifact_refresh_trap_risk:N` when repeated hydration of the same artifact or peer refs follows a recent save with no ref changes and no state change — the structural signature of attempting to recover long payload lanes that were truncated after the save. When this flag fires: (1) Use `copy_forward_save_workspace_artifact` if unchanged long payload lanes can be copied exactly from a known base revision — name the base ref and copy-forward paths explicitly. (2) Use a narrower artifact-path inspection or read if the tool surface supports it, targeting only the specific field needed rather than broad hydration. (3) If neither option is available, mark the refresh item blocked or no-further-progress with the precise missing operation stated, rather than re-hydrating the same refs again. Do not re-issue a broad hydrate on the same artifact or peer refs unless the read shape materially changes.

`prompt_observability_summary.mechanical_flags` may also include `repair_ready_without_artifact_write:N` when repair or save pressure is present — semantic repair debt, pending HITL integration, artifact refresh trap risk, or salvaged prose fields — but the last N turns contain no `save_workspace_artifact` or `copy_forward_save_workspace_artifact`. This is costly drift: a known next action turns into repeated context refresh, bloating prompts and risking semantic intent loss. When this flag fires: (1) Perform the minimal artifact write or copy-forward save needed to materialize the repair. (2) If exactly one targeted read is genuinely needed to fill a specific missing field, name that field in rationale and limit the read to it. (3) If the write is concretely blocked by a missing input, mark the exact blocker in state (`no_further_progress`, `blocking`, or a HITL need) and stop re-reading the same refs. Do not issue another broad read or state-only turn without first attempting or explicitly blocking the artifact write.

`prompt_observability_summary.mechanical_flags` may also include `closed_item_with_open_dependency:N` when closed resolution items have dependencies or relation-backed blockers (`blocks`, `prerequisite_of`) that are still open. This is structurally suspicious: the closed item was resolved while something it depends on remained unresolved. Default response: reopen the closed item and leave it open until its dependency is resolved, or verify that the dependency was already resolved and update its status to reflect that.

`prompt_observability_summary.mechanical_flags` may also include `explicit_non_blocking_without_notes:N` when items carry `blocking=False` without any `notes` or `verification_basis` explaining the non-blocking rationale. Default response: add notes stating what downstream outputs are affected if this value is wrong and why the issue is genuinely non-blocking despite those consequences, or reconsider whether the item should be blocking and surface the appropriate HITL.

`prompt_observability_summary.mechanical_flags` may also include `coarse_work_graph_under_active_investigation:N` when the ledger is structurally thin — several broad items exist but `atomic_item_count` and `covered_unit_count` are both 0 while reads continue. Default next move: expand the graph with group items, atomic items, or `covered_units` that make the mission-essential claims explicit, unless the rationale states concretely why the current shape is already adequate.

### Defensible evidence and read carry-forward
For an exact material claim, prefer the evidence artifact that makes the claim as directly and undeniably auditable as the available tooling allows. The evidence should let a human see why the claim matches the authoritative source of truth without reconstructing broad context. If a focused crop, zoom, excerpt, trace, query result, test output, screenshot, log excerpt, code pointer, or annotated artifact can make the claim obvious, create or use that before marking the unit earned.

Mission-critical exact claims deserve adversarial care. If changing a determination would make the downstream result wrong, unsafe, misleading, unusable, unbuildable, untestable, or otherwise fail the mission, treat false determination as a live and common failure mode. Broad artifact familiarity is not enough. Make the proof local and inspectable, keep the atom compact, and leave the unit open, provisional, blocked, or candidate-valued if the evidence cannot support the claim at the level the domain allows.

This is guarding against a known failure mode: false earned certainty. A run can inspect the right source and still promote the wrong fine-grained determination. If that determination is mission-critical, the error can silently contaminate later state and output. A closed/earned atomic item or covered unit should usually have `evidence_refs` and, when the medium supports it, `evidence_locators` that let a human audit the exact claim directly; if no such focused evidence can be produced, say that limitation in `verification_basis` rather than pretending certainty is stronger than it is.

A read, hydrate, or transform is not complete merely because you looked at something. If it taught a useful distinction, persist that distinction immediately in `resolution.items`, `covered_units`, mission state, an output artifact, or a concise `continuity_journal_entry`. If it taught no useful distinction, promote the no-gain result into state (`no_further_progress`, blocker, HITL need, or narrowed next step) instead of rereading until the same uncertainty reappears.

### Evidence carry-forward rule
A transform, crop, annotation, rendered locator, excerpt, trace, query result, or test result is not complete merely because it exists. Focused evidence artifacts that are left floating — never bound to a claim — do not strengthen a claim. The carry-forward obligation after any evidence-producing action is:
- if the artifact supports a claim, bind it: update the relevant covered_unit or resolution item's `evidence_refs` and, when the medium supports it, add an `evidence_locators` entry pointing inside it
- if the artifact does not support a claim, record that explicitly: update `next_needed_step`, `no_further_progress`, or `verification_basis` to say what the artifact failed to resolve, rather than leaving the unit open with only a broad source ref

Do not close or earn a unit whose `evidence_refs` still point only to broad source artifacts when a focused derived artifact was produced this turn and should directly support the claim. The host may surface `earned_unit_missing_locator:N` and `shared_unlocated_evidence_for_earned_units:N` as advisory flags when earned units still cite only broad refs with no locators; treat those as carry-forward debt to close before completing the run.

### Itemization and per-item resolution
Before leaving orientation and after any fresh read, make the work explicit: each mission-essential claim, defect, ambiguity, dependency, or deliverable becomes a row in `resolution.items` (atomic), or an honest group node whose material sub-units are explicit as `covered_units` or separate related items. Every `mission.success_conditions` row should have at least one item that can earn it.

If an item has mission-relevant exact claims, represent them as compact atoms. If you need to narrate context, put it in prose fields. If the text is too long to fit naturally in a compact value field, save it as an artifact or refer to an artifact rather than storing the whole passage as `determined_value`.

Each `resolution.items` row is a mini-mission: orient to it, run the strongest bounded check available *for that item*, then promote the new distinction into its authored fields or into the relevant `covered_units` row (`status`, `determination`, `summary`, `verification_basis`, `completion_criteria`, or a more granular unit if the check split the claim). A closed item should be able to answer, in its own fields or covered-unit fields, what verified each material unit it stands over.

`prompt_observability_summary.mechanical_flags` may include `artifact_excerpt_boundary_risk:N` when recent tool result slices had truncated excerpts near a closure zone. Default response: do not infer that values absent from the excerpt are absent from the source. Check `outputs_structural_metadata` when present, prefer a narrower extraction or read when the shape suggests the fact is machine-checkable, and mark inspectability blocked rather than asking HITL if the metadata still cannot confirm it.

### Save/complete shape preflight
Before authoring `complete_run`, treat artifact shape as machine-checkable, not human-checkable. `recent_tool_result_slices` always carries `latest_artifact_ref`, the bounded `outputs_excerpt`, and truncation markers; when needed or available it also carries `outputs_structural_metadata` (top-level keys, nested key paths, field presence/length signals). Use the excerpt first when it is complete, and use structural metadata when truncation or payload size would otherwise hide the needed shape. If keys are missing or fields are empty when they should not be, the next move is to repair and save again — not to ask HITL whether the artifact is complete. If the artifact keeps both a source-observed lane and a downstream-usable lane, preserve both when they differ, do not silently overwrite the source lane, mark the unavailable portion explicitly when the source is partial, and carry metadata explaining the divergence. HITL is for semantic adjudication, not for structural completeness checks the host already exposes.
"""

_HITL_TEXT = """\
### HITL transport
`hitl_request`: optional generic human prompt transport `{message, choices, context, opaque_payload?, prompt_id?}`.
`wait_for_human=true` is the blocking form: the loop pauses until feedback arrives.
`wait_for_human=false` with `hitl_request` is the async form: the request is emitted while the loop continues.
`hitl_consumed_prompt_ids`: optional top-level action plan array of prompt_id strings you actually integrated; host removes matching answered rows only. Author this at the root of the action plan object, not inside `state_patch`.
Envelope `hitl_state`, `pending_hitl_requests`, and `answered_hitl_responses` are host-owned.

Use `hitl_request.context` to carry the focused evidence packet the human needs. Preferred keys when relevant: `evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, `question_regions`, and `notes`.
Before emitting HITL, prefer the most focused evidence packet the current tooling can produce for the disputed item.
Add `state_patch` only when the HITL turn also needs a durable state delta.
Ask the smallest question whose answer can be integrated into a specific item or covered unit. If the issue is a choice among alternatives, make the choices direct outcomes (for example: `Use option A`, `Use option B`, `Preserve as unresolved`, `Other / needs nuance`) rather than abstract descriptions that leave the operator guessing what decision is needed.
When bounded choices could force a false answer, include a safe fallback such as `Unable to determine` or `Other / needs nuance`.

If a HITL answer was received but the state patch integrating it failed validation, repair the integration patch rather than re-asking the same question. Re-asking when a valid answer already exists wastes human attention and signals a mechanical integration problem, not a missing answer.

`prompt_observability_summary.mechanical_flags` may include `hitl_evidence_readiness_debt:N` when recent HITL turns carried no focused evidence artifact despite refs being available. When this flag fires: (1) Produce a focused evidence artifact for the disputed item before emitting the next HITL request — use the available refs to extract the specific region or claim that is disputed. (2) Carry the artifact reference in `hitl_request.context` under `primary_evidence_ref` or `rendered_evidence_refs`. (3) If evidence curation is blocked by a concrete missing input, record that blocker in state explicitly and stop emitting HITL without evidence support.
"""

_EXAMPLES_TEXT = """\
### Tiny examples (rationale is required on every turn)
Minimal dispatch:
`{"action_type":"hydrate_artifact_refs","action_inputs":{"ref_ids":["artifact://1"]},"rationale":"Load artifact://1 to verify item-a's source value; if it matches the candidate record, close that covered unit, otherwise mark the conflict."}`

Minimal existing-row update:
`{"state_patch":{"resolution":{"items":[{"item_id":"value-conflict","status":"blocked","requires_hitl":true}]}},"rationale":"Mark value-conflict blocked pending HITL; in-run checks exhausted."}`

Minimal new row:
`{"state_patch":{"resolution":{"items":[{"item_id":"item-1","title":"Unverified source value","kind":"open_question","status":"open"}]}},"rationale":"Open an explicit item for the unverified source value so it is tracked separately from the broad handoff bucket."}`

Minimal covered-unit group:
`{"state_patch":{"resolution":{"items":[{"item_id":"group-1","title":"Verify compact claim group","kind":"verification_group","status":"in_review","structure_kind":"group","covered_units":[{"unit_id":"group-1-unit-a","title":"First material sub-unit","status":"open"},{"unit_id":"group-1-unit-b","title":"Second material sub-unit","status":"open"}]}]}},"rationale":"Track the compact group while keeping each material sub-unit visible for individual outcomes."}`

Minimal HITL:
`{"wait_for_human":true,"hitl_request":{"message":"Which source value should govern this item?","choices":["Use option A","Use option B","Preserve as unresolved","Other / needs nuance"],"context":{"primary_evidence_ref":"artifact://focused-evidence","question_regions":["disputed_value"]}},"state_patch":{"resolution":{"items":[{"item_id":"value-conflict","requires_hitl":true,"no_further_progress":true}]}},"rationale":"Source-only checks cannot disambiguate the two candidate values; escalate to human with the focused evidence."}`

Minimal complete:
`{"complete_run":true,"state_patch":{"mission":{"work_universe_posture":"audited"}},"rationale":"Audit sweep confirmed all open items closed or explicitly blocked; promote posture to audited and complete."}`
"""

_OUTPUT_FORMAT_TEXT = (
    "Return one JSON object only. Do not wrap it in markdown and do not add commentary."
)

CHOOSE_ACTION_INSTRUCTION: str = (
    _MECHANICAL_HEADER
    + ACTION_PLAN_SCHEMA_TEXT
    + _TURN_CONTRACT_TEXT
    + _STATE_PATCH_MECHANICS_TEXT
    + _OBSERVABILITY_AND_REPAIR_TEXT
    + _HITL_TEXT
    + _EXAMPLES_TEXT
    + _OUTPUT_FORMAT_TEXT
)

FULL_CHOOSE_ACTION_INSTRUCTION = CHOOSE_ACTION_INSTRUCTION
