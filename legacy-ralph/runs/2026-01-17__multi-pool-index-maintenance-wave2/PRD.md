# PRD: Multi-Pool Index Maintenance (Wave 2) — No-Throw Pool Open + EVERYTHING + Health Report + Logging

## Context
We already have correct doc-slice primitives and an Inventory → Diagnose → Execute flow for FINAL (v0), plus compaction recommendation plumbing.

What’s missing for “product-grade” maintenance is:
- a safe, typed **pool-open boundary** that never throws and returns stable reason codes
- full **EVERYTHING pool** support (head-only v0) through the same maintenance surfaces
- a stable **pool health report** shape for UI/agents (reuse existing stats/compaction logic)
- structured logging (no stderr prints)

## Goal
Make index maintenance a deterministic, no-throw, multi-pool system with stable report payloads that UI and agents can rely on.

## Non-goals (explicitly deferred)
- Any “atomic-ish” delete/build redesign (build-first-then-delete is a footgun and is deferred).
- Auto-light / auto-aggressive scheduling logic (UI can decide when to call execute).
- UI endpoints/panels in this wave (backend contract first).
- Non-head draft hydration expansion beyond head-form draft ids for EVERYTHING.

## Users / Use cases
- As a UI, I want a stable payload that says “pool open OK/UNAVAILABLE + reason + health stats + optional slice diagnoses”.
- As an agent, I want maintenance calls to never throw on common operational failures and instead return stable reason codes.
- As the system, I want EVERYTHING pool doc-slice maintenance (head-only v0) to work end-to-end like FINAL.

## Scope
Backend maintenance layer only:
- `backend/retrieval/engine/*` (MaintenanceController boundary + report shapes)
- `backend/retrieval/lanes/semantic/*` (store open behavior + stats reuse + logging cleanup)
- `backend/corpus/*` (already draft-aware; no new draft modes in this wave)

## Constraints / invariants
- MaintenanceController (or its wrapper) must **never throw** for common pool-open failures:
  - schema mismatch
  - missing artifacts
  - open/load failures
- Reason codes must be stable (reuse existing `DiagnosticReasonCode` enum).
- View selection must be explicit for multi-pool:
  - do not implicitly assume FINAL based on pool_identifier defaults.
- Reuse existing stats + compaction logic (`get_stats()`, `should_compact()`); do not reimplement.
- Logging must use repo logging conventions (no new heavy dependencies).

## Success criteria
- Pool-open boundary returns `PoolOpenReport` with stable reason codes and never throws.
- EVERYTHING pool supports Inventory → Diagnose → Execute for doc slices (head-only v0).
- Pool health report is stable and includes compaction recommendation derived from existing stats logic.
- Index maintenance paths no longer print to stderr; they log via the repo logger with useful structured fields.

## Edge cases
- Pool open fails due to schema mismatch: report `UNAVAILABLE_SCHEMA_VERSION_MISMATCH` with action_hint `REBUILD_POOL`.
- Pool open fails due to missing artifacts: report a stable UNAVAILABLE reason code (no stack trace leakage).
- Pool open succeeds, but slice hydration fails: slice is `unavailable` with a stable reason code; controller still returns pool health.



