# Transcript Edit Loop Focus-Cycle Architecture

Date: March 5, 2026
Status: Active target architecture
Audience: Internal and external planning/review agents

## 1) Purpose
This document describes the current target architecture for the transcript-edit loop after the shift away from deterministic HITL patching.

It explains:
- the loop's atomic process
- the role of transcript, ledger, memory, evidence, and feedback
- what remains deterministic versus semantic
- how closure is accumulated iteratively
- how human feedback re-enters the loop

This is the operational architecture target, not a historical refactor log.

## 2) Core design decision
The transcript-edit loop should be:
- ledger-guided
- focus-cycle driven
- agent-resolved
- deterministically gated

The active path should avoid deterministic regex-style edit drafting and brittle patch-shaping logic.

The agent decides the semantic move.
The deterministic runtime enforces rails, boundedness, persistence, and closure gates.

Current operating stance (Phase 5):
- closed-world convergence proof only (transcript + source image + existing tools + HITL evidence)
- no dependency retrieval execution in-loop
- dependency blockers are classified and reported honestly at terminalization

## 3) Canonical entities
### 3.1 Transcript
The transcript is the mutable working document and current deed text being refined.

### 3.2 Source evidence
Source evidence includes:
- deed image refs
- opened transcript spans
- image verification artifacts
- candidate draft evidence
- retrieval/dependency artifacts (as integrated)

### 3.3 Decision ledger
The decision ledger is the working case file and authoritative closure state.

It stores:
- per-decision item state
- blocking vs optional status
- selected value / alternatives
- evidence refs
- closure requirements
- layer semantics
- unresolved closure predicates

It drives:
- focus selection
- closure gating
- terminal interpretation

Contradiction identity rule (Phase 7):
- mapping-critical source-internal contradictions (for example `Range 75` vs `Range 74`) must stay attached to their real decision key
- contradiction identity should not be blurred into neighboring PLSS keys during focus/evidence/HITL flow
- Layer 2 canonical-sanity contradictions are first-class blockers until resolved or explicitly accepted with risk

### 3.4 Continuity memory
Continuity memory is bounded runtime continuity, not canonical truth.

Examples:
- recent attempts for a focus item
- recently failed strategies
- newly arrived human feedback
- why focus shifted

Continuity memory must not replace artifacts, refs, or ledger truth.

### 3.5 Human feedback
Human feedback is evidence input, not a direct patch recipe.

The loop persists feedback structurally and reinjects it into the next semantic focus-cycle.

### 3.6 External context injections
Focus packets include a bounded `external_context_injections[]` lane for persistent external semantic state.

Current first-class injected type:
- `human_resolution_ticket`

Structured fields include:
- `type`
- `ticket_id`
- `decision_key`
- `lifecycle_state`
- `strength`
- `payload`
- `created_at` / `updated_at`
- optional `answered_at` / `integrated_at`
- optional `relevance`

This is generic infrastructure; HITL tickets are the first concrete class.

## 4) Deterministic vs semantic
### 4.1 Deterministic runtime responsibilities
The deterministic layer is responsible for:
- phase ordering
- idempotency
- bounded contracts
- payload validation
- artifact persistence
- tool execution
- apply mechanics
- ledger persistence
- closure gating
- terminalization
- live-run behavior sanity:
  - bounded evidence waits/timeouts
  - bounded retries
  - throttled wait-state reporting
  - call/accounting visibility

### 4.2 Semantic agent responsibilities
The resolver is responsible for:
- interpreting transcript and source evidence
- interpreting human feedback
- selecting the next semantic move
- deciding whether more evidence is needed
- deciding whether an edit is safe
- drafting a bounded edit plan when appropriate
- deciding whether a blocker remains unresolved

## 5) The atomic loop: focus-cycle
One transcript-edit iteration should be one focus-cycle around one unresolved closure item.

### 5.1 Reconcile state
Read:
- current transcript ref/hash
- current ledger
- latest evidence artifacts
- newly arrived human feedback
- bounded continuity memory

### 5.2 Select focus
Choose the highest-priority unresolved closure item from the ledger.

Priority rules:
- mapping-blocking items outrank optional items
- newly answered human-feedback items should be prioritized
- dependency-blocked items can be terminalized if no autonomous move remains
- when contradiction evidence exists, focus should remain anchored to that contradiction key (for example `range`) rather than generic PLSS narration

