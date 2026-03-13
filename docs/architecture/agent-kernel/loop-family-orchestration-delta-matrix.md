# Loop-Family Orchestration Delta Matrix

Date: 2026-03-13
Status: Active planning reference for next-stage convergence
Related docs:
- `docs/architecture/agent-kernel/target-agent-kernel-v1.md`
- `docs/architecture/agent-kernel/current-to-next-vocabulary-crosswalk.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`

## Purpose

Document the concrete orchestration gap between the two current loop families so that next-stage convergence work is grounded in actual code rather than abstract descriptions.

This matrix is the primary planning artifact for deciding what belongs in the shared orchestration kernel vs what stays domain-specific.

References used:
- `backend/agents/controller/controller_runtime_loop.py`
- `backend/agents/controller/controller_context.py`
- `backend/agents/controller/controller_runtime_step_prep.py`
- `backend/agents/transcript_edit/controller.py`
- `backend/agents/transcript_edit/loop_state.py`
- `backend/agents/transcript_edit/progress_evaluation.py`
- `backend/agents/transcript_edit/focus_packet.py`
- `backend/agents/transcript_edit/focus_resolver.py`
- `backend/agents/transcript_edit/iteration_repair_runtime.py`
- `backend/agents/transcript_edit/decision_ledger.py`
- `backend/agents/transcript_edit/blocker_registry.py`

---

## Delta Matrix

### 1. Orientation

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | `_build_bootstrap_context()`, `seed_bootstrap_step` in `controller_runtime_loop.py` | `run_transcript_edit_controller_loop` calls an orient/baseline LLM pass; `update_ledger_from_orient_baseline` initializes `decision_ledger` | Both have a startup pass; content is domain-specific | **Shared**: orientation phase exists in loop grammar. **Domain**: what orientation produces (bootstrap context blob vs baseline ledger entries) | Orchestration kernel should guarantee an orient phase runs. Each domain pack should define what it produces. |

---

### 2. Refresh / Audit

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | None — no dedicated reaudit step. `phase_hint` is inferred from dashboard state (`_infer_phase_hint`) | `pending_reaudit_after_apply` flag triggers re-audit pass after apply actions. `update_ledger_from_iteration` after each audit. `blocking_signature` / `blocking_unresolved_count` are refreshed each iteration | Transcript-edit has explicit refresh; deed does not | **Shared**: the concept that a re-observation pass exists after material change. **Domain**: what "auditable state" means and what to re-examine | Deed needs to gain a work-state refresh step. Domain packs define the audit content; orchestration kernel drives when to re-audit (e.g., after an apply-type action). |

---

### 3. Work-State Projection

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | None. Dashboard from kernel reflects IR state, but no explicit work-item list projection. `_build_context_packet` produces a context blob for LLM consumption | `decision_ledger`: each decision item has typed state (selected, blocked, pending, unresolved). `unresolved_mapping_blocking_requirements`, `unresolved_closure_requirements` enumerate work items. `sync_registry_from_ledger` keeps blocker registry aligned | Transcript-edit has explicit work-state projection; deed does not | **Shared**: loop should have a work-item surface (what items are open, closed, blocked). **Domain**: what constitutes a work item, what its states mean | Deed needs generic work-state projection hooks: project observations into open work items, project into blockers, derive closure candidates. Domain packs define the projection logic. |

---

### 4. Blockers

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | No first-class blocker model. Anti-thrash via: `refusal_streak`, `previous_refusal_signature`, `repeated_inspection_count`, `repeated_span_open_count`, `semantic_span_repair_count` (loop-local counters in `controller_runtime_loop.py`) | `blocker_registry` with typed blockers, lifecycle states (open / waiting_human / resolved), tick counts, HITL linkage. `select_primary_blocker_with_reason` picks highest-priority blocker. `apply_proposed_emergent_blocker_updates` for LLM-proposed new blockers. `blocker_registry.py` module | Transcript-edit has rich blockers; deed has only anti-thrash signals | **Shared**: the concept of an explicit open-blocker surface. **Domain**: blocker taxonomy, blocker acceptance thresholds, emergent blocker promotion rules | Deed needs generic blocker hooks: at minimum, a surface to record blockers that prevent progress. Anti-thrash counters can map to informal blockers first. |

---

### 5. Focus Selection

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | None — agent proposes any action type it chooses. No focus-item selection step before proposal | `choose_investigation_focus(decision_ledger)` selects a `decision_key`. `_select_focus_target(blocker_registry, decision_ledger, fallback_focus, focus_feedback)` in `iteration_repair_runtime.py` | Transcript-edit has explicit focus selection; deed does not | **Shared**: each iteration should have an active focus item or focus hint. **Domain**: what focus items are, how they are ranked, and when focus should switch | This is the biggest structural gap. Deed needs to adopt focus-item-centric orchestration. Generic focus selection contract: given current work-state, select the highest-priority focus item for this iteration. Domain packs supply work-item surface and ranking rules. |

