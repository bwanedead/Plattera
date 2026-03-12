# Harness Review Operating Routine

Date: 2026-03-12
Status: Active
Scope: Phase 12-13 operational maturity

Primary references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/migration/harness-delta-ledger.md`
- `docs/architecture/migration/harness-decisions.md`
- `docs/architecture/harness/canonical-trace-schema.md`
- `docs/architecture/harness/minimal-shared-run-state-envelope.md`

## Purpose

Turn trace/review tooling into a repeatable engineering ritual that produces
durable evidence artifacts for harness evolution.

This routine is observational only:
- no runtime enforcement
- no scheduler/watcher behavior
- no dashboard platform scope

## Artifact Policy

Operational review artifacts are explicit opt-in JSON bundles produced by
`backend/harness/review/tool.py`.

Bundle contents:
- canonical trace record per run
- shared run-state envelope per run
- per-run review summary
- aggregate summary
- metadata including generation timestamp, tool/version markers, loop-family
  marker, and partial-trace note

Storage policy:
- write only when explicitly requested
- no background persistence
- raw artifacts remain source of truth; canonical traces remain additive

## When Reviews Must Run

Run this routine at minimum:
- after major harness-layer changes (`backend/harness/*`, trace adapters,
  run-state builders, review reporting/tooling)
- before and after contract-shape changes informed by trace observations
- on a recurring live-loop monitoring cadence (minimum weekly during migration;
  tighten to every major release once stable)

## Ownership

During migration:
- primary owner: harness engineering implementer on the change
- secondary reviewer: designated architecture reviewer for convergence phases

For recurring cadence:
- owner should be the active harness steward for the week/sprint
- outputs should be attached to migration work items or architecture notes

## Standard Workflow

1. Select one or more persisted run payloads (controller, transcript-edit, or mixed).
2. Build review bundles via `harness.review.tool`:
   - single-run for targeted diagnosis
   - multi-run for distribution/churn analysis
3. Explicitly write the bundle JSON artifact when sharing or archiving evidence.
4. Answer the required review questions (below) in the work record.
5. Record actionable findings:
   - candidate contract updates
   - compatibility seam changes
   - test additions/regressions
6. Update migration artifacts (`harness-delta-ledger.md`, `harness-decisions.md`)
   when decisions or capability status materially change.

## Required Review Questions

Every routine run must answer:
- terminal class distribution:
  - what share is `completed`, `failed`, `waiting_human`, `waiting_evidence`, etc.?
- top reason codes:
  - which reason codes dominate and are they expected?
- partial-trace rate:
  - how often are traces partial and why?
- waiting rates:
  - `waiting_human` rate and `waiting_evidence` rate
- verification-missing-on-completion count:
  - how many completed runs lacked verification events?
- repeated/churny runs:
  - where are high-iteration or repeated-action-shape patterns appearing?
- ergonomics observations:
  - which recurring emitted action/event patterns suggest contract mismatch,
    discoverable ergonomic aliases, or prompt/contract clarification opportunities?

## Recording Findings

Each review record should include:
- artifact path(s)
- run_ids and loop families covered
- concise findings list (blocking/advisory)
- recommended follow-up (contract update, seam cleanup, test addition, doc update)
- explicit note when no actionable findings were detected

## Regression Pack Link

The Phase 14 harness regression pack (`backend/harness/test_harness_regression_pack.py`)
is the compact safety net for recurring review semantics.

Use the recurring review routine and artifact bundles to discover drift candidates,
then encode stable, high-signal expectations in the regression pack:
- terminal class/reason posture
- waiting and resumability posture
- verification presence/absence
- partial-trace and selected review-flag behavior
- mixed-run aggregate rates

Do not turn the regression pack into full-shape snapshots of every field.

## Guardrails

- Do not convert review flags into hidden runtime policy enforcement.
- Do not expand this routine into a trace analytics platform.
- Do not store artifacts implicitly.
- Keep bundle shape stable and bounded so comparisons remain practical.