### 5.3 Build focus packet
Assemble a bounded packet for one decision item:
- `decision_key`
- focused ledger item
- closure requirement
- transcript ref/hash
- bounded relevant spans
- bounded relevant image verification results
- latest feedback for this item
- relevant `external_context_injections` for this focused decision item
- recent attempts for this item
- bounded memory summary

Deterministic packet budgeting rules:
- cap focused span count and per-span text length
- cap image verification result count and observed-text length
- include only attempts for the same `decision_key`
- cap feedback/note payload sizes
- prefer refs/summaries over large inline blobs

### 5.4 Semantic resolve
Resolver receives focus packet and returns one move:
- `apply_edit_plan`
- `request_human_feedback`
- `gather_more_evidence`
- `mark_blocked`
- `mark_resolved_no_edit`

Focus/evidence fidelity expectation:
- evidence checks should align to the focused contradiction key by default
- if fallback checks are broader, runtime should report that fallback explicitly

### 5.5 Deterministic execute
Runtime executes selected move:
- validate/apply edit plan
- emit HITL prompt
- gather spans
- verify with image
- retrieve external evidence
- persist artifacts and refs

`gather_more_evidence` is executed through typed `evidence_request` dispatch:
- `open_spans`
- `image_verify`
- `retrieve_dependency_evidence` (explicitly unsupported until wired)

Runtime observability model (Phase 6):
- `iteration` remains one focus-cycle
- `llm_call_seq` tracks API/model calls inside the run
- `phase_attempt` tracks retries for repeated evidence attempts

### 5.6 Commit outcome
Runtime:
- updates ledger from new evidence/results
- appends continuity memory
- persists fresh state
- re-audits/reconciles when edits were applied

### 5.7 Terminal gate
End when:
- mapping-blocking closure is achieved, or
- no autonomous closure move remains and blocked state must be reported

Honest stop behavior:
- repeated unchanged focus/evidence/transcript state increments no-progress handling
- pending HITL without new feedback is not counted as progress
- before no-progress terminalization with a pending prompt, runtime performs one bounded last-chance feedback drain so just-arrived valid feedback is not skipped
- apply/edit is not treated as closure progress until a later re-audit/reconcile confirms improvement

## 6) Focus resolver contract
Resolver should return a bounded object containing:
- `decision_key`
- `move`
- `reason`
- optional `edit_plan`
- optional `feedback_prompt`
- optional `evidence_request`
- optional `closure_update_hint`
- optional `iteration_summary`

Deterministic acceptance rules:
- focus selection is runtime-owned and happens before resolver call
- resolver output must stay scoped to focused `decision_key`
- `mark_resolved_no_edit` is accepted only if deterministic ledger state agrees
- `mark_blocked` is accepted only under deterministic conditions (invalid move, dependency blocker, budget exhaustion, no autonomous path)
- `apply_edit_plan` is accepted only when bounded plan validation passes and scope checks hold
- repeated identical evidence requests are budget-limited unless new signal arrives
- long-running evidence emits sparse thresholded status transitions and a deterministic timeout/failure classification

`closure_update_hint` is advisory only and does not directly mutate ledger truth.

### 6.1 Move semantics
`apply_edit_plan`: enough evidence for safe bounded edit.

`request_human_feedback`: ambiguity remains; focused human input is next best action.

`gather_more_evidence`: autonomous evidence gathering should continue before escalation/edit.

`mark_blocked`: item cannot be autonomously resolved under current conditions.

`mark_resolved_no_edit`: focused item no longer materially unresolved or no mutation needed.

## 7) Human feedback lifecycle
1. Backend emits authoritative prompt for one focused unresolved item.
2. User submits structured response.
3. Response is stored as feedback evidence.
4. Runtime creates/updates `human_resolution_ticket` lifecycle state.
5. Next focus-cycle includes ticket context via `external_context_injections`.
6. Resolver decides what feedback means and which move follows.
7. Deterministic runtime executes selected move and updates ticket lifecycle.

Ticket lifecycle states:
- `issued_waiting_feedback`
- `answered_unintegrated`
- `integration_attempted_failed`
- `integrated`
- `superseded`
- `stale`

Important:
- feedback is not deterministically transformed into deed patch
- feedback influences semantic resolution

### 7.1 Pending prompt and supersession semantics (Phase 6.2)
- One authoritative pending prompt exists per active focused item.
- Prompt identity remains stable until one of:
  - consumed valid feedback for that prompt
  - explicit supersession with a recorded reason
