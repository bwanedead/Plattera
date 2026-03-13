# Target Agent Kernel v1

Date: 2026-03-13
Status: Seed architecture contract for the next convergence stage

Related docs:
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/migration/unified-mission-runtime-plan-2026-03-12.md`
- `docs/transcript-edit-loop-orchestration.md`
- `docs/agent-loop-system-overview.md`

## Purpose

Define the next architecture target after shared harness and mission-runtime convergence:

- one holistic `agent kernel architecture`
- one shared loop law across domains
- one shared loop-memory law across domains
- domain-specific content injected without domain-specific top-level controller species

This document is intentionally a seed contract.

It is meant to:
- lock the direction of travel
- keep future docs and implementation aligned
- prevent a new round of architecture drift while the next refactor stage is still being designed

It is not meant to:
- fully specify every interface yet
- replace the currently implemented harness docs as the source of truth for present code
- justify a clean-slate rewrite

## Status Boundary

This document is forward-looking.

For current implemented v1 boundaries, the active harness docs still take precedence:
- `docs/architecture/harness/mission-runtime-contracts-v1.md`
- `docs/architecture/harness/target-harness-v1.md`

This seed is describing the next convergence stage after that shared harness layer, not redefining what the current repo already implements.

## Working Naming

Use this naming consistently:

- `agent kernel architecture`:
  - the full agentic kernel architecture as a whole
- `execution kernel`:
  - the step/action execution substrate
- `orchestration kernel`:
  - the shared convergence loop and loop-memory substrate
- `domain pack`:
  - domain-specific policy, projection, and move logic layered onto the orchestration kernel

Important naming note:
- current repo docs often use `agent kernel` in the narrower sense now represented by `backend/agent_kernel/`
- this seed uses `agent kernel architecture` for the broader future stack while preserving `backend/agent_kernel/` as the execution kernel

Avoid framing this stage as a "unified kernel" project.
The goal is one `agent kernel architecture` with clear internal parts, not a separate branded subsystem.

## Relation To Current Harness Vocabulary

This seed should be read as a forward remap of the current harness vocabulary, not a competing terminology set.

| Current active term | Current meaning | Next-stage interpretation in this seed |
| --- | --- | --- |
| `MissionRuntime` | mission lifecycle orchestration and continuity owner | likely narrows toward mission shell responsibilities and coordinates the orchestration kernel rather than remaining the sole deep loop owner |
| `RuntimeCapability` | reusable cross-mode orchestration mechanics, currently underspecified in code | likely becomes the first explicit home for orchestration-kernel mechanics or their immediate precursor |
| `ModePolicy` | domain-local interpretation / acceptance / transition recommendation | likely evolves toward a smaller domain pack boundary |
| Execution kernel | deterministic step execution mechanics | remains the execution kernel |
| `MissionLedger` / `ModeTransition` | mission-owned continuity records | remain mission-owned records; not candidates for domain ownership |

Working interpretation rule:
- current docs answer "who owns what in the implemented v1 runtime?"
- this seed answers "what should the next deeper convergence stage grow toward after v1?"

## Current Ground Truth

The repo already has meaningful convergence work in place:

- shared execution kernel
- shared harness layer
- shared mission runtime shell
- shared terminal taxonomy
- shared trace and run-state normalization work

But the deepest loop mechanics are still split:

- `deed_to_ir` remains primarily action-proposal-centric
- `transcript_edit` already behaves more like a work-state convergence loop

This means the repo currently has:
- shared execution mechanics
- partially shared mission shell mechanics
- not yet one shared orchestration law

## Core Direction

The architecture target is:

- one execution kernel
- one orchestration kernel
- one family of shared loop-memory structures
- domain packs that differ in content and policy, not in fundamental loop shape

The strongest architecture test is:

> A new domain should be addable by implementing a domain pack, not by creating a new top-level controller loop.

The next strongest test is:

> A single mission should eventually be able to move fluidly across work items owned by multiple domains without looking like handoffs between different controller species.

## Target Layering

### 1. Execution Kernel

The execution kernel remains domain-agnostic and mechanical.

It owns:
- action execution
- budgets
- idempotency
- step persistence
- artifact refs
- deterministic refusal semantics
- tool dispatch

Current anchor:
- `backend/agent_kernel/`

### 2. Orchestration Kernel

The orchestration kernel is the missing shared center of gravity.

It should own:
- loop phase order
- loop-memory structure
- focus selection flow
- move selection flow
- progress evaluation flow
- HITL lifecycle as a generic concept
- closure / continue / terminal decisions
- resumability semantics

It should not own:
- transcript-specific closure semantics
- deed-specific compile/judge/bundle semantics
- domain-specific blocker meaning
- domain-specific evidence meaning

### 3. Domain Packs

Each domain pack should inject only what is domain-specific.

A domain pack should own:
- orientation contents
- work-state projection rules
- blocker taxonomy
- evidence strategy
- verification rules
- closure rules
- move repertoire
- move-to-action compilation
- domain-specific prompts
- domain-only cached state

Examples:
- transcript-edit domain pack
- deed-to-IR domain pack
- future mixed mapping / retrieval / validation packs

### 4. Mission Runtime / Harness Shell

The mission runtime remains valuable as the outer shell, but it should not remain the deepest owner of loop behavior.

It should own:
- mission identity
- mode / active pack selection
- cross-mode continuity envelope
- transitions and mission-level summaries
- CLI / API / observability entry surfaces

It should increasingly sit above the orchestration kernel rather than wrapping distinct family-sized controllers.

## Candidate Shared Loop Law

The current candidate loop law is that every domain loop should eventually run the same core formula:

1. orient
2. refresh
3. project
4. select focus
5. resolve move
6. execute
7. evaluate progress
8. decide continue / escalate / close
9. terminalize or continue

This phase grammar is a seed-level working target, not yet a frozen contract.

It is grounded in observed transcript-edit orchestration patterns (orient baseline, audit/reaudit, focus selection, focus_packet → resolve_focus_move, progress classify, HITL/closure decision) and should be cross-checked against both loop families before being frozen.

The contents of each phase should vary by domain pack.
The phase grammar itself should increasingly converge.

This grammar freeze is the primary goal of Phase 2 (orchestration-kernel contract freeze) in the next-stage roadmap.

## Candidate Shared Loop Memory

The orchestration kernel should own the generic categories of loop memory.

The current working target is:

- continuity memory
  - recent attempts
  - refusal / repeat / thrash history
  - bounded summaries
- work-state memory
  - unresolved work items
  - blockers
  - focus state
  - closure posture
- evidence memory
  - gathered evidence
  - evidence attempts
  - cached per-focus evidence
- feedback memory
  - pending prompts
  - ownership
  - answered / consumed / stale / superseded state
- progress memory
  - baseline signatures
  - deltas
  - stagnation counters
  - progress reasons
- domain state
  - domain-specific cached payloads that do not generalize cleanly

The family loops should not keep inventing different top-level memory schemes once this exists.

## What Must Be Generalized

The next convergence stage should generalize these currently valuable patterns:

- transcript-edit focus / blocker / progress architecture where it is truly reusable
- transcript-edit explicit closure posture and HITL lifecycle
- deed/controller refusal-repair and anti-thrash continuity ideas
- artifact-first persistence and refs-not-blobs discipline

The goal is to preserve the strengths from both existing families while relocating them under one shared loop architecture.

## What Must Not Be Flattened

The target is not generic mush.

Do not flatten away:
- transcript-edit closure layer semantics
- transcript-edit decision identity and contradiction fidelity
- deed-to-IR authoring / verification semantics
- domain-specific acceptance thresholds
- domain-specific evidence ordering where it is actually weight-bearing

Shared mechanics should converge.
Domain truth should remain local.

## Main Remaining Delta

The biggest remaining delta is not shell-level unification.

It is that the two families still differ in the unit of orchestration:

- deed-to-IR:
  - primarily "what action next?"
- transcript-edit:
  - primarily "what unresolved focus item matters next, what move should apply, and did it converge?"

The architecture target in this document requires the shared core to converge on the stronger focus/work-state shape while still extracting reusable continuity ideas from both families.

## Migration Posture

This stage should stay contract-first, not patch-first.

The recommended order is:

1. freeze the target agent-kernel direction
2. document the remaining orchestration delta between loop families
3. define orchestration-kernel contracts
4. define shared loop-memory contracts
5. define domain-pack boundaries
6. build the migration roadmap / decisions / delta ledger for this stage
7. only then begin implementation slices

Implementation should remain additive and review-heavy.

## Likely Follow-On Docs

If this seed direction is accepted, the next spine will likely include only the minimum docs needed to keep implementation aligned:

- orchestration-kernel contracts v1
- shared loop-memory model v1
- domain-pack interface v1
- loop-family orchestration delta matrix
- agent-kernel convergence roadmap
- agent-kernel decisions log
- agent-kernel delta ledger

## Decision Rule

When evaluating future changes for this stage, prefer the option that moves the repo toward:

- one shared loop law
- one shared loop-memory law
- one orchestration kernel
- one execution kernel
- domain packs instead of domain-sized controllers

Avoid changes that:

- create another parallel top-level runtime shell
- let domain-specific controller mechanics harden as permanent architecture
- move too much domain truth into the shared core
- over-specify the final generic ledger before shared contracts are proven

## Working Conclusion

Plattera should move toward one `agent kernel architecture` with:

- a retained `execution kernel`
- a new shared `orchestration kernel`
- domain packs layered on top
- a mission/harness shell above that structure

The next stage is not primarily about more shell unification.

It is about making the actual loop mechanics and memory model shared across domains so that future work can operate as one agent architecture rather than multiple adjacent loop species.
