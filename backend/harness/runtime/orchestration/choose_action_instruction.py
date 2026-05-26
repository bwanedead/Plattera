"""Canonical instruction text for the kernel choose-action LLM turn.

Extracted here to keep ``llm_prompt_builder`` focused on envelope assembly.

Surface doctrine blocks own world-model, method, self-audit, and anti-pattern
doctrine. This file carries the action-plan contract and short action-adjacent
reminders that directly affect how the agent authors the next JSON turn.
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
- one action: `{"actions": [{"alias": "a", "action_type": "tool_id", "action_inputs": {...}}], "rationale": "..."}`
- multiple actions: `{"actions": [{"alias": "a", "action_type": "tool_id", "action_inputs": {...}}, {"alias": "b", "action_type": "tool_id", "action_inputs": {...}}], "rationale": "..."}`
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
- Tool dispatch uses the top-level `actions` list. Choose each row's `action_type` only from the provided `tool_ids`.
- No-dispatch state-authoring turns are valid.
- If `actions` is absent or empty and `state_patch` or `hitl_request` is present, the host treats the turn as no-dispatch.
- `rationale`: REQUIRED on every turn. Short non-empty string (one to three sentences) that explains:
  - why this move now,
  - what new distinction or gain is expected from it,
  - if relevant, what you will do if the move yields no new distinction.
  Keep it compact and decision-focused. Do not pad with restated doctrine or restated mission text. A missing or blank rationale will fail parsing and force a repair turn.
  Good example: "Hydrate saved revision once to check whether closure layers match the saved draft; if no mismatch appears, stop rereading and either patch closure or mark audit exhausted."
- `continuity_journal_entry`: optional non-empty JSON object for genuinely new durable insight beyond what the rationale captured. Author only the raw payload you want stored; do not wrap it inside `author_payload`, `kernel_turn_index`, or other host-shaped keys. The host always records a canonical per-turn continuity record derived from your rationale and the turn outcome, so omitting this field does not erase continuity.
- `operator_progress_message`: short user-facing intent line for timeline/UI visibility. Include it on every normal choose-action turn. Say what you are doing now or about to do next in one concise sentence (present tense is fine). This is for humans skimming the run, not internal reasoning — keep detailed reasoning in `rationale`. Do not duplicate the full rationale here.
"""

