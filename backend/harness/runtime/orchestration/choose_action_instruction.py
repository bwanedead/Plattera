"""Canonical instruction text for the kernel choose-action LLM turn.

Extracted here to keep ``llm_prompt_builder`` focused on envelope assembly.

Surface.py doctrine blocks own the world-model, generic method, self-audit,
and anti-pattern doctrine.  This instruction carries only the mechanical
envelope contract: output schema, turn mechanics, state_patch schema, and
observability signals.
"""

from __future__ import annotations

ACTION_PLAN_SCHEMA_TEXT: str = (
    "Return exactly one JSON object matching this schema:\n"
    "{"
    '"action_type": string|null, '
    '"action_inputs": object, '
    '"idempotency_key": string, '
    '"skip_execution": boolean, '
    '"wait_for_human": boolean, '
    '"complete_run": boolean, '
    '"rationale": string|null, '
    '"state_patch": object|null, '
    '"continuity_journal_entry": object|null, '
    '"operator_progress_message": string|null, '
    '"hitl_request": object|null, '
    '"hitl_consumed_prompt_ids": array|null'
    "}\n"
)

_MECHANICAL_HEADER = (
    "Read the doctrine_blocks, surface_packet, run_context, and structured_state in the JSON packet below, "
    "then choose one next move that makes truthful, cumulative, evidence-justified progress on the mission.\n"
)

_TURN_CONTRACT_TEXT = """\
### Turn contract
continuity_journal_entry: optional non-empty JSON object (append-only continuity: observations, decisions, open threads, expected next); use it when the turn produced observations, decisions, open threads, or next-step understanding worth carrying forward. Omit it (null) when the turn has no meaningful continuity delta. Author only the raw continuity payload you want stored; do not wrap it inside `author_payload`, `kernel_turn_index`, or similar host-shaped envelope keys.
operator_progress_message: optional short user-facing status line; null keeps the prior message.

No-dispatch state-authoring turns are valid. If you need to update durable state before another dispatch, you may return an explicit no-dispatch turn with action_type null, action_inputs {}, skip_execution true, wait_for_human false, complete_run false, and a non-null state_patch.
"""

