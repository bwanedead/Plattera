# Harness Engineering Ambition & Gap Map

Date: 2026-03-11

## Status

This is a **working ambition document**, not a fixed doctrine.

It exists to:
- capture the strongest harness-engineering ideas currently informing Plattera
- compare those ideas against Plattera's current architecture
- identify the most meaningful gaps between current state and target state
- provide a direction of travel that can evolve as the system matures

This document should be treated as:
- a top-down design aid
- a review lens for future harness changes
- a living reference for iteration priorities

It should **not** be treated as:
- a rigid one-shot migration plan
- proof that current architecture is wrong
- a ban on novel patterns that emerge from Plattera's domain

If Plattera discovers useful patterns that differ from generic agent-harness advice, those patterns should be preserved and documented, not discarded just because they are non-standard.

---

## Why This Exists

Recent public writing on harness engineering converges on a clear idea:

**the model is only one part of an agent system; the harness is the surrounding runtime that makes the model useful, reliable, and inspectable.**

Across the material reviewed, strong harnesses tend to share these traits:
- explicit state outside the model
- crisp tool boundaries
- bounded loops with budgets and stop conditions
- verification before completion
- durable continuity across sessions/context windows
- observability rich enough to understand failures after the fact
- an outer improvement loop driven by traces/evals rather than intuition

Plattera already embodies some of these ideas strongly.

But Plattera is also in a transitional state:
- some harness patterns are mature and disciplined
- some are specialized and domain-strong but not yet generalized
- some capabilities exist platform-wide but are not yet exposed in all relevant loop contexts
- some observability exists in substance without yet being unified under one canonical trace model

This document is intended to make those realities explicit.

---

## Harness North Star

The target standard for Plattera should be:

**artifact-centered, evidence-producing, blocker-aware, verification-gated loops over explicit durable state, with complete run observability and a real outer improvement loop.**

That implies a harness with the following weight-bearing properties.

### 1. One clear control-plane architecture

The system should have a stable reusable harness spine rather than multiple mostly-independent loop personalities.

That spine should define:
- run/session identity
- state ownership
- tool-menu reality
- iteration boundaries
- stop/escalation semantics
- verification gates
- observability contracts

### 2. Explicit durable state outside the model

The model should not be the continuity layer.

Durable state should hold:
- run objective
- current working artifacts
- evidence gathered
- unresolved blockers
- latest accepted conclusions
- verification status
- budgets consumed
- completion / blocked / waiting status

### 3. Tools as bounded capabilities

Tools should be:
- distinct
- typed
- validated locally
- auditable
- exposed per context intentionally

The tool menu should reflect actual runtime reality, not theoretical capability.

### 4. Verification before completion

The harness should not accept "looks done."

Completion should require:
- deterministic closure gates where available
- evidence that required checks were performed
- explicit blocked/waiting states where completion cannot yet be justified

### 5. Blockers as first-class state

Blockers should not only appear as narrative prose.

They should be:
- explicit
- typed
- tied to evidence
- tied to next actions
- tied to escalation conditions

### 6. Continuity across sessions/context windows

The harness should preserve working truth across long runs without relying on raw rolling chat history.

### 7. Full run observability

A mature harness should let operators answer:
- what was the request?
- what state did the run start with?
- what steps were taken?
- what tools were called?
- what evidence was gathered?
- what blockers appeared?
- what verification occurred?
- why did the run stop?
- what final state was reached?

### 8. Outer-loop improvement machinery

The system should support not only running agents, but improving them.

That means:
- normalized traces
- repeatable failure analysis
- benchmark/regression tasks
- reason-code analytics
- loop-family comparison

---

## What Plattera Already Does Well

Plattera is not starting from zero. Several parts of the current architecture are already aligned with strong harness practice.

### Controller / kernel split

The generic agent-loop architecture already has a healthy core split:
- controller proposes
- kernel executes one action
- artifacts and refs are authoritative
- budgets, idempotency, latest refs, and claimability live in deterministic runtime code

This is a strong foundation and should be preserved.

### Refs-not-blobs and artifact truth

Plattera's artifact-first design is a real strength.

Durable refs, persisted artifacts, and explicit latest pointers are exactly the kind of externalized state a serious harness should rely on.

### Tool-menu realism

Plattera already distinguishes:
- the full action universe
- the actions wired in a given runtime context

