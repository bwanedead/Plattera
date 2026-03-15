# Agent Kernel Convergence Roadmap

Date: 2026-03-13
Status: Active working roadmap for next convergence stage
Primary references:
- `docs/architecture/agent-kernel/target-agent-kernel-v1.md`
- `docs/architecture/agent-kernel/loop-family-orchestration-delta-matrix.md`
- `docs/architecture/agent-kernel/current-to-next-vocabulary-crosswalk.md`
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/migration/unified-mission-runtime-plan-2026-03-12.md`

## Purpose

Sequence the next convergence stage after the shared harness and mission runtime work.

This roadmap is:
- short and phased
- contract-first in posture
- additive over the current shared harness layer

It is not:
- a clean-slate rewrite plan
- a timeline
- a claim that current harness work needs to be redone

The current implemented harness layer is the foundation for this next stage, not its target.

---

## Relationship to Prior Convergence Work

The harness convergence program (Phases 1-14) established:
- shared execution kernel
- shared mission runtime shell
- shared terminal taxonomy
- shared canonical trace model
- shared run-state envelope
- review/eval foundation

This roadmap picks up from that foundation and addresses the remaining delta: two loop families with different orchestration units, memory schemes, and loop laws that still operate as monolithic mode blobs inside the mission runtime.

---

## Phase 1. Architecture Clarification Spine ✓ complete

**Outputs:**
- `docs/architecture/agent-kernel/target-agent-kernel-v1.md` (tightened seed)
- `docs/architecture/agent-kernel/current-to-next-vocabulary-crosswalk.md` (includes `mode pack` reconciliation)
- `docs/architecture/agent-kernel/loop-family-orchestration-delta-matrix.md`
- this roadmap
- updated docs navigation

---

## Phase 2. Orchestration-Kernel Contract Freeze ✓ complete

**Goal:** Define the shared loop law and orchestration kernel contracts in docs before any runtime implementation.

**Outputs:**
- `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md`

**Frozen:**
- loop phase grammar: orient (run-start) → refresh → project → select-focus → resolve-move → execute → evaluate-progress → decide → terminalize-or-continue (per-iteration)
- `OrchestratorContext`: what the orchestration kernel assembles each iteration
- `FocusPacket`: domain-to-orchestration handoff for one focused work item
- `MoveDecision`: chosen next move for the active focus
- `MoveExecutionPlan`: compiled execution-kernel action from a move decision
- `ProgressDelta`: normalized progress evaluation output
- `HitlState`: generic human-feedback lifecycle substrate
- `TerminalDecision`: shared terminal scaffold mapped from domain closure conditions

---

## Phase 3. Shared Loop-Memory Contract Freeze ✓ complete

**Goal:** Define the shared loop-memory category contract.

**Outputs:**
- `docs/architecture/agent-kernel/shared-loop-memory-v1.md`

**Minimum to define:**
- continuity memory category (recent attempts, refusal/thrash history, bounded summaries)
- work-state memory category (work items, blockers, focus state, closure posture)
- evidence memory category (gathered evidence, per-focus cache)
- feedback memory category (pending prompts, ownership, lifecycle states)
- progress memory category (baseline signatures, stagnation counters, progress reasons)
- domain-state memory category (domain-specific cached payloads that do not generalize)

**Constraint:** do not model this contract on `TranscriptEditLoopState` fields directly. Use the category structure from the delta matrix. Both families contribute to the category shape; neither is the template.

**Done when:** the six memory categories are explicitly defined and each domain's existing fields can be mapped to categories with clear domain-local carve-outs.

---

## Phase 4. Domain-Pack Boundary Freeze ✓ complete

**Goal:** Define what a domain pack owns and what it must not own.

**Outputs:**
- `docs/architecture/agent-kernel/domain-pack-interface-v1.md`

**Minimum to define:**
- domain pack protocol: the interface a domain pack must implement to plug into the orchestration kernel
- what the pack owns (orientation contents, work-state projection rules, blocker taxonomy, evidence strategy, verification rules, closure rules, move repertoire, move-to-action compilation, domain prompts)
- what the pack must not own (loop phase ordering, loop-memory category management, progress evaluation logic, generic HITL substrate, terminal scaffold)

**Done when:** the domain-pack interface is explicit enough that a new domain could be added by implementing one pack without creating a new top-level controller loop.

---

## Phase 5. Transcript-First Extraction Plan ✓ complete

**Goal:** Define a concrete extraction plan for promoting reusable transcript-edit orchestration patterns into the orchestration kernel.

**Outputs:**
- `docs/architecture/migration/transcript-extraction-plan.md`

**Extraction targets (from `loop-family-orchestration-delta-matrix.md`):**
- orient baseline as a generic orchestration phase
- audit/reaudit trigger as a generic post-apply refresh
- focus selection flow (generic; transcript decision_ledger is domain-supplied work-state)
- focus_packet → resolve_focus_move as the shared move layer
- `classify_iteration_progress` as the shared progress evaluator (with domain-supplied metrics)
- HITL lifecycle substrate (pending/waiting/answered/consumed/superseded state machine)

**Constraint:** extract the mechanics; leave transcript-specific semantics in the transcript domain pack. Do not copy transcript-edit's closure layer, decision identity logic, or span evidence waterfall into the shared core.

**Done when:** every extraction target has a clear "stays in domain pack" / "moves to orchestration kernel" call, backed by a concrete interface.

---

## Phase 6. Deed Migration onto Shared Focus/Work-State Shape

**Goal:** Migrate `deed_to_ir` from action-loop semantics to focus-item-centric semantics.

**Preconditions:** Phases 2-4 must be complete (contracts frozen).

**Work:**
- map deed observations to work items
- define deed focus selection (what is the highest-priority unresolved work item for deed?)
- define deed progress metrics for shared `ProgressDelta` contract
- define deed domain pack interface implementation
- define deed terminal conditions mapped to shared terminal scaffold

**Done when:** `deed_to_ir` can run a loop cycle using the shared orchestration kernel with a deed domain pack, with equivalent behavior to today.

---

## Phase 7. Blended Multi-Domain Mission Planning

**Goal:** Enable a single mission to execute a linear roundtrip `deed_to_ir → transcript_edit → deed_to_ir` under one shared orchestration kernel, with mission continuity, correct terminal semantics, and coherent trace lineage.

**Status:** Implementation complete — proof run pending.

**Contract invariant (F1 / taxonomy):**
`mission_status.terminal_class` must always be one of the 6 shared TerminalClass values (`completed | blocked | waiting_human | waiting_evidence | exhausted | failed`) or `None`. Do not invent pseudo-classes such as `"transitioning_to_*"` — transition state is observable via `transition_history` and `cycles[*].transition`, not via the taxonomy field.

**Implemented work:**
- D1: Mission terminal semantics fixed — `mission_status.terminal=False` while a transition is in flight; `mission_status.terminal_class=None` (never a pseudo-class); transition visibility retained via `transition_history` and `cycles[*].transition`
- D2: Deed mode start request built lazily per-cycle so ledger refs (from transition handoffs) can be incorporated when deed resumes after transcript
- D3: `infer_deed_ir_ref_from_ledger()` added (parity with `infer_transcript_ref_from_ledger`) for ledger-driven deed resumability
- D4: Deed kernel runs in a mission now use `mission-{mission_id}-deed-{hex}` request prefix (parity with `mission-{mission_id}-tx` for transcript)
- D5: Transition handoff bundles are now explicitly curated (`_curate_deed_to_tx_handoff_refs`, `_curate_tx_to_deed_handoff_refs`) rather than passing all high_signal_refs implicitly
- D6: `build_mission_trace_index()` added; persisted as `mission_trace_{mission_id}.json` after multi-cycle roundtrips; ref appended to `high_signal_artifact_refs`
- D7: `--enable-roundtrip` auto-enables deed orchestration kernel; warns when `--max-cycles < 3`

**Canonical proof path (operator):**
```
python -m api.mission_runtime_cli \
  --objective "deed_to_ir_then_transcript_edit_roundtrip" \
  --initial-mode deed_to_ir \
  --mission-id phase7-proof-01 \
  --max-cycles 6 \
  --enable-roundtrip \
  --deed-dossier-id <your_dossier_id> \
  --tx-scenario practice_legaltext \
  --tx-validation-mode live_hitl \
  --tx-max-iterations 12 \
  --done-file tmp/done_phase7.json
