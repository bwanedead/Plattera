# Domain-Pack Interface v1

Date: 2026-03-14
Status: Contract freeze for Phase 4 planning (docs only — no runtime implementation yet)
Primary references:
- `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md`
- `docs/architecture/agent-kernel/shared-loop-memory-v1.md`
- `docs/architecture/agent-kernel/loop-family-orchestration-delta-matrix.md`
- `docs/architecture/agent-kernel/current-to-next-vocabulary-crosswalk.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`

## Purpose

Define the minimum domain-pack boundary so that domain logic can be extracted from today's family-sized `ModePolicy` controllers without leaking into the orchestration kernel.

This document:
- defines the callable protocol a domain pack must implement
- defines what a domain pack owns and must not own
- defines how domain authority projects into shared memory categories
- provides two grounded worked examples (transcript-edit and deed-to-IR)

This document does not:
- implement a domain pack in code
- refactor any existing controller or ModePolicy
- change the mission runtime model
- define a domain registry or plugin platform

---

## What a Domain Pack Is

A domain pack is a bounded content surface that implements domain-specific meaning, policy, and compilation for one domain. It plugs into the orchestration kernel's phase grammar as a set of callable hooks.

A domain pack is:
- a collection of callable hooks, one per phase gate
- the authority for domain work-item schema, domain closure rules, domain evidence strategy, domain prompt content, and domain move compilation
- the owner of domain-state memory (the sixth loop-memory category)

A domain pack is not:
- a controller loop
- a second mission runtime
- the owner of phase ordering, loop-memory management, stagnation policy, or HITL state machine

**Ergonomics principle:** a domain pack should feel like "domain meaning + domain policy + domain compilation." It provides content and rules; the orchestration kernel drives the loop.

---

## Domain-Pack Protocol

These are the conceptual hooks a domain pack must implement to participate in the frozen phase grammar. Language-specific interface definitions are deferred to Phase 5+ implementation.

Each hook receives an `OrchestratorContext` (defined in `orchestration-kernel-contracts-v1.md`) that carries the current loop-memory state, work-state surface, active focus key (on genuine resume), and execution kernel handle.

---

### Hook 1 — orient

**Phase:** 1 (run-start, once)

Called once before the iteration loop begins.

**Domain pack produces:**
- domain initial work-state baseline (the starting work-item collection derived from source observations)
- domain initial context (bootstrap state the domain needs for first `project`)
- initial domain-state memory contents

**Orchestration kernel does:**
- guarantees this hook runs exactly once before the iteration loop
- uses the orientation output to populate the first iteration's work-state surface

**Must not produce:** mission-level artifacts, MissionLedger updates, or canonical trace events (those are harness-layer concerns).

---

### Hook 2 — refresh *(conditional)*

**Phase:** 2 (per-iteration, conditional)

Called when `ProgressDelta.reset_refresh` was true in the prior iteration (i.e., an apply-type action executed successfully).

**Domain pack produces:**
- re-examined work-state (re-audit or re-projection of observations after the apply)
- updated blocker surface if applicable

**Orchestration kernel does:**
- decides whether to call this hook (from `ProgressDelta.reset_refresh`)
- skips the hook if no refresh is needed

**Must not produce:** a new loop iteration; refresh is a phase within the current iteration.

---

### Hook 3 — project

**Phase:** 3 (per-iteration)

Updates the shared Work-State memory category from the domain's authoritative sources.

**Domain pack produces a `WorkStateProjection` containing** three persisted sub-surfaces (kernel writes these atomically into Phase 3 Work-State memory) plus one ephemeral input consumed by phase 4:

Persisted sub-surfaces (written to Work-State memory):
- updated work-item collection: list of work items with identity keys, current states, and closure requirements — shape is domain-defined; presence of the collection is orchestration-required
- updated blocker surface: active blockers with lifecycle states — minimum: blocker identity, state, associated work-item key
- closure posture summary: bounded read of items blocking closure (how many, what class)

