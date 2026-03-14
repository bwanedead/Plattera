# Shared Loop-Memory Contract v1

Date: 2026-03-13
Status: Contract freeze for Phase 3 planning (docs only — no runtime implementation yet)
Primary references:
- `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md`
- `docs/architecture/agent-kernel/loop-family-orchestration-delta-matrix.md`
- `docs/architecture/agent-kernel/current-to-next-vocabulary-crosswalk.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`
- `docs/architecture/harness/minimal-shared-run-state-envelope.md`

## Purpose

Define the shared loop-memory contract so that the next convergence stage has a stable, category-shaped memory law across domains.

This document:
- defines the six memory categories and what each is for
- establishes ownership rules (orchestration kernel vs domain pack)
- defines the minimum persistence/resume requirements
- relates loop-memory to the existing harness layers it must not duplicate
- provides a field-mapping appendix grounding categories in both existing loop families

This document does not:
- specify exact field names, struct schemas, or storage formats
- replace domain-specific memory authority (transcript closure truth, blocker registry lifecycle)
- add new canonical trace, run-state, or MissionLedger fields
- design a storage platform or universal run ledger

---

## Memory Layer Distinction

Loop-memory is one of four distinct memory-related layers in the system. They must not compete or duplicate each other.

| Layer | What it holds | Authority | Scope |
| --- | --- | --- | --- |
| `MissionLedger` | Mission identity, active mode, transition history, bounded posture summaries | `MissionRuntime` (mission shell) | One per mission; survives mode switches |
| Shared run-state envelope (`backend/harness/run_state.py`) | Bounded read-model projection: identity, blocker summary, progress summary, resumability snapshot | Harness layer (read-model, not authoritative source) | Derived from loop-memory and mission ledger; used for observability |
| Canonical traces (`backend/harness/tracing/`) | Event history per run: step records, model calls, refusals, blocker transitions, terminal outcomes | Harness tracing layer (append-only, authoritative for history) | Per run; not a working state container |
| **Loop-memory (this contract)** | Orchestration kernel's authoritative working state for convergence: what the loop needs to decide, track progress, manage HITL, and terminate correctly | Orchestration kernel (categories); domain packs (domain-state category) | Per run, per active domain context; the source from which run-state is derived |

**Rule: loop-memory is the authoritative working state. Run-state is a bounded projection from loop-memory. Traces are an append-only event stream derived from loop-memory transitions. MissionLedger is a mission-level summary, not loop-level detail.**

Do not push loop-memory into `MissionLedger`.
Do not treat the shared run-state envelope as authoritative loop state.
Do not treat canonical traces as a resumable working state container.

---

## The Six Memory Categories

### 1. Continuity Memory

**Purpose:** Track what has been attempted, what failed, what pattern of repetition or thrash is forming, and provide bounded recency context for each iteration.

**Orchestration-kernel owned:**
- bounded list of recent iteration outcomes (action type, outcome, reason code, focus key if applicable)
- anti-thrash signals by action class: per-action-type repetition counts and last-seen signatures
- refusal/invalid-plan strike surface: current strike count, last refusal reason code
- bounded run summary: short persisted narrative of what has been accomplished so far (artifact ref, not inline blob)

**Domain pack may extend with:**
- domain-specific repair context (e.g., deed refusal-repair skeleton, transcript repair context hint)
- domain-specific "no-progress" diagnostic context beyond the shared stagnation counter

**Does not include:**
- full event history (canonical trace owns that)
- per-focus attempt history (evidence memory owns that within a focus scope)

---

### 2. Work-State Memory

**Purpose:** Track what work items are open, what blockers are active, what the current focus is, and what the overall closure posture is.

**Orchestration-kernel owned (category structure):**
- work-item surface: collection of work items with their states (open/blocked/resolved/closed) — shape is domain-defined, presence of the surface is orchestration-required
- blocker surface: collection of active blockers with lifecycle state (open/waiting/resolved) — minimum fields: blocker id, state, associated work item key; taxonomy is domain-defined
- focus state: current active focus key, focus stagnation streak count
- closure posture summary: bounded read of how many items are blocking closure — not the authority for closure truth (domain pack owns that)

