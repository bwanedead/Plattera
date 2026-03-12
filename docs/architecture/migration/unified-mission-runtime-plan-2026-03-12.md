# Unified Mission Runtime Plan

Date: 2026-03-12
Status: Working migration plan
Related docs:
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/agent-loop-system-overview.md`
- `docs/transcript-edit-loop-orchestration.md`

## Purpose

Define the next major convergence step after the shared harness spine: move from multiple loop-family orchestrators toward one shared mission runtime over one shared execution kernel, while preserving the useful domain-specific shapes already discovered in deed-to-IR and transcript-edit work.

This is a migration plan, not a claim that the final runtime design is already fully proven.

## Core Direction

The target is not:
- one giant monolithic controller
- one flattened domain policy
- a clean-slate rewrite that discards current loop-family work

The target is:
- one shared mission runtime
- one shared execution kernel
- specialized mode policies for each domain
- explicit mode transitions
- one shared trace/review/run-state story across the full mission lifecycle

For v1, mode transitions should remain linear and synchronous rather than nested. One mission should feel like one continuous agent unit moving through states such as `deed_to_ir -> transcript_edit -> deed_to_ir`, with persisted continuity across the whole lifecycle.

## Current Ground Truth

### What is already shared

The repo already has real shared harness infrastructure:
- a shared execution substrate centered on `KernelSessionManager`
- shared canonical traces
- shared terminal taxonomy
- shared run-state envelope
- shared review/reporting tooling

This means the migration does not start from zero.

### What is still split

The main remaining split is at the mission-controller/orchestration layer:
- the deed/controller-kernel family is closer to a reusable generic runtime shell
- the transcript-edit family contains stronger domain-shaped orchestration patterns such as orient baseline, blocker lifecycle, evidence focus, and HITL handling

Those transcript-edit patterns should not be discarded. They should be promoted where generic and preserved where domain-specific.

## Architectural Shape

## 1. Shared Execution Kernel

The shared execution kernel should remain the domain-agnostic mechanical substrate.

It owns:
- action execution
- budgets
- idempotency
- refs and artifact persistence
- deterministic refusal semantics
- tool dispatch

Current anchor:
- `backend/agent_kernel/session.py`

## 2. Shared Mission Runtime

The shared mission runtime should become the top-level orchestrator for all agentic mission work.

It owns:
- mission identity and lifecycle
- active mode
- iteration sequencing
- proposal, validation, execution, and observation loop flow
- shared continuity state
- terminal handling
- mode-switch handling
- trace emission and run-state updates

The best current starting point is the existing controller runtime loop rather than a brand new runtime.

Current anchor:
- `backend/agents/controller/controller_runtime_loop.py`

## 3. Specialized Mode Policies

Domain-specific behavior should be expressed as specialized mode policies layered on top of the shared mission runtime.

Examples:
- `deed_to_ir`
- `transcript_edit`
- future mission/domain modes

A mode policy should define:
- context building
- tool and action menu policy
- blocker interpretation
- evidence strategy
- verification rules
- completion rules
- transition triggers

Mode policies should keep weight-bearing domain truth local.

Mode policies should not become a disguised copy of the old family controllers. They should own domain decisions, not accumulate reusable orchestration mechanics that belong in shared runtime capabilities.

## 4. Shared Runtime Capabilities

The shared runtime should absorb generic orchestration capabilities that are useful across domains.

These should become shared capabilities:
- orient/startup audit
- bounded continuity memory
- blocker tracking as a generic concept
- evidence gathering as a generic concept
- verification-before-completion
- HITL as a generic runtime capability
- loop-brake/no-progress detection
- transition evaluation

These should remain mode-specific:
- transcript-edit decision ledger semantics
- transcript-edit closure layers and mapping-readiness rules
- transcript-edit exact evidence waterfall ordering
- deed-to-IR compile/judge/bundle/declare-done semantics
- domain-specific blocker classes and acceptance thresholds

## Layering Discipline

The target layering should remain explicit:
- mission runtime owns mission lifecycle, mode switching, shared continuity, mission trace, and terminal handling
- execution kernel owns step execution, budgets, idempotency, refs, and deterministic action execution
- mode policy owns domain decision logic
- runtime capability owns reusable orchestration mechanics

Implementation should resist collapsing these layers back together.

## 5. Linear Mode Transitions for v1

The first unified runtime should support explicit, synchronous mode transitions within a single mission identity.

This is intentionally simpler than child subruns.

The runtime should:
- persist the reason for switching modes
- record the prior and next mode
- carry forward the relevant artifacts and continuity summary
- record what the receiving mode is expected to do
- preserve a resumable note for returning to the prior mode
- preserve one mission trace/story
- allow later resumption of the prior mode with updated context

The agent may surface the need for a transition, but the runtime should validate and apply it explicitly.

## Runtime Contracts To Add

The next design/implementation pass should define these contracts explicitly:

### MissionRuntime
- owns mission lifecycle, active mode, iteration cycle, terminal routing, transition routing, and shared continuity state

### ModePolicy
- owns domain-specific context, verification logic, blockers, completion logic, and transition triggers

### RuntimeCapability
- owns optional generic runtime behaviors such as orient, blockers, evidence, verification, HITL, and loop-brake behavior

### MissionLedger
- owns the bounded persisted mission-level summary:
  - active mode
  - prior mode history
  - key artifact refs
  - unresolved blockers summary
  - verification summary
  - transition history
  - resumability summary

MissionLedger should remain intentionally small. It should not become a giant universal runtime blob or duplicate full mode-local truth such as transcript-edit ledger internals, registry internals, or transient runtime caches.

### ModeTransition
- owns the explicit transition event:
  - source mode
  - target mode
  - reason
  - handoff artifacts
  - continuity note
  - resume note

## Migration Strategy

The migration should be inversion-of-control, not replacement-by-rewrite.

The principle is:
- preserve what each loop family already got right
- move orchestration ownership upward into the shared runtime
- keep domain truth inside mode policies

## Phase 1. Freeze the architecture contract

Define the new shared runtime contracts in docs first:
- `MissionRuntime`
- `ModePolicy`
- `RuntimeCapability`
- `MissionLedger`
- `ModeTransition`

Also explicitly document that v1 uses synchronous in-place mode switching, not child subruns.

This phase should produce a short follow-on contract doc for implementers that defines the minimum interface expectations for these runtime concepts without over-specifying internals.

## Phase 2. Build the mission runtime shell

Create the shared mission runtime shell by evolving the existing controller runtime structure.

Do not replace the kernel.
Do not rewrite the domain controllers wholesale.

At this phase, the runtime should gain:
- active mode tracking
- mission-ledger persistence
- transition event recording
- shared continuity update flow

## Phase 3. Extract generic capabilities from transcript-edit

Transcript-edit should contribute reusable orchestration patterns to the shared runtime.

The first extraction targets are:
- orient baseline
- blocker lifecycle handling
- evidence/focus handling
- verification gate
- HITL handling
- no-progress/reconsideration signals

This phase should extract patterns, not force transcript-specific semantics into the core.

## Phase 4. Adapt deed-to-IR as the first shared-runtime mode

The deed/controller-kernel family is the best first mode to run fully on the shared mission runtime because its current loop shape is already closer to a generic shell.

The runtime should take over orchestration while keeping:
- current context packet behavior
- refusal/repair behavior
- compile/judge/bundle behavior
- terminal expectations

## Phase 5. Adapt transcript-edit as the second shared-runtime mode

Transcript-edit should then be migrated onto the same mission runtime shell while preserving:
- decision ledger authority
- blocker registry authority
- transcript-specific verification and mapping-readiness semantics
- transcript-specific HITL and promotion behavior

The goal is not to erase transcript-edit’s domain shape. The goal is to stop it from owning a separate top-level runtime.

## Phase 6. Add cross-mode mission transitions

First supported path:
- `deed_to_ir -> transcript_edit -> deed_to_ir`

Expected runtime behavior:
- mapping/deed mode detects a transcript-sensitive issue
- mission runtime persists a mode transition
- transcript-edit mode operates against a targeted handoff
- transcript-edit returns updated artifact/readiness state
- deed mode resumes with preserved mission continuity

This should grow from the existing handoff packet and mapping bridge concepts rather than replacing them with a disconnected transition system.

## Phase 7. Tighten observability around multi-mode missions

Canonical trace, run-state, and review surfaces should be extended to represent:
- active mode
- ordered mode history
- transition events
- resume context summary

The mission should remain one traceable story even when it moves across multiple modes.

## Interface and Compatibility Expectations

The first implementation should preserve existing entry surfaces where practical and adapt them through compatibility layers.

Near-term policy:
- avoid breaking existing callers unless the migration requires it
- prefer adapters over abrupt contract replacement
- keep shared runtime interfaces additive first, then deprecate older loop-family entry surfaces deliberately

## Testing Expectations

The implementation phase should cover:

### Shared runtime tests
- single-mode mission lifecycle
- transition recording
- invalid transition rejection
- mission resume after transition

### Deed-to-IR mode tests
- existing behavior remains intact under shared runtime ownership
- refusal repair still works
- compile/judge/bundle flow still holds

### Transcript-edit mode tests
- orient baseline still runs
- decision ledger and blocker registry remain authoritative
- HITL waiting/resume still works
- transcript verification behavior remains intact

### Cross-mode tests
- deed-to-IR can trigger transcript-edit transition
- transcript-edit can return updated context/artifacts
- deed-to-IR can resume correctly
- one mission trace shows the full mode sequence in order

## Explicit Assumptions

- v1 prioritizes simplicity and continuity over nested subrun purity.
- One mission should feel like one continuous agent across the pipeline.
- The shared kernel remains in place; this is not a kernel rewrite.
- The current controller runtime is the best starting shell for the shared mission runtime.
- Transcript-edit contributes reusable orchestration patterns and keeps its domain truth.
- Child subruns remain a later option once the full linear pipeline is stable.

## Decision Rule

During implementation, prefer changes that move the repo toward:
- one orchestrator shape
- one mission continuity story
- one shared review/trace story
- domain-specific policy layered on top

Avoid changes that:
- create another parallel runtime shell
- flatten transcript-edit or deed-to-IR into generic mush
- move too much domain truth into the shared core too early
