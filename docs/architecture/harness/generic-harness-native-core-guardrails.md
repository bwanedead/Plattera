# Generic Harness Native Core Guardrails

Date: 2026-03-26
Status: Refactor guardrail doc
Scope: Implementation-facing rules for the shared harness core migration

Related:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/domain-pack-constitution.md`
- `docs/architecture/harness/generic-harness-native-core-target.md`
- `docs/architecture/harness/generic-harness-native-core-roadmap.md`
- `docs/ethos/architecture-ethos.md`
- `docs/ethos/structure-ethos.md`

---

## 1. Purpose

This document translates the constitutions and repo ethos into concrete **refactor-process guardrails** for the native harness-core migration.

It exists because this kind of cleanup is where corruption usually sneaks back in through:

- compatibility convenience
- helper creep
- adapter stacks
- deterministic semantic shortcuts
- “we will delete it later” dead code accumulation

This document is implementation-facing.

The constitutions remain the higher law.

These guardrails are meant to stay present in every refactor slice.

If a slice is “native” on paper but violates these rules in practice, it is not a successful slice.

---

## 2. Ownership Rule For The Refactor

The migration must preserve this triangle:

- harness owns mechanics
- domain pack owns semantics
- agent authors motion

That means:

- shared core code may carry continuity, persistence, execution, and observation
- domain code may interpret work meaning, closure meaning, feedback meaning, and handoff meaning
- neither shared core nor deterministic domain helpers may author what the next meaningful move is

If a refactor makes these harder to distinguish, it is a bad refactor even if the code gets smaller.

---

## 3. Determinism Rule For The Refactor

This migration must make semantic theft by deterministic code **harder**, not easier.

Reject any shared-core refactor that:

- ranks candidate work in a way that becomes practical focus truth
- injects next-step hints into continuity state
- upgrades ambiguous state into semantic meaning without model authorship
- invents blocker meaning through shared taxonomies
- turns convenience summaries into semantic truth stores
- silently chooses the active work item from deterministic heuristics

Allowed deterministic behavior:

- shape validation
- continuity transport
- persistence
- bounded summaries
- execution dispatch
- retry and budget mechanics
- generic lifecycle transport

Forbidden deterministic behavior:

- work authorship
- focus authorship
- next-move authorship
- closure authorship
- semantic interpretation of domain evidence

---

## 4. Native-Over-Compatibility Rule

Do not build the new core by stacking new wrappers over old shared-core packages.

Preferred order:

1. define the native shared contract
2. move useful behavior into that contract and its helpers
3. sever old call paths
4. delete the old shared surface

What is not acceptable:

- a permanent adapter stack where `mission_state` / `resolution_state` is just a nicer shell over `work_board` / `decision_ledger`
- leaving old shared-core packages alive as shadow canonical implementations
- preserving old runtime payloads as the default path “for now” without a retirement plan

---

## 5. No Permanent Dual-System Rule

This migration must not end in a polite coexistence between:

- the shiny native system
- the real but hidden legacy system underneath it

That means:

- the final shared-core path must have one canonical home per responsibility
- the old and new organized-work metaphors must not both remain load-bearing
- the native path must stop depending on legacy shared-core packages once replacement behavior exists

Allowed during migration:

- a narrow, temporary shim with an explicit deletion trigger

Not allowed as a destination:

- a permanent “new API over old substrate” arrangement
- two public package centers for the same responsibility
- keeping legacy packages alive because deleting them feels risky or inconvenient

---

## 6. Deletion Is Part Of The Refactor

Deletion is not optional cleanup around the edges.

Deletion is part of the design correction.

The migration should actively remove:

- retired shared-core packages
- orphan compatibility modules
- helper files that no longer own unique behavior
- dead tests that only protect deleted metaphors
- docs that continue teaching retired shared-core concepts as if they are live

Every slice should ask:

- what new native surface is replacing this legacy surface?
- once the new surface exists, what can be deleted immediately?

If the answer is “nothing can be deleted yet” for too many slices in a row, the migration is starting to balloon instead of simplify.

---

## 7. Retirement Accounting Rule

Every refactor slice should explicitly name:

- what native surface was strengthened or introduced
- what old file, export, helper, or path is now deletable
- what temporary shim, if any, still remains
- what future slice is expected to delete that shim

Preferred migration posture:

- replace
- sever
- delete

Discouraged migration posture:

- add
- alias
- defer deletion indefinitely

If a slice cannot point to any reduced legacy surface area, it should be treated as suspect until proven otherwise.

---

## 8. Slimming Rule

The target aesthetic for this refactor is:

- fewer layers
- fewer metaphors
- fewer compatibility packages
- fewer pass-through helpers
- fewer duplicate read models

The migration should trend toward:

- tighter module responsibilities
- thinner shared helper surfaces
- more direct contracts
- less plumbing

Do not mistake:

- more adapters
- more aliases
- more compatibility wrappers
- more “temporary” projections

for progress.

The system should become smaller and more direct as it becomes more native.

---

## 9. Separation-Of-Concerns Rule

Slimming does **not** mean collapsing responsibilities into bigger files.

Reject refactors that “simplify” by:

- merging unrelated concerns into one large core file
- turning the kernel into a catch-all
- hiding domain semantics inside shared runtime helpers
- moving domain-specific logic into shared validation or continuity utilities

Preferred simplification:

- fewer concepts
- fewer layers
- clearer boundaries
- smaller canonical surface area

Not:

- fewer files at the cost of blur

---

## 10. Retirement Discipline

Every legacy shared-core surface should be classified as one of:

- rename-only
- behavior-to-rehome
- temporary shim
- delete-on-cutover

Temporary shims must have:

- a clearly named replacement
- a bounded owner
- a retirement condition

What must not happen:

- compatibility surfaces lingering without a deletion decision
- retired metaphors staying in public exports
- dead modules surviving because they are inconvenient to remove

---

## 11. File And Module Smell Checks

During the migration, treat these as warning smells:

- a new file exists only to translate one old shared-core name to another
- a module’s main job is preserving retired vocabulary
- a helper surface is only there because the old structure still exists
- both the old and new shared-core concepts are being taught in the same primary runtime path
- a refactor adds more package-level indirection than it deletes

When these appear, stop and ask whether the old surface should just be removed.

---

## 12. Required Review Questions Per Slice

Every harness-core refactor slice should be reviewed with these questions:

1. Did the slice reduce shared-core legacy surface area?
2. What old files, exports, or helpers became deletable because of this slice?
3. Did any deterministic helper gain semantic authority?
4. Did any shared helper start interpreting domain meaning?
5. Is the new core path more direct than before?
6. Did the number of compatibility layers go down, not up?
7. Is the result more native, more mechanical, and more generic?
8. Did we remove old public teaching surfaces or merely annotate them?

If the answers trend the wrong way, the slice is regressing even if tests pass.

---

## 13. Summary

The native harness-core migration must be:

- constitutional
- subtractive
- trunk-first
- separation-preserving
- anti-ballooning

The goal is not to politely preserve the old system.

The goal is to replace it with a smaller, cleaner, more native trunk and to delete what no longer belongs.
