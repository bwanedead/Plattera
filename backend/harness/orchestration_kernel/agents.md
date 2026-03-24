# agents.md

## Scope
- Folder: `backend/harness/orchestration_kernel/`
- Purpose: Shared orchestration host and loop-governance layer. Sits above the execution kernel (`agent_kernel/`) and domain packs (`agents/*/domain_pack.py`).

## Contracts & invariants
- **Kernel is rails-first, not a semantic planner.** The loop still runs the same coarse hook order, but `selected_focus_key` is pack/agent-authored and `ranked_work_item_list` is advisory context only. Do not reintroduce kernel-owned focus selection or semantic phase doctrine.
- **Kernel owns:** `active_focus_key`, `focus_stagnation_streak`, `HitlState`, `no_progress_streak`, `evidence_signal_counter` (loop_memory), `invalid_plan_strikes`, terminal decision, and continuity rails.
- **Domain pack owns:** `decision_ledger`, `blocker_registry`, evidence assembly, move resolution, compilation, progress metric derivation, closure rules, and authored `selected_focus_key` when continuity is absent.
- **WorkStateProjection** has 3 persisted sub-surfaces (`work_item_collection`, `blocker_surface`, `closure_posture_summary`) + 1 ephemeral `ranked_work_item_list` (advisory candidate context, never persisted). `selected_focus_key` is continuity-carried when present and otherwise authored by pack/model startup understanding.
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
- HITL behavior differs from legacy loop: kernel terminates with `waiting_human` and resumes; legacy loop polled non-blocking. This is intentional.
- `run_artifact_ref` in `KernelLoopResult` defaults to `None` — the mission runtime adapter must pass the correct ref if available.

## Patterns
- Naming: hook functions on `DomainPack` match the loop seams (`orient`, `refresh`, `project`, `build_focus_packet`, `resolve_move`, `compile_move`, `supply_progress_metrics`, `supply_closure_rules`, `integrate_feedback`).
- Structure: `contracts.py` → frozen dataclasses + Protocol; `loop_memory.py` → mutable kernel state; `kernel.py` → orchestration host; `progress.py` → shared warning/telemetry evaluator.

## Links
- Docs: `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md`
- Docs: `docs/architecture/agent-kernel/domain-pack-interface-v1.md`
- Docs: `docs/architecture/migration/transcript-extraction-plan.md`
- Execution kernel: `backend/agent_kernel/`
- Transcript domain pack: `backend/agents/transcript_edit/domain_pack.py`
- Mission runtime adapter: `backend/harness/mission_runtime/modes/transcript_edit.py`
