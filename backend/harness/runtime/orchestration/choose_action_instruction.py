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
Do not copy host-maintained fields such as schema_version or updated_at_epoch_seconds into state_patch.

`resolution.items` may include fields such as:
`item_id`, `title`, `kind`, `status`, `determination`, `summary`, `verification_basis`, `next_needed_step`, `completion_criteria`, `structure_kind`, `sequence_scope`, `sequence_index`, `blocking`, `requires_hitl`, `no_further_progress`, `dependencies`, `evidence_refs`, `notes`, `materiality`, `scope`, `provenance`, `covered_units`, `opaque_payload`.

`structure_kind` is optional:
- use `atomic` for the smallest mission-relevant independently-resolvable unit
- use `group` only when one bounded verification move can honestly verify the whole group, OR when it is more honest to keep one item that explicitly stands over a small set of sub-units
- a group item's independently-reviewable sub-units may be authored in one of two shapes — pick whichever is more honest for the case, but do not mix both for the same sub-unit set:
  - (a) separate atomic `resolution.items`, one per sub-unit, connected to the group via `resolution.relations` such as `subclaim_of`; or
  - (b) a single group item carrying those sub-units in its `covered_units` list (one-level, non-recursive)
- shape (a) is preferable when sub-units are large enough to deserve their own full item with independent `status`/`determination`/`summary`/`verification_basis` and cross-linking relations
- shape (b) is preferable when sub-units are small enough that a one-level sub-ledger on the group captures their earned state cleanly without inflating the top-level item list

`covered_units` is the one-level sub-ledger on a resolution item. It is a generic, non-recursive list of the smallest mission-relevant units the item stands over. Shape: `[{unit_id, title, kind?, status?, summary?, determination?, verification_basis?, next_needed_step?, evidence_refs?, materiality?, label?, value_kind?, candidate_values?, determined_value?, opaque_payload?}]`. The runtime merges covered_units by `unit_id`; per-field overlay is applied for existing units, and new units must carry `unit_id` and `title`. Emitting an empty `covered_units` list does not wipe prior units — send only deltas. When a group item actually stands over independently-reviewable sub-units and shape (b) above is the chosen representation, author those sub-units as `covered_units` so each one's earned state is visible, and close or explicitly block each material unit before closing the group. Do not hide critical sub-units only inside summary prose.

Compact value fields on a covered unit:
- `label`: short UI-grade label; renderers fall back to `title` when absent.
- `value_kind`: optional hint for the kind of value this unit carries (e.g. `bearing`, `distance`, `date`, `decision`, `status`, `text_span`). No strict enum.
- `candidate_values`: known possibilities / options / outcomes so far. This list is **not exhaustive**; if another possibility appears, add it. Do not close a unit just because one candidate currently looks preferable.
- `determined_value`: the earned resolved value/outcome. Author this only when the unit is actually earned — which also means `verification_basis` and `evidence_refs` support it. A disputed exact-value unit should not be marked `earned` without `determined_value` plus supporting evidence.

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

`state_patch_feedback` reports the kernel outcome of the prior patch (`applied` / `rejected` / `not_applied` / `no_patch`). If the prior patch was semantically right but mechanically malformed, prefer the smallest local repair rather than rewriting broad state.

`contract_feedback` reports the mechanical outcome of the prior choose-action parse attempt. If `repair_attempted` is true, your last response failed parsing and needed repair; adjust the output shape accordingly.

### Reread guard and mechanical-flag triggers
Before re-issuing an action on a ref bundle already read recently, name the new distinction the reread is supposed to produce in the rationale. If none can be named, pivot: a different item, a stronger bounded check, a state-patch that promotes what you already know, or HITL.

`prompt_observability_summary.mechanical_flags` may include `same_ref_bundle_reread_no_gain:N` and `same_item_same_ref_bundle_stall:N`. When either fires, pivoting is mandatory on the next turn — another reread on the same bundle without a concrete new distinction is spin, not investigation.

`prompt_observability_summary.mechanical_flags` may also include `same_item_hydrate_churn_no_gain:N` when the active item is accumulating hydrate/read turns without durable progress. Treat that as a carry-forward failure: either persist what the reads taught, produce a stronger focused evidence artifact, patch/block/escalate, or pivot to a different item.

### Defensible evidence and read carry-forward
For an exact material claim, prefer the evidence artifact that makes the claim as directly and undeniably auditable as the available tooling allows. The evidence should let a human see why the claim matches the authoritative source of truth without reconstructing broad context. If a focused crop, zoom, excerpt, trace, query result, test output, screenshot, log excerpt, code pointer, or annotated artifact can make the claim obvious, create or use that before marking the unit earned.

Work as if a skeptical reviewer may challenge the claim later: protect the run from being falsely accused of incorrect work by carrying the clearest available proof shape with the earned claim. A closed/earned atomic item or covered unit should usually have `evidence_refs` that let a human audit the exact claim directly; if no such focused evidence can be produced, say that limitation in `verification_basis` rather than pretending certainty is stronger than it is.

A read, hydrate, or transform is not complete merely because you looked at something. If it taught a useful distinction, persist that distinction immediately in `resolution.items`, `covered_units`, mission state, an output artifact, or a concise `continuity_journal_entry`. If it taught no useful distinction, promote the no-gain result into state (`no_further_progress`, blocker, HITL need, or narrowed next step) instead of rereading until the same uncertainty reappears.

### Itemization and per-item resolution
Before leaving orientation and after any fresh read, make the work explicit: each mission-essential claim, defect, ambiguity, dependency, or deliverable becomes a row in `resolution.items` (atomic), or an honest group node whose material sub-units are explicit as `covered_units` or separate related items. Every `mission.success_conditions` row should have at least one item that can earn it.

Each `resolution.items` row is a mini-mission: orient to it, run the strongest bounded check available *for that item*, then promote the new distinction into its authored fields or into the relevant `covered_units` row (`status`, `determination`, `summary`, `verification_basis`, `completion_criteria`, or a more granular unit if the check split the claim). A closed item should be able to answer, in its own fields or covered-unit fields, what verified each material unit it stands over.
"""

_HITL_TEXT = """\
### HITL transport
`hitl_request`: optional generic human prompt transport `{message, choices, context, opaque_payload?, prompt_id?}`.
`wait_for_human=true` is the blocking form: the loop pauses until feedback arrives.
`wait_for_human=false` with `hitl_request` is the async form: the request is emitted while the loop continues.
`hitl_consumed_prompt_ids`: optional array of prompt_id strings you actually integrated; host removes matching answered rows only.
Envelope `hitl_state`, `pending_hitl_requests`, and `answered_hitl_responses` are host-owned.

Use `hitl_request.context` to carry the focused evidence packet the human needs. Preferred keys when relevant: `evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, `question_regions`, and `notes`.
Before emitting HITL, prefer the most focused evidence packet the current tooling can produce for the disputed item.
Add `state_patch` only when the HITL turn also needs a durable state delta.
Ask the smallest question whose answer can be integrated into a specific item or covered unit. If the issue is a choice among alternatives, make the choices direct outcomes (for example: `Use option A`, `Use option B`, `Preserve as unresolved`, `Other / needs nuance`) rather than abstract descriptions that leave the operator guessing what decision is needed.
When bounded choices could force a false answer, include a safe fallback such as `Unable to determine` or `Other / needs nuance`.
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