```
Then watch with `hitl_watch`, inject HITL when prompted, re-watch to completion.

**Artifacts that prove completion:**
- `high_signal_artifact_refs` contains refs from all three cycles
- `transition_history` shows two applied transitions with explicit `handed_forward_artifact_refs`
- `mission_status.terminal=true` only in the final payload
- `mission_traces/mission_trace_{mission_id}.json` exists and has two `applied_transitions`

**Done when:** the canonical proof path above produces a `mission_status.terminal=true` result with a coherent trace (per-run trace refs + mission trace index ref).

---

## Managerial Operating Mode

Follow the same approach used in the harness convergence program:
- define contracts in docs before implementation
- review each phase outcome against prior contract docs before proceeding
- one focused phase at a time
- update delta tracking docs when capabilities advance
- do not claim phase complete until concrete evidence exists

---

## Failure Modes to Watch

1. **Competing vocabulary**: next-stage seed terms collide with current harness terms. Avoid by using the crosswalk strictly.
2. **Over-wide extraction**: transcript-edit domain truth gets promoted into the shared orchestration kernel. Avoid by keeping domain-specific closure semantics, ledger identity, and evidence waterfall ordering out of shared contracts.
3. **Premature implementation**: starting Phase 6 (deed migration) before contract freeze in Phases 2-4. Do not start implementation before the contracts are reviewable.
4. **Oversized domain pack**: the deed or transcript-edit domain pack becomes as large as the old family controller. Keep domain packs focused on content and domain policy only.
5. **Memory contract over-specification**: defining a shared loop-memory schema that is just `TranscriptEditLoopState` renamed. The memory contract must be category-shaped, not field-shaped.

---

## Success Criteria

This roadmap is succeeding when:
- a new domain can be added via a domain pack without creating a top-level controller loop
- both existing domains produce `FocusPacket → MoveDecision → MoveExecutionPlan` per iteration
- one shared progress evaluator runs across both domains
- one shared HITL substrate handles human feedback lifecycle for all domains
- one mission trace tells a coherent story across multi-domain cycles
- `backend/harness/mission_runtime/` becomes a thinner shell coordinating above the orchestration kernel rather than invoking monolithic family controllers

---

## Relation to Harness Convergence Roadmap

This roadmap is a **successor**, not a replacement.

The harness convergence program (Phases 1-14) addressed: shared spine, shared traces, shared terminal taxonomy, shared run-state, review foundation.

This roadmap addresses: shared loop law, shared loop-memory model, shared orchestration mechanics, domain packs.

When this roadmap conflicts with `harness-convergence-roadmap.md`, the harness roadmap governs for currently implemented boundaries. This roadmap governs for next-stage planning only.
