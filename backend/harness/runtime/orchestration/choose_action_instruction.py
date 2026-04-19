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
- Missing prose fields means no prose delta.
- Do not author transport-only ceremony such as `idempotency_key`; the host owns it.

Minimal valid turn shapes:
- dispatch: `{"action_type": "tool_id", "action_inputs": {...}}`
- state-only delta: `{"state_patch": {...}}`
- async HITL: `{"hitl_request": {...}}` or `{"hitl_request": {...}, "state_patch": {...}}`
- blocking HITL: `{"wait_for_human": true, "hitl_request": {...}}` or `{"wait_for_human": true, "hitl_request": {...}, "state_patch": {...}}`
- complete: `{"complete_run": true, "state_patch": {...}}`
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
- `continuity_journal_entry`: optional non-empty JSON object for genuinely new continuity only. Author only the raw payload you want stored; do not wrap it inside `author_payload`, `kernel_turn_index`, or other host-shaped keys.
- `operator_progress_message`: optional short user-facing status line. Omit it unless the user-facing status actually changed.
- `rationale`: optional. Use prose only when it adds durable information not already captured structurally.
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
`item_id`, `title`, `kind`, `status`, `determination`, `summary`, `verification_basis`, `next_needed_step`, `completion_criteria`, `structure_kind`, `sequence_scope`, `sequence_index`, `blocking`, `requires_hitl`, `no_further_progress`, `dependencies`, `evidence_refs`, `notes`, `materiality`, `scope`, `provenance`, `opaque_payload`.

`structure_kind` is optional:
- use `atomic` for the smallest mission-relevant independently-resolvable unit
- use `group` only when one bounded verification move can honestly verify the whole group
- if a row uses `structure_kind="group"`, keep its atomic sub-items explicit as separate `resolution.items` and connect them with `resolution.relations` such as `subclaim_of`
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
Envelope fields such as `compacted_continuity_summary`, `recent_continuity_journal_entries`, and `recent_turn_timeline` are host-owned memory views. `recent_turn_timeline` is a deterministic, drop-only chronological projection of recent turn mechanics (action_type, execution_state, skip/wait/complete flags, refs-changed signal, artifact_ref_count) — not a semantic summary. Do not rewrite these fields.

`prompt_observability_summary` is host-authored loop-health context. It may reveal drift, stall risk, thin proof posture, missing graph edges, malformed sequence lanes, closure blockers, or repair-loop risk. It does not decide the mission for you.

`state_patch_feedback` reports the kernel outcome of the prior patch (`applied` / `rejected` / `not_applied` / `no_patch`). If the prior patch was semantically right but mechanically malformed, prefer the smallest local repair rather than rewriting broad state.

`contract_feedback` reports the mechanical outcome of the prior choose-action parse attempt. If `repair_attempted` is true, your last response failed parsing and needed repair; adjust the output shape accordingly.
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
When bounded choices could force a false answer, include a safe fallback such as `Unable to determine` or `Other / needs nuance`.
"""

_EXAMPLES_TEXT = """\
### Tiny examples
Minimal dispatch:
`{"action_type":"hydrate_artifact_refs","action_inputs":{"ref_ids":["artifact://1"]}}`

Minimal existing-row update:
`{"state_patch":{"resolution":{"items":[{"item_id":"range-conflict","status":"blocked","requires_hitl":true}]}}}`

Minimal new row:
`{"state_patch":{"resolution":{"items":[{"item_id":"item-1","title":"Unverified range","kind":"open_question","status":"open"}]}}}`

Minimal HITL:
`{"wait_for_human":true,"hitl_request":{"message":"Which range governs?","choices":["Range 75 governs","Range 74 governs","Preserve contradiction as unresolved","Other / needs nuance"],"context":{"primary_evidence_ref":"artifact://crop-1","question_regions":["north_range_label"]}},"state_patch":{"resolution":{"items":[{"item_id":"range-conflict","requires_hitl":true,"no_further_progress":true}]}}}`

Minimal complete:
`{"complete_run":true,"state_patch":{"mission":{"work_universe_posture":"audited"}}}`
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
