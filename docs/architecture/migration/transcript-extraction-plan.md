# Transcript-First Extraction Plan

Date: 2026-03-14
Status: Phase 5 planning doc — extraction targets defined; no runtime implementation yet
Primary references:
- `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md`
- `docs/architecture/agent-kernel/shared-loop-memory-v1.md`
- `docs/architecture/agent-kernel/domain-pack-interface-v1.md`
- `docs/architecture/agent-kernel/loop-family-orchestration-delta-matrix.md`
- `docs/architecture/migration/agent-kernel-convergence-roadmap.md`

## Purpose

Define a concrete extraction plan for each reusable transcript-edit orchestration mechanic that should move into the shared orchestration kernel. Each extraction target has:
- a current code anchor (file + symbol)
- a clear kernel-vs-pack boundary call
- the specific interface seam
- what must not be extracted (domain-specific semantics that stay in the transcript-edit pack)

This document does not:
- implement any runtime code
- refactor any existing controller or ModePolicy
- change the mission runtime shape

This plan is the input to Phase 6 (deed migration) and Phase 7 (blended missions). Phase 6 depends on these boundaries being frozen.

---

## Constraint

Extract the mechanics; leave transcript-specific semantics in the transcript domain pack.

Do not copy:
- transcript-edit's closure layer (ledger-based acceptance, scope qualification)
- decision identity logic (`decision_key`, `decision_ledger` schema)
- span evidence waterfall ordering (span_context → image_verification → visual_evidence)

These are domain-specific content and policy. They belong in the transcript-edit domain pack.

---

## Extraction Targets

### T1 — Orient Baseline as a Generic Orchestration Phase

**Current code anchor:**
- `_build_orient_inputs()` → `controller.py:946` (builds orient LLM inputs)
- `update_ledger_from_orient_baseline()` → `decision_ledger_state.py` (processes orient result into `decision_ledger`)
- `initialize_decision_ledger()` → `decision_ledger_state.py:70` (seeds empty ledger before orient)
- `run_transcript_edit_controller_loop()` → `controller.py:107` (drives orient at loop start)

**Moves to orchestration kernel:**
- guarantee that orientation phase runs once at loop start (first iteration only)
- call `domain_pack.orient(context)` (hook 1) at the right position in the phase grammar
- orientation is not repeated within a continuous run (restart semantics handled by continuity memory)

**Stays in transcript-edit domain pack (hook 1 implementation):**
- `_build_orient_inputs()` — what LLM inputs the orient pass uses
- `update_ledger_from_orient_baseline()` — how orient output populates `decision_ledger`
- `initialize_decision_ledger()` — the domain-specific work-item container initialization
- orient LLM prompt content and response parsing

**Interface seam:**
- kernel calls `domain_pack.orient(context: OrchestratorContext) -> None` once at loop start
- domain pack writes its orient output into domain-state memory (sixth category); kernel does not inspect orient output directly

---

### T2 — Audit/Reaudit Trigger as a Generic Post-Apply Refresh

**Current code anchor:**
- `state.pending_reaudit_after_apply` flag — `TranscriptEditLoopState` field; set when an apply-type action is executed
- Reset and re-audit logic in `run_transcript_edit_controller_loop()` → `controller.py:538–569`
- `update_ledger_from_iteration()` — called after audit step, refreshes `decision_ledger` from audit output

**Moves to orchestration kernel:**
- the concept that a `pending_refresh` flag is set after a material change (apply-type action)
- the kernel drives a refresh call (hook 2) at the start of the next iteration when the flag is set
- the kernel owns the flag — it is part of Continuity memory (recent state, not work-state)

**Stays in transcript-edit domain pack (hook 2 implementation):**
- what constitutes a "material change" triggering refresh (apply action semantics)
- what the re-audit step examines (transcript audit pass, LLM output parsing)
- `update_ledger_from_iteration()` — how re-audit output refreshes `decision_ledger`
- apply-reaudit baseline tracking (`apply_reaudit_baseline_blocking_count`, `apply_reaudit_baseline_blocking_signature`)

