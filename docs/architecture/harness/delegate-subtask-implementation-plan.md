# Delegate Subtask Implementation Plan

This document tracks the implementation phases for `delegate_subtask`.

The architecture intent lives in [`delegate-subtask-architecture.md`](delegate-subtask-architecture.md). This plan is a rollout checklist so work can be handed to coding agents without losing the original boundaries.

---

## Phase 0: Architecture Alignment And Code Inventory

Goal: identify the exact seams to touch before implementation.

Deliverables:

- locate current action parsing, action execution, model-call adapter, prompt composition, image evidence attachment, audit timeline, and batch-policy seams
- decide package ownership for generic subtask infrastructure
- decide profile registration shape for generic and domain-owned profiles
- confirm no implementation will let subtask results mutate mission state directly
- record any hotspot or file-size risks before coding starts

Acceptance:

- implementation target files are known
- no code behavior changes yet
- architecture still matches the Harness Constitution

---

## Phase 1: Generic Contract And Registry Scaffold

Goal: make `delegate_subtask` a valid generic action with strict mechanical validation.

Deliverables:

- action contract accepts `delegate_subtask`
- generic input shape validates bounded fields:
  - `profile`
  - `task`
  - `context_refs`
  - optional `isolation`
  - optional `output_contract`
- invalid profile / too many refs / overlong task fail repairably
- profile registry exists as a shared harness service
- profile metadata supports at least:
  - profile id
  - owner
  - allowed input ref kinds
  - prompt source
  - result schema
  - model policy
  - max refs
  - max result size
  - batch cap
  - max turns, initially `1`

Acceptance:

- parser tests cover valid/invalid `delegate_subtask`
- registry tests cover generic and domain profile lookup
- no child model calls yet
- no state mutation path exists

---

## Phase 2: Single-Turn Subtask Execution

Goal: execute one isolated subtask and return a bounded tool result.

Deliverables:

- generic subtask runner resolves `context_refs`
- runner builds a compact child prompt from:
  - profile prompt
  - parent-authored task
  - allowed refs/media
  - output contract
- child prompt omits parent graph, closure ledger, broad doctrine, and peer candidates by default
- runner invokes model through the existing provider seam
- runner validates child response into a bounded result row
- result statuses support:
  - `completed`
  - `ambiguous`
  - `insufficient_input`
  - `failed`
- no `confidence` field in the contract

Acceptance:

- single subtask executes against a fake/model stub in tests
- malformed child output becomes bounded failure/repair behavior
- result appears as a normal action result for the parent
- no raw `b64` appears in prompt/audit text

---

## Phase 3: Parent Projection, Audit, And Observability

Goal: make subtask behavior visible and cheap to inspect.

Deliverables:

- parent next-turn prompt receives bounded subtask result summaries
- timeline renders:
  - subtask alias/id
  - profile
  - task excerpt
  - input refs
  - status
  - result summary
  - bounded errors
- trace metadata records parent prompt cost and subtask prompt cost separately
- prompt budget report gets a subtask/model-call bucket if needed
- resume snapshots preserve completed subtask action results safely

Acceptance:

- human timeline can debug subtask use without raw JSON
- prompt/audit tests prove no raw media payloads leak
- subtask cost is not hidden inside parent prompt accounting

---

## Required Follow-Up Before Phase 5 (Profile-Specific Result Schemas) — COMPLETE

Implemented in `backend/harness/runtime/orchestration/subtasks/result_schema.py`:

- profile `result_schema` validation at registration time
- schema-driven child result normalization in `runner.py`
- schema-driven bounded projection in `projection.py`
- dynamic timeline rendering for profile-specific result fields

Phase 5 (`transcript_edit.visual_source_observation`) can now depend on custom result payload fields.

---

## Phase 4: Batching And Failure Isolation

Goal: allow several independent subtasks in one parent turn.

Deliverables:

- `delegate_subtask` is batchable through normal native `actions`
- tool/profile-owned cap, initially small (suggested cap: 4)
- each subtask row has independent alias, input refs, status, and result
- one failed subtask does not invalidate successful sibling subtasks unless the failure is structural to the whole batch
- batch results remain bounded in prompt/timeline projection

Acceptance:

- tests cover multiple `delegate_subtask` actions in one turn
- tests cover partial failure
- tests cover over-cap rejection
- batching remains optional, not required

---

## Phase 5: First Domain Profile For Transcript Edit

Goal: add the first practical profile without making transcript-edit semantics part of the generic harness.

Profile:

- `transcript_edit.visual_source_observation`

Deliverables:

- domain-owned profile prompt for isolated visual/source observation
- profile accepts image refs
- profile instructs:
  - use only supplied inputs
  - preserve source-visible marks/text
  - do not normalize unless asked
  - state ambiguity directly
  - do not infer from peer drafts or graph state
- parent doctrine teaches the tool lightly:
  - use delegation for narrow subtasks that benefit from isolated attention
  - keep blind reads blind when candidate imprinting could matter
  - integrate results through normal graph/artifact/HITL channels

Acceptance:

- transcript-edit pack tests prove profile is registered
- parent prompt mentions delegation without making it mandatory
- no transcript-edit labels leak into shared harness contracts

---

## Phase 6: Live Behavior Experiment

Goal: determine whether isolated subtask attention improves the real failure mode.

Experiment:

- use the known localized crop where the main loop read `N. 2° 00' W.`
- have parent agent delegate a blind source-observation subtask over that crop
- compare:
  - parent direct read
  - delegated blind read
  - optional delegated discriminative read if explicitly requested

Evaluation:

- did the delegated read avoid candidate imprinting?
- did it reduce parent turns?
- did it reduce prompt cost?
- did the parent correctly treat the result as advisory?
- did the timeline make the event clear?

Acceptance:

- if it reads correctly, continue hardening the profile
- if it still reads incorrectly, treat the problem as model visual limitation and lean harder on user correction/HITL
- do not expand into persistent subagents until this experiment shows value

---

## Phase 7: Future Extension, Not V1

These are deferred until single-turn delegation proves useful.

Possible future work:

- asynchronous subtask execution
- true parallel provider calls
- persistent child task state
- child `max_turns > 1`
- child resume checkpoints
- child tool permissions
- stronger-model escalation profile
- cheaper-model probe profile
- generic review subagents
- artifact consistency subagents

These must not be mixed into the first implementation unless explicitly approved.

---

## Current Recommended First Coding Brief Scope

The first coding handoff should cover Phases 1 through 3 only.

Do not start with persistent subagents, async execution, or broad domain profile suites. Build the generic scaffold, prove one isolated model call can run safely, and make the parent/timeline projection observable.

After that, hand off Phase 4 and Phase 5 as separate work, then run the Phase 6 behavior experiment.
