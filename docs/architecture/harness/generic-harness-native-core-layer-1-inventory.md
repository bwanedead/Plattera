# Generic Harness Native Core Layer 1 Inventory

Date: 2026-03-27
Status: Shared-trunk inventory and first-layer replacement map
Scope: Shared harness core only; domain rebuilds happen later

Related:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/generic-harness-native-core-guardrails.md`
- `docs/architecture/harness/generic-harness-native-core-target.md`
- `docs/architecture/harness/generic-harness-native-core-roadmap.md`
- `docs/architecture/harness/native-harness-core-and-domain-pack-architecture-v1.md`

---

## 1. Purpose

This document inventories the **first shared layer that must be corrected** before the harness can become natively aligned end to end.

It exists to answer:

- what is still load-bearing in the shared trunk today
- what functionality must be preserved during cutover
- what can be renamed, what must be re-homed, and what should be deleted
- what the correct first implementation order is

This is not a domain migration doc.

It is the shared-trunk replacement map that should govern the first serious harness refactor slices.

---

## 2. First-Layer Scope

This first layer includes the shared surfaces that currently define the organized-work and continuity grammar of the harness:

- `backend/harness/orchestration_kernel/`
- `backend/harness/work_board/`
- `backend/harness/decision_ledger/`
- `backend/harness/run_state.py`
- `backend/harness/mission_runtime/`
- `backend/harness/tracing/adapters/mission_runtime.py`

This first layer does **not** require transcript-edit to be preserved as an architectural template.

It also does not yet require:

- transcript-edit internal rebuild
- deed-to-IR rebuild
- frontend/viewer cleanup
- final domain re-entry

Those come later.

The point of this layer is to make the **shared trunk itself** native first.

---

## 3. Functionality That Must Survive The First Layer

The first layer may replace old shapes, but it must preserve the useful mechanics already present:

- mission continuity across cycles
- active-item continuity
- kernel-owned HITL transport state machine
- kernel-owned loop brakes and retry rails
- bounded blocker / waiting / verification posture summaries
- prompt-event and rationale-strip observability
- traceability and run-state reporting
- mission-runtime transition application and artifact handoff transport

The refactor must preserve those mechanics without preserving the old metaphors that currently house them.

---

## 4. Inventory By Shared Area

## 4.1 Orchestration Kernel

Primary files:

- `backend/harness/orchestration_kernel/contracts.py`
- `backend/harness/orchestration_kernel/loop_memory.py`
- `backend/harness/orchestration_kernel/kernel.py`
- `backend/harness/orchestration_kernel/progress.py`
- `backend/harness/orchestration_kernel/run_progress_frame.py`
- `backend/harness/orchestration_kernel/trace_collector.py`

Why this is the first cut:

- the live loop still centers `WorkStateProjection`
- loop memory still stores `work_item_collection`, `blocker_surface`, and `closure_posture_summary`
- focus continuity still speaks `selected_focus_key` / `active_focus_key`
- the kernel remains the practical organized-work center of the harness

Legacy constructs to retire from the kernel center:

- `WorkStateProjection`
- `work_item_collection`
- `blocker_surface`
- `closure_posture_summary`
- `selected_focus_key`
- `ranked_work_item_list`
- `active_focus_key` as the long-term canonical name

Functionality to preserve:

- HITL transport law
- retryable refusal handling
- invalid-plan and repeated-refusal brakes
- no-progress counters as mechanical telemetry only
- prompt-event / rationale continuity transport
- bounded terminal decision rails

Classification:

- `contracts.py`: behavior-to-rehome
- `loop_memory.py`: behavior-to-rehome
- `kernel.py`: behavior-to-rehome
- `progress.py`: keep but re-audit after kernel cutover
- `run_progress_frame.py`: keep, then align to native names
- `trace_collector.py`: keep, then align payload names if needed

First-layer judgment:

- this is the true center of gravity
- if this area is not corrected first, every later migration will become another adapter around old kernel truth

---

## 4.2 Shared Organized-Work Compatibility Packages

Primary files:

- `backend/harness/work_board/contracts.py`
- `backend/harness/work_board/emergence.py`
- `backend/harness/work_board/lifecycle.py`
- `backend/harness/work_board/recent_iteration_lane.py`
- `backend/harness/work_board/__init__.py`
- `backend/harness/decision_ledger/contracts.py`
- `backend/harness/decision_ledger/__init__.py`

Current reality:

- `work_board` still owns real helper behavior, not just naming residue
- `decision_ledger` is a compatibility package layered on top of `work_board`
- `recent_iteration_lane.py` still carries old board grammar and even a future-motion-shaped slot (`next_move_more_likely`)

Retirement targets:

- the `work_board` package as a canonical shared package center
- the `decision_ledger` package as a canonical shared package center
- `work_board.v1` as the enduring organized-work wire identity
- board/ledger-shaped continuity field names

Classification:

- `work_board/contracts.py`: behavior-to-rehome into native `resolution_state` helpers, then delete
- `work_board/emergence.py`: re-justify each helper individually; keep only truly generic mechanics, otherwise delete
- `work_board/lifecycle.py`: keep only if the lifecycle rules still make sense as native generic item lifecycle helpers
- `work_board/recent_iteration_lane.py`: replace and delete
- `work_board/__init__.py`: delete-on-cutover
- `decision_ledger/contracts.py`: delete-on-cutover once callers migrate
- `decision_ledger/__init__.py`: delete-on-cutover once callers migrate

Constitutional watchpoint:

- `emergence.py` is especially sensitive because “promotion” helpers can quietly become deterministic work authorship if they do more than structural gating

---

## 4.3 Shared Run-State And Runtime Projection

Primary files:

- `backend/harness/run_state.py`
- `backend/harness/mission_runtime/contracts.py`
- `backend/harness/mission_runtime/runtime.py`
- `backend/harness/mission_runtime/observability.py`
- `backend/harness/mission_runtime/capabilities/transition.py`
- `backend/harness/mission_runtime/mapping_family.py`
- `backend/harness/tracing/adapters/mission_runtime.py`

Current reality:

- `run_state.py` already exposes `mission_state` / `resolution_state`, but still imports transcript-edit `decision_ledger` adapters and still supports legacy readers
- mission-runtime contracts still expose semantic convenience fields like:
  - `next_step_hint`
  - `expected_next_work`
- observability and trace payloads still serialize those fields

Retirement targets:

- legacy organized-work readers inside `run_state.py`
- semantic next-work hint fields in mission-runtime contracts and observations
- trace payloads that keep teaching those hint fields as normal runtime truth

Functionality to preserve:

- mission identity and mode continuity
- transition application
- artifact handoff refs
- blocker / verification / resumability posture
- family coordination transport
- run-state hydration for the native shared model

Classification:

- `run_state.py`: behavior-to-rehome and slim after kernel cutover
- `mission_runtime/contracts.py`: behavior-to-rehome; remove next-work / next-step hint semantics
- `mission_runtime/runtime.py`: keep, but adapt to the new contract shapes
- `mission_runtime/observability.py`: keep, then cut legacy or semantic hint fields
- `mission_runtime/capabilities/transition.py`: keep, then re-audit against the new contract
- `mission_runtime/mapping_family.py`: keep, but remove semantic forward-work hint dependence
- `tracing/adapters/mission_runtime.py`: keep, then cut `expected_next_work` from trace payloads

Constitutional watchpoint:

- `next_step_hint` and `expected_next_work` are small but real semantic-authoring risks and should not survive as shared-trunk runtime truth

---

## 4.4 First-Layer Follow-On: Shared Execution-Core Purity Check

This is not the first cut, but it is the next shared-core audit after organized-work cutover.

Primary follow-on surfaces:

- `backend/agent_kernel/models.py`
- `backend/agent_kernel/actions.py`
- `backend/agent_kernel/session.py`
- `backend/agent_kernel/run_artifact.py`

Why it matters:

- the harness is not truly end to end until the execution-core side is also generic and pack-driven
- mission-specific action families or artifact slots in shared execution contracts would undermine the same native goal from a different direction

This should begin only after the organized-work center is no longer legacy-shaped.

---

## 5. First-Layer Implementation Order

The correct first-layer sequence is:

1. lock the replacement map for the kernel-centered shared surfaces
2. cut over the orchestration kernel contracts and loop memory to native shared state
3. replace shared organized-work helpers with native `resolution_state` helpers
4. clean shared continuity / lane helpers so they are observational only
5. cut over `run_state`, mission-runtime contracts, observability, and tracing to the native model
6. delete retired `work_board` / `decision_ledger` shared packages and old shared exports

What not to do:

- start by deleting compatibility packages before the kernel no longer depends on the old grammar
- start in transcript-edit and try to infer the trunk shape from domain pain
- leave the mission-runtime hint fields alive because they look harmless

---

## 6. Phase Exit Tests For The First Layer

Do not call the first layer complete until all of the following are true:

- the kernel no longer uses `WorkStateProjection` as its organized-work center
- loop memory no longer stores the old three-surface work-state grammar as native truth
- shared organized-work helpers speak `resolution_state` directly
- `work_board` and `decision_ledger` are no longer shared-core package centers
- continuity helpers are observational only and carry no next-step residue
- mission-runtime contracts no longer expose `next_step_hint` / `expected_next_work` as shared runtime truth
- run-state, observability, and tracing speak the native model directly
- old shared-core files that no longer own unique behavior have been deleted

---

## 7. Summary

The first layer is the **shared trunk organized-work center**.

The real starting point is:

- orchestration kernel
- shared organized-work helper packages
- run-state / mission-runtime / trace projection seams

If that layer becomes native, the rest of the harness can be rebuilt or re-entered on top of a clean trunk.

If that layer stays legacy-shaped, every later “native” improvement will still sit on old kernel truth.
