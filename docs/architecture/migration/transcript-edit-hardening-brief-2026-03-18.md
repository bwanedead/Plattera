# Transcript-Edit Hardening Brief

Date: 2026-03-18
Status: Planning brief - parent artifact for implementation work
Primary references:
- `docs/agent-testing/transcript-edit-loop-holistic-intent.md`
- `docs/transcript-edit-loop-orchestration.md`
- `docs/transcript-edit-loop-focus-cycle-architecture-2026-03-05.md`
- `docs/architecture/harness/transcript-edit-state-authority.md`
- `docs/architecture/migration/transcript-extraction-plan.md`

## Purpose

Define the canonical hardening brief for the transcript-edit loop before additional implementation work proceeds.

This document is the parent planning artifact for the next hardening phase. It is intended to anchor downstream implementation and any narrower follow-on specs so they do not drift into parallel philosophies.

This brief does not redesign transcript-edit from scratch. The loop already contains many of the right primitives. The hardening goal is to make those primitives cohere so the runtime naturally behaves like a disciplined accumulating investigator rather than a reactive text fixer.

## Problem Statement

The current transcript-edit loop is no longer missing vocabulary. It already has many of the concepts needed for sane behavior:
- decision-ledger-driven closure truth
- blocker registry lifecycle
- focus packets
- investigation brief support
- emergent blocker creation
- HITL lifecycle handling
- event/reporting surfaces

The remaining risk is architectural incoherence rather than concept absence.

A loop can support orientation, investigation, planning, verification, blocker promotion, and HITL and still behave badly if:
- state ownership is blurry
- promotion rules are implicit
- selection pressure favors the wrong next move under uncertainty
- prompting over-carries doctrine that should live in architecture
- runtime rails quietly become a hidden flowchart
- observability cannot explain why the run behaved as it did

The next hardening phase therefore targets:
- doctrine
- state ownership
- promotion rules
- selection pressure
- runtime rails
- observability
- doctrine-oriented testing

## Core Design Rule

Behavior should emerge from doctrine + state + incentives + rails, not from hardcoded step scripts.

This is a first-class design constraint.

The hardening effort must not solve transcript-edit by hiding a brittle authored choreography behind prompts or runtime glue.

We do want:
- strong doctrine
- explicit state ownership
- disciplined promotion rules
- selector incentives that favor the right kind of work under weak understanding
- runtime rails that validate and reject unsound moves
- observability rich enough to explain the emergent path

We do not want:
- hidden scripted choreography
- rigid "first A then B then C" loop law
- runtime code that becomes the real investigator
- prompts that act like a checklist instead of transmitting posture and priorities
- support surfaces quietly becoming canonical truth

## What The Loop Should Be

Transcript-edit should behave like an accumulating case investigation.

Its job is not merely to clean text. Its job is to move from deed evidence and T0 drafts toward mapping-ready truth in a sane, evidence-driven, additive way.

That means the loop should:
- orient to the case before premature repair pressure
- build a mapping-critical inventory of what is known, uncertain, contradictory, missing, and non-blocking
- promote materially relevant unresolved issues into explicit focus or blocker state
- attempt autonomous closure using available evidence and tools
- preserve unresolved truth honestly when ambiguity remains
- escalate only after disciplined narrowing and local exhaustion
- leave each iteration with a richer case model or a smaller real blocker set than before

The loop should not behave like a chain of isolated repair attempts that rediscover the same world each iteration.

## Generic Harness Doctrine vs Transcript-Edit Domain Policy

These must remain distinct.

### Generic harness doctrine

Generic harness doctrine includes:
- accumulating investigation
- bounded planning
- durable vs mutable vs immediate state separation
- disciplined promotion rules
- materiality-aware escalation
- honest unresolved truth
- valid-progress law
- anti-hard-scripting rule
- observability as a step story

This doctrine should be portable in principle, but it should not be abstracted broadly until transcript-edit proves it in practice.

### Transcript-edit domain policy

Transcript-edit domain policy includes:
- mapping-critical inventory expectations
- the four closure layers
- deed-specific blocker categories
- transcript contradiction handling
- image evidence and verification conventions
- dependency classification for downstream mapping
- mapping impact classification

These are domain-pack concerns, not generic harness law.

## Domain Success Frame: Four Layers Of Closure

Transcript-edit continues to use the four closure layers as its domain success frame.

### Layer 1: Canonical recovery

Does the working transcript match the canonical source deed content?

### Layer 2: Canonical sanity

If the deed itself contains contradictions or inconsistencies, does the loop preserve that reality rather than pretending the source is clean?

### Layer 3: Dependency completeness

Does the loop detect when external references or additional context are required for mapping?