**Interface seam:**
- kernel calls `domain_pack.refresh(context: OrchestratorContext) -> None` each iteration (not just post-apply; domain pack decides internally whether a re-audit pass is needed based on its domain-state)
- domain pack signals to the kernel via hook return whether the refresh produced new signal (the new-evidence-signal flag from hook 7 captures this outcome)

---

### T3 — Focus Selection Flow

**Current code anchor:**
- `choose_investigation_focus(ledger)` → `decision_ledger_focus.py:25` (generic ledger-based focus selection fallback)
- `_select_focus_target(blocker_registry, decision_ledger, fallback_focus, focus_feedback)` → `iteration_repair_focus.py:36` (full focus selection with blocker priority and feedback context)
- Called in `handle_repair_iteration()` → `iteration_repair_runtime.py:831`

**Live divergence note:** `focus_stagnation_streak` currently lives in `backend/agents/transcript_edit/loop_state.py` and is written by the domain controller, not the kernel. During T3 extraction, this field must be promoted to kernel-owned Work-State memory. On first run under the new kernel, the pre-extraction value should be treated as a reset (start at 0); it must not be seeded from the legacy domain loop-state, which has a different semantics scope.

**Moves to orchestration kernel:**
- the phase 4 select-focus step: kernel reads the domain-supplied `WorkStateProjection.ranked_work_item_list` (ephemeral; produced by hook 3) and selects the highest-priority uncompleted, unblocked focus item
- the kernel owns the `active_focus_key` and `focus_stagnation_streak` (Work-State memory; focus state sub-surface)
- focus switching logic: if current focus is completed or stagnant, kernel selects the next item using the ranked list

**Stays in transcript-edit domain pack (via hook 3 projection):**
- `choose_investigation_focus()` — the ranking logic that produces the ordered focus hint list (becomes input to `WorkStateProjection.ranked_work_item_list`)
- `_select_focus_target()` — blocker-aware, feedback-aware re-ranking (domain pack uses this internally to compute its ranked ordering before supplying it in hook 3)
- ledger state interpretation (in-target-scope qualification, mapping-blocking priority)

**Interface seam:**
- domain pack supplies `ranked_work_item_list` in hook 3 `WorkStateProjection` (ephemeral; consumed by phase 4; not persisted)
- kernel's generic focus selection iterates the ranked list and sets `active_focus_key`
- domain pack does not call focus selection functions at kernel call sites; it pre-computes the ranking and hands it off

---

### T4 — FocusPacket → ResolveFocusMove as the Shared Move Layer

**Current code anchor:**
- `build_focus_packet(decision_ledger, decision_key, span_context, image_verification_payload, feedback, ...)` → `focus_packet.py:18` (assembles all evidence for a focus key)
- `resolve_focus_move(focus_packet, planner_client, ...)` → `focus_resolver.py:10` (calls LLM planner, returns move decision)
- `_active_answered_unintegrated_ticket()` → `focus_resolver.py:145` (pre-integration HITL check inside resolver)

**Moves to orchestration kernel:**
- the phase 5 (resolve-move) structure: kernel calls hook 4 to get a `FocusPacket`, then calls hook 5 to get a `MoveDecision`
- the guarantee that every iteration produces the triple: `FocusPacket → MoveDecision → MoveExecutionPlan`
- the kernel's HITL pre-check: before calling hook 5, if `OrchestratorContext.hitl_state == waiting_human`, kernel routes to HITL path instead of calling resolve-move
- the move execution dispatch: kernel calls hook 6 to compile the `MoveDecision` to `MoveExecutionPlan`, then passes to execution kernel

