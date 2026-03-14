# Orchestration Kernel Contracts v1

Date: 2026-03-13
Status: Contract freeze for Phase 2 planning (docs only — no runtime implementation yet)
Primary references:
- `docs/architecture/agent-kernel/target-agent-kernel-v1.md`
- `docs/architecture/agent-kernel/loop-family-orchestration-delta-matrix.md`
- `docs/architecture/agent-kernel/current-to-next-vocabulary-crosswalk.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`

## Purpose

Define the minimum shared loop-law contract for the orchestration kernel so that the next convergence stage has a stable shared interface before implementation begins.

This document:
- freezes the shared phase grammar
- defines the minimum contract surfaces needed for the orchestration kernel
- keeps boundaries explicit with the current harness layer above and the execution kernel below
- defers loop-memory schema detail and domain-pack interface detail to later phases

It is not a runtime implementation plan.
It is not a replacement for the current active harness contracts.

---

## Relation to Current Harness Contracts

This document is the next deeper layer after `docs/architecture/harness/mission-runtime-contracts-v1.md`.

The current harness contract defines:
- `MissionRuntime` — mission lifecycle, mode selection, continuity
- `ModePolicy` — domain interpretation and transition recommendations
- `RuntimeCapability` — reusable cross-mode orchestration mechanics (conceptually named; implementation underspecified)
- Execution kernel — deterministic step execution

This orchestration-kernel contract defines what goes **inside** `RuntimeCapability` and beneath `MissionRuntime`:
- the shared iteration loop that drives all domain families
- the contract surfaces that domain packs inject into that loop

`RuntimeCapability` in the current harness vocabulary is the direct predecessor: the orchestration kernel crystallizes the reusable mechanics that `RuntimeCapability` was always intended to hold. The orchestration kernel does not remove `RuntimeCapability` — it gives it explicit content and contracts.

**This contract does not replace or override `mission-runtime-contracts-v1.md`.**
The mission runtime shell remains the owner of mission identity, mode switching, and cross-mode continuity.
The orchestration kernel is a layer the mission shell delegates to, not a competing authority.

For the position-in-the-stack diagram, see `docs/architecture/agent-kernel/target-agent-kernel-v1.md` (Target Layering section).

---

## Status Boundary

For currently implemented boundaries, `mission-runtime-contracts-v1.md` governs.
For currently implemented execution substrate, `backend/agent_kernel/` governs.

This document governs planning for the next convergence stage only.
Do not use this contract as a source of authority for today's runtime behavior.

---

## Phase Grammar (frozen)

The shared loop law is organized into one run-start phase and one per-iteration loop.

### Run-Start Phase

**1. orient**

Runs once at the start of a run (not every iteration).

- Orchestration kernel guarantees this phase runs before the iteration loop begins.
- Domain pack defines what orientation produces: initial work-state baseline, initial context, starting conditions.
- Output feeds the first iteration's `project` phase.

Trigger: run start (or explicit restart signal from mission shell).

---

### Per-Iteration Loop

Phases 2–9 run on each iteration in order. Some phases are conditional.

**2. refresh** *(conditional)*

Runs when a prior iteration produced a material change that requires re-examination (e.g., an apply-type action was executed).

- Orchestration kernel tracks whether a refresh is needed based on prior iteration's `ProgressDelta.reset_refresh` signal.
- Domain pack defines what "refresh" means (e.g., re-audit, re-examine observations).
- If refresh is not triggered, this phase is skipped.

**3. project**

Updates the work-state surface from the latest available observations.

- Orchestration kernel calls domain pack to project current observations into the work-state surface.
- Output: updated open work items, updated blocker posture, updated closure posture.

**4. select-focus**

Selects the highest-priority focus item for this iteration.

- Orchestration kernel runs generic focus selection using the work-state surface and any active blocker posture.
- Domain pack supplies the ranked work-item list and focus-selection hints.
- Output: one active focus key (or a `no-focus` signal if no open work items exist).

**5. resolve-move**

Given the active focus, determines the next move.