### Layer 4: Mapping impact

Does the loop distinguish between unresolved issues that block mapping and those that are only transcript-quality imperfections?

These layers are domain policy and should remain transcript-edit-specific until a broader shared closure model is warranted.

## Anti-Script Rule

The loop must not be hardened by encoding a hidden authored checklist.

### Good doctrine transmission

Prompting and local move framing should teach:
- orient before escalating when case understanding is weak
- prefer verification over guessing
- investigation and planning can be legitimate work when bounded and relevant
- repeated rediscovery without advancement is a defect
- unresolved truth should be preserved honestly

### Bad doctrine transmission

Prompting and runtime logic should not teach or enforce:
- fixed step orderings presented as universal law
- mandatory investigation rituals even when the case is already narrow
- mandatory escalation after a flat attempt count regardless of case state
- decorative planning that is disconnected from next-action choice

### Good selector behavior

Selector logic should be preference-based and state-aware.

It should favor:
- orientation
- inventory-building
- verification
- dependency naming and classification
- bounded planning

when the case model is weak.

It should favor:
- direct repair
- contradiction preservation
- classification refinement
- bounded escalation

when the case model is already narrow and the unresolved issue is materially defined.

### Good runtime rails

Runtime rails should:
- validate
- persist
- gate
- bound
- reject unsound moves
- detect repeated no-signal loops

Runtime rails should not secretly author the full investigation path.

## State Ownership Model

Transcript-edit should explicitly distinguish three state layers.

### 1. Durable official state

Purpose:
- canonical run truth
- authoritative state for durable closure and lifecycle claims

Examples:
- decision ledger
- blocker registry
- official ticket / escalation lifecycle state
- handoff truth
- terminal truth

Current primary code surfaces:
- `backend/agents/transcript_edit/decision_ledger.py`
- `backend/agents/transcript_edit/blocker_registry.py`
- `backend/agents/transcript_edit/terminalization.py`

Rules:
- durable state is authoritative
- durable state should not contain every provisional thought
- durable state should be the source for closure, lifecycle, and terminal claims

### 2. Mutable support state

Purpose:
- cognitive support for additive understanding
- revisable working organization
- compact continuity that helps later iterations stand on earlier ones

Examples:
- investigation brief
- working case notebook
- mutable plan
- knowns/open questions/recent attempts/likely next move

Current primary code surfaces:
- `backend/agents/transcript_edit/focus_packet.py`
- `backend/agents/transcript_edit/loop_state.py`
- planning and prompting surfaces that shape working context

Rules:
- support state is editable and revisable
- support state is not canonical truth
- support state should stay concise and high-signal
- support state must not silently become a second ledger

### 3. Immediate execution state

Purpose:
- bounded local context for the current move
- current-step guidance, not long-term memory

Examples:
- focus packet
- current move framing
- bounded evidence bundle
- current focus-target context

Current primary code surfaces:
- `backend/agents/transcript_edit/focus_packet.py`
- resolver/planner prompt payload construction
- iteration runtime glue

Rules:
- execution state should be narrow and action-shaped
- execution state should not try to serve as full run memory
- execution state should be reconstructible from durable/support surfaces where possible

## Promotion Principle

Not every useful thought should become durable truth.

The architecture should define clear promotion paths:
- note -> support-state observation
- focus item -> explicit bounded work candidate
- blocker -> durable unresolved material issue
- official truth -> canonical classified run state or final promoted outcome

Illustrative examples:
- a loose suspicion stays in the investigation brief
- a repeated or material unresolved issue becomes a focus item
- a mapping-relevant unresolved issue becomes a blocker
- a resolved durable classification belongs in the ledger or terminal truth

Promotion should be governed by:
- materiality
- persistence across iterations
- mapping impact
- evidence sufficiency
- scope relevance
- local exhaustion when escalation is considered

Demotion and reclassification must also be allowed:
- blocker -> non-blocking item
- focus item -> provisional note
- disputed item -> resolved no-edit classification
- stale ticket -> superseded lifecycle state

## Valid Progress Principle

Each major step should either:
- increase structured understanding of the case, or
- reduce a materially relevant blocker

If it does neither, it is likely not a sane step.

Direct text edits are not the only valid progress.

Understanding-building can be valid progress when case understanding is weak. This includes:
- orientation
- inventory construction
- contradiction classification
- image verification
- dependency naming
- mapping-impact assessment
- bounded planning

This principle should shape selector policy, runtime gating, and test assertions.

## Main Anti-Patterns