Ephemeral phase-4 input (consumed by focus selection; not persisted in Work-State memory; re-derived on restart):
- ranked work-item list with focus-selection hints: domain-supplied ordering for phase 4 selection (e.g., transcript: in-target-scope items first, then mapping-blocking by priority; deed: phase-hint priority order) — kernel's generic focus selection reads this ordering; domain pack supplies the ranking, kernel makes the final selection

**Orchestration kernel does:**
- calls this hook each iteration
- writes the three persisted sub-surfaces into the Work-State memory category atomically
- uses the ephemeral ranked list for phase 4 focus selection; discards it after selection

---

### Hook 4 — build focus packet

**Phase:** 5 (resolve-move), step 1

Called after focus selection (phase 4) with the selected focus key.

**Domain pack produces:** a `FocusPacket` (as defined in `orchestration-kernel-contracts-v1.md`) containing:
- focus identity and current work-item state
- closure requirement for this focus key
- recent attempts from continuity memory (bounded)
- assembled evidence (span context, image verification, visual evidence, as applicable)
- feedback state if any pending or consumed human feedback exists for this focus key
- domain-specific fields as needed

**Orchestration kernel does:**
- calls this hook with the focus key selected in phase 4
- passes the `FocusPacket` to the move resolver hook (hook 5)
- does not validate `FocusPacket` contents — domain pack owns quality here

---

### Hook 5 — resolve move

**Phase:** 5 (resolve-move), step 2

Given the `FocusPacket`, determines the next move.

**Domain pack produces:** a `MoveDecision` (as defined in `orchestration-kernel-contracts-v1.md`) containing:
- move type: the class of move chosen (e.g., `apply_edit`, `gather_evidence`, `request_hitl`, `verify`, `reorient`, `skip`, `declare_done`)
- focus key: which focus item this move targets
- move rationale: brief reason for trace/review
- confidence hint: optional, used by kernel to decide pre-execution validation

This hook may be backed by an LLM call. The domain pack owns all prompt construction and move selection logic.

**Orchestration kernel does:**
- calls this hook after `build_focus_packet`
- passes the `MoveDecision` to the move compiler hook (hook 6)

---

### Hook 6 — compile move

**Phase:** 5 (resolve-move), step 3

Compiles `MoveDecision` → `MoveExecutionPlan` for execution-kernel dispatch.

**Domain pack produces:** a `MoveExecutionPlan` (as defined in `orchestration-kernel-contracts-v1.md`) containing:
- action type: must be a valid `ActionType` from `backend/agent_kernel/`
- action payload: parameters for the execution kernel
- expected artifact outputs: artifact refs the kernel should produce
- HITL intent flag: whether this plan is requesting human feedback

**Orchestration kernel does:**
- validates that `action_type` is non-null and `action_payload` is structurally present
- refuses invalid plans at the orchestration layer before dispatch
- dispatches valid plans to the execution kernel (phase 6)

---

### Hook 7 — supply progress metrics

**Phase:** 7 (evaluate-progress)

Supplies the domain-specific metric inputs for the shared `ProgressDelta` classifier.

**Domain pack produces a `ProgressMetricInputs` bundle containing:**
- current work-state signature: a stable string derived from current work-item/blocker state (domain-defined hash)
- prior work-state signature: from prior iteration (may come from Progress memory via context)
- current blocking count and prior blocking count: numeric signals for blocking delta
- new-evidence-signal flag: bool — whether new evidence arrived this iteration (domain pack derives from comparing current vs. prior evidence cache state; kernel uses this flag to increment `evidence_signal_counter` in Evidence memory — counter is kernel-owned)
- pending HITL state: whether a feedback prompt is currently outstanding — domain pack reads `context.hitl_state` from `OrchestratorContext`, not from Feedback memory directly

**Orchestration kernel does:**
- runs the shared progress classifier with these inputs → `ProgressDelta`
- owns stagnation counter updates and loop-brake policy

**Domain pack must not:** own or increment the stagnation counter, write to Progress memory directly, or override loop-brake thresholds.

---

### Hook 8 — supply closure rules

**Phase:** 8 (decide)

Supplies domain closure evaluation used in the shared `TerminalDecision` mapping.