**Stays in transcript-edit domain pack (hooks 4, 5, 6):**
- `build_focus_packet()` — evidence assembly (span context, image verification, visual evidence, feedback payload) → hook 4 implementation
- `resolve_focus_move()` — transcript-specific LLM planning call and move parsing → hook 5 implementation
- the full evidence waterfall ordering (span context priority rules, image verification gating) — domain-specific assembly policy
- move-to-action compilation (transcript edit actions, HITL prompt formatting) → hook 6 implementation
- `_active_answered_unintegrated_ticket()` — domain pack checks its own ticket state in hook 4 to include feedback payload in the focus packet; the kernel's HITL check uses `OrchestratorContext.hitl_state`, not the domain's internal ticket state

**Interface seam:**
- kernel calls `domain_pack.build_focus_packet(context) -> FocusPacket` (hook 4)
- kernel calls `domain_pack.resolve_move(focus_packet, context) -> MoveDecision` (hook 5)
- kernel calls `domain_pack.compile_move(move_decision, context) -> MoveExecutionPlan` (hook 6)
- domain pack uses its own internal resolver logic; the kernel only inspects the returned contract types, not internal pack state

---

### T5 — `classify_iteration_progress` as the Shared Progress Evaluator

**Current code anchor:**
- `classify_iteration_progress(*, previous_finding_signature, current_finding_signature, previous_blocking_signature, current_blocking_signature, previous_blocking_count, current_blocking_count, previous_signal_counter, current_signal_counter, pending_feedback_prompt_id, pending_reaudit_after_apply, apply_reaudit_baseline_blocking_count, apply_reaudit_baseline_blocking_signature) -> tuple[bool, str, bool]`
- → `progress_evaluation.py` (the only progress classifier in the codebase)
- Returns `(made_progress: bool, reason_code: str, reset_refresh: bool)`

**Moves to orchestration kernel:**
- the progress evaluation phase (phase 7 in the phase grammar): kernel calls the shared evaluator with domain-supplied inputs
- the shared evaluator signature: `evaluate_progress(metrics: ProgressMetrics) -> ProgressDelta`
- stagnation counter management: kernel owns `no_progress_streak` (Progress memory category) and increments/resets it based on `ProgressDelta.made_progress`
- `ProgressDelta` contract (frozen in Phase 2): `made_progress: bool`, `reason_code: str`, `reset_refresh: bool`

**Stays in transcript-edit domain pack (hook 7 implementation):**
- which signals constitute progress (blocking count reduction, audit signature change, feedback arrival, apply-reaudit improvement)
- baseline signature computation: `blocking_signature`, `finding_signature` derivation — domain-specific observation schema
- `apply_reaudit_*` baseline fields — transcript-specific post-apply tracking inputs
- the domain pack supplies `ProgressMetrics` via hook 7; it does not call `classify_iteration_progress` directly at kernel call sites after extraction

**Interface seam:**
- kernel calls `domain_pack.supply_progress_metrics(context) -> ProgressMetrics` (hook 7)
- kernel passes `ProgressMetrics` to the shared `evaluate_progress()` function
- shared evaluator is a pure function: inputs → `ProgressDelta`; no domain-specific logic inside it after extraction
- `new_evidence_signal: bool` in `ProgressMetrics` is derived by the domain pack by comparing current vs. prior evidence cache state; kernel uses it to increment `evidence_signal_counter` (kernel-owned)

**Extraction constraint:** the shared evaluator must not embed transcript-specific field names. Current `classify_iteration_progress` uses transcript-specific parameter names (`pending_reaudit_after_apply`, `apply_reaudit_baseline_blocking_count`). The shared version must accept only generic metric types. Transcript-edit maps its specific fields to those generic types inside hook 7.

---

### T6 — HITL Lifecycle Substrate