The hardening effort should explicitly guard against:
- premature HITL, especially on iteration 1 without clear exceptional justification
- repeated rediscovery without state advancement
- direct repair under weak case understanding
- support-state sprawl becoming a shadow ledger
- runtime-authored hidden choreography
- decorative planning with no operational effect
- evidence gathering that produces no new signal and is still repeatedly selected
- terminal claims that are not clearly grounded in durable state

## Selection Pressure And Next-Move Law

Selection pressure is the behavioral heart of the hardening effort.

The problem is not whether the loop can orient, investigate, verify, plan, repair, escalate, or classify. The problem is whether it selects the right kind of work at the right level of understanding.

### When understanding is weak

Prefer:
- orientation
- mapping-critical inventory
- contradiction surfacing
- image verification
- dependency classification
- bounded planning

Strongly disfavor:
- immediate repair
- generic escalation
- repeated broad re-audits with no new signal

### When understanding is moderate but unresolved

Prefer:
- targeted verification
- blocker clarification
- focused repair if safe
- reclassification of mapping impact
- precise escalation only if local narrowing is exhausted

### When understanding is strong and the blocker is narrow

Prefer:
- direct repair
- explicit blocker resolution
- precise HITL request
- terminal classification or promotion when closure is honestly achieved

### Selector-law requirement

This law should be expressed as preference surfaces and acceptance criteria, not as a hidden flowchart.

Current likely touchpoints:
- focus ranking and fallback selection logic behind `decision_ledger.py`
- blocker prioritization and active selection logic behind `blocker_registry.py`
- prompt surfaces in `backend/agents/transcript_edit/prompting.py`
- focus packet shaping in `backend/agents/transcript_edit/focus_packet.py`

## Planning And Investigation As Support Surfaces

Planning and investigation are valid support surfaces, but neither is a substitute for action or truth ownership.

### Investigation brief

Purpose:
- descriptive sticky note for accumulated case understanding

Likely contents:
- current knowns
- open questions
- recent attempts
- uncertainty hotspots
- likely next sensible move

The investigation brief should remain:
- concise
- editable
- non-canonical

### Plan

Purpose:
- bounded near-term working rail

Likely contents:
- intended next step or next short sequence
- sequencing assumptions
- what would force replanning
- why the current move ordering is sane

The plan should remain:
- case-specific
- directly useful
- revisable
- subordinate to durable truth and runtime rails

Current likely touchpoints:
- `backend/agents/transcript_edit/planner.py`
- `backend/agents/transcript_edit/prompting.py`
- any working-plan content carried via focus packets or prompt payloads

## Escalation Doctrine

HITL should be treated as the result of disciplined narrowing, not generic help-seeking.

Escalation is appropriate only when all of the following are true:
- the loop has oriented enough to understand the case shape
- the unresolved item has been made explicit as a blocker or dependency
- autonomous evidence-gathering has been attempted or ruled out
- the unresolved issue remains materially relevant to mapping closure
- the request is bounded enough to unlock the next state transition directly

Premature escalation should be treated as a defect signal, not as acceptable loop personality.

Current likely touchpoints:
- blocker lifecycle and ticket pairing in `backend/agents/transcript_edit/blocker_registry.py`
- feedback lifecycle and ticket handling modules
- move selection prompt doctrine in `backend/agents/transcript_edit/prompting.py`

## Runtime Rails

Runtime rails should enforce discipline without becoming hidden choreography.

The runtime should own:
- move boundedness
- focus coherence
- repeat-budget limits
- escalation eligibility
- safe apply gates
- blocker-ticket lifecycle integrity
- no-progress detection
- persistence discipline

The runtime should not own:
- authored investigation sequencing
- domain-specific judgment that belongs in the resolver/domain pack
- decorative "plan first" or "investigate first" rituals divorced from state

Current likely touchpoints:
- iteration runtime and repair-path glue
- resolver gating modules
- loop-state runtime fields in `backend/agents/transcript_edit/loop_state.py`

## Observability Contract

Observability is part of correctness.

For each major step, the architecture should support emitting or reconstructing:
- what step happened
- why it happened now
- what evidence or state triggered it
- what changed
- why the next step followed

The goal is a legible step story, not only a log of raw actions.

At minimum, major-step observability should make visible:
- local objective
- triggering condition or evidence
- state delta
- outcome class
- next-step rationale

Current primary touchpoints:
- `backend/agents/transcript_edit/run_reporting.py`
- step emitters across controller and iteration runtime modules
- terminal summaries and closure history surfaces

Important defect signals:
- acting without a visible reason
- inability to reconstruct state progression
- escalation without visible local exhaustion
- repeated rediscovery with no advancement
- steps that do not appear to improve understanding or closure

## Doctrine-Oriented Testing

