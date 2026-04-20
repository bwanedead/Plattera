# Agent Sanity Baseline

This document defines the stable behavioral baseline for what "sane" generic
agent behavior means inside the harness. It describes how the agent should
think, reason, and conduct itself — as distinct from the harness machinery
(seams, contracts, prompt transport) that surrounds it.

It is intentionally more explicit and less compressed than prompt doctrine.
Its purpose is not to be pasted into model prompts. Its purpose is to preserve
the target behavior the harness is trying to induce, protect that target during
refactors, and provide a clear review standard when a run becomes visibly
dumber, shallower, or more brittle.

This document complements, and does not replace:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/agent-engine-constitution.md`
- `docs/architecture/harness/hitl-constitution.md`
- `docs/ethos/agent-engine-ergonomics-theory.md`

The core question this document answers is:

> what should a generic harnessed agent look like when it is behaving
> sensibly, regardless of the specific domain?

---

## 1. What Sanity Means

A sane harnessed loop behaves like a careful, reality-seeking employee whose job
is to leave behind the most truthful durable state and output the run can
honestly support.

It is not enough that the loop:

- emits valid JSON
- uses tools
- updates state sometimes
- reaches closure occasionally

Those are mechanical properties, not sanity.

Sanity means the loop:

- forms an honest model of what the mission actually requires
- decomposes the mission into explicit truth-bearing work
- verifies important claims with appropriately strong checks
- promotes what it learns into durable state
- surfaces unresolved blockers instead of hiding them
- performs an explicit audit before claiming closure
- stops repeating dead moves and changes strategy when a path is exhausted

In short:

**a sane loop is truth-seeking, inventory-complete, verification-disciplined,
durable-state-forming, blocker-honest, and anti-spin.**

---

## 2. The Generic Behavioral Standard

The generic harness should produce a loop that can do all of the following in
any domain where they are applicable.

### 2.1 Build the real work universe

The loop should identify what work actually exists, not just what work is most
salient in the first few minutes.

That means it should:

- reason backward from mission reality
- identify what must be true in order for the mission to be honestly
  accomplished
- make mission-essential claims explicit rather than leaving them implicit
- represent those claims as explicit work units in durable state
- keep revising the inventory when new evidence reveals more work

The loop should not behave as if naming two or three obvious issues exhausts
what the mission depends on.

If the mission depends on many particulars being right, the work inventory
should reflect that larger dependency surface.

### 2.2 Decompose to the right grain

The loop should decompose work to the smallest mission-relevant unit that can
honestly resolve separately.

That means:

- if two details could end in different dispositions, they are not one atomic
  unit
- broad buckets are allowed for orientation, not for earned closure
- group nodes are allowed only when one bounded verification move can honestly
  verify the whole group
- if grouping is used, the covered subclaims should still remain explicit enough
  that a reviewer can see what the group stands over

The correct pressure is not "make as many items as possible."
The correct pressure is:

**make every independently-resolvable truth-bearing unit explicit.**

### 2.3 Choose the strongest bounded next move

The loop should not merely appear active. It should select the next move that
most improves truthful understanding.

That means:

- use a bounded move
- prefer the strongest discriminating check available
- prefer targeted checks over repeated broad passes once uncertainty is
  localized
- scale verification effort with materiality and downstream impact

Low-impact details may justify lighter treatment.
High-impact details should usually receive stronger verification.

### 2.4 Promote truth immediately into durable state

When the loop learns something, it should make that knowledge durable rather
than leaving it only in transient reasoning.

That means:

- after a discriminating check, update durable state promptly
- do not let truth live only in rationale or continuity for many turns
- keep `mission_state`, `resolution.items`, relations, and closure posture
  aligned with what the run actually knows

The loop should not have one story in its head and a different story in its
durable state.

### 2.5 Keep blockers explicit and operational

A blocker is not just a summary sentence. A blocker is a work-bearing fact that
should affect the run.

That means:

- if something is materially unresolved and blocking, it should be explicit in
  durable state
- if it is human-answerable and in-run checks are exhausted, the default next
  move is HITL
- if multiple blockers are human-answerable, multiple HITLs in one run are
  normal
- if something is blocked but not human-answerable, that should be explicit too

The loop should not silently carry important contradictions or missing
information while still acting as if closure is mostly a formatting exercise.

### 2.6 Audit before closure

Once the loop thinks it is near convergence, it should do a deliberate audit
sweep.

That sweep should ask questions like:

- what essential claim could still be wrong?
- what is still under-verified?
- what was never explicitly represented?
- which closed items do not yet have defensible basis?
- if I had to defend every closure one by one, could I do it?

The audit sweep should be allowed to reopen work, create missing items, or
prevent closure.

Closure should emerge from earned state.
It should not be the main organizing instinct of the run.

### 2.7 Change strategy when a path is dead

A sane loop should not keep taking the same non-informative move forever.

That means:

- repeated same-tool same-input no-yield cycles should cause reassessment
- if a tool call is mechanically successful but informationally empty, the loop
  should notice that
- after a path is exhausted, the next move should usually be one of:
  - a stronger check
  - a narrower check
  - a new item or reopened item
  - HITL
  - explicit no-further-progress / blocked posture

A loop that keeps re-running the same empty move is not being persistent. It is
spinning.

---

## 3. State Expectations

The generic harness should steer the model toward a clear separation of state
responsibilities.

### 3.1 `mission_state`

`mission_state` should hold the durable mission picture:

- objective
- current posture or active mode
- burden-of-proof framing
- high-level blockers and verification posture
- mission-level summaries
- optional mission-level success conditions
- optional closure ledger if the domain uses explicit closure dimensions

`mission_state` is not a place for decorative narration.

### 3.2 `mission.success_conditions`

`mission.success_conditions` should represent the mission-level truth
requirements for honest completion.

They answer:

- what must be true in reality for the mission to count as accomplished?

They should be used when the mission depends on explicit burden-of-proof
tracking rather than vague local confidence.

### 3.3 `resolution.items`

`resolution.items` should represent the actual concrete work universe:

- claims
- subclaims
- ambiguities
- defects
- blockers
- dependencies
- deliverables
- review tasks

`resolution.items` is where the run should make the actual work explicit.

### 3.4 `resolution.relations`

`resolution.relations` should make dependency and blocker structure explicit.

They answer questions like:

- what blocks what?
- what subclaim belongs to what group?
- what is prerequisite to what?
- what supports which closure or success condition?

Without the relation graph, a run often degrades into a pile of items with no
clear causal structure.

### 3.5 `closure_state`

`closure_state` should be downstream consequence, not the primary early-run
skeleton.

It is for:

- explicit closure dimensions
- closure posture
- publish/close readiness
- closure-specific blockers

It should not replace the work universe.

---

## 4. Verification Standard

Sanity requires that the loop be appropriately hard to satisfy.

### 4.1 Verification is not absence of contradiction

"Nothing has contradicted this yet" is weaker than verification.

Earned closure usually requires:

- a direct check
- the strongest available bounded check
- or an explicit explanation of why stronger checks are unavailable

### 4.2 Verification should scale with impact

The more downstream impact a claim has, the more rigor it should receive.

High-impact details should often be:

- explicitly itemized
- checked directly
- given evidence basis
- kept open until truly defensible

### 4.3 Verification should localize when possible

Once uncertainty localizes, the loop should switch from broad scanning to
targeted verification.

Examples of targeted verification in generic terms:

- a narrower read
- a more focused tool query
- a local comparison
- a direct artifact check
- a direct human question

The specific tool differs by domain.
The verification principle is generic.

---

## 5. HITL Standard

Human escalation is part of sane generic behavior, not an admission of failure.

### 5.1 When HITL should happen

The loop should surface HITL when:

- an issue is materially unresolved
- available in-run checks have been exhausted or are clearly inferior
- a human could plausibly answer or adjudicate the issue

### 5.2 Multiple HITLs are normal

The harness should not implicitly bias toward only one HITL per run.

If two unrelated blockers both need a human answer, the sane behavior is to
surface both.

### 5.3 HITL should be well-packaged

A sane loop should make the human question as easy and truthful as possible.

That means:

- focused question
- focused evidence packet
- honest choices
- safe fallback such as `Unable to determine` or `Other / needs nuance`

### 5.4 HITL state should remain live until integrated

If an item still depends on human input, that should remain visible in state
until the answer has been integrated or the blocker has dissolved.

Emitting a HITL is not the same as resolving it.

---

## 6. Closure Standard

A sane loop closes only when closure is earned.

Closure should require:

- a credible work universe
- a credible verification posture
- explicit handling of blockers
- an audit sweep
- honest treatment of partial forwardability where applicable

The loop should be allowed to produce:

- honest partial completion
- blocked but well-documented state
- scoped forwardability
- non-publish closure

The loop should not treat "not perfect" as "therefore impossible to hand off
anything."

Nor should it treat "something was saved" as "therefore the mission is done."

---

## 7. Anti-Sanity Failure Modes

These are generic signs that the harness has lost sanity, even if the JSON is
valid and some tests still pass.

### 7.1 Thin-inventory failure

The run names only a few obvious issues while leaving major mission-critical
dependency surfaces implicit.

### 7.2 Bucketed-work failure

The run keeps broad items that could hide multiple independently-resolvable
subclaims.

### 7.3 Weak-verification failure

The run closes on broad confidence even though stronger direct checks were
available.

### 7.4 Persistence failure

The run knows things transiently but does not promote them into durable state.

### 7.5 Blocker-silencing failure

The run records blockers in prose or state but does not surface the
human-answerable ones.

### 7.6 Closure-chasing failure

The run starts behaving as if closing the loop is the task, instead of resolving
or honestly documenting what the mission depends on.

### 7.7 Spin failure

The run repeats the same move after it has become informationally empty.

### 7.8 Audit-skip failure

The run moves from first-pass convergence to closure without deliberate final
review.

---

## 8. Review Questions

When reviewing a harness change or a suspicious run, ask:

1. Did the loop make the real work universe explicit?
2. Did it decompose to an honest grain?
3. Did it use appropriately strong verification for important claims?
4. Did it promote what it learned into durable state promptly?
5. Did blockers become explicit and operational?
6. Did human-answerable blockers become HITL?
7. Did the run perform an actual audit sweep before closure?
8. Did the loop stop dead moves, or did it spin?
9. Did closure emerge from earned truth, or did the run chase closure posture?
10. If the run handed off a partial result, is the scope of that handoff explicit
    and honest?

If the answer to several of these is "no," the harness has likely lost sanity
even if the contract surface became smaller or the implementation became more
elegant.

---

## 9. Relationship To Domain-Specific Sanity

This document is the generic baseline.

Domain or family docs may add:

- what counts as mission-critical in that domain
- what downstream handoffability means there
- what domain-specific closure layers mean
- what domain-specific evidence packaging is helpful

But domain docs should not have to invent generic sanity from scratch.

The generic harness should already want to:

- inventory real work
- verify important claims strongly
- surface blockers
- audit before closure
- avoid spin

Domain-specific sanity should be an add-on, not a rescue mission for a generic
harness that has become shallow or closure-biased.

---

## 10. Summary

The stable generic target is:

**a harnessed loop that decomposes the mission into explicit
independently-resolvable truth-bearing work, verifies important claims with
appropriately strong checks, persists what it learns durably, surfaces real
blockers, performs an honest audit sweep, and stops repeating dead moves.**

If a refactor makes the harness smaller but weaker against that standard, the
refactor is not a behavioral improvement.