**Current code anchor:**
- `set_pending_feedback_prompt(...)` → `feedback_lifecycle.py:263` (issues HITL prompt, updates `decision_ledger` + `blocker_registry`)
- `drain_pending_feedback(...)` → `feedback_lifecycle.py:367` (polls for response, handles stale/superseded, transitions to `answered_unintegrated`)
- `apply_consumed_feedback(...)` → `feedback_lifecycle.py:608` (increments `evidence_signal_counter`, resets `no_progress_streak`)
- `derive_waiting_feedback_projection()` → `state_projection.py` (projects `blocker_registry` HITL surface)
- `HitlState` values: `no_prompt`, `waiting`, `answered_unintegrated`, `consumed` — frozen in Phase 2

**Moves to orchestration kernel:**
- the `HitlState` state machine: `no_prompt → waiting → answered_unintegrated → consumed` (and `superseded` for stale prompts)
- the kernel owns all `HitlState` transitions; no domain pack may write `HitlState` directly
- the waiting detection: between iterations, kernel checks if feedback has arrived (generic poll); if `answered_unintegrated`, kernel fires hook 9 (integrate feedback) before phase 2
- the resumability contract: `waiting_human` terminal class maps to `HitlState.waiting`; kernel produces this in `TerminalDecision` and mission shell persists it in `MissionLedger`

**Stays in transcript-edit domain pack (hook 9 implementation):**
- `set_pending_feedback_prompt()` — when to issue a HITL prompt and what to ask (domain-specific; hook 5 or hook 6 triggers this by including a HITL move in `MoveDecision`)
- `drain_pending_feedback()` — how to poll for feedback and what makes a response stale/superseded (transcript-specific feedback store lookup)
- `apply_consumed_feedback()` — how to integrate received feedback into `decision_ledger` and `blocker_registry` (domain-specific work-state update → hook 9 implementation)
- HITL ticket lifecycle log (`hitl_lifecycle_log`) — domain-state memory; not shared
- `derive_waiting_feedback_projection()` — domain's projection of its internal HITL surface into the Feedback memory category (part of hook 3 or hook 9 territory)

**Interface seam:**
- kernel's poll mechanism is generic: checks if feedback exists for the current `pending_feedback_prompt_id` (which is kernel-visible from Feedback memory)
- domain pack signals HITL intent by returning a `MoveExecutionPlan` with `hitl_intent_flag == True` from hook 6; the kernel advances `HitlState` from `no_prompt` to `waiting` — no separately-dispatched function is involved
- domain pack integrates received feedback via hook 9: `domain_pack.integrate_feedback(feedback_response, context) -> IntegrationResult`
- kernel advances `HitlState` from `answered_unintegrated` to `consumed` only on successful hook 9 return

---

## Kernel-vs-Pack Boundary Narrative

The kernel owns the **loop structure** and **generic state**. The domain pack owns **content** and **policy**:

| Concern | Owner |
| --- | --- |
| Phase grammar execution order | Orchestration kernel |
| active_focus_key, focus_stagnation_streak | Orchestration kernel |
| HitlState transitions | Orchestration kernel |
| evidence_signal_counter, no_progress_streak | Orchestration kernel |
| TerminalDecision emission | Orchestration kernel |
| Orient content, work-item schema | Domain pack |
| Blocker taxonomy, acceptance rules | Domain pack |
| Focus ranking rules | Domain pack (supplied via hook 3) |
| Evidence assembly, move compilation | Domain pack (hooks 4–6) |
| Progress metric derivation | Domain pack (hook 7) |
| Feedback integration logic | Domain pack (hook 9) |
| decision_ledger, blocker_registry | Domain pack (authoritative; projected not shared) |

---

## Sequencing Plan

Extraction must be sequenced so that each step has a stable boundary before the next begins.

**Step 1 — Orient phase seam (T1)**
- Simplest boundary: one-shot hook at loop start; no state-machine risk.
- Validates the hook-call pattern before more complex targets.
- Unblocks: confirms domain pack can write domain-state memory without kernel coupling.