The hardening phase should add doctrine-oriented tests rather than only schema-oriented tests.

These tests should assert behavior such as:
- no premature HITL under weak initial understanding
- visible state advancement across iterations
- no repeated rediscovery without change
- support for emergent focus creation
- planning/investigation counted as valid progress when appropriate
- honest unresolved blocker preservation
- sane mapping-blocking vs transcript-quality distinction
- intelligible step-story observability

Test work should likely touch:
- transcript-edit unit tests near the owning modules
- scenario-style tests for iteration behavior
- observability payload tests for `run_reporting.py`

## Concrete Workstreams

### Workstream 1: Parent doctrine and ownership brief

Goal:
- freeze the behavioral law for this hardening phase

This brief is that artifact.

Follow-on specs derived from it should remain subordinate to it.

### Workstream 2: State ownership and promotion spec

Goal:
- define exactly what belongs in durable official state, mutable support state, and immediate execution state
- define promotion and reclassification rules

Primary existing module anchors:
- `backend/agents/transcript_edit/decision_ledger.py`
- `backend/agents/transcript_edit/blocker_registry.py`
- `backend/agents/transcript_edit/loop_state.py`
- `backend/agents/transcript_edit/focus_packet.py`

Not changing yet:
- broader shared harness state-envelope contracts
- domain-pack extraction boundaries already defined elsewhere

### Workstream 3: Selector and escalation policy

Goal:
- make next-move pressure explicitly favor sane understanding-building under weak case models
- make premature escalation and repeated rediscovery structurally disfavored

Primary existing module anchors:
- focus ranking and selection helpers behind `decision_ledger.py`
- blocker selection helpers behind `blocker_registry.py`
- planner/resolver doctrine surfaces in `backend/agents/transcript_edit/prompting.py`
- planner support in `backend/agents/transcript_edit/planner.py`

Not changing yet:
- broader multi-loop selector generalization
- deed-to-IR migration behavior

### Workstream 4: Runtime-rails refinement

Goal:
- ensure runtime enforces boundedness and coherence without becoming a hidden flowchart

Primary existing module anchors:
- repair/iteration runtime modules
- resolver gating modules
- `backend/agents/transcript_edit/loop_state.py`

Not changing yet:
- the broader mission-runtime phase grammar
- shared orchestration-kernel extraction plan

### Workstream 5: Observability contract

Goal:
- make the run reconstructible as step -> why -> state delta -> next step

Primary existing module anchors:
- `backend/agents/transcript_edit/run_reporting.py`
- emitter call sites across controller and iteration runtime
- terminal summary surfaces

Not changing yet:
- global trace schema outside transcript-edit unless a clear compatibility gap forces it

### Workstream 6: Doctrine-oriented test hardening

Goal:
- prove the loop behaves according to the doctrine rather than only passing schema checks

Primary existing module anchors:
- transcript-edit tests adjacent to the owning modules
- scenario tests for iteration behavior
- observability tests

Not changing yet:
- global benchmark programs
- cross-model performance comparisons

## Execution Order

Recommended implementation order:

1. Freeze this parent brief.
2. Draft the state ownership and promotion spec from it.
3. Draft the selector/escalation policy from it.
4. Draft the observability contract from it.
5. Map those specs onto concrete transcript-edit modules before code changes.
6. Implement state and selector changes first.
7. Implement observability changes alongside behavior changes so review remains possible.
8. Harden tests after the first implementation pass and again after review.

Prompt changes should be treated as doctrine-transmission work inside selector/runtime implementation, not as a standalone architecture layer.

## Non-Goals

This hardening phase is not trying to:
- build a hidden deterministic flowchart
- define a universal transcript-edit sequence
- overfit to one practice deed
- abstract the whole harness before transcript-edit proves the pattern
- turn support artifacts into canonical truth
- optimize raw speed ahead of behavioral sanity
- change the already-documented broader harness convergence roadmap

## Definition Of Done

This hardening phase is complete when transcript-edit demonstrates that:
- the loop behaves like an accumulating investigator rather than a reactive fixer
- behavior is shaped without hidden scripted choreography
- state surfaces are clearly owned and promotion paths are coherent
- selector pressure favors sane understanding-building under uncertainty
- escalation is disciplined and materiality-aware
- runtime rails enforce discipline without authorship drift
- observability can tell the run as a legible step story
- doctrine-oriented tests prove the behavior strongly enough to justify later broader abstraction

## Final Principle

The goal is not to make the loop rigid.

The goal is to make it sane.

Good behavior should emerge from:
- doctrine
- state continuity
- selector incentives
- runtime rails
- observability

and not from brittle authored scripts hiding behind the prompt or the controller.