**Domain pack produces a `ClosureEvaluation` containing:**
- `domain_complete`: bool — whether the domain's acceptance criteria are met
- `domain_terminal_class`: one of the six shared `TerminalClass` values (from `backend/harness/terminal_taxonomy.py`); if `domain_complete` is false and the domain cannot proceed, use `blocked` with `closure_reason_code: impossible_unsupported`
- `closure_reason_code`: stable reason code for trace (carries specific subtype, e.g., `impossible_unsupported`, `no_workable_items`)
- `open_items_summary`: brief summary of what remains open (for terminal output)

**Constraint:** domain pack must not return `domain_terminal_class == waiting_human` from hook 8 unless `OrchestratorContext.hitl_state != no_prompt`. New HITL intent is expressed through hook 5/6 by returning a `MoveExecutionPlan` with `hitl_intent_flag == True`; hook 8 is a closure evaluation only.

**Orchestration kernel does:**
- reads `domain_complete` + `TerminalDecision` inputs to decide continue/terminate
- maps domain evaluation to `TerminalDecision.terminal_class` (using `TerminalClass` from `backend/harness/terminal_taxonomy.py`)
- applies generic loop-brake policy independently: if stagnation counter threshold is exceeded → `exhausted` (reason_code: `stagnation_threshold_reached`), regardless of domain_complete

---

### Hook 9 — integrate feedback

**Timing:** fires at the start of an iteration when `OrchestratorContext.hitl_state == answered_unintegrated`, before phase 2 (refresh). Integration updates domain work-state; the subsequent phase 3 `project` call then reflects the integrated state.

Called when a human feedback response has arrived but has not yet been integrated into domain work-state.

**Domain pack:**
- integrates the received response into its authoritative domain work-state (e.g., transcript: `apply_consumed_feedback`, `update_ledger_from_iteration`)
- signals integration completion to the orchestration kernel via the hook return value

**Orchestration kernel does:**
- calls this hook with the received feedback response
- advances `HitlState` from `answered_unintegrated` to `consumed` on successful integration
- remains the sole actor that writes `HitlState`

**Domain pack must not:** write `HitlState` directly. The integration-completion handshake is a return value, not a state mutation.

---

### Phase 9 — kernel-only

Phase 9 (`terminalize-or-continue`) has no domain pack hook. The orchestration kernel routes terminal signals to the mission shell without domain participation at this phase. Domain input to termination decisions is fully captured in hook 8 (`ClosureEvaluation`).

---

## Domain-Pack Ownership Table

### Domain pack owns

| What | Examples |
| --- | --- |
| Work-item schema and authoritative lifecycle state | Transcript: decision items with `selected_value`, `state`, `closure_requirement`; deed: TBD at Phase 6 |
| Blocker taxonomy meaning and acceptance thresholds | Transcript: emergent blocker kinds, archetype menu; deed: TBD |
| Evidence strategy: which evidence to gather, in what order, under what conditions | Transcript: span context → image verification → visual evidence waterfall; deed: dashboard snapshot, span seeds |
| Evidence payload schema (what is in each evidence artifact) | Transcript: span_context shape, image_verification_payload shape; deed: TBD |
| Prompt content and move menu | Move type vocabulary, LLM prompt construction, planning client |
| Closure semantics and acceptance criteria | Transcript: `has_unresolved_mapping_blocking_closure`, scope closure rules; deed: TBD |
| Domain-state memory category contents | Transcript: `convention_context`, `llm_call_seq`; deed: context packet internals |
| Feedback prompt content and response interpretation | What the HITL prompt asks, how a choice maps to domain work-state update |
| Domain-specific tool and action applicability | Which `ActionType` values are valid for this domain in this focus state |

### Domain pack must not own

| What | Why |
| --- | --- |
| Phase ordering and loop law | Owned by orchestration kernel; loop must not be re-invented inside a pack |
| Loop-memory container management (categories 1–5) | Categories are owned by the orchestration kernel; packs supply inputs, not containers |
| `HitlState` lifecycle transitions | Orchestration kernel is the sole state machine actor; packs signal completion, not state |
| Stagnation counter and loop-brake thresholds | Orchestration kernel policy; if packs owned this, each domain would have a competing brake |
| Evidence repeat-guard budget and `evidence_signal_counter` | Both owned by orchestration kernel; domain pack supplies the new-evidence-signal flag (hook 7), kernel increments the counter |
| `TerminalDecision` emission and terminal class mapping | Orchestration kernel maps pack closure evaluation to terminal scaffold; packs supply closure evaluation, not the scaffold |
| Mission identity, mode switching, cross-mode transitions | Owned by `MissionRuntime` and `MissionLedger` at the mission shell level |
| Execution kernel dispatch | Orchestration kernel dispatches via `KernelSessionManager`; packs compile plans, not dispatch calls |