That is a healthy harness property and avoids a lot of false assumptions.

### Stable reason codes and refusal paths

The system already has meaningful deterministic refusal behavior and stable reason codes.
That is important for both debugging and future eval loops.

### Transcript- and run-level observability

Plattera already has substantial trace-like infrastructure in substance:
- controller transcripts
- kernel step records
- SSE/event-bus progress streams
- latest refs dashboards
- blocker/closure snapshots
- terminal summaries

This is already much stronger than the average ad hoc agent loop.

### Domain-specific closure semantics

The transcript-edit system in particular is strong on:
- explicit blocker identity
- closure requirements
- human-escalation lifecycle
- bounded repair iterations
- evidence-first handling

These are valuable domain-native innovations and should not be flattened into generic mush.

---

## Main Gaps Between Plattera and the Target Harness

These are the most important current deltas.

### Gap 1. Plattera has more than one harness personality

Today Plattera has:
- a relatively clean generic controller/kernel harness
- a more bespoke transcript-edit orchestration harness

They share infrastructure, but they do not yet feel like two domain policies sitting on top of one shared harness spine.

Implication:
- improvements in one family do not automatically strengthen the other
- continuity, blocker handling, and observability concepts are expressed differently across loops

### Gap 2. Long-horizon continuity is not yet unified

The generic controller uses:
- context packets
- run summary logs
- digest memory
- parse-resync paths

The transcript-edit loop uses:
- decision ledger
- blocker registry
- pending prompt state
- resume fields

Both approaches are reasonable, but they are not one canonical continuity model.

Implication:
- cross-loop reasoning about "state of a run" is harder than it should be
- future harness-wide tooling will be harder to build

### Gap 3. Trace observability exists, but not yet as one canonical trace model

Plattera already records a lot.

But it does not yet appear to have one normalized per-run trace object that consistently nests:
- request metadata
- iterations
- tool calls
- model calls
- evidence events
- blocker transitions
- verification steps
- terminal outcome

Implication:
- run debugging is possible
- cross-run analysis is weaker than it should be
- outer-loop harness improvement remains more manual than systematic

### Gap 4. Outer-loop harness improvement is underdeveloped

Plattera has rich observability inputs, but does not yet appear to have a mature harness-improvement loop built on top of them.

Missing or underdeveloped pieces likely include:
- normalized trace review workflows
- failure-pattern mining across many runs
- benchmark task packs for loop families
- regressions tied to reason-code distributions
- side-by-side harness experiments

### Gap 5. Transcript-edit carries too much orchestration gravity

The transcript-edit architecture has improved through module splitting, but it still has two structural hot spots:
- repair-path orchestration remains too heavy
- closure state currently spans both `decision_ledger` and `blocker_registry`

Implication:
- control-plane complexity is higher than ideal
- consistency requires runtime reconciliation work
- future evolution risks adding more policy mass in the wrong place

### Gap 6. Capability exposure is still uneven across loops

Some platform capabilities exist but are not wired into all relevant runtime contexts.

The clearest current example is retrieval in transcript-edit:
- the platform has retrieval capability
- transcript-edit can classify dependency blockers
- transcript-edit does not yet operationalize retrieval as a first-class attempt path in the loop

Implication:
- the harness can sometimes represent a missing move without yet being able to take it

### Gap 7. Completion semantics are not yet unified across loop families

Plattera has strong completion/blocked thinking, but not yet one shared completion ontology across loop families.

The target should be a common harness-level understanding of:
- done
- blocked
- waiting on human
- waiting on evidence
- exhausted

with domain-specific closure checks layered on top.

---

## Working Target Shape

The likely target architecture is not "replace everything with one giant universal loop."

It is:

**one shared harness spine with domain-specific loop policies on top.**

That shared spine should likely include the following.

### Shared harness spine

- canonical run identity and metadata
- canonical trace schema
- canonical iteration/step envelope
- canonical blocker/escalation envelope
- canonical verification event shape
- canonical terminal outcome taxonomy
- shared observability/export surface

### Domain policy layers

- feature-graph / mapping policy
- transcript-edit policy
- future policies for other loop families

Each policy can still define:
- its own tool menu
- its own closure logic
- its own evidence hierarchy
- its own guardrails

But the surrounding runtime should feel structurally consistent.

---

## Working Target Trace Concept For Plattera

If Plattera wants parity with the "trace" concept used in modern harness systems, the practical target is:

### One canonical trace per run

Each run trace should capture:
- run id / session id
- loop family
- request inputs
- starting context summary
- runtime tool menu
- budgets
- every iteration
- every model/tool call
- every refusal
- every blocker transition
- every verification event
- every escalation event
- terminal classification

### Nested child runs / steps

Inside that trace, child records should represent:
- LLM proposal calls
- tool/action executions
- retrieval steps
- evidence checks
- verification passes
- HITL events

### Searchable fields

The trace model should support analysis by:
- reason code
- blocker type
- action type
- loop family
- terminal classification
- iteration count
- verification presence/absence
- human-escalation state

This does not require LangSmith specifically.
It does require a coherent internal trace model.

---

## Recommended Architectural Direction

The current highest-value direction appears to be:

### 1. Preserve the good kernel/controller foundation

Do not throw away:
- one-step kernel execution
- artifact truth
- idempotency
- bounded tool proposals
- deterministic refusal semantics

These are foundational strengths.

### 2. Generalize the harness spine, not the domain logic

Do not try to prematurely erase domain distinctions.

Instead:
- standardize the harness envelope
- preserve domain-specific policy where it is weight-bearing

### 3. Normalize run observability into a real trace system

Plattera likely already has most of the raw ingredients.

The missing step is to normalize them into one coherent run-trace model and make cross-run analysis first-class.

### 4. Reduce duplicate authority in transcript-edit

The transcript-edit loop should likely move toward:
- one canonical closure-state owner
- one thinner blocker view / lifecycle layer
- less orchestration mass in repair-runtime glue

### 5. Close the gap between represented capabilities and executable capabilities

If a loop can represent a blocker class that should be machine-attempted before HITL, the tool menu and iteration policy should eventually reflect that.

### 6. Build an outer-loop harness improvement workflow

This should become an explicit system goal, not an occasional manual exercise.

Practical examples:
- review top failed traces by loop family
- cluster failures by reason-code pattern
- compare successful vs failed traces for the same task type
- track premature-stop rates
- track verification-missing rates
- track repeated-action / churn patterns

---

## Suggested Near-Term Ambitions

These are ambitions, not commitments.

### Ambition A. Define a canonical run-trace schema

Create a Plattera-native trace contract that all loop families can emit into, even if only partially at first.

### Ambition B. Define a shared terminal taxonomy

Clarify harness-level terminal states that all loop families map into.

### Ambition C. Clarify canonical state ownership in transcript-edit

Decide what is the true owner of unresolved closure state and what is merely a projection/view.

### Ambition D. Standardize continuity concepts across loop families

Move toward one shared vocabulary for:
- working memory
- resumable state
- blocker state
- recent evidence
- verification state

### Ambition E. Stand up an outer-loop review ritual

Even before building sophisticated tooling, adopt a disciplined review loop over recent runs and their failure patterns.

---

## Open Design Questions

These questions are intentionally left open.

### 1. What should be canonical state across all loop families?

Not every loop needs the same state fields.
But there should likely be a shared minimum envelope.

### 2. How much of transcript-edit should become general harness infrastructure?

Some of its ideas are generic and valuable.
Some are domain-specific and should remain specialized.

### 3. Should Plattera converge on one loop engine or one loop framework?

Those are not the same.

One engine implies more behavioral uniformity.
One framework implies shared harness rails with more policy freedom.

### 4. What novel patterns should Plattera preserve?

Plattera already has niche strengths, especially in:
- blocker-native operation
- closure semantics
- artifact truth
- operator-visible phase/event reporting

Those may become contributions to a stronger harness design rather than temporary quirks.

---

## Working Conclusion

Plattera is already beyond the "prompt plus tools" stage.

It has many hallmarks of a serious harness:
- explicit deterministic runtime layers
- real artifact truth
- bounded tool contracts
- structured refusal paths
- blocker-aware orchestration
- substantial run observability

The next step is not merely fixing broken runs.

The next step is maturing from:
- strong loop implementations

into:
- a clearer, more unified harness architecture

with:
- one shared harness spine
- one clearer trace model
- one more systematic outer improvement loop
- less duplicated authority in specialized orchestration layers

That should remain a working ambition rather than a rigid doctrine.

The right standard is:

**be structurally ambitious, evidence-driven, and willing to revise the design as real loop behavior teaches us more.**