---

### 6. Move Resolution

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | LLM proposes `KernelStepProposal` directly via `_propose_next_step`. No intermediate focus packet / move resolution layer | `build_focus_packet(decision_ledger, decision_key, span_context, image_verification_payload, feedback, ...)` → `resolve_focus_move(focus_packet, planner_client, ...)` → move decision → parsed into action type or HITL prompt. `focus_packet.py`, `focus_resolver.py` | Transcript-edit has focus_packet → move layer; deed does not | **Shared**: every iteration should produce: focus packet, move decision, move execution plan. **Domain**: focus packet contents, available moves, move-to-action compilation | Deed currently jumps directly from context observation to raw action proposal. It needs an intermediate move layer. Every domain should produce a `FocusPacket`, a `MoveDecision`, and a compiled action. |

---

### 7. Execution

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | `session_manager.step(step_request)` via `KernelSessionManager`. Kernel handles budgets, idempotency, artifact persistence | `step_kernel_action(session_manager, ...)` — same execution kernel underneath | Both families use the same execution kernel | **Fully shared** — already converged at execution layer | No migration needed here. Both families already delegate to `backend/agent_kernel/`. |

---

### 8. Progress Evaluation

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | Coarse signals only: `refusal_streak`, `phase_hint` change, `executed_steps` count. No dedicated progress classifier | `classify_iteration_progress(previous_finding_signature, current_finding_signature, previous_blocking_signature, current_blocking_signature, previous_blocking_count, current_blocking_count, previous_signal_counter, current_signal_counter, pending_reaudit_after_apply, ...)` → `(made_progress: bool, reason: str, reset_reaudit: bool)`. `progress_evaluation.py` | Transcript-edit has a real progress classifier; deed does not | **Shared**: a `ProgressDelta` contract. Inputs: baseline signatures and counts supplied by domain pack. Output: made_progress bool + reason code + stagnation counter update. **Domain**: which metrics constitute a signal (blocking count vs audit signature vs feedback arrival) | Deed needs to supply progress metrics so the orchestration kernel can run a shared progress classification. The shared classifier should be generic; domain packs supply the metric inputs. |

---

### 9. HITL Lifecycle

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | None built into the loop | Rich HITL state machine in `TranscriptEditLoopState`: `pending_feedback_prompt_id`, `pending_feedback_prompt`, `pending_feedback_decision_key`, `feedback_received_count`, `feedback_consumed_count`, `feedback_stale_count`, `feedback_superseded_count`, `superseded_feedback_prompt_ids`, `hitl_lifecycle_log`. Lifecycle managed through `feedback_lifecycle.py`, `blocker_registry.py` ticket linkage | HITL exists only in transcript-edit today | **Shared**: HITL substrate: pending prompt ownership, waiting state, answered-but-unintegrated state, consumed state, superseded state, resumability rules. **Domain**: when to prompt, what to prompt, how to integrate feedback into domain work-state | Transcript-edit HITL should become one implementation of a generic HITL substrate rather than the owner of the concept. Deed should later gain HITL capability through the shared substrate, not by reimplementing it. |

---

### 10. Terminalization

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | Terminal if `step_result.terminal is not None` (kernel signals done), or `refusal_streak >= _MAX_REFUSAL_STREAK`, or `iterations >= max_iterations`. Terminal is action-loop / refusal centric | Terminal if `blocking_unresolved_count == 0` with closure check (completed), or `no_progress_streak >= max`, or `invalid_plan_strikes >= max`, or `pending_reaudit_after_apply` exhausted. Terminal is work-state / closure centric | Different terminal grammars — both converge through shared `TerminalClass` at the harness layer | **Shared**: a terminal decision scaffold with: `completed`, `blocked_waiting_human`, `blocked_waiting_evidence`, `exhausted_no_progress`, `invalid_refused`, `impossible_unsupported`. **Domain**: closure rules (deed: kernel declares done; transcript: unresolved blocking count reaches zero with closure check) | The shared `TerminalClass` taxonomy in `backend/harness/terminal_taxonomy.py` is already the right shared layer. Domain packs need to map their terminal conditions to the shared taxonomy explicitly. |

---

### 11. Memory Surfaces

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | Local loop variables: `last_refusal`, `refusal_streak`, `previous_refusal_signature`, `run_summary_ref/excerpt`, `recent_digest_memory`, `phase_hint`, `repeated_inspection_ref/count`, `repeated_span_open_signature/count`, `semantic_span_repair_signature/count`. No persistent loop-memory object | `TranscriptEditLoopState` dataclass with ~50 fields spanning: continuity, work-state, evidence, feedback, progress, HITL lifecycle. Domain-rich, persisted as part of run artifacts | Different memory schemes — both untyped or domain-typed, neither uses a shared loop-memory contract | **Shared** categories: continuity memory (recent attempts, refusal/thrash history), work-state memory (open work items, blockers, focus state, closure posture), evidence memory (gathered evidence, per-focus evidence cache), feedback memory (pending prompts, consumed/stale state), progress memory (baseline signatures, stagnation counters). **Domain**: domain-specific cached state that does not generalize cleanly | The shared loop-memory contract freeze is Phase 3 of the next-stage roadmap. Both families contribute field families; neither schema should be adopted wholesale. |