---

## How Domain Authority Projects into Shared Categories

Domain packs hold authoritative state internally and project a bounded view into shared memory. They do not write shared memory directly, and shared memory does not hold the authoritative state.

- **Work-state:** domain pack projects via hook 3 (`WorkStateProjection`); kernel writes to Work-State memory atomically; domain authority (`decision_ledger`, `blocker_registry`) stays inside the pack; kernel does not read domain-internal sources.
- **Evidence:** domain pack supplies evidence inside `FocusPacket` (hook 4); domain pack signals new-evidence arrival via `ProgressMetricInputs` (hook 7); kernel owns `evidence_signal_counter`.
- **Feedback:** domain pack reads `HitlState` from `OrchestratorContext` (not direct memory access); integration-completion handshake is a hook 9 return value; kernel advances `HitlState`.
- **Progress:** domain pack supplies metric inputs in hook 7; kernel runs progress classifier and writes stagnation counter; domain pack never writes Progress memory.

---

## Worked Example 1: Transcript-Edit Domain Pack

The transcript-edit domain is work-item-centric. Its domain authority lives in `decision_ledger` (focus item states and closure truth) and `blocker_registry` (blocker lifecycle truth). Both are grounded in `backend/agents/transcript_edit/`.

### Domain authorities
- `decision_ledger` (`decision_ledger.py`): work-item surface — decision items with `state`, `closure_requirement`, `in_target_scope`, `selected_value`
- `blocker_registry` (`blocker_registry.py`): blocker lifecycle — emergent blockers, archetype blockers, `linked_prompt_id`, tick counts, row-level state

### Hook implementations

**orient** — calls `initialize_decision_ledger` + `update_ledger_from_orient_baseline` on the source transcript. Produces initial decision items and initial `convention_context` for domain-state. Span seed bootstrapping (`load_transcript_span_seeds_for_mapping` in `backend/agents/controller/bootstrap.py`) happens here.

**refresh** — re-audits the transcript after an apply. Calls transcript audit pipeline to refresh decision item states and re-project blocker surface.

**project** — projects `decision_ledger` items into the work-item collection; projects `blocker_registry` rows into the blocker surface; calls `has_unresolved_mapping_blocking_closure` for closure posture summary.

**build focus packet** — calls `build_focus_packet()` (`focus_packet.py`) with current `decision_ledger`, selected `decision_key`, span context from Evidence memory, `image_verification_payload`, feedback from Feedback memory, `continuity_log` from Continuity memory, and blocker registry view.

**resolve move** — calls `resolve_focus_move()` (`focus_resolver.py`) backed by `TranscriptEditPlanPlanner.propose_focus_move()`. Returns a `MoveDecision` with move types such as: `apply_edit_plan`, `gather_more_evidence`, `request_human_feedback`, `mark_blocked`, `mark_resolved_no_edit`.

**compile move** — maps move types to `ActionType` values:
- `apply_edit_plan` → `ActionType.APPLY_EDIT`
- `gather_more_evidence` → `ActionType.RETRIEVE_EVIDENCE` or image verification action
- `request_human_feedback` → HITL action (sets `hitl_intent=True`)
- `mark_blocked` / `mark_resolved_no_edit` → loop-internal (no execution kernel action; produces `declare_done` or no-op plan)

**supply progress metrics** — derives `previous_finding_signature` and `current_finding_signature` from `decision_ledger`; provides `previous_blocking_unresolved_count` and current count; reports new-evidence-signal flag when evidence cache changes (kernel increments `evidence_signal_counter`); reads `HitlState` from `OrchestratorContext`.

