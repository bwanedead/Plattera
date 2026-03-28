# agents.md

## Scope
- Folder: `backend/harness/orchestration_kernel/`
- Purpose: Shared orchestration host and loop-governance layer. Sits above the execution kernel (`agent_kernel/`) and domain-pack seam.

## Contracts & invariants
- **Kernel is rails-first, not a semantic planner.** The loop still runs the same coarse hook order, but active work selection and semantic closure meaning stay agent/domain-authored. Do not reintroduce kernel-owned focus selection or phase doctrine.
- **Kernel owns:** continuity rails, HITL state, no-progress safeguards, invalid-plan safeguards, and terminal decision mechanics. It must not author semantic work inventory or closure truth.
- **Domain packs own:** domain evidence assembly, move resolution, execution compilation, progress metrics, and closure rules behind the shared kernel hooks. The harness should not teach retired domain-specific ontology as if it were part of kernel law.
- Current shared continuity is carried through `mission_state` / `resolution_state` plus bounded kernel observability. Treat older kernel-owned focus/inventory grammar as retired unless current code explicitly proves otherwise.
- **Domain packs must not write kernel-owned fields.** They surface updates only via hook return values.
- **Hook 8 constraint:** domain pack must not return `waiting_human` from `supply_closure_rules` unless `hitl_state != "no_prompt"`.
- **TerminalClass** values: `completed | blocked | waiting_human | waiting_evidence | exhausted | failed`. Subtypes go in `reason_code`, not as separate terminal classes.
- **HitlState machine:** `no_prompt → waiting → answered_unintegrated → consumed`. Kernel is sole actor writing this state.
- **`pending_refresh`** is set by the kernel when `ProgressDelta.reset_refresh` fires. Domain pack must not write this field.

## Allowed changes
- Add new fields to `LoopMemoryState` only when the kernel has a genuine governance need; update `contracts.py` in sync.
- Extend `DomainPack` protocol with new hooks only with a clear contract definition in docs first.
- `evaluate_progress` in `progress.py` is shared — changes affect all domain packs; test broadly before changing.

## Commands
- Test: `pytest backend/harness/orchestration_kernel/` (no tests yet; add alongside D4 parity checks)
- Lint: run from venv root

## Gotchas
- `MoveExecutionPlan.action_type` uses `Any` annotation (not `ActionType`) to avoid circular import with `agent_kernel.models`. The type alias comment in `contracts.py` explains this.
- Domain pack `evidence_signal_counter` (domain-owned) and `loop_memory.evidence_signal_counter` (kernel-owned) are separate counters. Hook 9 increments domain counter; kernel pre-phase increments kernel counter.
- HITL behavior differs from older loop behavior: kernel terminates with `waiting_human` and resumes; the older flow polled non-blocking. This is intentional.
- `run_artifact_ref` in `KernelLoopResult` defaults to `None` — the mission runtime adapter must pass the correct ref if available.
- If local docs drift back toward older kernel-owned focus/inventory grammar, treat that as stale teaching unless the current code still proves otherwise.

## Patterns
- Naming: hook functions on `DomainPack` match the loop seams (`orient`, `refresh`, `project`, `build_focus_packet`, `resolve_move`, `compile_move`, `supply_progress_metrics`, `supply_closure_rules`, `integrate_feedback`).
- Structure: `contracts.py` → frozen dataclasses + Protocol; `loop_memory.py` → mutable kernel state; `kernel.py` → orchestration host; `progress.py` → shared warning/telemetry evaluator.

## Links
- Docs: `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md`
- Docs: `docs/architecture/agent-kernel/domain-pack-interface-v1.md`
- Execution kernel: `backend/agent_kernel/`
- Domain packs: `backend/agents/`
- Mission runtime core: `backend/harness/mission_runtime/runtime.py`
