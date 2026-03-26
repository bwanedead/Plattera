# Generic Harness Native Core Roadmap

Date: 2026-03-26
Status: Planning roadmap
Scope: Shared harness trunk migration toward the native `mission_state` / `resolution_state` model

Related:

- `docs/architecture/harness/generic-harness-native-core-target.md`
- `docs/architecture/harness/native-harness-core-and-domain-pack-architecture-v1.md`
- `docs/architecture/harness/mission-state-and-resolution-state-architecture.md`
- `docs/architecture/harness/harness-constitution.md`

---

## 1. Purpose

This roadmap defines the implementation order for making the **shared harness core** natively aligned to:

- `mission_state`
- `resolution_state`
- active-item continuity

It is intentionally trunk-first.

It assumes older domains may be adapted later or rebuilt later.

That means this roadmap does **not** prioritize preserving transcript-edit-era shared contracts as the architectural center.

---

## 2. Current Shared-Core Reality

Current repo reality is split:

- the canonical direction is already documented as `mission_state` / `resolution_state`
- the reporting/projection layer already carries that model
- but the orchestration kernel still runs on older work-state contracts and continuity shapes
- shared compatibility packages (`harness.work_board`, `harness.decision_ledger`) still contain real contracts and helpers

So the trunk is directionally correct, but not yet natively coherent.

---

## 3. Non-Negotiable Outcomes

This roadmap succeeds only if it produces all of the following:

- the shared kernel becomes natively aligned to the new generic state model
- `work_board` and `decision_ledger` stop being shared-core package centers
- active-item continuity becomes the only deterministic focus rail that matters
- shared continuity lanes and packet helpers stop preserving next-step hint residue
- old domain compatibility does not dictate trunk architecture

---

## 4. Phase Plan

## 4.1 Phase 1: Shared-Core Inventory Freeze

Goal:

- explicitly classify which shared-core legacy surfaces are naming-only and which carry real behavior

Primary targets:

- `backend/harness/orchestration_kernel/`
- `backend/harness/work_board/`
- `backend/harness/decision_ledger/`
- `backend/harness/run_state.py`
- mission-runtime observation / trace seams

Outputs:

- a replacement map for:
  - rename-only surfaces
  - behavior-rehome surfaces
  - temporary shims
  - delete-on-cutover surfaces

---

## 4.2 Phase 2: Native Kernel Contract Cutover

Goal:

- replace the kernel’s transitional organized-work contract with one aligned to native generic state

Primary targets:

- `backend/harness/orchestration_kernel/contracts.py`
- `backend/harness/orchestration_kernel/loop_memory.py`
- `backend/harness/orchestration_kernel/kernel.py`
- any focus continuity helpers tied to the old work-state projection grammar

Actions:

- remove `WorkStateProjection` as the lasting shared work contract
- replace `work_item_collection`, `blocker_surface`, and `closure_posture_summary` as the practical center of shared work memory
- align focus continuity to `active_item_id` and native generic work summaries

Important:

- preserve generic blocker/waiting/closure posture as bounded summaries
- do not introduce deterministic work ranking while doing this

---

## 4.3 Phase 3: Shared Organized-Work Helper Replacement

Goal:

- replace `work_board` / `decision_ledger` shared helper packages with native generic-state helpers

Primary targets:

- `backend/harness/work_board/`
- `backend/harness/decision_ledger/`

Actions:

- create or adapt native helpers around `resolution_state`
- move any genuinely reusable behavior into the native helper layer
- delete or bury the older package surfaces once the kernel no longer depends on them

Important:

- preserve generic lifecycle and continuity utilities only if they remain generic
- remove any helper shape that assumes board/ledger metaphors as the final model

---

## 4.4 Phase 4: Shared Continuity / Lane Cleanup

Goal:

- make shared continuity helpers purely observational and native-model aligned

Primary targets:

- bounded recent-lane helpers
- packet-support continuity helpers
- shared tracing/observability helpers that still depend on old field names or old continuity slots

Actions:

- remove next-step hint residue from shared continuity shapes
- rename board/ledger-shaped continuity fields to native generic names
- keep continuity history useful without making it prescriptive

---

## 4.5 Phase 5: Runtime / Observability / Trace Native Projection

Goal:

- make runtime and observation layers speak the native model directly

Primary targets:

- `backend/harness/run_state.py`
- mission-runtime observation helpers
- tracing adapters
- review/reporting helpers that still assume legacy organized-work payloads

Actions:

- make `mission_state` / `resolution_state` the primary outward shared-state model
- delete or isolate legacy payload readers
- stop emitting old shared-core vocabulary from shared observation layers

---

## 4.6 Phase 6: Domain Re-entry

Goal:

- bring domains back onto the corrected trunk

Preferred order:

1. a tiny validation domain or harness sanity pack
2. deed-to-IR if convenient
3. transcript-edit rebuilt or freshly adapted later

Important:

- domains should consume the corrected trunk
- they should not shape it during this phase

---

## 5. Migration Rules

Use these rules through the entire roadmap:

- preserve behavior, not legacy containers
- if a legacy surface carries useful mechanics, re-home them into native shared helpers before deletion
- do not keep adapter stacks as the final design
- do not let runtime reporting become the only place where the new model is “real”

---

## 6. Determinism Watchpoints

The shared-core migration should be reviewed against these specific risks:

- ranked work-item lists returning as practical focus truth
- next-step hint fields reappearing in shared continuity containers
- shared generic helpers inventing blocker meaning
- compatibility shims quietly becoming the real source of semantic work state

The trunk should become more generic and more mechanical as it gets cleaner.

---

## 7. Effort Shape

This is not a cosmetic rename pass.

It is also not a full greenfield rewrite of the harness.

The expected shape is:

- medium effort in shared contracts and shared helpers
- medium-high effort in orchestration kernel cutover
- medium effort in runtime/trace/reporting cleanup
- then domain rebuild or re-entry after the trunk is corrected

The hardest part is the kernel contract cutover.

That is the real center of gravity.

---

## 8. Completion Standard

This roadmap is complete when:

- the shared harness core no longer depends on `work_board` / `decision_ledger` as primary contract packages
- kernel continuity is native to `mission_state` / `resolution_state`
- shared continuity helpers are observational only
- shared runtime/trace/reporting surfaces speak the native model directly
- at least one domain can run against the corrected trunk without reviving the old metaphors

---

## 9. Summary

The clean sequence is:

1. fix the trunk
2. retire shared legacy packages
3. then bring domains back

That is the fastest route to the shiny end-to-end harness without creating a second system beside the first.