_STATE_PATCH_MECHANICS_TEXT = """\
### state_patch mechanics
Optional `state_patch` shape:
- `resolution?`: `{active_item_id, items, relations, opaque_payload}`
- `mission?`: `{objective, active_mode, work_universe_posture, motion_posture, motion_posture_basis, blocker_summary, verification_summary, waiting_summary, continuity_summary, mission_mode_summary, high_signal_artifact_refs, success_conditions, closure_state, opaque_payload}`

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
`item_id`, `title`, `kind`, `status`, `determination`, `label`, `value_kind`, `candidate_values`, `determined_value`, `summary`, `verification_basis`, `next_needed_step`, `completion_criteria`, `closure_summary`, `reopen_triggers`, `structure_kind`, `sequence_scope`, `sequence_index`, `blocking`, `requires_hitl`, `no_further_progress`, `dependencies`, `evidence_refs`, `evidence_locators`, `notes`, `materiality`, `scope`, `provenance`, `covered_units`, `opaque_payload`.

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
Atomic rows and `covered_units` are compact claim rows, not artifact storage. Keep compact `label`, `value_kind`, `candidate_values`, `determined_value`, `evidence_refs`, and `evidence_locators`; put long text in artifacts or prose fields. If a closed/earned row has a compact answer, put it in `determined_value`, not only in `summary` or `verification_basis`. The host flag `long_determined_value_units:N` means one or more earned units carry an oversized `determined_value` — move the long content to an artifact and keep the row compact.

### Prompt work-graph projection
The prompt-visible graph is a compact projection of durable state, not the full notebook. Use `closure_summary` and `reopen_triggers` on closed rows. Do not store full artifacts or long notebook prose in graph value fields.

### Evidence refs vs evidence locators
`evidence_refs` identify the artifact that proves the claim. `evidence_locators` identify where inside that artifact the claim is proven — you author locators; the runtime validates them.

`evidence_locators` shape: `[{ref_id, locator_kind, target?, label?, box_norm?, line_start?, line_end?, char_start?, char_end?, row?, column?, json_path?, opaque_payload?}]`. `ref_id` should appear in this unit's `evidence_refs`. Common `locator_kind` values include `image_region` (use `box_norm` as four floats in [0.0, 1.0] ordered `[x_min, y_min, x_max, y_max]`), `text_span` / `log_span` / `code_span`, `table_cell`, and `json_path`. For other shapes, use `opaque_payload`.

The host may surface `earned_unit_missing_locator:N` when a closed/earned unit has `evidence_refs` but no `evidence_locators` — add a locator when the medium supports it, or record the limitation in `verification_basis`.

- if order matters, use `sequence_scope` and `sequence_index`, and also author dependency meaning with relations such as `prerequisite_of` or `blocks`
- sequence metadata helps traversal and presentation; it is not the dependency graph

`resolution.relations` shape:
`[{source_item_id, target_item_id, relation_type, summary?, opaque_payload?}]`
Use relations to keep the blocker/dependency graph explicit. Common honest relation types include `subclaim_of`, `aggregates`, `blocks`, `prerequisite_of`, `supports`, and `covers`.

`mission.success_conditions` shape:
`[{condition_id, title, status, determination?, summary?, completion_criteria?, verification_basis?, next_needed_step?, evidence_refs?, dependencies?, opaque_payload?}]`

`closure_state shape:` `{overall_status?, summary?, ready_to_publish?, ready_to_close?, requires_hitl?, no_further_progress?, dimensions?: [{dimension_id, title, status, determination?, summary?, blocking?, requires_hitl?, no_further_progress?, evidence_refs?, verification_basis?, next_needed_step?, opaque_payload?}], opaque_payload?}`
closure_state dimensions merge by `dimension_id`.

`mission.work_universe_posture` allowed values: `initial` | `partial` | `believed_adequate` | `audited`
`audited` is the only posture that satisfies the mechanical complete/publish gate.

`mission.motion_posture` allowed values: `inventory` | `resolution`
- `inventory`: discovering, naming, and structuring the work universe
- `resolution`: item-level learn, prove, inspect, delegate, adjudicate, earn, or close motion
Keep `motion_posture` separate from `work_universe_posture`. Setting `motion_posture=resolution` is an authored commitment, not an automatic side effect of tools. Do not set `motion_posture=resolution` while `work_universe_posture` is still `initial` or `partial` unless your rationale names why baseline inventory is already adequate. The harness surfaces both for visibility; it does not block tools based on `motion_posture`.

Optional `motion_posture_basis`: short explanation of why the current motion posture is honest (bounded string).

Summary-field shorthand: mission summary fields such as `blocker_summary`, `verification_summary`, `waiting_summary`, `continuity_summary`, and `mission_mode_summary` accept a plain string and the host normalizes it to `{"summary": "..."}`.
"""