- Baseline escalation should not immediately re-emit a new prompt in the same iteration after fresh feedback is consumed for that focus item.
- Late feedback for stale/superseded prompt ids is recorded as stale and not silently treated as active consumption.
- Runtime tracks durable HITL counters/state:
  - feedback received
  - feedback consumed
  - feedback stale
  - feedback superseded
- Runtime also tracks durable ticket lifecycle truth in ledger-backed injections.
- Terminal reporting uses durable HITL state in addition to rolling progress events.

### 7.2 Answered-unintegrated guardrail
If an active binding `human_resolution_ticket` for the focused decision is `answered_unintegrated`, runtime guardrails prevent silent indefinite ignoring.

Resolver/runtime must move toward one of:
- apply a safe bounded edit plan
- explicit blocked outcome with clear reason
- tighter follow-up HITL question when first answer is demonstrably insufficient
- materially different evidence request with remaining budget and explicit justification

### 7.3 Post-feedback resolver-invalid robustness
When a focused item has active answered/integration-pending ticket context:
- resolver-invalid outputs use a tighter repair prompt including injected-context summary
- retries remain bounded
- if retries exhaust, runtime terminalizes with explicit post-feedback invalid classification (not generic no-progress ambiguity)

Compact diagnostics are preserved for operator/debug use:
- focused `decision_key`
- ticket lifecycle state/id when present
- validation error class
- bounded raw-output excerpt
- malformed post-feedback `apply_edit_plan` attempts are repair-hardened; if safe plan schema cannot be produced, runtime can fall back to an explicit bounded blocked move rather than repeatedly cycling malformed apply payloads

### 7.4 Post-feedback observability lane
Live diagnostics now include explicit post-feedback seam events:
- `resolver_attempt`
- `resolver_outcome`
- `resolver_move_gate`
- ticket lifecycle transition events (`ticket_issued_waiting_feedback`, `ticket_answered_unintegrated`, `ticket_integration_attempted_failed`, `ticket_integrated`, `ticket_superseded`, `ticket_stale`)

These events include compact ticket snapshot fields where relevant:
- `ticket_id`
- `ticket_state`
- `ticket_strength`
- `ticket_decision_key`
- optional `answered_at` / `integrated_at`

Terminal summary now exposes concise seam fields:
- `post_feedback_ticket_seam_state`
- `post_feedback_ticket_snapshot`

## 8) Ledger and 4-layer closure model
The architecture preserves layer model:
- Layer 1: canonical recovery
- Layer 2: canonical sanity
- Layer 3: dependency completeness
- Layer 4: optional transcript quality

Ledger is authoritative structured expression of closure states.

Operationally:
- Layers 1-3 mapping-blocking items drive loop
- Layer 4 items are secondary
- terminal summaries remain coherent with ledger closure state

## 9) Role of memory
Bounded continuity memory may include:
- run summary log
- recent focus attempts
- compact iteration notes

Memory reduces thrash and preserves continuity.
Memory is not canonical transcript truth or closure truth.

## 10) Current implementation status
### 10.1 Completed foundations
- closure-consistent gating
- ledger-based unresolved mapping-blocking predicates
- focus packet module
- focus resolver module
- iteration pipeline pivot toward focus-cycle handling

### 10.2 Transitional areas
- dependency retrieval execution remains explicitly unsupported pending retrieval-stage wiring
- resolver guidance still depends on prompt quality and bounded context quality
- closed-world convergence proof is active: progress/no-progress and terminal classification are now explicit runtime concerns
- live API behavior may still show transient upstream failures (for example provider 500s); runtime now classifies/retries/bounds these without treating every transient as a local logic bug
- resolver-invalid outcomes are now retry-bounded and classified, but final quality still depends on model output stability under live load

### 10.3 Explicitly superseded direction
Regex-style deterministic HITL override builders are not the intended active architecture.

## 11) Near-term implementation target
Next steps:
- make move-returning resolver contract fully first-class
- enrich focus packet where needed
- keep orchestration thinner in iteration pipeline
- continue deterministic rails for validation, persistence, and closure gates

## 12) Summary
Target architecture is:
- deterministic rails
- semantic focus resolution
- ledger-guided iteration
- continuity memory for bounded context
- human feedback as evidence
- repeated focus-cycle that accumulates closure over time