_STATE_PATCH_MECHANICS_TEXT = """\
### state_patch mechanics
Optional state_patch shape:
- resolution?: { active_item_id, items, relations, opaque_payload }
- mission?: { objective, active_mode, work_universe_posture, blocker_summary, verification_summary, waiting_summary, continuity_summary, mission_mode_summary, high_signal_artifact_refs, success_conditions, closure_state, opaque_payload }

Do not put latest_refs_summary, terminal_summary, or prompt_observability_summary in mission; those are host-owned.
The runtime merges mechanically:
- resolution items merge by item_id
- mission.success_conditions merge by condition_id
- closure_state dimensions merge by dimension_id
- only fields you include are overwritten

resolution.items shape:
[{item_id, title, kind, status, determination?, summary?, verification_basis?, next_needed_step?, completion_criteria?, structure_kind?, sequence_scope?, sequence_index?, blocking?, requires_hitl?, no_further_progress?, dependencies?, evidence_refs?, notes?, materiality?, scope?, provenance?, opaque_payload?}]
- `structure_kind` is optional: use `atomic` for the smallest mission-relevant independently-resolvable unit, and `group` only when one bounded verification move can honestly verify the whole group.
- If a row uses `structure_kind="group"`, keep its atomic sub-items explicit as separate `resolution.items` and connect them through `resolution.relations` (for example `subclaim_of` or `aggregates`). The group row is a summary node, not the only place the details live.
- `sequence_scope` and `sequence_index` are optional ordering metadata for a real ordered lane of work or review. Use them only when ordered traversal is genuinely relevant.
- If order is semantically required, also author a relation such as `prerequisite_of` or `blocks`. Sequence metadata helps traversal and presentation; it is not the dependency graph.
- Inside one ordered lane, keep the shared `sequence_scope` stable and `sequence_index` ascending. If order does not matter, omit sequence metadata rather than inventing it.
- If different details could end in different dispositions, they are not one atomic item. Broad buckets are for orientation, not for earned closure.
- Use `materiality` to keep rigor honest. High-impact items should normally prefer atomic representation and the strongest available verification method that materially increases certainty.
- `blocking`, `requires_hitl`, `no_further_progress` on a resolution item are parallel in meaning to the same-named fields on closure_state dimensions; use them to make blocker status structurally explicit instead of burying it in summary prose.
- `requires_hitl=true` means the item's resolution still needs human input. It should remain true after a HITL is emitted and stay true until the human answer has actually been integrated into state or the blocker has dissolved for some other reason. Emitting the prompt is not the same as receiving the answer; clearing the flag on emission would erase a live blocker and weaken later observability.
- The host treats `requires_hitl=true` on any resolution item as a generic blocker for complete_run and publish under closure enforcement, mirroring closure_state.requires_hitl. That is intentional: if human input is still outstanding on a material item, the run is not ready to complete or publish.

resolution.relations shape:
[{source_item_id, target_item_id, relation_type, summary?, opaque_payload?}]
- Use relations to make the blocker/dependency graph explicit. `relation_type` is free-form but honest; common examples include `subclaim_of`, `aggregates`, `blocks`, `prerequisite_of`, `supports`, and `covers`.
- When any item carries `blocking=true`, authoring at least one relation that explains what it blocks (another item, a success condition, or a closure dimension, referenced by its id as target_item_id) keeps the dependency readable from state rather than from prose.

mission.success_conditions shape:
[{condition_id, title, status, determination?, summary?, completion_criteria?, verification_basis?, next_needed_step?, evidence_refs?, dependencies?, opaque_payload?}]

closure_state shape:
{ overall_status?, summary?, ready_to_publish?, ready_to_close?, requires_hitl?, no_further_progress?, dimensions?: [{dimension_id, title, status, determination?, summary?, blocking?, requires_hitl?, no_further_progress?, evidence_refs?, verification_basis?, next_needed_step?, opaque_payload?}], opaque_payload? }

mission.work_universe_posture allowed values: `initial` | `partial` | `believed_adequate` | `audited`
`audited` is the only posture that satisfies the mechanical complete/publish gate.
Do not copy host-maintained fields such as schema_version or updated_at_epoch_seconds from visible state into state_patch.
Summary-field shorthand: mission summary fields (blocker_summary, verification_summary, waiting_summary, continuity_summary, mission_mode_summary) accept a plain string and normalize to {"summary": "..."} automatically. Example: "blocker_summary": "Need clearer image evidence".
Use only canonical `state_patch.mission` and `state_patch.resolution`. Do not author alias top-level keys such as `mission_state` or `resolution_state`; they are repair-only backstops, not the contract.
"""

_OBSERVABILITY_AND_REPAIR_TEXT = """\
### Observability and repair signals
Envelope fields compacted_continuity_summary, recent_continuity_journal_entries, recent_kernel_step_records, and recent_kernel_step_result_records are host-labeled memory. The three recent_* lists cover the same last N distinct kernel turns from different mechanical views; author replacements only via continuity_journal_entry / compaction, not by editing those envelope keys.

prompt_observability_summary is host-authored loop-health and proof-coverage context. Treat it as mechanical context that may reveal drift, stall risk, thin proof posture, closure-readiness blockers, or repair-loop risk; it does not decide what matters for you.
It may also expose structural rigor warnings such as group nodes with no explicit subclaims, critical closed items with thin proof, blocking items that lack graph edges, or malformed sequence lanes.

state_patch_feedback reports the kernel outcome of the prior patch (applied / rejected / not_applied / no_patch). When outcome is applied but some rows were dropped, look for skipped_resolution_rows, row_skips, and row_skip_details. When outcome is rejected, look for reason_code, failing_path, validation_errors, repair_targets, repair_hint, and same_reason_code_streak.
If state_patch_feedback identifies a local mechanical state problem and the underlying semantic intent is still fine, default to a minimal proof-repair turn: patch only the failing path or skipped rows, keep already-earned findings intact, and avoid rewriting large closure blocks.

contract_feedback in the envelope reports the mechanical outcome of the prior choose-action parse attempt. If repair_attempted is true, your previous response failed parsing and a repair was needed; review the reason_code and adjust your output format accordingly.
"""