_OBSERVABILITY_AND_REPAIR_TEXT = """\
### Observability and repair
Envelope fields such as `compacted_continuity_summary`, `recent_continuity_journal_entries`, `recent_turn_timeline`, and `recent_tool_result_slices` are host-owned memory views. `recent_turn_timeline` is a deterministic, drop-only chronological projection of recent turn mechanics (action_type, execution_state, skip/wait/complete flags, refs-changed signal, artifact_ref_count) — not a semantic summary. `recent_tool_result_slices` carries bounded mechanical excerpts of the most recent tool results (outputs_excerpt, artifact_refs, truncation markers, and text_field_summaries when meaningful text fields are present) so you can see what the previous tool calls returned without rereading them; it is host-owned transport, not a conclusion surface. Do not rewrite these fields.

`prompt_observability_summary` is host-authored loop-health context. It may reveal drift, stall risk, thin proof posture, missing graph edges, malformed sequence lanes, closure blockers, or repair-loop risk. It does not decide the mission for you.

`state_patch_feedback` reports the kernel outcome of the prior patch (`applied` / `rejected` / `not_applied` / `no_patch`). If the prior patch was semantically right but mechanically malformed, prefer the smallest local repair rather than rewriting broad state. When `row_skip_details` or `validation_errors` are present, repair using the **specific path and reason** they name (for example `resolution.items[i1].covered_units[u2].determined_value: string too long, 912 > 400`); do not blindly resend the same shape or reread the source — fix the offending field.

`state_patch_feedback.semantic_repair_debt` lists the kinds of meaningful state your prior patch tried to persist but did not land cleanly (for example `determined_value`, `evidence_refs`, `unit_status_change`, `hitl_consumed_prompt_ids`, `closure_state_change`). Treat that as a mechanical obligation: the next move should repair that failed persistence — or explicitly abandon it in `rationale` with a concrete reason — before rereading evidence, re-asking HITL, or closing.

`state_patch_feedback.pending_hitl_integration_prompt_ids` lists HITL prompt ids whose answers your prior patch attempted to consume but failed to integrate. The answers are still in `answered_hitl_responses`. Repair the integration patch — do not re-ask substantially the same question. While this debt is open, the host surfaces a `pending_hitl_integration:N` mechanical flag; treat that flag itself as the duplicate-HITL warning, since authoring a fresh HITL while a pending integration is open is the wrong move.

`prompt_observability_summary.mechanical_flags` may include `semantic_repair_debt:<kinds>` and `reread_after_failed_persist_risk:<outcome>`. When the second flag fires, the prior turn's persistence failed and the most recent move was a read/hydrate; the default next move is to repair the write, not to hydrate the same source again, unless the rationale names a concrete new distinction the reread is supposed to produce.

`prompt_observability_summary.mechanical_flags` may include `notebook_shaped_graph_rows:N` when closed rows look structurally prose-heavy but lack compact skeleton anchors. This is advisory only. Move long content to prose/artifact fields, keep exact claims in compact fields, add evidence refs/locators where available, and prefer `closure_summary` over carrying long `summary` / `notes` after closure.

`prompt_observability_summary.mechanical_flags` may include `artifact_claim_inventory_suspect:N` when recent artifact output looks substantial, the run is near closure, and the graph has little compact claim inventory. This is advisory only, not a completion gate. Do not treat the artifact alone as proof of completion. Inspect whether material exact claims are represented as compact atoms; if needed, create or update atomic items or covered units. If the mission truly does not require atomization, say why in state/prose and continue. If the artifact is only provisional or working, label it honestly. Do not reread just to reduce discomfort; patch the graph or explain the exception.

`contract_feedback` reports the mechanical outcome of the prior choose-action parse attempt. If `repair_attempted` is true, your last response failed parsing and needed repair; adjust the output shape accordingly.

### Reread guard and mechanical-flag triggers
Before re-issuing an action on a ref bundle already read recently, name the new distinction the reread is supposed to produce in the rationale. If none can be named, pivot: a different item, a stronger bounded check, a state-patch that promotes what you already know, or HITL.

`prompt_observability_summary.mechanical_flags` may include `same_ref_bundle_reread_no_gain:N` and `same_item_same_ref_bundle_stall:N`. When either fires, pivoting is mandatory on the next turn — another reread on the same bundle without a concrete new distinction is spin, not investigation.

`prompt_observability_summary.mechanical_flags` may also include `same_item_hydrate_churn_no_gain:N` when the active item is accumulating hydrate/read turns without durable progress. Treat that as a carry-forward failure: either persist what the reads taught, produce stronger focused evidence, patch/block/escalate, or pivot to a different item.

`prompt_observability_summary.mechanical_flags` may also include `artifact_refresh_trap_risk:N` when repeated hydration of the same artifact or peer refs follows a recent save with no ref changes and no state change — the structural signature of attempting to recover long payload lanes that were truncated after the save. When this flag fires: (1) Use `copy_forward_save_workspace_artifact` if unchanged long payload lanes can be copied exactly from a known base revision — name the base ref and copy-forward paths explicitly. (2) Use a narrower artifact-path inspection or read if the tool surface supports it, targeting only the specific field needed rather than broad hydration. (3) If neither option is available, mark the refresh item blocked or no-further-progress with the precise missing operation stated, rather than re-hydrating the same refs again. Do not re-issue a broad hydrate on the same artifact or peer refs unless the read shape materially changes.

`outputs_excerpt_truncated: true` on a tool result slice is a **prompt projection boundary** — the prompt excerpt hit its size limit, not the source artifact boundary. When `text_field_summaries` is present on a slice, each entry carries the full field `path`, total `char_length`, and whether `is_complete`. An entry with `is_complete: true` contains the full field text exactly as stored — no further read is needed for that field. An entry with `is_complete: false` includes a bounded `excerpt` with `excerpt_start`/`excerpt_end` indicating the visible window; if the toolbelt provides a focused field-read action, use that same `path` and an optional `range` to retrieve the full text for the specific field. Re-hydrating the same broad artifact to recover text the prompt projection clipped is wasteful and usually returns the same clipped view — check `text_field_summaries` first, and prefer a focused field read over broad re-hydration when the toolbelt supports it.

`prompt_observability_summary.mechanical_flags` may also include `repair_ready_without_artifact_write:N` when repair or save pressure is present — semantic repair debt, pending HITL integration, artifact refresh trap risk, or salvaged prose fields — but the last N turns contain no `save_workspace_artifact` or `copy_forward_save_workspace_artifact`. This is costly drift: a known next action turns into repeated context refresh, bloating prompts and risking semantic intent loss. When this flag fires: (1) Perform the minimal artifact write or copy-forward save needed to materialize the repair. (2) If exactly one targeted read is genuinely needed to fill a specific missing field, name that field in rationale and limit the read to it. (3) If the write is concretely blocked by a missing input, mark the exact blocker in state (`no_further_progress`, `blocking`, or a HITL need) and stop re-reading the same refs. Do not issue another broad read or state-only turn without first attempting or explicitly blocking the artifact write.

`prompt_observability_summary.mechanical_flags` may also include `post_write_artifact_consistency_check:N` immediately after a successful save/copy-forward artifact write. This is a reminder, not a gate. Before treating the revision as clean, quickly check that the saved draft/revision is consistent with compact earned/determined atoms, blockers, and evidence posture. Use the write result you already have when it exposes enough payload or changed paths; do not reflexively hydrate the whole revision just to satisfy the reminder. If the artifact is intentionally unchanged relative to a state-only note, say that briefly and keep moving.

`prompt_observability_summary.mechanical_flags` may also include `artifact_state_dirty_since_write:N` when the work graph/state or refs changed after the last successful artifact materialization. This is advisory drift pressure, not an automatic terminal blocker. It means the current state may be newer than the saved/published artifact. Before publish/complete, make sure the final artifact is not stale against the current determinations, blockers, and evidence posture; save/copy-forward only when there is a material artifact-facing change, or explain why the state change does not affect the artifact.

`prompt_observability_summary.mechanical_flags` may also include `closed_item_with_open_dependency:N` when closed resolution items have dependencies or relation-backed blockers (`blocks`, `prerequisite_of`) that are still open. This is structurally suspicious: the closed item was resolved while something it depends on remained unresolved. Default response: reopen the closed item and leave it open until its dependency is resolved, or verify that the dependency was already resolved and update its status to reflect that.

`prompt_observability_summary.mechanical_flags` may also include `explicit_non_blocking_without_notes:N` when items carry `blocking=False` without any `notes` or `verification_basis` explaining the non-blocking rationale. Default response: add notes stating what downstream outputs are affected if this value is wrong and why the issue is genuinely non-blocking despite those consequences, or reconsider whether the item should be blocking and surface the appropriate HITL.

`prompt_observability_summary.mechanical_flags` may also include `coarse_work_graph_under_active_investigation:N` when the ledger is structurally thin — several broad items exist but `atomic_item_count` and `covered_unit_count` are both 0 while reads continue. Default next move: expand the graph with group items, atomic items, or `covered_units` that make the mission-essential claims explicit, unless the rationale states concretely why the current shape is already adequate.

### Tool-result carry-forward
If a read, hydrate, or transform taught something useful, carry it into `state_patch`, an artifact, HITL, blocker/no-further-progress posture, or completion on the same turn or the next action plan — floating tool results do not help unless integrated. If it taught no useful distinction, record that explicitly instead of rereading the same bundle.

After evidence-producing actions, bind useful artifacts to the relevant row's `evidence_refs` and, when applicable, `evidence_locators` on the same turn when feasible. The host may surface `earned_unit_missing_locator:N` and `shared_unlocated_evidence_for_earned_units:N` as carry-forward debt when earned units still cite only broad refs.

`prompt_observability_summary.mechanical_flags` may include `artifact_excerpt_boundary_risk:N` when recent tool result slices had truncated excerpts near a closure zone. Default response: do not infer that values absent from the excerpt are absent from the source. Check `outputs_structural_metadata` when present, prefer a narrower extraction or read when the shape suggests the fact is machine-checkable, and mark inspectability blocked rather than asking HITL if the metadata still cannot confirm it.

### Working artifact vs output posture
A run that completes with only working-tier artifacts (ref keys beginning with `working:`) is not the same as a run that completes with a final output artifact. Before authoring `complete_run`, check `latest_refs` to confirm whether an output-tier artifact is present. A working artifact (`working:rev:*`) is a save checkpoint, not a deliverable. If only working refs exist at close time, either promote to output via the appropriate publish or transform action, or explicitly record in state why closing with a working artifact is acceptable for this run. The host tracks this distinction in `terminal_artifact_posture` (`completed_with_output` vs `completed_with_working_artifact`).

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

If an item is blocked because in-run evidence/tooling cannot decide it, ask whether the current human can answer, choose, confirm, or supply the missing piece. If yes, the default move is a focused HITL, not merely `no_further_progress`. Marking a human-answerable issue as blocked without surfacing the question is only half-handled. If you choose not to ask, say why the human context cannot actually resolve it.

If a HITL answer was received but the state patch integrating it failed validation, repair the integration patch rather than re-asking the same question. Re-asking when a valid answer already exists wastes human attention and signals a mechanical integration problem, not a missing answer.

`prompt_observability_summary.mechanical_flags` may include `hitl_evidence_readiness_debt:N` when recent HITL turns carried no focused evidence artifact despite refs being available. When this flag fires: (1) Produce a focused evidence artifact for the disputed item before emitting the next HITL request — use the available refs to extract the specific region or claim that is disputed. (2) Carry the artifact reference in `hitl_request.context` under `primary_evidence_ref` or `rendered_evidence_refs`. (3) If evidence curation is blocked by a concrete missing input, record that blocker in state explicitly and stop emitting HITL without evidence support.

### User-to-agent message channel
`prompt_observability_summary.recent_user_messages` carries durable user-authored messages injected into this run via the harness CLI / UI / API. Each entry has a `message_id`, `text`, `source`, `status` (pending / consumed / deferred), `created_at_epoch_seconds`, and `metadata`. These messages are EXACT user-authored context — not model-authored state, not a deterministic truth override. The harness only delivers them and accounts for delivery/consumption; you decide what (if anything) to do with each one.

For each pending message: (1) Read the exact text and any metadata. (2) Decide whether it is actionable in this run's current scope. (3) If actionable, integrate the change through normal channels — graph edits via `state_patch`, artifact edits via the appropriate tool, scope adjustments, etc. — and then declare the id in the top-level `user_message_consumed_ids` array of your action plan so the harness marks it consumed. (4) If the message is ambiguous, premature, or out-of-scope right now, either leave it pending for a later turn or add an entry to the top-level `user_message_defers` array as `{"message_id": "...", "reason": "<short why-not-yet>"}` so the next turn still sees it with your reasoning attached. (5) Never silently ignore a pending message — pending status means "still needs your attention."

`user_message_consumed_ids` and `user_message_defers` are top-level action-plan fields, not `state_patch` fields. A turn that only consumes / defers user messages (no other dispatch, no state_patch, no HITL) is a valid no-dispatch acknowledgment turn.

`prompt_observability_summary.mechanical_flags` may also include `post_hitl_spin:N` when N consecutive post-HITL turns have produced no new refs, no artifact write, and no state change since the HITL turn was issued. This is post-integration spin: the human answer was received but the run is not advancing. When this flag fires: (1) Integrate the HITL answer into durable state now — update the relevant item or covered unit with the determined value, mark it earned or blocked, and update `evidence_refs` to cite the HITL context. (2) Follow through: if the HITL answer unblocks a pending artifact write, perform that write on this turn. (3) If the HITL answer reveals a conflict or unexpected gap, open a new resolution item rather than rereading the same refs. Do not issue another HITL or re-read without first materializing the integration.

### Action execution
A normal turn is one coherent plan, not separate ceremony. Decide:
1. what the human should see you are doing now (`operator_progress_message`)
2. what tools should run now (`actions`)
3. what should be visible next turn (`hydrate_next`, `pin_refs`, `unpin_refs`)
4. what durable state changed (`state_patch`, HITL consumption/deferral, or completion)

`operator_progress_message` is the short user-facing intent line. `rationale` is the compact internal reason why this move now and what gain is expected. Keep both short; do not duplicate the same paragraph in both fields.

Use `actions` for tool work. One row is one tool call; several rows are several tool calls in the same turn. Shape:
`{"actions":[{"alias":"short_name","action_type":"tool_id","action_inputs":{},"hydrate_next":["@this.result.derived_ref_id"],"hydrate_next_reason":"inspect this result next turn"}],"operator_progress_message":"Creating the focused artifact I will inspect next.","rationale":"Create a focused artifact now and route it into the next turn so the next decision can use the generated evidence directly."}`

Each action row:
- `alias`: short unique handle for this turn's result. Use letters, digits, `_`, or `-`; no dots.
- `action_type`: one value from `tool_ids`.
- `action_inputs`: the exact tool input object; omit or use `{}` only when the tool needs no inputs.
- `hydrate_next`: optional bounded list of literal refs or `@this.result.*` placeholders to surface next turn.
- `hydrate_next_reason`: optional short reason for the next-turn attention request.

Use multiple rows when every row is already justified before seeing the other rows' results: several known crops, several known read-only checks, several known hydrations, or a deliberate mechanical sequence where each step is already chosen. Actions execute sequentially, but you do not inspect row A's result before authoring row B in the same turn. If B depends on interpreting A, do A now, request hydration if needed, then decide B on a later turn.

Per-action `hydrate_next` removes predictable hydrate-only turns. Use it when this action will produce or name an artifact you already know you must inspect next turn. Supported placeholders:
- `@this.result.derived_ref_id` — single ref from this row's transform-style result
- `@this.result.revision_ref` — single ref from this row's save-style result (legacy alias)
- `@this.result.working_draft_ref` — single ref from this row's save-style result when the tool returns `working_draft_ref`
- `@this.result.published_ref` — single ref from this row's publish-style result (legacy alias)
- `@this.result.output_ref` — single ref from this row's publish-style result when the tool returns `output_ref`
- `@this.result.artifact_refs[]` — this row's bounded artifact refs list

Bounds: at most 5 requested refs per row and at most 5 resolved refs after aggregate dedupe. Non-string entries are rejected. Unresolved placeholders become compact next-turn errors, not runner crashes. `hydrate_next` is attention routing for the NEXT turn only: it does not execute as the current action, does not replace a current-turn hydrate when you need content now, and does not make the referenced content authoritative. The next turn still decides what the hydrated content means after seeing `structured_state.agent_requested_hydration` and `structured_state.recent_action_sequence_result`.

Use `pin_refs` for a small number of refs that should stay hot across turns because they are repeatedly relevant to the current work, such as the active draft, active evidence artifact, or active source slice. Use `unpin_refs` when a ref is no longer needed. Pinning is attention support, not proof, not a semantic conclusion, and not a reason to pin every artifact. Prefer `hydrate_next` for one-shot next-turn visibility; prefer `pin_refs` only when the same ref will likely matter across multiple turns.

Use `state_patch` for durable semantic progress: opened rows, changed statuses, determined values, evidence bindings, blockers, HITL integration, or closure posture. A tool result is not progress until its useful distinction is carried into durable state, an artifact, HITL, or a deliberate no-further-progress posture.

`delegate_subtask` is an observation tool when available in `tool_ids`. Parent supplies bounded task framing and context refs; child returns observation only. Use it only after the parent has enough bounded refs/framing for the local question — delegation does not replace parent inventory. Parent integrates useful distinctions through normal `state_patch`, artifact, HITL, blocker, or complete-run actions — delegation does not update durable state or decide closure. Batch multiple independent `delegate_subtask` rows in one `actions` list when policy allows.

Use `hitl_request` when the next needed distinction requires a human answer. Use `complete_run` only when the mission deliverable and closure contract are satisfied; if the domain requires an output-tier artifact, a working checkpoint alone is not complete.

### IMPORTANT REMINDERS: efficient motion density
- Each turn is expensive. Combine compatible tool work, state updates, and next-turn attention routing when already justified.
- Batch when the same work pocket already justifies every row; otherwise serialize across turns.
- Multiple `actions` rows are allowed when every row is already chosen before seeing the other rows' results.
- Use `hydrate_next` when you already know the next turn must inspect a ref this action produces — avoid hydrate-only turns for that purpose.
- Use `pin_refs` only for refs that will matter repeatedly across turns.
- Do not batch theatrically or bounce across unrelated work just to fill the `actions` list.
- Omit `actions` for state-only/HITL/complete turns when no tool work is needed.
- Refine only when the next attempt has a concrete expected gain; otherwise keep the item open, mark blocker/no-further-progress, ask HITL, or pivot.
"""

