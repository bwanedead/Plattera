# Harness Decisions Log

Date: 2026-03-11
Status: Active
Primary sequencing reference: `docs/architecture/migration/harness-convergence-roadmap.md`

## Purpose

Record major architectural decisions and reversals for harness convergence.

This log is practical by design:
- concise decision entries
- explicit rationale and consequences
- explicit revisit triggers

## Entries

### HD-001: Treat convergence as a harness program, not isolated loop refactors
- Status: Accepted
- Decision: Run migration as a phased architecture program with shared contracts and a tracked delta ledger.
- Rationale: Isolated refactors do not reliably converge ownership, vocabulary, or observability across loop families.
- Consequences: Work is sequenced and review-heavy; implementation phases must update migration records.
- When to revisit: If phased program overhead materially blocks delivery or if loop families diverge for justified product reasons.

### HD-002: Normalize traces before broad state convergence
- Status: Accepted
- Decision: Define and adopt a canonical trace schema and adapters before attempting broad continuity/state unification.
- Rationale: Observability normalization is lower-risk and creates the evidence base needed for state ownership decisions.
- Consequences: Early work emphasizes schema/adapters and may allow temporary parallel state models.
- When to revisit: After trace adapters are in place and evidence shows state convergence can proceed safely.

### HD-003: Shared harness framework with domain policies
- Status: Accepted
- Decision: Converge toward one shared harness spine with domain-specific loop policies preserved where weight-bearing.
- Rationale: We need shared infrastructure consistency without flattening domain-specialized behavior that carries real value.
- Consequences: Contract work must define shared vs domain boundaries explicitly in each phase.
- When to revisit: If policy-specific behavior repeatedly forces shared-spine exceptions that imply wrong boundary placement.

### HD-004: Keep docs cleanup light and intentional
- Status: Accepted
- Decision: Establish a clean active architecture/migration spine in `docs/architecture/` without full docs-tree reorganization now.
- Rationale: Improves navigability quickly while avoiding disruptive docs churn during active migration.
- Consequences: Older docs remain in place and are treated as reference/historical unless linked as active.
- When to revisit: If active docs become hard to navigate again or if architecture surface grows enough to justify broader reorganization.

### HD-005: Shared terminal taxonomy is harness-level; reason codes remain granular
- Status: Accepted
- Decision: Use a shared harness terminal class set for cross-loop comparability while preserving loop/domain reason-code granularity.
- Rationale: Cross-loop analysis needs normalized classes, but operational diagnosis still needs detailed reason codes.
- Consequences: Implementations must map local outcomes to harness classes without collapsing reason codes.
- When to revisit: If taxonomy classes are too coarse for reliable steering or too fine for consistent mapping.

### HD-006: Shared blocker envelope, domain-specific blocker content
- Status: Accepted
- Decision: Define one shared blocker/escalation envelope while allowing domain-specific blocker payload extensions.
- Rationale: Shared lifecycle and escalation semantics are needed for convergence; domain payloads still carry specialized value.
- Consequences: Non-blocker-native loops may synthesize blockers first; transcript-edit keeps richer closure internals as extensions.
- When to revisit: After migration phases show whether envelope fields are insufficient or overly heavy.

### HD-007: Minimal shared run-state envelope stays narrower than full run ledger
- Status: Accepted
- Decision: Adopt a minimum shared run-state envelope for resumability and comparability, defer full canonical run ledger design.
- Rationale: Premature full-ledger abstraction risks overfitting and monolith drift before contracts are proven in implementation.
- Consequences: Keep baseline fields small and extension-friendly; trace remains the detailed event record.
- When to revisit: After Phase 5 and 6 implementation evidence clarifies true shared state pressure.

### HD-008: Transcript-edit authority split (ledger closure truth, registry lifecycle truth)
- Status: Accepted
- Decision: In transcript-edit, decision ledger is canonical for unresolved closure truth; blocker registry is canonical for blocker and escalation lifecycle truth; loop-state pending prompt fields and terminal outputs are projection/compatibility layers.
- Rationale: Current code already derives closure gates from ledger and lifecycle transitions from registry; formalizing split removes ambiguous dual ownership before migration.
- Consequences: Implementation must route authority reads/writes through canonical owners and treat compatibility fields as non-authoritative projections.
- When to revisit: After Phase 5 migration when duplicate pending-prompt paths are retired or when emergent blocker behavior suggests a different authority split.

### HD-009: Canonical trace normalization uses per-loop adapters with a shared builder
- Status: Accepted
- Decision: Implement canonical traces with per-loop-family adapters (`controller_kernel`, `transcript_edit`) that feed a small shared canonical builder layer for schema/order/index enforcement.
- Rationale: Avoids a central trace monolith while still enforcing one canonical contract surface.
- Consequences: Loop semantics remain owned by family adapters; shared builder remains contract mechanics only.
- When to revisit: If a third loop family reveals missing shared seams or duplicate adapter logic that justifies refactoring boundaries.

### HD-010: First rollout slice is adapter-first and read-only across both loop families
- Status: Accepted
- Decision: First implementation slice ships read-only canonical trace adapters for both loop families from existing persisted artifacts, with schema and mapping tests; no runtime rewrites.
- Rationale: Lowest-risk path to prove canonical schema viability across heterogeneous sources.
- Consequences: Early traces may be partial for some historical runs; runtime emitters are deferred.
- When to revisit: After first slice results show where runtime-native enrichment is worth the complexity.

### HD-011: Raw-plus-canonical retention model
- Status: Accepted
- Decision: Keep existing raw observability artifacts as source of truth and treat canonical traces as additive normalized derivatives linked to raw source refs.
- Rationale: Preserves forensic fidelity and avoids lossy migration to a new single store.
- Consequences: Search should target canonical fields, while deep replay/debug follows source links to raw artifacts.
- When to revisit: If storage/query costs or operational complexity justify changing default retention and indexing strategy.

## Change Protocol

For each new major decision or reversal, append an entry with:
- decision id
- status (`accepted`, `superseded`, `reversed`, `proposed`)
- rationale
- consequences
- explicit revisit condition

If an accepted decision is revised, keep original entry and add a newer entry that references the prior id.