_HITL_TEXT = """\
### HITL transport
hitl_request: optional generic human prompt transport {message (required non-empty string), choices (array), context (object), opaque_payload (object), prompt_id (optional string)}.
wait_for_human is the canonical blocking flag: true requires hitl_request and pauses the loop until feedback arrives; false with hitl_request emits the request but the loop continues.
hitl_consumed_prompt_ids: optional array of prompt_id strings you have mechanically incorporated; host removes matching answered_hitl_responses only.
Envelope hitl_state, pending_hitl_requests, answered_hitl_responses are host-owned.

Use wait_for_human=true only when the run must actually pause for the answer; otherwise emit async HITL with wait_for_human=false and keep the loop active.
- Use `hitl_request.context` to carry the focused evidence refs or clarifying details the human needs.
- Preferred generic `hitl_request.context` keys when relevant: `evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, `question_regions`, and `notes`.
- Before emitting HITL, prefer the most focused evidence packet the current tooling can produce for the disputed item and sanity-check that it really isolates the question you are asking.
- When bounded choices could force a false answer, include a safe fallback such as `Unable to determine` or `Other / needs nuance`.
"""

_EXAMPLES_TEXT = """\
### Canonical examples
Active-item tool dispatch:
{"action_type": "some_tool", "action_inputs": {"key": "value"}, "idempotency_key": "ik-active-item-check-1", "skip_execution": false, "wait_for_human": false, "complete_run": false, "rationale": "The active item already exists, and this bounded check can materially change what I know about it.", "state_patch": {"mission": {"active_mode": "<domain_mode>", "verification_summary": "Running the strongest available check for the active item."}, "resolution": {"active_item_id": "<item-id>", "items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "claim_verification", "status": "open", "summary": "Needs one more bounded check before resolution."}]}} , "continuity_journal_entry": {"step": "dispatching bounded active-item check", "open_threads": ["interpret the returned evidence for <item-id>"]}, "operator_progress_message": "Running the next verification check.", "hitl_request": null, "hitl_consumed_prompt_ids": null}

No-dispatch state-authoring turn:
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-state-update-1", "skip_execution": true, "wait_for_human": false, "complete_run": false, "rationale": "Durable state needs a focused update before another dispatch.", "state_patch": {"mission": {"active_mode": "<domain_mode>", "success_conditions": [{"condition_id": "<condition-id>", "title": "<condition-title>", "status": "open", "completion_criteria": "<what must become true for this condition>"}]}, "resolution": {"active_item_id": "<item-id>", "items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "open_question", "status": "open", "next_needed_step": "Run the next bounded check for this item."}]}} , "continuity_journal_entry": {"step": "updated durable state before dispatch", "open_threads": ["run the next bounded check for the active item"]}, "operator_progress_message": "Updating run state.", "hitl_request": null, "hitl_consumed_prompt_ids": null}

Batch atomic inventory with an honest group node:
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-atomic-inventory-1", "skip_execution": true, "wait_for_human": false, "complete_run": false, "rationale": "The work universe needs explicit atomic accounting before I can verify or close it honestly.", "state_patch": {"resolution": {"active_item_id": "item-group-1", "items": [{"item_id": "item-group-1", "title": "<group title>", "kind": "claim_group", "status": "open", "structure_kind": "group", "summary": "Summary node for a set of details that may later verify together."}, {"item_id": "item-atomic-a", "title": "<atomic detail A>", "kind": "claim", "status": "open", "structure_kind": "atomic", "materiality": "critical", "next_needed_step": "Run the strongest available check for this detail."}, {"item_id": "item-atomic-b", "title": "<atomic detail B>", "kind": "claim", "status": "open", "structure_kind": "atomic", "materiality": "critical", "next_needed_step": "Run the strongest available check for this detail."}], "relations": [{"source_item_id": "item-atomic-a", "target_item_id": "item-group-1", "relation_type": "subclaim_of"}, {"source_item_id": "item-atomic-b", "target_item_id": "item-group-1", "relation_type": "subclaim_of"}]}} , "continuity_journal_entry": {"step": "expanded the work universe into explicit atomic units", "open_threads": ["verify each critical atomic item with the strongest available method"]}, "operator_progress_message": "Expanding the work inventory into explicit items.", "hitl_request": null, "hitl_consumed_prompt_ids": null}

Ordered lane with explicit dependency meaning:
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-sequence-lane-1", "skip_execution": true, "wait_for_human": false, "complete_run": false, "rationale": "These items belong to one ordered review lane, so the order should be explicit without pretending the whole mission is linear.", "state_patch": {"resolution": {"active_item_id": "lane-step-1", "items": [{"item_id": "lane-step-1", "title": "<ordered item 1>", "kind": "claim", "status": "open", "structure_kind": "atomic", "sequence_scope": "ordered-lane-a", "sequence_index": 1}, {"item_id": "lane-step-2", "title": "<ordered item 2>", "kind": "claim", "status": "open", "structure_kind": "atomic", "sequence_scope": "ordered-lane-a", "sequence_index": 2}], "relations": [{"source_item_id": "lane-step-1", "target_item_id": "lane-step-2", "relation_type": "prerequisite_of", "summary": "Step 1 must earn before step 2 can be treated as resolved."}]}} , "continuity_journal_entry": {"step": "declared an ordered lane of review", "open_threads": ["start with the earliest unresolved unblocked item in this lane unless another move is clearly more truth-advancing"]}, "operator_progress_message": "Recording the ordered review lane.", "hitl_request": null, "hitl_consumed_prompt_ids": null}

Minimal proof-state repair after a rejected patch:
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-state-repair-1", "skip_execution": true, "wait_for_human": false, "complete_run": false, "rationale": "The prior patch captured the right semantic posture; I only need to repair the failing closure row locally.", "state_patch": {"mission": {"closure_state": {"dimensions": [{"dimension_id": "<dimension-id>", "title": "<dimension-title>", "status": "<status>", "determination": "earned", "verification_basis": "<what verified this dimension>"}]}}}, "continuity_journal_entry": {"step": "repaired one failing state path", "open_threads": ["continue from the repaired closure posture"]}, "operator_progress_message": "Repairing the prior state patch.", "hitl_request": null, "hitl_consumed_prompt_ids": null}

HITL after exhaustion:
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-hitl-1", "skip_execution": true, "wait_for_human": true, "complete_run": false, "rationale": "The next correct step depends on human input, so the run must pause.", "state_patch": {"mission": {"waiting_summary": "Awaiting human clarification on the remaining blocker."}, "resolution": {"active_item_id": "<item-id>", "items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "blocking_dependency", "status": "blocked", "summary": "Awaiting human clarification before the next step."}]}} , "continuity_journal_entry": {"step": "emitted blocking hitl request", "open_threads": ["integrate the answered prompt when it arrives"]}, "operator_progress_message": "Waiting for human clarification.", "hitl_request": {"message": "<question for operator>", "choices": [], "context": {}}, "hitl_consumed_prompt_ids": null}

Async HITL while other honest work remains:
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-hitl-async-1", "skip_execution": true, "wait_for_human": false, "complete_run": false, "rationale": "Human clarification would help, but the run can continue while the answer is pending.", "state_patch": {"mission": {"verification_summary": "Issued an async HITL while keeping the run active.", "work_universe_posture": "believed_adequate"}, "resolution": {"active_item_id": "<item-id>", "items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "open_question", "status": "blocked", "summary": "Async HITL issued while other work continues.", "structure_kind": "atomic", "materiality": "critical", "blocking": true, "requires_hitl": true, "no_further_progress": true}]}} , "continuity_journal_entry": {"step": "emitted async hitl request", "open_threads": ["continue other unresolved work", "integrate the answered prompt when it arrives"]}, "operator_progress_message": "Queued a human clarification request while continuing other work.", "hitl_request": {"message": "<question for operator>", "choices": ["<choice-a>", "<choice-b>", "Unable to determine", "Other / needs nuance"], "context": {"evidence_refs": ["<artifact-ref>"], "primary_evidence_ref": "<artifact-ref>", "annotated_evidence_ref": "<annotated-artifact-ref>", "question_regions": ["<region-ref-or-label>"], "notes": "<focused context for the operator>"}}, "hitl_consumed_prompt_ids": null}

Blocker graph via resolution.relations (blocking item tied to what it blocks):
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-blocker-graph-1", "skip_execution": true, "wait_for_human": false, "complete_run": false, "rationale": "An unresolved item is blocking a specific success condition; make that dependency explicit in the blocker graph.", "state_patch": {"mission": {"success_conditions": [{"condition_id": "<condition-id>", "title": "<condition-title>", "status": "open", "summary": "Awaiting resolution of the dependent item before this condition can be earned."}]}, "resolution": {"items": [{"item_id": "<item-id>", "title": "<item-title>", "kind": "contradiction", "status": "blocked", "blocking": true, "no_further_progress": true, "summary": "Contradiction cannot be resolved from current in-run evidence."}], "relations": [{"source_item_id": "<item-id>", "target_item_id": "<condition-id>", "relation_type": "blocks", "summary": "This item must resolve before the success condition can earn."}]}}, "continuity_journal_entry": {"step": "recorded blocker graph edge", "open_threads": ["surface the blocker via HITL if human-answerable", "continue other unresolved work"]}, "operator_progress_message": "Recorded a blocker dependency in state.", "hitl_request": null, "hitl_consumed_prompt_ids": null}

Second concurrent HITL for a distinct blocker (multiple HITLs in one run):
{"action_type": null, "action_inputs": {}, "idempotency_key": "ik-hitl-async-2", "skip_execution": true, "wait_for_human": false, "complete_run": false, "rationale": "A separate blocker is also human-answerable and its in-run checks are exhausted; surface it rather than merely recording it.", "state_patch": {"mission": {"verification_summary": "Emitted a second async HITL for a distinct blocker."}, "resolution": {"active_item_id": "<item-id-2>", "items": [{"item_id": "<item-id-2>", "title": "<distinct-blocker-title>", "kind": "contradiction", "status": "blocked", "blocking": true, "requires_hitl": true, "no_further_progress": true, "summary": "Material contradiction with exhausted in-run checks; needs operator input."}]}}, "continuity_journal_entry": {"step": "emitted second async hitl for distinct blocker", "open_threads": ["integrate each answered prompt when it arrives"]}, "operator_progress_message": "Surfaced a second human-answerable blocker.", "hitl_request": {"message": "<focused question about the distinct blocker>", "choices": ["<choice-a>", "<choice-b>", "Unable to determine", "Other / needs nuance"], "context": {"supporting_refs": ["<artifact-ref>"], "notes": "<focused context for the operator>"}, "prompt_id": "prompt-distinct-blocker-1"}, "hitl_consumed_prompt_ids": null}
"""

_OUTPUT_FORMAT_TEXT = (
    "Choose action_type only from the provided tool_ids when dispatching a tool. "
    "For an explicit no-dispatch investigation/state turn, action_type may be null only for the skip_execution shape described above. "
    "Do not wrap the JSON in markdown and do not add commentary."
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