**supply closure rules** — calls `has_unresolved_target_scope_mapping_blocking_closure` + `has_unresolved_mapping_blocking_closure`. Domain is `completed` when no unresolved mapping-blocking items remain in target scope.

**integrate feedback** — calls `apply_consumed_feedback` + `update_ledger_from_iteration` with the received ticket response. Updates `decision_ledger` and `blocker_registry` with the integrated answer. Returns integration-complete signal → kernel advances `HitlState` to `consumed`.

### What stays inside the pack

The full `decision_ledger` schema (all item fields beyond the work-item projection), the full `blocker_registry` rows, the `convention_context`, the span evidence waterfall ordering, the `TranscriptEditPlanPlanner` planning client, and all prompt templates.

---

## Worked Example 2: Deed-to-IR Domain Pack

The deed-to-IR domain is currently action-loop-centric (`controller_runtime_loop.py`). It lacks first-class work items; loop memory is carried as loose local variables (`refusal_streak`, `phase_hint`, `run_summary_ref`, etc.). The worked example describes the intended pack shape at Phase 6, grounded in what exists today.

### Current state (reference for migration)
- Loop: `_run_controller_loop_impl()` — flat action loop, LLM proposes raw action via `_propose_next_step()`
- Focus proxy: `phase_hint` (e.g., `"bootstrap"`, `"span_repair"`, `"semantic_repair"`) — not a first-class work-item key
- Anti-thrash: `refusal_streak`, `repeated_inspection_count`, `repeated_span_open_count`, `semantic_span_repair_count`
- Context: `_build_context_packet()` assembles the observation surface
- No HITL state machine today

### Pack boundary (today and Phase 6 direction)

Per-hook assignments for deed are Phase 6 migration planning work, deferred to the transcript-first extraction plan (Phase 5) and deed migration plan (Phase 6). The current `_run_controller_loop_impl()` contains everything that will eventually be distributed between the orchestration kernel and the deed domain pack.

The key gap: deed currently lacks first-class work items — `phase_hint` (e.g., `"bootstrap"`, `"span_repair"`) is a focus proxy, not a structured work-item key. Phase 6 will establish a deed work-item schema derived from gap analysis. Until then, deed's hook implementations are TBD in detail.

### What stays inside the pack

The `_build_context_packet()` assembly logic, `_propose_next_step()` planning client, thrash-detection guardrail helpers (`_inspection_thrash_refusal`, `_span_open_thrash_refusal`, `_semantic_span_repair_thrash_refusal`), retrieval intent mapping, `phase_hint` derivation, and all deed-specific prompts.

---

## Guardrails

| Failure mode | Prevention rule |
| --- | --- |
| Domain pack becomes a second controller loop | Domain pack hooks are stateless callables; they do not own a loop, iteration counter, or phase sequencer |
| Domain closure truth leaks into shared Work-State | Projection (hook 3) writes a bounded view; domain-authoritative state stays inside the pack |
| Domain pack writes `HitlState` directly | Integration-completion handshake returns a signal; kernel is the sole state-machine actor |
| Domain pack overrides stagnation policy | `ProgressMetricInputs` are data inputs, not policy values; loop-brake thresholds are kernel-owned |
| Move type taxonomy bloat | Freeze only the move types needed to route execution; domain packs may extend; do not pre-enumerate all hypothetical future moves |
| Domain-state grows into a second work-state | If a domain-state field is needed by the orchestration kernel for loop control, it must be promoted to a shared category; kernel does not read domain-state |
| Multiple domain packs own competing closure authority | Each domain pack supplies one `ClosureEvaluation`; the orchestration kernel emits the `TerminalDecision` |

---

## Implementation Posture

Do not implement domain packs in code until Phase 5 (transcript-first extraction plan) maps each extract target to a concrete hook placement.

Phase 5 will define:
- which transcript-edit mechanics move into the orchestration kernel (shared phase logic)
- which transcript-edit mechanics move into the transcript-edit domain pack (hook implementations)
- the hook return type shapes (language-specific interface)

Current controllers (`_run_controller_loop_impl` for deed, `iteration_pipeline.py` for transcript-edit) remain authoritative for today's behavior. This contract governs planning only.
