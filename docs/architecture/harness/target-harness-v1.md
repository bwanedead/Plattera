# Target Harness v1 (Working Contract)

Date: 2026-03-11
Status: Working architecture contract (ambitious, revisable)
Primary sequencing reference: `docs/architecture/migration/harness-convergence-roadmap.md`

## Purpose

Define the target shared harness shape for convergence work without over-freezing design details too early.

This document sets boundaries and minimum contracts that future implementation phases should map to.

## Scope Boundary

This is a harness contract for:
- shared execution envelope and observability vocabulary
- cross-loop comparability
- migration direction

This is not:
- a full runtime implementation spec
- a mandate for one giant unified runtime object
- a complete canonical run ledger design

## Shared Harness Spine (Target)

The shared spine should own:
- run identity and request metadata envelope
- iteration envelope (phase + bounded progress summary)
- canonical trace/event model
- blocker/escalation envelope
- verification envelope
- terminal outcome taxonomy
- shared observability/export surface

## Domain Policy Layer (Remains Specialized)

Loop families keep domain-specific policy where it is weight-bearing:
- tool menu and action wiring
- evidence strategy and ordering
- closure logic and acceptance thresholds
- domain guardrails and risk policy

Convergence target is shared harness infrastructure with domain policies on top, not behavior flattening.

## Canonical Trace Schema (Conceptual v1)

Trace is a shared harness contract, but detailed schema fields and event categories are owned by:
- `docs/architecture/harness/canonical-trace-schema.md`

This document keeps boundary-level intent only:
- all loop families emit into one canonical trace model
- adapters may emit partial traces early, but schema semantics stay stable
- trace remains the detailed event history; run-state envelope stays bounded

## Shared Terminal Taxonomy (Harness-Level)

All loop families should map outcomes into a common harness taxonomy:
- `completed`
- `blocked`
- `waiting_human`
- `waiting_evidence`
- `exhausted`
- `failed`

Domain reasoning remains specific, but terminal classification vocabulary should be shared.

## Shared Blocker and Escalation Envelope

Minimum shared blocker envelope:
- blocker identity
- blocker kind and blocking impact (distinct axes)
- blocker state
- evidence summary
- next valid actions
- escalation envelope and linked human/escalation state

This envelope should support both generic controller/kernel and transcript-edit loop families.

## Minimal Shared Run-State Envelope

The minimum shared run-state envelope should include:
- objective/request metadata
- current working refs/artifacts
- unresolved blockers summary
- verification status summary
- latest terminal/progress classification
- resumability/waiting status

Domain-specific extensions are expected and should remain extension fields rather than forcing early over-unification.

## Temporary Exceptions (Accepted for Migration)

During migration, these are acceptable:
- loop family specific continuity structures remain in parallel while adapters normalize traces
- family-specific closure/state ownership can continue until explicit authority cleanup decision is implemented
- uneven capability exposure may remain temporarily where wiring work is not yet phased in

Each temporary exception should be tracked in `docs/architecture/migration/harness-delta-ledger.md`.

## Open Questions

The following are intentionally unresolved and must remain visible:
- Transcript-edit authority split is now defined in `docs/architecture/harness/transcript-edit-state-authority.md`; remaining question is how much of that split should generalize to other loop families.
- What minimum shared run-state fields are truly required by both loop families in implementation, not theory?
- Where should shared trace adapters live so observability converges without creating a new monolith?
- Which domain-specific semantics should stay local even after taxonomy/envelope convergence?

## Relationship to Broader State Convergence

A fuller shared ledger/state abstraction is intentionally deferred.

Current policy:
- converge observability, outcomes, blockers, and state authority clarity first
- let broader shared ledger/state emerge from implementation pressure and proven usage

This keeps the architecture serious without speculative over-design.