**Step 2 — Focus selection + move layer (T3 + T4, together)**
- The deepest architecture seam. Everything downstream depends on `FocusPacket → MoveDecision → MoveExecutionPlan` being the shared unit.
- T3 and T4 must be extracted together: T3 supplies the ranked list (hook 3); T4 is the kernel driving phase 4 from that list, then calling hooks 4–6. Extracting either alone leaves the select-focus → resolve-move boundary hanging.

**Step 3 — Progress evaluator (T5)**
- Once T4 is in place, T5 follows naturally: hook 7 supplies metrics, shared evaluator classifies.
- The shared evaluator signature must be designed before T5 extraction — it cannot embed transcript field names.

**Step 4 — HITL substrate (T6)**
- Requires T4 (move layer produces HITL intent) and T5 (feedback arrival is a progress signal).
- Most complex state machine. Extract last among the six targets to avoid prematurely generalizing a substrate that has complex interaction with focus resolution.

**Step 5 — Refresh trigger (T2)**
- Domain-pack side (hook 2 implementation) can be extracted in parallel with T3/T4: the hook call pattern is established by T1 and the hook 2 implementation is simpler.
- Kernel-side trigger must not be finalized until T5 is complete. The kernel-owned `pending_refresh` flag is fed by `ProgressDelta.reset_refresh`, which is T5's output contract. Wiring the kernel refresh trigger before T5 produces a flag with no stable input and the wrong semantics (current code: `pending_reaudit_after_apply` is a transcript-specific field; generic: `ProgressDelta.reset_refresh` is the shared signal).
- Constraint: do not finalize the kernel-side refresh trigger before `ProgressDelta.reset_refresh` is frozen in the shared progress evaluator.

This sequencing is for Phase 6+ implementation. Phase 5 (this document) only defines the boundaries; no code changes are made here.

---

## Verification Plan

Each extraction target is correctly bounded when:

**T1 (orient):**
- Orchestration kernel calls hook 1 exactly once at loop start (not on resume if continuity memory is present)
- Orient output is visible in domain-state memory; no orient fields leak into Work-State, Evidence, or Continuity categories
- A new domain pack can implement hook 1 without importing any transcript-edit module

**T2 (refresh):**
- `pending_refresh` flag is in Continuity memory, not in domain-state
- Hook 2 fires when kernel decides a refresh is needed; domain pack does not self-trigger
- Domain pack can implement refresh (returning no-new-signal) without any transcript-edit dependency

**T3 (focus selection):**
- Kernel's phase 4 uses only `WorkStateProjection.ranked_work_item_list`; it does not read `decision_ledger` or `blocker_registry` directly
- `active_focus_key` is written only by the kernel; domain pack never writes it
- `ranked_work_item_list` is ephemeral: not present in persisted Work-State memory snapshot

**T4 (move layer):**
- Every iteration produces `FocusPacket → MoveDecision → MoveExecutionPlan` via hooks 4–6
- Kernel dispatches execution via `MoveExecutionPlan` without inspecting domain-specific move types
- Focus packet assembly logic is inside the domain pack; kernel holds only the `FocusPacket` contract type

**T5 (progress evaluator):**
- Domain pack computes `ProgressMetrics` internally; hook 7 returns the generic type
- `no_progress_streak` increments in kernel using `ProgressDelta.made_progress`, not via any domain pack call

**T6 (HITL substrate):**
- `HitlState` transitions occur only in orchestration kernel code
- Domain pack hook 9 returns `IntegrationResult`; kernel advances state on success
- `waiting_human` terminal class is emitted by kernel, not by domain pack
- A second domain pack (deed) can gain HITL capability by implementing hook 9 without reimplementing the state machine

---

## What This Plan Does Not Cover

- Deed-to-IR migration onto focus/work-state shape (Phase 6)
- Runtime implementation of the orchestration kernel (Phase 6+)
- Domain pack registry or plugin loading
- `MissionRuntime` shell restructuring (Phase 7)
- Blended multi-domain mission execution (Phase 7)
