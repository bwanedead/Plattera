# Transcript-Edit Authority Migration Notes

Date: 2026-03-11
Status: Phase 3 migration planning notes (implementation-facing)
Primary authority reference:
- `docs/architecture/harness/transcript-edit-state-authority.md`

## Purpose

Provide concrete migration guidance for implementing transcript-edit authority convergence without improvisation.

Normative ownership rules live in:
- `docs/architecture/harness/transcript-edit-state-authority.md`

This file is an execution checklist only.

## Current Authority Hotspots

1. Closure truth vs blocker rows
- Ledger computes unresolved closure truth.
- Registry projects ledger unresolved rows but also holds operational lifecycle state.
- Risk: duplicated transition logic if both surfaces mutate unresolved state intent.

2. Waiting-human ownership split
- Loop state keeps `pending_feedback_*` fields.
- Registry keeps blocker row lifecycle with linked prompt ids.
- Risk: timeout/waiting classifications can diverge.

3. Escalation persistence split
- Registry stores prompt linkage and lifecycle transitions.
- Ledger stores human-resolution ticket records.
- Risk: stale or mismatched ticket/prompt lifecycle if updates are not coordinated.

4. Terminal/read-model coupling
- Terminal summary consumes ledger, registry, and runtime fields.
- Risk: read model accidentally becoming a de facto authority source.

## Workstreams

1. Authority boundary hardening
- Enforce ledger-only closure reads/writes for unresolved closure truth.
- Enforce registry-only blocker/escalation lifecycle transitions.

2. Waiting/resume normalization
- Derive waiting-human ownership from registry-first logic.
- Keep `pending_feedback_*` fields as compatibility projections until deprecation.

3. Projection cleanup
- Keep terminalization/result payload builders projection-only.
- Prevent lifecycle transitions in read-model code paths.

4. Compatibility and deprecation
- Keep API/UI payload semantics stable while internal ownership converges.
- Retire duplicate authority paths only after invariants hold.

## Recommended Order of Change

1. Introduce explicit authority invariants and tracing points (no behavior change).
2. Move waiting-state derivation to registry-first checks; keep legacy compatibility fields.
3. Route escalation transition writes through registry lifecycle APIs.
4. Keep ledger ticket mirror writes only as compatibility artifacts while long-term ticket model remains open.
5. Update terminal/read-model composition to consume canonical owners only.
6. Decommission duplicate pending-prompt authority paths after compatibility period.

## Expected Break Risks

High risk:
- waiting-timeout classification regression (`needs_review` vs `failed` when feedback is pending).
- resume behavior regressions when only partial resume payloads are provided.
- stale prompt supersession handling causing orphan `answered_unintegrated` blockers.

Medium risk:
- terminal summary drift if projection fields assume old pending-prompt authority.
- mismatch between ledger ticket lifecycle and registry lifecycle during partial migrations.

Low risk:
- docs/schema naming drift in non-runtime artifacts.

## Test Surfaces Likely To Catch Regressions

Prioritize tests around:
- `backend/agents/transcript_edit/controller.py`
  - timeout conversion and result status paths
  - resume bootstrap paths
- `backend/agents/transcript_edit/feedback_lifecycle.py`
  - prompt issuance, supersession, stale/received transitions
- `backend/agents/transcript_edit/blocker_registry_lifecycle.py`
  - lifecycle transition correctness
  - emergent blocker transitions
- `backend/agents/transcript_edit/decision_ledger_closure.py`
  - unresolved closure derivation invariants
- `backend/agents/transcript_edit/terminalization.py`
  - terminal projection correctness from canonical sources

Recommended invariant checks (runtime or tests):
- ledger unresolved set equals projection subset in registry for ledger-backed decisions.
- at most one blocker row owns active waiting-feedback prompt linkage at a time.
- pending compatibility fields (if present) match registry waiting/active ownership.

## Stability Requirements for API/UI Consumers

Keep stable during migration:
- terminal payload fields currently consumed by transcript-edit UI and logs.
- `runtime_hitl_state` compatibility keys (`pending_feedback_prompt_id`, counters, registry snapshot).
- resume request compatibility fields (`resume_pending_feedback_*`, `resume_blocker_registry`).

Allowed to evolve:
- internal authority source for each stable field.
- internal projection composition as long as field semantics remain stable.

## Migration Exit Criteria

Authority convergence for transcript-edit is ready to close when:
- closure truth has a single owner (ledger) with no competing lifecycle writes.
- waiting/escalation lifecycle has a single owner (registry) with no competing owners.
- pending feedback runtime fields are projection/cache only.
- terminal/read-model builders are projection-only.
- compatibility fields remain stable or are formally deprecated with timeline.