**Domain pack owns the authority for:**
- work-item schema and state transitions (e.g., transcript: decision items with `selected_value`, `state`, `closure_requirement`; deed: TBD)
- blocker taxonomy and acceptance thresholds (transcript: emergent blockers, HITL-linked blockers; deed: TBD)
- closure rules: what "all work items closed" means for this domain
- detailed blocker lifecycle (transcript: `blocker_registry` with `linked_prompt_id`, tick counts, row-level state)

**Important boundary:** the orchestration kernel may read work-state to drive focus selection and closure decisions, but it does not own or re-derive the authoritative blocker lifecycle or closure truth. Those remain domain-owned. The kernel reads projections, not the raw authority.

---

### 3. Evidence Memory

**Purpose:** Track what evidence has been gathered for work items, prevent redundant evidence re-fetching, count new signal arrivals, and cache per-focus evidence artifacts.

**Orchestration-kernel owned (category structure):**
- evidence attempt record per focus key: tracks how many times evidence was gathered for a given focus item, and what was returned — prevents thrash on evidence that didn't help
- repeat attempt budgets: configurable maximum attempts per evidence type per focus key — `evidence_repeat_guard`
- new-signal counter: incremented when genuinely new evidence arrives; used by progress evaluation to detect signal-driven progress — `evidence_signal_counter`

**Domain pack owns:**
- per-focus evidence payload schema (transcript: span_context, image_verification_payload, visual_evidence; deed: dashboard snapshot, span seeds)
- evidence strategy: which evidence types to gather first, in what order, under what conditions
- evidence artifact refs: actual persisted artifact paths for evidence (domain-specific)

**Cacheability rule:** per-focus evidence caches are transient by default. They may be re-derived from artifacts on restart. Only evidence that is expensive to re-gather (e.g., LLM-based image verification results) warrants persistence. The domain pack decides which of its evidence fields are worth persisting; the orchestration kernel does not mandate evidence persistence.

---

### 4. Feedback Memory (HITL)

**Purpose:** Own the HITL lifecycle substrate: which prompts are pending, which responses have arrived, which have been consumed, which have become stale or superseded. This is the persistent surface that enables safe HITL resume.

**Orchestration-kernel owned:**
- `hitl_state`: the canonical `HitlState` value (idle / pending / answered_unintegrated / consumed / superseded) — as defined in `orchestration-kernel-contracts-v1.md`
- pending prompt record: when state is `pending` — prompt id, focus key the prompt targets, iteration it was emitted on
- received-but-unintegrated flag: when state is `answered_unintegrated` — the received response entry, awaiting domain-pack integration into work-state
- consumed flag + consumed iteration: when state is `consumed` — which iteration integrated the response
- superseded prompt ids: set of prompt ids that are no longer relevant due to work-state changes
- lifecycle event log: bounded append-only log of HITL lifecycle transitions — `hitl_lifecycle_log` (bounded, not full history)
- feedback lifecycle counters: received count, consumed count, stale count, superseded count — for progress-evaluation signal and trace

**Domain pack owns:**
- what the feedback prompt asks and how it is structured (prompt content is domain-specific)
- how to integrate a received response into domain work-state (transcript: `apply_consumed_feedback`, `update_ledger_from_iteration`; deed: TBD)
- the meaning of a given feedback response in the domain context

**Integration-completion handshake:** the domain pack signals integration completion to the orchestration kernel via a hook return value or lifecycle callback. The orchestration kernel is the sole actor that advances `HitlState` from `answered_unintegrated` to `consumed`. Domain packs do not directly write `HitlState`.

**Resumability authority:** feedback memory is the authoritative surface for HITL resume posture. The orchestration kernel derives `resumable=true` from `HitlState==pending`. The mission shell reads resumability from the orchestration kernel's projection. `MissionLedger` holds only a bounded resumability summary, not the full feedback memory.