- Domain pack builds a `FocusPacket` for the active focus key.
- Domain pack's move resolution logic (may include an LLM call) produces a `MoveDecision`.
- Domain pack compiles the `MoveDecision` into a `MoveExecutionPlan`.
- Orchestration kernel validates that the plan is structurally complete before handing it to execution.

**6. execute**

Dispatches the `MoveExecutionPlan` to the execution kernel.

- Orchestration kernel passes the compiled action to `backend/agent_kernel/` via existing `KernelSessionManager` step interface.
- Execution kernel handles budgets, idempotency, tool dispatch, artifact persistence, and refusal semantics.
- Output: execution result (step state, new artifact refs, refusal if applicable).

**7. evaluate-progress**

Classifies iteration progress using domain-supplied metrics.

- Domain pack supplies progress metrics: work-state signatures, counts, signal counters, pending HITL state.
- Orchestration kernel runs shared progress classifier → `ProgressDelta`.
- Output: `ProgressDelta` (made_progress, reason_code, stagnation_increment, reset_refresh).

**8. decide**

Determines whether to continue, escalate, or close.

- Orchestration kernel reads `ProgressDelta`, `HitlState`, and stagnation counters.
- Domain pack supplies closure rules: what counts as "complete" for this domain.
- Orchestration kernel applies generic loop-brake policy: if stagnation exceeds threshold → escalate or close.
- Output: `TerminalDecision` (terminal or continue, with class and reason_code).

**9. terminalize-or-continue**

Either terminates the run or loops back to phase 2.

- If `TerminalDecision.terminal` is true: orchestration kernel signals the mission shell with the terminal outcome.
- If continuing: loop returns to phase 2 with updated loop-memory state.

---

## Phase Ownership Table

| Phase | Generic (shared) | Domain-injected |
| --- | --- | --- |
| 1. orient | Guarantees phase runs once; receives domain output | What orientation produces and how work-state baseline is initialized |
| 2. refresh | Tracks whether refresh is needed from prior `ProgressDelta` | What to re-examine; how to refresh work-state |
| 3. project | Calls domain projection hook; updates shared work-state surface | Work-item schema, projection rules, blocker taxonomy |
| 4. select-focus | Generic priority selection from work-state surface | Ranked work-item list; focus-selection hints |
| 5. resolve-move | Validates `MoveExecutionPlan` is complete before execution | Builds `FocusPacket`; runs move resolution; compiles `MoveExecutionPlan` |
| 6. execute | Calls execution kernel; receives step result | Action types and payloads (compiled in phase 5) |
| 7. evaluate-progress | Runs shared `ProgressDelta` classifier | Supplies metric inputs: signatures, counts, signal counters |
| 8. decide | Applies loop-brake policy; reads `TerminalDecision` | Closure rules: what terminal conditions mean for this domain |
| 9. terminalize-or-continue | Routes terminal signal or loops | Maps domain terminal conditions to shared `TerminalDecision` |

---

## Contract Surfaces

These are ownership and field expectations. Not language-specific type definitions.

### OrchestratorContext

What the orchestration kernel assembles each iteration before calling domain pack hooks.

Owns:
- reference to current loop-memory state (iteration number, stagnation counter, HITL state)
- reference to current work-state surface (populated by previous `project` phase)
- active focus key (present only on genuine mid-cycle resume — when a cycle was interrupted before phase 9 completed; absent on normal iteration start, in which case phase 4 re-runs select-focus from the current work-state surface)
- prior iteration's `ProgressDelta` (if not first iteration)
- execution kernel handle (`KernelSessionManager` compatible)
- domain pack handle (callable)

Does not own:
- mission identity (owned by `MissionLedger` at mission shell level)
- mode selection (owned by `MissionRuntime`)
- domain-specific cached state (owned by domain pack)

---

### FocusPacket

The domain-to-orchestration handoff describing one focused work item for this iteration.

Built by: domain pack in phase 5 (`resolve-move`).
Consumed by: domain pack's move-resolution logic.

