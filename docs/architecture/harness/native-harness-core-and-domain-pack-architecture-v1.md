# Native Harness Core And Domain-Pack Architecture v1

Date: 2026-03-22  
Status: Working architecture spec for core/packs separation  
Scope: Generic harness design, not domain implementation design

Related:
- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/agent-kernel/domain-pack-interface-v1.md`
- `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md`

## Purpose

This document defines the native target architecture for Plattera's generic harness.

It exists to answer one question clearly:

**What is the harness when no concrete domain is treated as the reference implementation?**

This document is intentionally about:
- ownership
- vocabulary
- boundaries
- registration seams
- banned leakage
- implementation order

It is intentionally **not**:
- a transcript-edit migration brief
- a promise of final field-level schemas
- a frozen plugin API for all time
- a defense of existing built-in mission families

The goal is to define the generic machine first.
Concrete domains return later as consumers of that machine.

---

## 1. Core Doctrine

The harness owns:
- process shape
- continuity
- execution rails
- generic state
- registration and composition seams

The domain pack owns:
- meaning
- ontology
- doctrine
- prompts
- tools/providers
- evidence strategy
- closure semantics
- domain interpretation of generic state

Short form:

**The harness owns process. The domain pack owns meaning.**

This is the primary architectural rule.

**Deed / feature-graph stack:** Compile, judge, georeference, render, and the feature graph itself are **domain infrastructure** for deed→IR. The harness may call them through providers and product-default composition; it must not encode their meaning as harness-native ontology. Session-level state uses generic `artifact_refs` buckets; deed-specific projection lives in domain-owned projectors.

---

## 2. Vocabulary

### 2.1 Approved generic terms

Use these as the target harness vocabulary:

- `mission_state`
- `resolution_state`
- `domain_pack`
- `provider`
- `execution_action`
- `transition`
- `terminal posture`
- `evidence`
- `blocker`
- `dependency`
- `focus`

### 2.2 Deprecated or discouraged terms

- `work_board`
  - deprecated migration vocabulary
- `decision_ledger`
  - acceptable only as legacy/transitional naming where code has not been migrated yet
  - do not treat it as the master conceptual term for the future harness

### 2.3 Naming intent

`mission_state` is the top-level harness continuity concept.

`resolution_state` is the generic active problem/work concept.

These terms are preferred because they do not force:
- a task-board metaphor
- a queue metaphor
- a backlog metaphor
- a purely linear ledger metaphor

If implementation later becomes graph-explicit, a graph may exist inside `resolution_state`.
The harness does not need to commit to graph vocabulary before the code actually warrants it.

---

## 3. Target Layer Stack

The native harness stack is:

1. `MissionRuntime`
2. `OrchestrationKernel`
3. `ExecutionKernel`
4. shared generic state surfaces
5. `DomainPack`

### 3.1 Mission Runtime

Owns:
- mission identity
- active pack / active mode
- continuity across cycles
- transition application
- resumability
- top-level observability
- top-level terminal handoff

Does not own:
- domain truth
- domain ontology
- domain closure meaning
- domain tool logic

### 3.2 Orchestration Kernel

Owns:
- loop law / phase grammar
- generic loop memory
- generic focus selection mechanics
- progress evaluation
- HITL lifecycle
- continue vs terminal routing

Does not own:
- domain interpretation
- domain evidence meaning
- domain closure doctrine
- domain ontology

### 3.3 Execution Kernel

Owns:
- provider dispatch
- idempotency
- budgets
- retries
- step persistence
- run/session artifact persistence
- generic execution result envelopes

Does not own:
- concrete mission families as built-ins
- domain ontology
- domain-specific action families as permanent core vocabulary

### 3.4 Shared generic state surfaces

Own:
- mission continuity containers
- active problem/work containers
- blocker/dependency/evidence envelopes
- orientation containers
- trace/event envelopes
- terminal taxonomy
- run/session envelopes

They do not own domain meaning.

### 3.5 Domain Pack

Owns:
- domain ontology
- prompt doctrine
- provider registration
- evidence strategy
- closure doctrine
- interpretation of generic state
- domain-native views/adapters if needed
- transition recommendations if needed

The domain pack is a skin on top of the harness, not a hidden co-owner of the core.

---

## 4. Minimal Invariants, Not Premature Ontology

This architecture deliberately avoids freezing large field-level schemas before implementation pressure proves them necessary.

The planning rule is:

**Define generic invariants early. Do not define speculative generic ontology early.**

That means:
- we should specify what kinds of objects the harness needs
- we should specify ownership and boundaries
- we should not prematurely declare detailed canonical field lists unless repeated runtime needs justify them

Examples of acceptable early commitments:
- a top-level continuity object exists
- an active problem/work object exists
- a domain pack registration seam exists
- a provider/action execution seam exists
- shared layers do not interpret domain payloads

Examples of unacceptable early commitments:
- forcing large fixed schemas for generic state before repo reality proves them
- turning illustrative fields into canonical architecture
- encoding domain-neutral-sounding but speculative ontology into the core

---

## 5. Mission State

`mission_state` is the harness-owned top-level continuity object.

### 5.1 What it is for

`mission_state` exists to preserve:
- identity
- continuity
- active pack/mode association
- resumability
- terminal/waiting posture
- references or pointers needed to resume or inspect the mission

### 5.2 What is safe to say now

`mission_state` must remain:
- minimal
- infrastructure-oriented
- generic
- pack-agnostic in meaning

It may point to pack-owned or domain-owned state.
It must not interpret or absorb that state's ontology.

### 5.3 What this doc intentionally does not freeze

This doc does **not** declare a final field list for `mission_state`.

Fields should emerge from repeated runtime needs, not from speculative architecture examples.

Derived summaries or convenience views may exist later.
They are not automatically part of the canonical core contract.

---

## 6. Resolution State

`resolution_state` is the harness-owned generic active problem/work surface.

### 6.1 What it is for

It represents the current shape of active work without forcing one narrow metaphor.

It should be capable of representing:
- sequential work
- revisited work
- blocked work
- dependency-shaped work
- parallelizable work
- convergent work

### 6.2 What is safe to say now

`resolution_state` may need to carry generic concepts such as:
- active items
- dependencies
- blockers
- evidence links
- ordering hints
- completion conditions
- state transitions
- opaque domain payload

But this document does **not** freeze final canonical fields.

### 6.3 Interpretation rule

The core may carry opaque domain payload inside `resolution_state`.
The core must not interpret domain-specific meaning from that payload.

### 6.4 Future graph possibility

If the internal implementation later becomes explicitly graph-shaped, that graph should live inside or beneath `resolution_state`.

Do not force graph terminology into the core before the implementation truly deserves it.

---

## 7. Domain Pack

A domain pack is a first-class architecture object.

It is not:
- one random adapter file
- a pile of mission helpers
- a secret extension of the harness core

It is:
- the bounded owner of mission meaning
- the provider of doctrine, tools, and interpretation for one mission family

### 7.1 Domain pack responsibilities

A domain pack may define:
- its ontology
- its prompt doctrine
- its evidence preferences
- its closure doctrine
- its state adapters/views
- its transition recommendations
- its provider/tool registrations
- its interpretation of generic harness surfaces

### 7.2 Domain pack responsibilities that must stay out of core

The domain pack must be the only place where it is intentional to define:
- what counts as evidence in that domain
- what a blocker means in that domain
- what completion means in that domain
- what tool families exist for that domain
- what semantic categories matter in that domain

---

## 8. Domain Pack Manifest

The harness should converge on a first-class registration seam conceptually equivalent to a `DomainPackManifest`.

This document does not freeze the final code signature.
It does define the categories of things the manifest must provide.

### 8.1 Manifest concerns

A manifest-like registration object should identify:
- pack identity
- active mode name
- pack version
- hook implementation surface
- provider registration surface
- doctrine/prompt surface
- closure policy surface
- transition policy surface
- optional state/observability adapters

### 8.2 Manifest rule

The harness should compose missions from registered packs.

It should not require:
- hardcoded built-in mission families in shared core
- hand-wired domain imports across shared layers as the long-term architecture

### 8.3 Registration rule

Packs should be registered and loaded through explicit seams.

The long-term target is:
- runtime selects a pack
- pack registers hooks/providers/doctrine
- shared core composes around those registrations generically

---

## 9. Execution Provider Model

The execution kernel should converge on a provider-based model rather than hardcoded concrete mission action families.

### 9.1 What the core should know

The core execution kernel may know:
- action identity
- provider identity
- payload structure
- expected outputs
- idempotency keys
- generic result envelopes

### 9.2 What the core should not know

The core execution kernel should not permanently encode:
- transcript-edit action families
- deed-to-IR action families
- concrete mission-specific artifact slots
- mission-specific output vocabularies as the native kernel contract

### 9.3 Migration direction

Shared kernel enums and built-in dependency bundles that hardcode mission families should be treated as transitional legacy unless they survive explicit generic review.

---

## 10. Banned Leakage

The following must not remain or be introduced as shared-core architecture:

- mission-specific action families in the execution kernel
- mission-specific latest-ref or artifact slots in shared kernel state
- mission-specific blocker classes
- mission-specific closure-layer systems
- mission-specific startup/read-model assumptions
- mission-specific prompt doctrine in shared layers
- mission-specific tool menus as built-in kernel truth

Sniff test:

If a concept would not make sense for all of the following, it probably does not belong in the shared core:
- transcript editing
- deed-to-IR
- a toaster workflow
- a research workflow
- an email assistant
- a finance-document workflow

---

## 11. Module Classification Direction

This is not a final migration ledger.
It is the current architectural judgment about likely ownership direction.

### 11.1 Likely core

These areas are directionally close to the desired generic core:

- `backend/harness/mission_runtime/`
- `backend/harness/orchestration_kernel/`
- `backend/agent_kernel/orientation/`
- `backend/harness/run_state.py`
- `backend/harness/terminal_taxonomy.py`

### 11.2 Transitional shared-core areas that need purification

These areas still appear to carry concrete mission families too directly:

- `backend/agent_kernel/models.py`
- `backend/agent_kernel/actions.py`
- `backend/agent_kernel/session.py`
- `backend/agent_kernel/run_artifact.py`

These should be reviewed as transitional core, not assumed-final architecture.

### 11.3 Pack-owned areas

Concrete mission packs should eventually own:

- `backend/agents/transcript_edit/`
- `backend/agents/controller/`

Those folders may still contain transitional seams today, but they should be treated conceptually as pack-owned territory rather than core harness templates.

---

## 12. Implementation Roadmap

### Phase 1 — Lock doctrine and vocabulary

Goal:
- finalize architecture language and separation boundary

Outputs:
- constitution alignment
- this spec
- explicit deprecation of `work_board`

### Phase 2 — Define native core contracts

Goal:
- define the minimal stable contract categories without overfreezing schemas

Outputs:
- mission runtime ownership
- orchestration kernel ownership
- execution kernel ownership
- `mission_state` role
- `resolution_state` role
- `DomainPackManifest` concept
- provider/action registration concept

### Phase 3 — Purify execution kernel

Goal:
- remove concrete mission built-ins from the shared execution substrate

Outputs:
- provider-based registration
- generic execution action/result envelopes
- no concrete mission action families as native core shape
- no concrete mission artifact slots as native core shape

### Phase 4 — Convert runtime composition to pack registration

Goal:
- make mission runtime compose around registered packs instead of hand-wrapped known domains

Outputs:
- pack registry or equivalent registration seam
- runtime composition driven by registration rather than built-in mission assumptions

### Phase 5 — Rename generic state surfaces

Goal:
- align naming with native architecture

Outputs:
- migration from `work_board` vocabulary
- migration toward `mission_state` and `resolution_state`

This should happen after ownership is corrected, not before.

### Phase 6 — Prove genericity with simple validation packs

Goal:
- test the harness without relying on legacy real domains

Suggested validation packs:
- toaster
- research
- document triage

These are not product features.
They are architecture proofs that the harness is truly generic.

### Phase 7 — Reintroduce real domains

Goal:
- design real mission packs from first principles against the new core

Transcript-edit and deed-to-IR should return later as pack consumers of the generic harness, not as template authors of the core.

---

## 13. Acceptance Criteria For “Generic Harness Complete”

Do not call the generic harness complete until all of the following are true:

- shared core imports no concrete domain modules by default
- execution kernel defines no concrete mission action families as native core shape
- shared run/session/result models contain no mission-specific slots as permanent core architecture
- `mission_state` and `resolution_state` are the canonical generic state concepts
- at least one simple non-transcript validation pack runs end-to-end
- transcript-edit is not required for any core harness test to make sense
- packs can be registered or swapped without editing shared core logic

---

## 14. Open Questions

These should remain explicit rather than being guessed away:

- What is the minimum truly stable generic state the harness must persist, versus what should remain pack-owned?
- What provider registration shape is mechanically simplest without becoming a new abstraction tangle?
- How much of today's `agent_kernel` should remain one package versus being split into a cleaner execution-core boundary?
- Which current summaries and read models should be core, adapter-owned, or deleted?
- When should `resolution_state` become graph-explicit, if at all?

Until these are proven by implementation pressure, keep the contracts thin.

---

## 15. Summary

The generic harness should be designed as if no concrete domain exists yet.

Its job is to provide:
- process shape
- continuity
- execution rails
- generic state
- registration seams

Its job is not to preserve the assumptions of any existing mission family.

Concrete domains come later as packs.
They do not define the native shape of the core.