**Important boundary:** transcript-edit's `blocker_registry` remains the authoritative source of HITL lifecycle truth for the transcript-edit domain pack. It is not absorbed into shared feedback memory. Shared feedback memory provides the generic `HitlState` projection used by the orchestration kernel for loop control. Domain packs project from their authoritative source into this shared surface.

---

### 5. Progress Memory

**Purpose:** Track iteration-over-iteration progress signals so the shared progress classifier (`ProgressDelta`) can detect stagnation, measure convergence, and drive loop-brake policy.

**Orchestration-kernel owned:**
- stagnation counter: incremented by `ProgressDelta.stagnation_increment` each iteration — `no_progress_streak`
- refresh-needed flag: set by `ProgressDelta.reset_refresh` after a material change (apply event) — `pending_refresh`
- refresh baseline: when a refresh is pending, the baseline work-state counts that the refresh should improve — `refresh_baseline_blocking_count`, `refresh_baseline_signature`
- last progress reason code: the most recent `ProgressDelta.reason_code` — for observability and run-state projection
- iteration count: total iterations executed — `iterations`

**Domain pack supplies (as inputs to `ProgressDelta` classifier):**
- current work-state signature: a stable string derived from the current work-item/blocker state — domain-defined hash
- prior work-state signature: from the previous iteration's progress memory snapshot
- current blocking count / prior blocking count: numeric signal for blocking delta
- signal counter: cumulative count of new evidence signals since run start (from evidence memory)
- pending HITL state: whether a feedback prompt is outstanding (from feedback memory)

**Important boundary:** the orchestration kernel runs the progress classifier and owns the stagnation counter. Domain packs supply the domain-specific metric inputs (signatures, counts, signal counters) but do not own stagnation policy. Loop-brake thresholds (max `no_progress_streak`) are orchestration-kernel policy, not domain pack policy.

---

### 6. Domain-State Memory

**Purpose:** Hold domain-specific cached payloads that do not generalize cleanly across domains and must not be forced into shared categories.

**Owned exclusively by domain pack.** The orchestration kernel does not read, write, or interpret domain-state contents.

Examples:
- `transcript_edit`: `convention_context` (document-specific convention rules), `span_seeds_ref`, `llm_call_seq`, `applied_non_normalization`, `applied_requires_review`, `applied_any_edits`
- `deed_to_ir`: any context packet internals, span/seed index caches, phase hint derivation state

**Rule:** if a field is only meaningful in one domain and the orchestration kernel never needs to inspect it for loop control decisions, it belongs in domain-state. When in doubt, put it here rather than forcing it into a shared category prematurely.

---

## Memory Ownership Summary

| Category | Owner | Domain pack role |
| --- | --- | --- |
| 1. Continuity | Orchestration kernel | May extend with domain-specific repair context |
| 2. Work-state | Orchestration kernel (category); domain pack (schema and authority) | Defines work-item schema, blocker taxonomy, closure rules |
| 3. Evidence | Orchestration kernel (category and repeat-guard); domain pack (payload schema and strategy) | Defines evidence types, payloads, persistence needs |
| 4. Feedback (HITL) | Orchestration kernel (lifecycle substrate and `HitlState`); domain pack (prompt content and integration) | Projects from domain-authoritative HITL source into shared `HitlState` |
| 5. Progress | Orchestration kernel (stagnation counter, refresh flag, loop-brake policy); domain pack (metric inputs) | Supplies progress metric inputs to shared classifier |
| 6. Domain-state | Domain pack exclusively | Full ownership |

---

## Persistence and Resume Expectations

This section defines minimum persistence requirements at the contract level, without specifying storage format or implementation.

### What must be persisted to support restart

A restarted run can re-orient (phase 1) but should not repeat work already completed.

Minimum to persist:
- work-state memory: current work items and their states, current blocker list
- continuity memory: `run_summary_ref` (artifact ref to bounded run narrative), `invalid_plan_strikes`, `action_repetition_signals`
- progress memory: `no_progress_streak`, `last_progress_reason`, current work-state signatures and counts (for first-iteration baseline)
- feedback memory: full `HitlState` + pending prompt record if state is `pending` (a restart during HITL pause must not lose the pending prompt)