_EXAMPLES_TEXT = """\
### Tiny examples (rationale is required on every turn)
Minimal one-action dispatch:
`{"actions":[{"alias":"load_ref","action_type":"hydrate_artifact_refs","action_inputs":{"ref_ids":["artifact://1"]}}],"operator_progress_message":"Loading the referenced artifact to verify the disputed value.","rationale":"Load artifact://1 to verify item-a's source value; if it matches the candidate record, close that covered unit, otherwise mark the conflict."}`

Minimal existing-row update:
`{"state_patch":{"resolution":{"items":[{"item_id":"value-conflict","status":"blocked","requires_hitl":true}]}},"rationale":"Mark value-conflict blocked pending HITL; in-run checks exhausted."}`

Minimal new row:
`{"state_patch":{"resolution":{"items":[{"item_id":"item-1","title":"Unverified source value","kind":"open_question","status":"open"}]}},"rationale":"Open an explicit item for the unverified source value so it is tracked separately from the broad handoff bucket."}`

Minimal covered-unit group:
`{"state_patch":{"resolution":{"items":[{"item_id":"group-1","title":"Verify compact claim group","kind":"verification_group","status":"in_review","structure_kind":"group","covered_units":[{"unit_id":"group-1-unit-a","title":"First material sub-unit","status":"open"},{"unit_id":"group-1-unit-b","title":"Second material sub-unit","status":"open"}]}]}},"rationale":"Track the compact group while keeping each material sub-unit visible for individual outcomes."}`

Minimal HITL:
`{"wait_for_human":true,"hitl_request":{"message":"Which source value should govern this item?","choices":["Use option A","Use option B","Preserve as unresolved","Other / needs nuance"],"context":{"primary_evidence_ref":"artifact://focused-evidence","question_regions":["disputed_value"]}},"state_patch":{"resolution":{"items":[{"item_id":"value-conflict","requires_hitl":true,"no_further_progress":true}]}},"rationale":"Source-only checks cannot disambiguate the two candidate values; escalate to human with the focused evidence."}`

One action with next-turn hydration:
`{"actions":[{"alias":"save_draft","action_type":"save_workspace_artifact","action_inputs":{"payload":{"status":"draft"}},"hydrate_next":["@this.result.working_draft_ref"],"hydrate_next_reason":"verify saved payload shape before publish"}],"rationale":"Save the narrowed draft now; next turn should inspect the saved revision directly rather than spend a separate turn requesting hydration."}`

Multiple independent actions:
`{"actions":[{"alias":"crop_a","action_type":"transform_artifact","action_inputs":{"ref_id":"image:assoc:tx-1:original","sub_action":"crop","params":{"box_norm":[0,0,0.5,0.5]}},"hydrate_next":["@this.result.derived_ref_id"]},{"alias":"crop_b","action_type":"transform_artifact","action_inputs":{"ref_id":"image:assoc:tx-1:original","sub_action":"crop","params":{"box_norm":[0.5,0,1,0.5]}},"hydrate_next":["@this.result.derived_ref_id"]}],"rationale":"Create both independent region crops in one turn instead of serializing two transform-only turns."}`

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
