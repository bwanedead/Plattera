# Mission Runtime Contracts v1

Date: 2026-03-12  
Status: Contract freeze for next implementation phase (docs only)  
Primary references:
- `docs/architecture/migration/unified-mission-runtime-plan-2026-03-12.md`
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/migration/harness-convergence-roadmap.md`

## Purpose

Lock boundary contracts for a unified mission runtime before runtime implementation starts, so mode integration does not invent interfaces ad hoc.

This document defines minimum ownership and contract expectations only. It is not a method-signature spec.

## Core Four-Layer Split

Unified mission runtime work is structured as four layers:
- `MissionRuntime`: mission lifecycle orchestration and continuity.
- Execution kernel: deterministic execution mechanics (`KernelSessionManager` lineage).
- `RuntimeCapability`: reusable cross-mode orchestration mechanics invoked by `MissionRuntime`.
- `ModePolicy`: domain-local interpretation, acceptance, and transition recommendation logic.

Record-contract note:
- `MissionLedger` and `ModeTransition` are runtime-owned record contracts used by these layers.
- They are not additional top-level runtime layers or independent orchestration components.

Boundary rule:
- `MissionRuntime` orchestrates.
- Kernel executes.
- Capabilities provide reusable mechanics.
- Policies decide domain truth.

## v1 Transition Rule

v1 mode switching is linear, synchronous, and in-place:
- one mission keeps one mission identity
- one mission keeps one continuity chain
- transitions are explicit and ordered
- child subruns are deferred

## Contract 1: `MissionRuntime`

### Owns
- mission lifecycle
- active mode
- iteration sequencing
- terminal handling
- mission-level continuity
- mode switching application
- mission-level trace segment structure

### Does not own
- domain truth
- domain-specific blocker semantics
- domain-specific closure semantics
- tool implementation logic

### Inputs
- mission start context (identity, objective/request metadata, initial mode)
- current mission ledger snapshot
- current mode policy outputs (interpretation + recommendations)
- runtime capability results
- kernel execution observations/results

### Outputs and responsibilities
- mission-level orchestration events and ordered trace segments
- validated mode transition application or rejection
- mission-ledger updates (bounded, append/projection safe)
- terminal classification routing through shared taxonomy surfaces
- resumable mission continuity summary

### Relationship to kernel and policies
- uses execution kernel for deterministic execution mechanics
- calls mode policy for domain-local interpretation and recommendations
- calls runtime capabilities for reusable mechanics
- validates and applies transition recommendations; policies do not self-switch mode

## Contract 2: `ModePolicy`

### Owns
- domain context assembly
- domain interpretation of observations and evidence
- domain completion and transition recommendations
- domain-local acceptance/verification rules
- mode-local blocker interpretation

### Does not own
- generic mission orchestration mechanics
- kernel execution mechanics
- hidden runtime execution layers
- mode-switch authority application

### Interaction with runtime capabilities
- may request capability usage through runtime-facing intents
- consumes capability outputs as domain evidence/context
- remains the owner of domain meaning and domain acceptance decisions

### Returns to runtime
- mode interpretation summary
- recommended next-step intent envelope
- completion recommendation (with reason context)
- transition recommendation (if any)
- mode-local verification/blocker posture summary

Constraint:
- `ModePolicy` must not become the old controller packed into one interface.

## Contract 3: `RuntimeCapability`

### Role
Reusable runtime behaviors callable by `MissionRuntime` across modes.

### Ownership boundary
- owns reusable mechanics
- does not own domain truth
- does not own generic mission lifecycle orchestration

### Distinction from `ModePolicy`
- capability: "how reusable mechanics are performed"
- policy: "what domain meaning and acceptance decisions are"

### v1 capability set (conceptual)
- startup/orient capability
- blocker handling capability
- evidence/verification capability
- HITL capability
- no-progress/rethink capability

Guardrail:
- capabilities must not collapse into a god-utility layer.
- capabilities are allowed only when reused across multiple modes and not already owned by policy decisions or runtime authority flow.

## Concern Ownership Matrix (v1)

| Concern | Mechanics owner | Decision owner | Authority/persistence owner |
| --- | --- | --- | --- |
| Blockers | `RuntimeCapability` may run reusable blocker mechanics (capture/update flow mechanics) | `ModePolicy` interprets blocker meaning and recommends blocker-driven actions/transitions | `MissionRuntime` persists mission-level posture in `MissionLedger`; mode-local authoritative blocker truth stays mode-local |
| Verification | `RuntimeCapability` may run reusable evidence/verification mechanics | `ModePolicy` decides acceptance/completion significance of verification outputs | `MissionRuntime` persists mission-level verification posture summary in `MissionLedger`; detailed verification truth stays mode-local |
| Mode transition | `MissionRuntime` runs transition mechanics (validation/apply/record) | `ModePolicy` may recommend transition | `MissionRuntime` is sole authority to accept/reject/apply and persist `ModeTransition` records |

## Contract 4: `MissionLedger`

### Purpose
Bounded persisted mission continuity state for one mission identity across mode switches.

### Must include (minimum)
- mission identity
- active mode
- mode history
- transition records
- high-signal artifact refs
- resumability summary
- high-signal mission status
- blocker posture summary (bounded, mission-level)
- verification posture summary (bounded, mission-level)

### Must stay out of scope
- full transcript-edit ledger or blocker registry internals
- full controller local memory
- duplicated mode-local authoritative state
- arbitrary runtime caches
- detailed blocker lifecycle rows
- detailed verification event history (trace owns event history)

Rule:
- `MissionLedger` is a mission-level continuity envelope, not a universal state sink.
- `MissionLedger` should only persist the allowed mission-level fields above.

## Contract 5: `ModeTransition`

`ModeTransition` is a strict record written as part of one continuous mission trace.

### Required conceptual fields
- prior mode
- next mode
- reason for switch
- handed-forward artifacts/refs
- expected next work in receiving mode
- resume note for prior mode
- transition status/result
- timestamp/ordering anchor

### Authority and flow
- agent/policy may recommend transition
- `MissionRuntime` validates and applies (or rejects) transition
- transition is persisted and reviewable in mission trace continuity

## Guardrails and Failure Modes

Prevent these failure modes during implementation:
- overfat `ModePolicy` that recreates family-specific controllers
- oversized `MissionLedger` that duplicates mode authorities
- ad hoc transition payloads without strict `ModeTransition` record shape
- generic runtime/capabilities absorbing domain truth

## Relationship to Current Runtime Families

- Deed-to-IR controller/kernel family is the closest starting runtime shell for `MissionRuntime` extraction.
- Transcript-edit family contributes reusable orchestration patterns and rich domain policy content.
- Both families converge into mode packs over one shared mission runtime, not separate forever-runtimes.

## Implementation Posture Locked by This Contract

- contract-first before runtime wiring expansion
- additive migration over current kernel/runtime anchors
- preserve domain truth in mode policies while converging orchestration and continuity in mission runtime