Must include:
- focus key / identity: which work item this iteration targets
- work item state: current state of this item (open, partially resolved, blocked, etc.)
- closure requirement or acceptance criteria: what "done" means for this item
- recent attempts: bounded list of prior attempts on this focus key (from loop memory)
- assembled evidence: evidence relevant to this focus (spans, image payloads, visual evidence as applicable)
- feedback state: any pending or consumed human feedback for this focus key
- domain-specific fields as needed (not prescribed here)

Does not own:
- generic loop-memory fields outside the focus scope (those live in loop-memory state)
- mission-level continuity records (those live in `MissionLedger`)

Kernel validation boundary:
The orchestration kernel does not validate `FocusPacket` contents — that is fully the domain pack's responsibility. The kernel's validation obligation begins at `MoveExecutionPlan` (phase 5 output), not at `FocusPacket` (phase 5 input). The kernel has no visibility into focus-packet quality before move resolution proceeds; this is intentional. Domain pack–level quality contracts belong to Phase 4 (domain-pack interface protocol).

---

### MoveDecision

The chosen next move for the active focus, produced by domain pack move resolution.

Must include:
- move type: the class of move chosen (e.g., `apply_edit`, `gather_evidence`, `request_hitl`, `verify`, `reorient`, `skip`, `declare_done`)
- focus key: which focus item this move targets
- move rationale: brief reason the move was chosen (for trace/review purposes)
- confidence hint: optional, used by orchestration kernel to decide whether to validate before execution

Move type taxonomy is not frozen in this contract.
Domain packs may extend move types; the orchestration kernel needs only enough to route execution correctly.

---

### MoveExecutionPlan

How a `MoveDecision` compiles to one or more concrete execution-kernel actions.

Built by: domain pack move compilation.
Consumed by: orchestration kernel in phase 6 (`execute`).

Must include:
- action type: execution-kernel action type (`ActionType` from `backend/agent_kernel/`)
- action payload: parameters for the kernel action
- expected artifact outputs: what artifact refs the kernel should produce (used for loop-memory update after execution)
- HITL intent flag: whether this plan is requesting human feedback (feeds `HitlState` update)

Validation rule:
- orchestration kernel validates that `action_type` is non-null and `action_payload` is structurally present before dispatching to execution kernel.
- invalid plans are refused at the orchestration layer, not the execution layer.

---

### ProgressDelta

Normalized output of shared progress evaluation (phase 7).

Must include:
- `made_progress`: bool — did this iteration move work forward?
- `reason_code`: str — stable reason code for trace/review (e.g., `blocking_count_reduced`, `new_signal_arrived`, `no_material_change`)
- `stagnation_increment`: int — 0 if progress was made, 1 if not (used by decide phase for loop-brake policy)
- `reset_refresh`: bool — whether the next iteration should run a refresh phase (typically true after a successful apply)

Domain pack supplies:
- prior work-state signature
- current work-state signature
- prior blocking count / current blocking count
- signal counter delta
- pending HITL state

Orchestration kernel runs the classifier; domain pack supplies the metrics.

Patterns drawn from: `classify_iteration_progress` in `backend/agents/transcript_edit/progress_evaluation.py`. That function is an implementation reference, not the normative interface spec. The shared classifier should generalize the input/output shape — it must not adopt that file's signature directly.

---

### HitlState

The generic human-feedback lifecycle substrate.

Owned by: orchestration kernel (as part of loop-memory state).
Updated by: orchestration kernel after execution phase when `MoveExecutionPlan.hitl_intent` is set.
Consumed by: evaluate-progress, decide phases.

States (mutually exclusive per prompt):
- `idle`: no pending human feedback
- `pending`: a feedback prompt has been emitted; waiting for human response
- `answered_unintegrated`: a response has arrived but not yet processed into work-state
- `consumed`: feedback has been integrated into work-state for this focus key
- `superseded`: the prompt was overtaken by a later change and is no longer relevant

Ownership rules:
- orchestration kernel owns the lifecycle state machine (transitions between states above)
- orchestration kernel surfaces the resumability signal to the mission shell
- specific field names and struct shape belong to Phase 3 (shared loop-memory schema) — explicitly deferred

Domain pack supplies:
- what the feedback prompt asks
- how to integrate a received response into domain work-state

Orchestration kernel supplies:
- lifecycle state transitions
- resumability signal to mission shell