May be transient (recomputed on restart):
- evidence caches (re-derived from artifacts; domain pack decides which are worth persisting)
- `recent_digest_memory` inline content (reconstructable from run summary artifact)
- domain-state (domain pack decides which fields survive restart)

### What must be persisted to support HITL resume

A HITL-paused run must resume without losing the feedback context.

Minimum to persist:
- all of restart requirements above
- feedback memory: pending prompt id, focus key, emitted iteration, `hitl_lifecycle_log`, `superseded_feedback_prompt_ids`

Domain pack additionally persists:
- its authoritative HITL source (transcript: blocker_registry; deed: TBD)

### What must be persisted for cross-mode continuity

When a mission transitions between domain packs:

- `MissionLedger` carries mission-level posture summaries (high-signal artifact refs, resumability summary, terminal status) — this is not loop-memory
- loop-memory is not transferred wholesale across mode switches; each mode runs its own loop-memory context
- the receiving mode starts fresh (with orient phase) but with access to `MissionLedger` artifact refs and transition handoff note

**Rule:** do not design loop-memory to survive cross-mode transitions. Mission-level continuity is `MissionLedger`'s job.

---

## Relation to Existing Harness Layers

The Memory Layer Distinction table above states the full boundary rule. This section adds one genuinely new detail: how run-state envelope fields map back to their source categories.

**Run-state envelope projection sources** (from `backend/harness/run_state.py` ← loop-memory):

| Run-state field | Source category |
| --- | --- |
| `blocker_summary` | Work-state memory — blocker surface projection |
| `progress_summary` | Progress memory — `no_progress_streak`, `last_progress_reason`, `iterations` |
| `resumability` | Feedback memory — `HitlState` resumability projection |
| `terminal_snapshot` | Terminalization output |

Run-state is derived from loop-memory; it does not feed back into it. `MissionLedger` boundary rules from `mission-runtime-contracts-v1.md` remain in force — do not push loop-memory fields into it. Canonical traces are append-only event history derived from loop-memory transitions — they are not a resumable working state container.

---

## Guardrails

| Failure mode | Prevention rule |
| --- | --- |
| Shared memory becomes a transcript-shaped ledger | Memory contract is category-shaped, not field-shaped. The field-mapping appendix exists to ground categories; it does not define the schema. |
| Domain closure truth leaks into shared categories | Work-state memory owns a closure posture summary (bounded projection) but not the authoritative closure rules. Transcript `decision_ledger` and `blocker_registry` remain domain-owned. |
| Feedback memory absorbs domain HITL authority | Shared feedback memory provides the `HitlState` projection. Transcript `blocker_registry` remains the authoritative HITL source for the transcript domain pack. |
| Loop-memory gets pushed into MissionLedger | `MissionLedger` boundary rules are explicit and preserved. Loop-memory is a separate layer. |
| Progress memory absorbs loop-brake thresholds from domains | Loop-brake policy (max `no_progress_streak`) is orchestration-kernel policy. Domain packs supply metric inputs, not policy values. |
| Giant universal ledger | No new universal ledger object is created. Loop-memory is six categories with clear ownership. |
| Run-state becomes a second authority | Run-state remains a bounded projection/read-model. It is derived from loop-memory, not authoritative over it. |
| Domain-state becomes a domain-level monolith | If a domain-state field starts being needed by the orchestration kernel for loop control, it must be promoted to the appropriate shared category rather than causing the kernel to acquire domain-state read access. |

---

## Field-Mapping Appendix

This appendix maps current loop-family fields to their target memory category. It exists to ground the category definitions — it is not the schema.

### deed_to_ir

