# Trace Implementation Plan

Date: 2026-03-11
Status: Phase 4 implementation plan (adapter-first rollout)
Primary design reference:
- `docs/architecture/harness/trace-normalization-and-adapter-design.md`

## Purpose

Provide a concrete rollout plan for canonical trace normalization that implementation agents can execute without inventing architecture.

## Rollout Phases

## Phase 4A: Foundation and contract guardrails

Deliverables:
- shared canonical trace schema types and version constants
- shared event builder/order/index helpers
- completeness/warning metadata contract
- timestamp normalization policy (`source` vs `derived_sequence`)

Likely code areas:
- `backend/harness/tracing/schema.py` (new)
- `backend/harness/tracing/builder.py` (new)

Exit criteria:
- schema tests validate required top-level and event fields
- ordering/indexing determinism tests pass

## Phase 4B: Read-only controller/kernel adapter

Deliverables:
- adapter that reads controller transcript artifact + kernel run artifact and emits canonical trace
- source linkage metadata for event provenance

Likely code areas:
- `backend/harness/tracing/adapters/controller_kernel.py` (new)
- read-only integration with `backend/agents/controller/controller_transcript.py`
- read-only integration with `backend/agent_kernel/run_artifact.py`

Exit criteria:
- fixture-based tests cover success, refusal-heavy, and truncated transcript scenarios
- terminal and key event categories map without ambiguity

## Phase 4C: Read-only transcript-edit adapter

Deliverables:
- adapter that reads tx run registry snapshot and emits canonical trace
- blocker/escalation mapping that respects Phase 3 authority split

Likely code areas:
- `backend/harness/tracing/adapters/transcript_edit.py` (new)
- read-only integration with:
  - `backend/api/endpoints/transcript_edit_agent.py` snapshot shape
  - `backend/agents/transcript_edit/run_reporting.py`
  - `backend/agents/transcript_edit/terminalization.py`
  - `backend/agents/transcript_edit/decision_ledger.py`
  - `backend/agents/transcript_edit/blocker_registry.py`

Exit criteria:
- tests cover normal completion, waiting feedback, and partial-history runs (`progress_log` capped)
- canonical blocker/escalation events derive from registry lifecycle and ledger context without dual authority

## Phase 4D: Export and developer consumption

Deliverables:
- on-demand export path for canonical trace JSON (internal helper or endpoint)
- optional sidecar persistence decision implemented if approved

Likely code areas:
- `backend/harness/tracing/storage.py` (optional new)
- small integration point in API/service layer (to be chosen in implementation brief)

Exit criteria:
- engineers can generate canonical traces for representative controller and transcript-edit runs
- no runtime loop behavior changes required

## Suggested first implementation slice (mandatory)

Implement Phase 4A -> Phase 4B -> Phase 4C as sequential read-only adapters with tests, no runtime rewiring.

Rationale:
- validates cross-family viability quickly
- keeps blast radius low
- avoids parallel tracing platform rewrite

Gate between 4B and 4C:
- do not start transcript-edit adapter implementation until authority-fixture tests are defined for:
  - ledger-only closure truth mapping
  - registry-only blocker/escalation lifecycle mapping

## Test Surfaces

Core tests:
- canonical schema validation tests (`required fields`, `event kinds`, `versioning`)
- deterministic ordering/index tests across heterogeneous source timestamps
- controller adapter mapping tests (run header, proposed step, kernel step result, terminal)
- transcript-edit adapter mapping tests (progress events, blocker lifecycle, HITL events, terminal)
- partial trace tests (`missing_components`, `completeness_status=partial`)

Source-specific fixtures:
- controller transcript files with truncation markers
- kernel run artifacts with refusals and terminal outcomes
- tx run registry snapshots with bounded `progress_log` and `critical_events`

## Risks and Mitigations

1. Ordering ambiguity across mixed sources
- Mitigation: explicit ordering key and deterministic tie-break rules in shared builder.

2. Transcript-edit history truncation hides transitions
- Mitigation: partial-trace metadata + warnings; do not fabricate absent transitions.

3. Blocker authority regression in mapping logic
- Mitigation: enforce Phase 3 rule in adapter tests (ledger closure truth, registry lifecycle truth).

4. New trace layer becoming monolithic
- Mitigation: keep loop-family adapters separate and shared builder minimal.

## Must Remain Stable During Rollout

- Existing controller and transcript-edit runtime behavior
- existing API run snapshots and viewer event flows
- existing raw artifact persistence paths and formats

Canonical traces are additive observability outputs in this phase.

## Reviewer Focus Areas

Architecture reviewer:
- verify adapter boundaries are non-monolithic
- verify Phase 3 authority split is honored in tx mapping
- verify shared builder is contract-only, not policy-heavy

Code efficiency reviewer:
- verify no over-engineered abstraction stack
- verify adapter outputs reuse current source artifacts directly
- verify first slice scope stays read-only and low-risk

## Handoff Checklist for Implementation Brief

- identify initial file skeletons and test files
- pick first consumer entrypoint for trace export (CLI or internal API)
- define fixture corpus for both loop families
- confirm no runtime loop codepaths are rewritten in first slice
