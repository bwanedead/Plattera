# Transcript-Edit State Authority

Date: 2026-03-11
Status: Phase 3 authority contract (definition only)
Program references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/harness/shared-blocker-escalation-envelope.md`
- `docs/architecture/harness/minimal-shared-run-state-envelope.md`

## Purpose

Set a canonical ownership model for transcript-edit state so implementation phases do not guess where truth lives.

This document resolves authority for:
- unresolved closure truth
- blocker lifecycle truth
- feedback/escalation lifecycle truth
- resumability/waiting truth

This is an architecture decision and migration plan, not a runtime refactor spec.

## A) Current-State Diagnosis

## Decision ledger (`decision_ledger*`)

What it currently owns:
- unresolved closure semantics and closure requirement shape
- scope-aware closure derivations and layer closure status
- external context injections (including human-resolution tickets)
- source-completeness and scope summaries used in terminal reasoning

Code evidence:
- `unresolved_closure_requirements`, `has_unresolved_target_scope_mapping_blocking_closure`, and related closure selectors are ledger-derived in `backend/agents/transcript_edit/decision_ledger_closure.py`.
- controller baseline and iteration gates use ledger-first closure checks in `backend/agents/transcript_edit/controller.py`.
- focus selection reads unresolved closure from ledger in `backend/agents/transcript_edit/decision_ledger_focus.py`.

Diagnosis:
- ledger already behaves as canonical unresolved-closure authority.

## Blocker registry (`blocker_registry*`)

What it currently owns:
- blocker row lifecycle state (`open`, `waiting_feedback`, `answered_unintegrated`, `resolved`, `superseded`)
- active blocker selection
- prompt linking and feedback-state transitions
- emergent blocker lifecycle (including blockers not represented as base ledger decision rows)

Code evidence:
- lifecycle transitions are implemented in `backend/agents/transcript_edit/blocker_registry_lifecycle.py` (`link_prompt_to_blocker`, `mark_feedback_received`, `mark_feedback_stale`, emergent update operations).
- selection and active blocker behavior is registry-driven in `backend/agents/transcript_edit/blocker_registry_selection.py`.
- controller health-check logic explicitly treats registry as a projection from ledger for legacy unresolved closure rows via `sync_registry_from_ledger(...)`.

Diagnosis:
- registry is a mixed surface today: projection for ledger-derived closure blockers plus canonical lifecycle state machine for blocker operations and emergent blockers.

## Pending feedback prompt / HITL runtime fields (`TranscriptEditLoopState`)

What it currently holds:
- `pending_feedback_prompt_id`
- `pending_feedback_decision_key`
- `pending_feedback_prompt`
- lifecycle counters and logs

Code evidence:
- values are written/cleared in `backend/agents/transcript_edit/feedback_lifecycle.py`.
- timeout conversion checks both pending runtime fields and registry rows in `backend/agents/transcript_edit/controller.py` (`_should_convert_timeout_to_waiting_feedback`).

Diagnosis:
- pending feedback ownership is currently duplicated between loop-state runtime fields and blocker registry lifecycle rows.

## Terminal summary / runtime HITL payload (`terminalization.py`, controller `_runtime_hitl_state`)

What it currently does:
- composes terminal payloads from event history, ledger, registry snapshots, and runtime fields
- computes terminal classification and summary projections

Diagnosis:
- terminal surfaces are intended as derived views, but they currently consume duplicated inputs because authority is not singular everywhere.

## Resumability/request fields (`contracts.py`, controller resume path)

What it currently does:
- resume request allows both `resume_blocker_registry` and explicit pending feedback prompt fields
- loop bootstrap restores both surfaces

Diagnosis:
- resumability truth is currently split across registry payload and standalone pending prompt fields.

## B) Authority Model Recommendation

## Canonical owners

1. Unresolved closure truth owner: `decision_ledger`
- Canonical source for whether closure requirements remain unresolved and whether they are mapping-blocking.
- `blocker_registry` must not independently decide unresolved closure truth for ledger-backed decisions.
- Invariant: registry-native emergent blockers may drive blocker lifecycle and escalation, but they do not create or clear closure truth unless promoted into a ledger-backed closure path.

2. Blocker lifecycle truth owner: `blocker_registry`
- Canonical source for blocker operational state transitions, active blocker selection, and blocker-level lifecycle metadata.
- Includes emergent blockers; emergent lifecycle should remain registry-native.

3. Feedback/escalation lifecycle truth owner: `blocker_registry` escalation/lifecycle fields
- Canonical waiting/answered/integration lifecycle state and prompt linkage live in blocker rows.
- Ledger human-resolution tickets remain durable context/audit artifacts, not state-machine authority.

4. Resumability/waiting truth owner: `blocker_registry`
- Run waiting/resume posture is determined from registry lifecycle state (`waiting_feedback`, linked prompt state, `answered_unintegrated`) plus terminal class mapping.
- Shared run-state envelope and loop-state pending prompt fields are derived serialization/cache layers, not authority.

5. Terminalization authority: projection-only
- `terminalization.py` and controller runtime HITL payloads are derived outputs and must not own lifecycle transitions.

## Layered ownership model

- Ledger: closure truth.
- Registry: blocker/escalation lifecycle truth.
- Loop state: runtime cache + convenience cursors.
- Terminal payload/result: read models for UI/API/reporting.

## C) Allowed Duplication vs Forbidden Duplication

## Allowed duplication

- Derived summaries in terminal payloads (`terminal_summary`, runtime HITL snapshot).
- Adapter projections needed for backward compatibility (resume fields, API payload compatibility keys).
- Cached convenience views for current-iteration efficiency, if they are recomputed or validated against canonical owners.
- Ledger ticket history that mirrors escalation events for auditability.

## Forbidden duplication

- Two structures independently deciding unresolved closure truth for the same decision key.
- Two structures independently deciding active waiting-human ownership for the same blocker/prompt.
- Lifecycle transitions applied in multiple owners without a defined source-of-truth writer.
- Terminal/read-model payloads becoming implicit authority because consumers rely on them as state input.

## D) Transition Strategy (Docs-Level, No Runtime Changes Here)

Recommended migration sequence:

1. Freeze authority boundaries in contracts and migration docs (this phase).
2. Standardize read paths around canonical owners (ledger for closure, registry for lifecycle).
3. Convert loop-state pending prompt fields to compatibility projections from registry state.
4. Restrict terminalization and result builders to projection role only.
5. Remove deprecated duplicate authority paths after compatibility verification.

Compatibility expectations during migration:
- Keep API/output fields stable where UI currently depends on them.
- Preserve `resume_pending_feedback_*` support until resume consumers move to registry-first resume contracts.
- Keep `runtime_hitl_state` shape stable while source-of-truth narrows.

## E) Relationship to Harness Convergence

This authority split enables later convergence phases:

- Canonical trace emission:
  - trace adapters can tag closure transitions from ledger and blocker/escalation transitions from registry without ambiguity.

- Shared blocker envelope:
  - transcript-edit can map registry lifecycle directly into the shared blocker/escalation envelope while preserving ledger closure semantics as linked context.

- Minimal shared run-state envelope:
  - resumability and blocker summary derive from registry lifecycle state.
  - verification/closure summary derives from ledger-derived closure and verification outputs.

- Shared harness spine migration:
  - controller-family loops can adopt analogous split (closure/verification summary owner vs blocker lifecycle owner) without forcing transcript-edit internals into generic loops.

## Open Questions (Remaining, Not Resolved Here)

- Should ledger human-resolution tickets remain persisted as first-class records long-term, or become pure projection from blocker lifecycle history?
- When controller-family blockers become explicit, should they follow the same two-layer split immediately or start with a single owner and split later?
- What is the final deprecation window for `resume_pending_feedback_*` fields once registry-first resumability is adopted?