`deed_to_ir` today operates with a flat action loop rather than a focus-item-centric work-state surface. Its fields map to categories as follows: refusal/repair-surface fields (`refusal_streak`, per-action-class repetition signals) → **Continuity**; run summary fields (`run_summary_ref`, `recent_digest_memory`) → **Continuity**; `phase_hint` (a focus proxy) → **Work-state**; `iterations` → **Progress**. Deed has no first-class HITL state today — it will gain generic `HitlState` via the shared substrate at Phase 6. Context packet internals, proposal repair skeletons, and span/seed caches → **Domain-state**.

The deed migration onto the shared focus/work-state shape is Phase 6 work. Category assignments for deed fields not enumerated here will be finalized when the deed domain pack interface is defined.

### transcript_edit (from `TranscriptEditLoopState`)

| Current field(s) | Target category | Notes |
| --- | --- | --- |
| `continuity_log` | Continuity | Per-focus recent attempt log |
| `invalid_plan_strikes` | Continuity | Invalid-plan strike surface |
| `decision_ledger` | Work-state | Work-item surface — domain authority stays in transcript pack |
| `blocker_registry` | Work-state | Blocker surface — domain authority stays in transcript pack |
| `last_focus_key`, `focus_stagnation_streak` | Work-state | Focus state |
| `latest_refs`, `current_transcript_ref` | Work-state | Work-item-associated artifact refs — note: these are also projected into the shared run-state envelope (`minimal-shared-run-state-envelope.md`); the run-state projection is downstream of loop-memory, not a competing authority |
| `span_context_by_decision_key` | Evidence | Cached per-focus span evidence |
| `image_verification_payload_by_decision_key` | Evidence | Cached per-focus image verification |
| `visual_evidence_by_decision_key` | Evidence | Cached per-focus visual evidence |
| `evidence_repeat_guard` | Evidence | Repeat attempt budget tracking |
| `evidence_signal_counter` | Evidence | New-signal counter |
| `span_seeds_ref` | Domain-state | Artifact ref for seeded span data — the orchestration kernel does not inspect this for loop control; seeding decisions belong to the domain pack's evidence strategy |
| `pending_feedback_prompt_id`, `pending_feedback_prompt`, `pending_feedback_decision_key`, `pending_feedback_emitted_iteration` | Feedback | Pending prompt record |
| `feedback_received_count`, `feedback_consumed_count`, `feedback_stale_count`, `feedback_superseded_count` | Feedback | Lifecycle counters |
| `feedback_entry_seen_keys`, `superseded_feedback_prompt_ids` | Feedback | De-dup and superseded state |
| `hitl_lifecycle_log` | Feedback | Bounded lifecycle event log |
| `latest_feedback`, `used_human_feedback` | Feedback | Most recent entry and consumed signal |
| `no_progress_streak` | Progress | Stagnation counter |
| `last_progress_reason` | Progress | Progress reason code |
| `previous_finding_signature`, `previous_blocking_signature`, `previous_blocking_unresolved_count`, `previous_signal_counter` | Progress | Baseline signatures and counts for progress classifier |
| `pending_reaudit_after_apply` | Progress | Refresh-needed flag |
| `apply_reaudit_baseline_blocking_count`, `apply_reaudit_baseline_blocking_signature` | Progress | Reaudit baseline |
| `applied_any_edits`, `applied_non_normalization`, `applied_requires_review` | Progress / Domain-state | Partially shared signal (applied_any_edits), partially domain-specific |
| `convention_context` | Domain-state | Transcript-specific convention rules |
| `llm_call_seq` | Domain-state | Internal sequencing, not shared |
| `iterations` | Progress | Iteration count |

---

## Implementation Posture

Do not begin implementing loop-memory containers in code until Phase 4 (domain-pack interface protocol) is frozen in docs, so that the domain pack's access pattern into loop-memory categories is defined before the container is built.

The domain-pack interface (Phase 4) will define:
- how domain packs read from and write to shared memory categories
- what domain packs must provide as projection inputs (e.g., metric inputs for `ProgressDelta`)
- how domain-state memory is stored alongside shared categories

Current loop-family code (`TranscriptEditLoopState`, controller runtime locals, `StepPreparationResult`) remains authoritative for today's behavior. This contract governs planning only.