---

### 12. Resumability / Continuity

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | None. Runs to completion or failure; no resume path | `blocker_registry` + `decision_ledger` provide resumable work-state. `derive_waiting_feedback_projection` produces HITL resume posture. Resume via `resume_pending_feedback_prompt_id`, `resume_pending_feedback_decision_key`, `resume_blocker_registry` fields on `TranscriptEditAgentRunRequest`. `state_projection.py` | Only transcript-edit has resumability | **Shared**: the concept that a stopped run has resumable state. Mission-level resumability summary already exists in `MissionLedger.resumability_summary`. **Domain**: what domain-specific state is needed to correctly resume | Deed needs at minimum a resumability signal. Shared orchestration-state artifact (separate from `RunArtifact`) is the right long-term container for cross-mode resumable state. |

---

### 13. Mission Shell Interaction

| | `deed_to_ir` today | `transcript_edit` today | Shared or domain-specific? | Target neutral abstraction | Migration notes |
| --- | --- | --- | --- | --- | --- |
| Code anchor | Wrapped as `DeedToIRModePolicy` in `backend/harness/mission_runtime/modes/deed_to_ir.py`. Shell calls `build_context → execution_adapter → interpret → recommend`. Today the execution adapter runs the entire family controller loop in one call | Wrapped as `TranscriptEditModePolicy` in `backend/harness/mission_runtime/modes/transcript_edit.py`. Same interface. Today the execution adapter runs the entire transcript-edit controller loop including HITL resume rounds in one call | Both families execute as monolithic blobs inside `ModeCycleContext.execution_adapter` | Target: mission shell should invoke the orchestration kernel per-iteration, not hand off to monolithic family controllers. The shift from "one call per mode cycle" to "orchestration kernel drives iterations above both domains" is the deepest structural change of the next stage | This is the most significant architectural migration. It cannot happen until the orchestration kernel exists and the domain packs have shrunk to the right size. |

---

## Summary: What Is Shared vs Domain-Specific

| Mechanic | Shared to orchestration kernel | Stays domain-specific (domain pack) |
| --- | --- | --- |
| Orientation | Phase exists (guaranteed to run) | What orientation produces |
| Refresh / audit | When to re-audit (e.g., after apply) | What to re-examine and how |
| Work-state projection | Work-item surface contract | What constitutes a work item and its states |
| Blockers | Open-blocker surface, lifecycle states | Blocker taxonomy, acceptance thresholds |
| Focus selection | Focus selection flow, focus priority mechanics | How to rank focus items, what they are |
| Move resolution | Focus packet → move decision → execution plan structure | Focus packet contents, available moves, move compilation |
| Execution | Kernel call | Nothing new (already shared) |
| Progress evaluation | `ProgressDelta` classifier (inputs → bool + reason code) | Which metrics constitute progress signals |
| HITL lifecycle | Pending/waiting/answered/consumed/superseded substrate | When to prompt, what to ask, how to integrate answers |
| Terminalization | Terminal scaffold (completed / blocked / exhausted / refused / impossible) | Domain closure rules mapped to scaffold |
| Memory surfaces | Memory category contract (6 categories) | Domain-specific cached state |
| Resumability | Resumable-state concept + persistence envelope | Domain-specific state needed to resume correctly |
| Mission shell interaction | Orchestration kernel drives iterations | Domain pack content injection per phase |

---

## Key Decisions This Matrix Informs

1. **Unit of orchestration must converge**: deed must become focus-item-centric (not action-loop-centric) before the orchestration kernel can govern both families. This is the precondition for Phase 5 (transcript-first extraction).

2. **Move layer is the architecture seam**: `FocusPacket → MoveDecision → MoveExecutionPlan` is the correct abstraction seam at the boundary between orchestration kernel and domain pack. Both families should produce this triple.

3. **Memory law cannot be modeled on transcript-edit's full state alone**: `TranscriptEditLoopState` is a useful source, but several fields are domain-specific. The shared memory contract should be category-shaped, not field-shaped.

4. **HITL substrate should become a shared capability, not a transcript-edit feature**: transcript-edit's HITL lifecycle is the right design; it should move to the shared orchestration layer, not be reimplemented per domain.

5. **The mission shell currently invokes monolithic family controllers**: this must change before multi-domain fluid iteration is possible. The orchestration kernel must own the iteration cycle; the mission shell coordinates between orchestration kernel and domain packs.