Grounded in: `feedback_lifecycle.py` and the HITL state fields in `TranscriptEditLoopState` — this substrate generalizes that mechanism without adopting transcript-specific semantics.

---

### TerminalDecision

The shared terminal scaffold that domain-specific closure conditions map into.

Produced by: orchestration kernel decide phase (with domain pack closure input).
Consumed by: terminalize-or-continue phase; mission shell for `MissionLedger.mission_status`.

Must include:
- `terminal`: bool — whether the run should stop
- `terminal_class`: one of the six shared terminal classes (from `backend/harness/terminal_taxonomy.py`):
  - `completed` — work done, closure requirements met
  - `blocked` — cannot proceed; run is resumable or requires intervention
  - `waiting_human` — HITL pending, run is resumable when feedback arrives
  - `waiting_evidence` — evidence unavailable, run is resumable when evidence arrives
  - `exhausted` — stagnation threshold reached, cannot proceed
  - `failed` — unrecoverable error; run cannot continue
- `reason_code`: str — stable reason code carrying the specific subtype for trace/review (e.g., `impossible_unsupported`, `invalid_refused`, `stagnation_threshold_reached`)

Domain pack maps:
- domain-specific closure rules → `completed`
- domain-specific cannot-proceed conditions → `blocked` (reason_code carries subtype, e.g., `impossible_unsupported`)
- domain-specific HITL conditions → `waiting_human`
- domain-specific evidence-wait conditions → `waiting_evidence`

Orchestration kernel maps:
- stagnation counter threshold → `exhausted` (reason_code: `stagnation_threshold_reached`)
- invalid plan strike count → `blocked` (reason_code: `invalid_refused`)
- unrecoverable execution errors → `failed`

This uses the existing `TerminalClass` vocabulary from `backend/harness/terminal_taxonomy.py` without modification.
No new terminal taxonomy is introduced in this contract.

---

## Explicit Deferrals

The following are deliberately excluded from this contract and belong to later phases:

**Phase 3 — Shared loop-memory schema:**
- Full field definitions for the six loop-memory categories (continuity, work-state, evidence, feedback, progress, domain-state)
- How loop-memory is persisted and resumed across runs
- Exact shape of the `OrchestratorContext.loop_memory_state` field

**Phase 4 — Domain-pack interface protocol:**
- The callable interface a domain pack must implement to plug into the orchestration kernel
- Domain pack registration / lookup
- Domain pack lifecycle (init, teardown)
- How domain packs access the execution kernel handle

**Phase 5+ — Migration implementation:**
- How transcript-edit patterns are extracted into the orchestration kernel
- How deed-to-IR is migrated onto the focus/work-state shape
- Runtime code changes to `MissionRuntime`, `ModePolicy`, `RuntimeCapability`

---

## Guardrails

Prevent these failure modes during implementation:

| Failure mode | Prevention rule |
| --- | --- |
| Orchestration kernel becomes a second mission shell | Orchestration kernel must not own mission identity, mode selection, or cross-mode transitions — those stay in `MissionRuntime` |
| Domain pack interface absorbs loop-memory | Loop-memory categories are owned by the orchestration kernel; domain packs supply metric inputs and read projections, not the memory container |
| Transcript-edit semantics freeze the generic core | `FocusPacket`, `ProgressDelta`, and `HitlState` must generalize from transcript patterns without adopting transcript-specific field names or closure semantics |
| Over-wide `MoveDecision` move type taxonomy | Freeze the minimum move types needed to route execution; domain packs may extend; do not pre-enumerate all possible future moves |
| `MoveExecutionPlan` diverges from execution-kernel action contracts | `MoveExecutionPlan.action_type` must remain compatible with `ActionType` in `backend/agent_kernel/` — this is not a new execution layer |

---

## Implementation Posture

- Do not begin implementing the orchestration kernel in code until Phase 3 (loop-memory schema) and Phase 4 (domain-pack interface) are also frozen in docs.
- The mission runtime contracts (`mission-runtime-contracts-v1.md`) remain in force for all currently active code.
- This contract is a forward planning artifact only.
