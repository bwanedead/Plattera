# Mission State Migration Roadmap

Date: 2026-03-26
Status: Planning roadmap
Scope: Shared naming migration, organized-work migration, transcript-edit focus cleanup, and rollout order

Related:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/mission-state-and-resolution-state-architecture.md`
- `docs/architecture/harness/domain-pack-architecture.md`
- `docs/architecture/harness/generic-harness-native-core-guardrails.md`
- `docs/architecture/harness/generic-harness-native-core-target.md`
- `docs/architecture/harness/generic-harness-native-core-roadmap.md`
- `docs/architecture/harness/generic-work-board.md`
- `docs/architecture/harness/transcript-edit-domain-pack-target.md`

---

## 1. Purpose

This document lays out the implementation order for moving the harness from the current transitional organized-work stack toward the intended `mission_state` / `resolution_state` model.

This is not a one-shot refactor.

The main concerns need to be separated:

- naming cleanup
- shared state-contract cleanup
- transcript-edit focus cleanup
- runtime continuity cleanup
- compatibility retirement

If all of those are mixed together, the migration will become harder to reason about and easier to break.

---

## 2. Current Reality

Current repo reality is:

- `work_board.v1` is still the stable wire/schema id
- `harness.decision_ledger` is the current compatibility-facing organized-work package
- the constitution already says the target concepts are `mission_state` and `resolution_state`
- transcript-edit still adds deterministic advisory focus ranking on top of the shared organized-work surface
- transcript-edit focus hydration still carries steering-shaped support content
- transcript-edit's live focus path is now continuity-first; `decision_ledger_focus` and related focus-authority helpers remain compatibility-only until retirement

So the migration is not about inventing a new direction from scratch.

It is about finishing a direction the constitution already points toward.

If older domains become disposable or rebuildable, the preferred implementation order may shift to:

- shared harness core first
- domain re-entry later

That trunk-first path is now captured in:

- `docs/architecture/harness/generic-harness-native-core-target.md`
- `docs/architecture/harness/generic-harness-native-core-roadmap.md`
- `docs/architecture/harness/generic-harness-native-core-guardrails.md`

Under that trunk-first path, compatibility retention is not the goal.

The goal is to move useful behavior into the native core model and delete the legacy shared-core surfaces that no longer belong.

---

## 3. Non-Negotiable Outcomes

This roadmap is successful only if it produces all of the following:

- `work_board` stops being active architecture vocabulary
- `mission_state` becomes the top-level shared continuity concept
- `resolution_state` becomes the shared organized-work concept
- active-item continuity replaces deterministic advisory focus ranking as the main coherence mechanism
- transcript-edit stops maintaining a de facto second focus-authority system
- shared state remains generic and domain packs remain semantic owners

---

## 4. Phase Plan

## 4.1 Phase 1: Vocabulary And Contract Freeze

Goal:

- establish `mission_state` / `resolution_state` as the official architecture vocabulary for new work

Actions:

- add the new architecture docs
- mark `generic-work-board.md` as transitional
- stop using `work_board` as the active teaching term in new docs
- stop describing `decision_ledger` as the final target metaphor

Expected result:

- the repo has one clear conceptual direction even if compatibility names still exist in code

---

## 4.2 Phase 2: Shared State Contract Definition

Goal:

- define the actual shared contract shape for `mission_state` and `resolution_state`

Primary targets:

- shared harness contracts
- minimal shared run-state envelope
- runtime observation / mission snapshot surfaces

Actions:

- introduce or adapt shared contract models for:
  - `mission_state`
  - `resolution_state`
  - generic `resolution_state` items
  - lightweight relations
  - `active_item_id`
- preserve compatibility aliases where needed
- keep the first version structurally simple

Important:

- do not build a heavy graph engine
- do not force every domain to fully rewrite native state immediately

Expected result:

- the harness has a real shared state target instead of just a naming aspiration

---

## 4.3 Phase 3: Runtime Active-Item Continuity

Goal:

- make `active_item_id` the primary mechanical continuity rail

Primary targets:

- mission runtime continuity surfaces
- focus-packet continuity plumbing
- runtime observation / recent-lane helpers

Actions:

- define how the runtime preserves:
  - `active_item_id`
  - bounded recent history for that item
  - item-local continuity summaries where useful
- ensure the runtime carries the previous active item forward mechanically
- ensure the agent remains free to continue, switch, reopen, or resolve

Important:

- this is continuity transport, not semantic item selection

Expected result:

- coherence across iterations without deterministic focus ranking

---

## 4.4 Phase 4: Transcript-Edit Focus Cleanup

Goal:

- remove the main remaining transcript-edit architectural mismatch with the constitution and the new state model

Primary targets:

- `backend/agents/transcript_edit/decision_ledger_focus.py`
- `backend/agents/transcript_edit/focus_hydration.py`
- transcript-edit focus packet assembly

Actions:

- remove or heavily demote deterministic advisory focus ranking
- stop treating ranked candidate ordering as the practical source of focus truth
- simplify hydration so it carries:
  - relevant evidence
  - relevant context
  - recent item history
  - item-local continuity
- remove or demote:
  - `working_plan`
  - `current_goal`
  - `advisory_hints`
  - steering-shaped `policy_signals`

Expected result:

- transcript-edit uses active-item continuity and shared organized-work truth rather than a second deterministic focus-authority layer

---

## 4.5 Phase 5: Transcript-Edit Resolution-State Projection

Goal:

- make transcript-edit's shared read truth explicitly `resolution_state`-shaped

Primary targets:

- current transcript-edit decision-ledger projection surfaces
- runtime packet read surfaces
- focus packet inputs

Actions:

- adapt the unified read projection from legacy work-board/decision-ledger wording toward `resolution_state`
- preserve native transcript-edit write seams only where still needed
- ensure runtime reads, closure reads, and packet reads consistently use the shared state projection

Expected result:

- transcript-edit native state remains bounded and local
- shared organized-work read truth becomes clearly shared-state based

---

## 4.6 Phase 6: Deed-To-IR Adoption

Goal:

- make deed-to-IR use the same shared state concepts without forcing transcript-edit-specific behavior into deed

Primary targets:

- deed runtime context/projection seams
- deed runtime result / packet surfaces where organized work is relevant

Actions:

- adopt the same `mission_state` / `resolution_state` vocabulary and contracts
- keep deed-native meaning in deed-local modules
- avoid introducing deed-specific shared ontology

Expected result:

- multiple domain packs now align to the same shared state model

---

## 4.7 Phase 7: Compatibility Retirement

Goal:

- demote old naming and compatibility surfaces so they stop teaching the wrong architecture

Primary targets:

- `harness.work_board`
- `harness.decision_ledger`
- docs and public helper surfaces

Actions:

- keep compatibility aliases where runtime stability still requires them
- explicitly mark them secondary
- retire or rename them once downstream usage is small enough

Expected result:

- `work_board` becomes a historical compatibility seam rather than living architecture

---

## 4.8 Phase 8: Live-Use Validation

Goal:

- validate the new state model under real mission usage before any freeze or authoring guide

Actions:

- run controlled live transcript-edit and deed-to-IR missions
- inspect whether `active_item_id` continuity produces coherent follow-through
- inspect whether items are naturally reopened, resolved, or superseded cleanly
- inspect whether any missing relation/history fields become obvious
- only then decide what should be frozen

Expected result:

- architecture hardens from use instead of paper preference

---

## 5. Recommended Immediate Starting Order

The next practical implementation order should be:

1. shared state contract definition
2. transcript-edit focus cleanup
3. runtime active-item continuity
4. transcript-edit shared-state projection cleanup
5. deed adoption

Reasoning:

- transcript-edit focus ranking is the clearest remaining architectural impurity
- shared contract naming should be settled before domain cleanup starts landing
- active-item continuity should replace ranking, not be bolted on afterward

---

## 6. Prompt Inheritance Note

For the current phase of this migration, prefer:

- `FULL` prompt inheritance as the default and active mode everywhere meaningful

`LIGHT` may remain as dormant compatibility or future optimization support.

But it should not be part of the active architectural story while the organized-work and continuity model are still changing.

---

## 7. Risks To Avoid

Main migration risks:

- renaming things without changing the underlying semantics
- replacing ranking with a softer-sounding but still deterministic chooser
- overbuilding a graph engine before the simpler shared state shape is proven
- forcing transcript-edit-specific assumptions into shared state contracts
- preserving compatibility names so strongly that they remain the real teaching surface

---

## 8. Definition Of Completion

This roadmap is complete when:

- `mission_state` and `resolution_state` are the actual shared architecture terms
- transcript-edit no longer relies on deterministic advisory focus ranking
- active-item continuity is the main coherence rail
- shared read truth is state-based rather than board/ledger-metaphor based
- compatibility layers remain secondary and obviously transitional
- the system has survived real usage before any freeze/authoring effort

---

## 9. Summary

The migration should not be treated as a rename-only pass.

It is a semantic cleanup with three main goals:

- better naming
- better organized-work structure
- removal of deterministic focus steering

The immediate highest-value target is transcript-edit focus cleanup, but it should be done against the shared `mission_state` / `resolution_state` direction rather than as another local patch.
