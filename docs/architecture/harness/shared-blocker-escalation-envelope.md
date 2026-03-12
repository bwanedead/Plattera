# Shared Blocker and Escalation Envelope

Date: 2026-03-11
Status: Phase 2 shared contract (definition only)
Program references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/target-harness-v1.md`

## Purpose

Define one blocker/escalation envelope that works across loop families while preserving domain-specific blocker content.

Why this matters:
- blockers become searchable, comparable, and resumable across loops
- escalation behavior becomes explicit instead of hidden in narrative fields
- terminal and waiting states can be derived consistently

## Shared Blocker Envelope (Minimum Fields)

Each blocker record must include:
- `blocker_id`: stable blocker identifier for the run.
- `blocker_kind`: problem-type taxonomy (`ambiguity`, `dependency`, `capability`, `validation`, `execution`, `human_input`, extendable).
- `blocking_impact`: closure-impact taxonomy (`mapping_blocking`, `closure_blocking`, `source_blocking`, `quality_only`).
- `state`: lifecycle state (see below).
- `scope`: scope tag (`in_target`, `outside_target`, `unknown`, or domain equivalent). Baseline policy: required field, but `unknown` is valid for synthesized/non-blocker-native loops.
- `summary`: concise problem statement.
- `evidence_summary`: bounded evidence state for this blocker.
- `next_valid_actions`: explicit bounded action list.
- `escalation`: escalation envelope (see below).
- `updated_at_epoch_seconds`: latest state update timestamp.

Recommended optional fields:
- `decision_key` (domain key when applicable)
- `linked_refs` (artifact refs)
- `owner` (component owning next action)

Terminology note:
- `blocker_kind` and `blocking_impact` are intentionally separate axes.
- This avoids overloading `class` with two meanings and aligns with existing transcript-edit usage where `blocking_class` already represents impact severity.

## Blocker Lifecycle (Harness-Level)

Shared lifecycle states:
- `open`: unresolved and actively machine-addressable.
- `waiting_human`: unresolved and waiting on human input.
- `waiting_evidence`: unresolved and waiting on external evidence/dependency input.
- `answered_pending_integration`: human/evidence response exists but not integrated yet.
- `resolved`: blocker closed.
- `superseded`: replaced by newer blocker context.

State semantics:
- `next_valid_actions` must align with lifecycle state.
- `resolved` and `superseded` should have empty actionable next steps.

## Escalation Envelope (Minimum)

`escalation` sub-object fields:
- `eligible`: whether escalation is currently valid.
- `escalation_state`: `not_needed`, `eligible`, `issued`, `waiting_response`, `response_received`, `integrated`, `stale`, `superseded`.
- `channel`: `human_feedback`, `dependency_request`, `capability_request`, or domain-specific extension.
- `prompt_or_ticket_id`: linked escalation artifact id when issued.
- `last_transition_reason`: bounded reason code/description.

## Relationship Rules

- Blocker state must be evidence-aware: evidence changes can reopen, resolve, or supersede blockers.
- Escalation eligibility must derive from blocker state + next valid machine actions.
- A blocker should not be simultaneously `resolved` and escalation `waiting_response`.
- Terminal `waiting_human`/`waiting_evidence` classifications should be derivable from blocker/escalation state.

## Current-to-Target Mapping

## Transcript-edit mapping (existing strong model)

Current blocker registry fields already align strongly:
- `blocker_id`, `decision_key`, `state`, `scope_status`, `current_evidence_summary`, `next_valid_actions`, linked prompt/ticket ids.
- existing `blocking_class` maps directly to shared `blocking_impact`.
- transcript decision identity / blocker archetype category maps to shared `blocker_kind`.

Mapping guidance:
- `waiting_feedback` -> `waiting_human`
- `answered_unintegrated` -> `answered_pending_integration`
- unresolved dependency-class closure requirements -> `waiting_evidence`
- existing lifecycle/ticket states populate `escalation` fields

## Controller/kernel family mapping (currently blocker-light)

Current signals to synthesize blocker envelope:
- refusals (`KernelRefusal.reason_code`, missing inputs, retryability)
- failure classification in dashboard
- stop reasons (`needs_user_choice`, `needs_upload`, `needs_capability`, validation failures)

Adoption guidance:
- start with synthesized blockers from refusal/stop contexts
- promote to explicit blocker records where repeated unresolved conditions occur
- keep domain payload thin until blocker-native behavior is needed

## What Stays Domain-Specific

Domain-specific fields may remain extensions:
- transcript decision-ledger internals and layer/scope proofs
- mapping/feature-graph specific semantic check payloads
- local heuristic ranking and archetype hints

The shared envelope defines minimum interoperability, not full domain ontology.

## Open Questions

- Should `answered_pending_integration` be mandatory day one for non-HITL loops or optional until needed?
- Where should blocker synthesis occur for non-blocker-native loops (trace adapter vs runtime wrapper)?
