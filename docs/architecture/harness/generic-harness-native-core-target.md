# Generic Harness Native Core Target

Date: 2026-03-26
Status: Target architecture and implementation anchor
Scope: Shared harness trunk only; transcript-edit and other domains are consumers, not template dictators

Related:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/domain-pack-constitution.md`
- `docs/architecture/harness/native-harness-core-and-domain-pack-architecture-v1.md`
- `docs/architecture/harness/mission-state-and-resolution-state-architecture.md`
- `docs/architecture/harness/generic-harness-native-core-guardrails.md`
- `docs/architecture/harness/generic-harness-native-core-roadmap.md`

---

## 1. Purpose

This document defines the intended **end-to-end native shape of the generic harness core**.

It exists for the situation where:

- the target shared architecture is now clearer than the historical implementation
- transcript-edit and other early domains should no longer be allowed to dictate the shape of the harness
- legacy `work_board` / `decision_ledger` compatibility must be retired rather than preserved forever

This is the trunk-first target.

It is not:

- a transcript-edit migration plan
- a promise that every existing domain will be migrated in place
- a requirement to preserve old runtime payload shapes indefinitely

---

## 2. Core Claim

The harness should become natively organized around:

- `mission_state`
- `resolution_state`
- active-item continuity
- generic runtime and orchestration mechanics
- pluggable domain packs

It should **not** remain natively organized around:

- `work_board`
- `decision_ledger`
- ranked candidate focus context
- transcript-edit checklist metaphors

If older domains still depend on those concepts, they should adapt or be rebuilt.

The harness core should not stay shaped around them.

---

## 3. What “Native” Means Here

The harness is native only when the live core uses the new model directly rather than projecting it from older compatibility surfaces.

That means:

- the orchestration kernel stores and carries generic continuity in terms that align with `mission_state` / `resolution_state`
- the primary organized-work helpers are `resolution_state` helpers, not `work_board` helpers under a new wrapper
- continuity lanes and packet surfaces do not preserve old semantic hint slots
- runtime, trace, and reporting surfaces can speak the new model directly

It does **not** mean:

- a new reporting layer projects `mission_state` while the kernel still runs on older internal work-state concepts
- the old packages remain load-bearing but are called “compatibility”
- the new system is just a thin narrative veneer over the old contracts
- the repo carries a public native path and a shadow legacy path for the same shared responsibility

---

## 4. Native Shared Stack

The intended shared stack is:

1. `MissionRuntime`
2. `OrchestrationKernel`
3. `ExecutionKernel`
4. `mission_state`
5. `resolution_state`
6. `DomainPack`

Shared ownership split:

- mission runtime owns top-level mission continuity, mode/pack selection, transition application, and observation
- orchestration kernel owns loop law, continuity transport, focus continuity carriage, and mechanical rails
- execution kernel owns action dispatch, idempotency, retries, and persistence
- `mission_state` owns top-level generic continuity
- `resolution_state` owns the generic active work/problem surface
- domain packs own semantics and mapping from domain-native truth into the shared generic containers

---

## 5. Native Kernel Model

The orchestration kernel is the most important shared seam to correct.

The native target is:

- kernel continuity should center active-item continuity rather than ranked work-item lists
- kernel memory should carry generic continuity and generic work state, not a historical “work-state projection” metaphor
- domain pack hook outputs should align to `resolution_state`-shaped shared truth rather than a three-surface transitional projection

Implication:

- `selected_focus_key` should be treated as transitional
- `ranked_work_item_list` should not remain the kernel-era organized-work companion surface
- `work_item_collection`, `blocker_surface`, and `closure_posture_summary` should not remain the practical native state model forever

The kernel may still preserve:

- active item continuity
- blocker posture
- waiting posture
- closure posture summaries

But those should exist as bounded summaries or views over native generic state, not as the harness’s final organized-work contract.

---

## 6. Native Shared State Model

`mission_state` should be the actual top-level continuity object.

`resolution_state` should be the actual generic organized-work surface.

The first-class deterministic rail should be:

- `active_item_id`

The first-class generic work shape should be:

- `items`
- `relations`
- bounded item-local history
- generic summaries or domain payload when needed

The harness may preserve and normalize this state.

It must not:

- rank practical meaning
- choose semantic next work
- inject next-step advice into continuity containers

---

## 7. Legacy Surfaces To Retire

The following should be treated as retirement targets, not permanent architecture:

- `backend/harness/work_board/`
- `backend/harness/decision_ledger/`
- `work_board.v1` as the lasting wire identity
- kernel-native `WorkStateProjection` as the final shared work contract
- continuity helpers that still preserve next-step hint slots or board-centric terminology
- shared continuity helpers that still expose legacy board/ledger vocabulary where native generic names now exist
- shared observability or trace surfaces that still speak the legacy model as if it were canonical

Transcript-edit-specific retirement targets are separate and can be handled later or by rebuild.

This document is about the shared trunk.

---

## 8. What Must Be Preserved During Retirement

Removing legacy structure must not throw away the useful behavior already present.

The native trunk still needs to preserve:

- generic continuity across iterations
- active-item continuity
- resumability and waiting posture
- blocker and verification summaries as bounded generic posture
- traceability and observability
- family coordination and handoff posture projection
- domain-pack replaceability

The migration should extract these behaviors from the legacy surfaces and re-home them in native shared contracts.

It should not preserve the old containers just because they currently house those behaviors.

---

## 9. Determinism Guardrail For The Core Refactor

This refactor is high-risk for constitutional drift because shared helpers and continuity utilities are the easiest place to smuggle deterministic authorship back in.

The core refactor must reject:

- ranked candidate focus truth in shared kernel memory
- next-move hint slots in shared continuity helpers
- scripted blocker meaning in shared contracts
- work-item creation from deterministic domain heuristics in shared layers
- mission-specific work semantics in shared runtime or orchestration contracts

The generic harness should become more mechanical and more generic as it becomes cleaner.

Not more “helpful.”

This implementation-facing discipline is expanded in:

- `docs/architecture/harness/generic-harness-native-core-guardrails.md`

---

## 10. Deletion And Slimming Rule

This target assumes the refactor is **subtractive** as well as corrective.

That means:

- if a shared legacy surface has no place in the native model, it should be deleted
- compatibility wrappers should be temporary and explicitly bounded
- the harness should get smaller and more direct as it becomes more native

The target is not:

- more adapters
- more compatibility shells
- more side-by-side old and new shared packages

The target is:

- fewer metaphors
- fewer helper layers
- fewer legacy modules
- more direct shared contracts
- one canonical shared-core path per responsibility

Every successful replacement slice should leave behind something that is now deletable.

If the new trunk keeps growing while the old trunk remains intact, the migration is failing even if the target contracts look better.

---

## 11. Relationship To Domains

This target explicitly allows the shared trunk to move ahead of older domains.

If an existing domain is too legacy-shaped, the preferred outcomes are:

- a thin temporary adapter while the trunk is corrected
- or a full domain rebuild against the corrected trunk

What is not acceptable:

- preserving a legacy shared shape because an older domain was built against it

The trunk sets the law.

Domains consume that law.

---

## 12. Definition Of “Shiny End-To-End Harness”

The generic harness can be considered clean only when all of the following are true:

- `mission_state` and `resolution_state` are the live shared state concepts, not just reporting/projection vocabulary
- the orchestration kernel no longer relies on `WorkStateProjection` as a legacy organized-work center
- `work_board` and `decision_ledger` are gone from shared core packages and primary contracts
- continuity helpers carry history and posture only, not next-step hint residue
- the runtime and observation layers can speak the native model directly
- old shared-core files that no longer own unique behavior have been removed, not merely deprecated in place
- there is no permanent shadow legacy substrate still carrying the same organized-work responsibility behind the native API
- at least one rebuilt or cleanly adapted domain can run against the new trunk without reintroducing the old metaphors

---

## 13. Summary

The goal is not:

- mission-state reporting on top of legacy kernel truth

The goal is:

- a generic harness whose live core is actually native to `mission_state` / `resolution_state`

That means:

- clean trunk first
- domains second
- legacy compatibility last and temporary

This is the architecture target the repo should now build toward.
