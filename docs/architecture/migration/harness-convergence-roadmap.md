# Harness Convergence Roadmap

Date: 2026-03-11

## Status

This is a working roadmap for moving Plattera toward a stronger, more unified harness architecture.

It is intended to:
- capture the current agreed direction of travel
- sequence the work in a low-regret order
- support managerial steering and course-correction as implementation proceeds
- preserve a durable record of the migration itself

It is not intended to be:
- a rigid one-shot migration script
- a claim that all current architecture is wrong
- a ban on revising the plan as new evidence appears

The standard for this roadmap is structural soundness, not compliance for its own sake.

---

## Purpose

Plattera has grown beyond isolated loop implementations.

The next step is to treat harness evolution as a program:
- define the target architecture more clearly
- measure the gap from current state to target state
- migrate in phases that preserve working behavior
- keep the design flexible enough to learn from implementation

The goal is not uniformity for its own sake.

The goal is:
- one stronger shared harness spine
- clearer ownership boundaries
- better run observability
- better outer-loop improvement capability
- domain-specific policy where domain-specific policy is actually weight-bearing

---

## What Should Be Preserved

These are current strengths and should be treated as load-bearing:
- controller/kernel separation
- artifact truth and refs-not-blobs
- deterministic refusal semantics and stable reason codes
- typed tool surfaces and tool-menu realism
- transcript-edit blocker/closure/HITL strengths
- substantial existing observability ingredients

The convergence effort should generalize these strengths, not erase them.

---

## What Needs To Change

Plattera currently has multiple loop personalities that share infrastructure but do not yet feel like domain policies on one shared harness spine.

The most important deltas are:
- no single canonical trace model across loop families
- no shared harness-level terminal taxonomy
- continuity/state concepts differ across loop families
- transcript-edit still has authority overlap in parts of its closure/blocker model
- observability is strong, but outer-loop harness improvement is not yet first-class
- documentation for architecture is useful but too flat and too easy to turn into a dumping ground

---

## Roadmap Principles

The migration should follow these rules:
- define contracts before broad implementation
- unify low-risk semantics before high-risk state ownership
- normalize observability before trying to fully unify loop behavior
- keep domain policy distinct from harness infrastructure
- allow the fuller shared run ledger to emerge from real usage instead of over-specifying it too early
- keep the migration itself observable and reviewable

---

## Phase Order

### Phase 1. Establish the architecture docs spine

Create and maintain a focused architecture/migration document set:
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/migration/harness-delta-ledger.md`
- `docs/architecture/migration/harness-decisions.md`
- this roadmap

Documentation discipline for this program should be light but intentional:
- use the `docs/architecture/` area for active architecture work
- leave older documents in place unless there is a clear reason to move them
- treat this as improved information architecture, not a full docs reorganization

### Phase 2. Define the shared contracts that reduce ambiguity fastest

Define, review, and stabilize:
- canonical trace schema
- shared terminal taxonomy
- shared blocker/escalation envelope
- minimal shared run-state envelope

Do not start with a fully-heavy canonical run ledger abstraction.
Let that emerge later if the lower-level contracts prove useful.

### Phase 3. Clarify transcript-edit authority

Before broad harness convergence implementation, explicitly decide:
- which structure is the canonical owner of unresolved closure state
- which structures are lifecycle views, projections, or compatibility layers

This is important because transcript-edit is currently one of the clearest architectural pressure points and will influence blocker and state contracts.

### Phase 4. Normalize run observability into a real trace system

Add a Plattera-native canonical trace model and adapt existing observability artifacts into it.

The trace model should capture:
- request and run metadata
- starting state summary
- iteration timeline
- model calls
- tool/action calls
- blocker transitions
- verification events
- escalation events
- terminal outcome

Implementation should begin with adapters and normalization, not by rewriting all loops first.

### Phase 5. Converge shared semantics

Once traces and vocabulary are clear:
- unify terminal outcome classes
- unify blocker/escalation concepts
- align minimal shared run-state concepts

Do not force identical loop behavior.
Shared harness semantics should converge before deeper state convergence.

### Phase 6. Converge continuity/state where it is truly beneficial

After the earlier phases are grounded in implementation:
- identify the minimum shared continuity/state concepts that both loop families actually need
- keep domain-specific extensions separate
- let the broader run ledger emerge from real usage pressure

### Phase 7. Migrate loop families onto the shared harness spine

Migrate incrementally:
- generic controller/kernel family first
- transcript-edit family next
- then broader capability-parity work such as transcript-edit retrieval exposure

The target is one shared harness framework with domain policies on top, not one giant universal loop.

### Phase 8. Stand up the outer improvement loop

Once canonical traces exist, make harness improvement an explicit operating practice.

Start with:
- trace review rituals
- reason-code pattern review
- failed-vs-success trace comparison
- verification-missing review
- churn/repeated-action review

Then grow toward:
- benchmark task packs
- regression suites
- trace analytics dashboards
- harness experiment comparisons

---

## How Progress Should Be Tracked

This migration should produce its own durable record.

Use `harness-delta-ledger.md` to track:
- target capability
- current state
- gap
- decision status
- migration phase
- evidence that the gap narrowed
- open questions

Use `harness-decisions.md` to track:
- major architectural decisions
- reversals or refinements
- why a decision changed

This is the migration trace for the architecture itself.

---

## Managerial Operating Mode

This program should be run with active steering rather than one long autonomous implementation burst.

Recommended mode:
- hand one focused phase or sub-phase to the coding agent
- review its outcome against the architectural contracts
- correct direction early when responsibility boundaries drift
- update delta tracking and decision records as the design becomes clearer

This means implementation should be:
- phased
- review-heavy
- architecture-led
- willing to pause when the target contract is still unclear

---

## Success Criteria

The roadmap is succeeding when:
- active architecture docs are easier to navigate and less dump-like
- harness contracts become clearer before large migrations
- loop families increasingly map into one shared trace and outcome vocabulary
- duplicated authority shrinks
- future changes have more obvious homes
- the repo gains a durable record of both the target architecture and the path taken toward it

The ultimate goal is not document neatness.

The ultimate goal is a more elite, weight-bearing harness architecture that remains adaptable as Plattera learns.

---

## Working Conclusion

Plattera should move toward:
- one shared harness spine
- clearer run observability
- clearer blocker/outcome vocabulary
- more disciplined state ownership
- a real outer improvement loop

The migration should remain ambitious but revisable.

The right posture is:
- structurally serious
- evidence-driven
- willing to preserve novel Plattera-native strengths
- willing to adjust as implementation teaches more

---

## Post-Phase-9 Status

Phases 1 through 9 of the original convergence program are now materially implemented:
- architecture docs spine
- shared harness contracts
- transcript-edit authority clarification
- canonical trace foundation, adapters, and consumption surface
- shared terminal taxonomy
- transcript-edit authority convergence and hardening
- minimal shared run-state envelope
- review/eval foundation
- operational review tooling

The program is no longer in the "define the core convergence primitives" stage.

The current state should be described as:
- core convergence spine implemented
- transcript-edit authority materially converged
- shared harness layer real and useful
- operational maturity still incomplete

The most important remaining deltas are no longer missing shared primitives.
They are:
- keeping `backend/harness/run_state.py` thin and non-duplicative
- resolving remaining harness-relevant compatibility seams
- deciding trace export/persistence policy
- turning review tooling into recurring practice
- adding benchmark/regression packs over normalized traces and review outputs

Important steering correction:
- Ralph and `legacy-ralph/` are out of scope for this harness-convergence program.

---

## Next Segment

### Phase 10. Make shared run-state thinner and explicitly settle its derivation model

The main current technical watchpoint is `backend/harness/run_state.py`.

This phase should:
- keep shared run-state as a minimal read-model layer
- remove duplicated transcript-edit waiting/resume derivation from the shared harness layer
- explicitly decide how shared run-state is derived:
  - from loop-family-owned normalized projection surfaces, or
  - from canonical trace plus minimal raw-state supplementation

This phase should not:
- reopen transcript-edit authority as a broad redesign
- create a giant canonical run ledger
- make `backend/harness` a second place where loop-family truth is reinterpreted

### Phase 11. Resolve active harness-relevant compatibility seams

This phase should focus on the compatibility surfaces that still matter to full convergence:
- `resume_pending_feedback_*` compatibility path
- `run_kernel` legacy/autopilot compatibility surface
- transcript-edit package/API naming overlap:
  - `backend/transcript_edit`
  - `backend/transcription_edit_loop`
  - `backend/api/endpoints/transcription_edit.py`
  - `backend/api/endpoints/transcript_edit_agent.py`

The target is not broad cleanup for its own sake.
The target is:
- explicit canonical-vs-compatibility classification
- deprecation paths where appropriate
- reduced ambiguity for future agents

### Phase 12. Decide and implement trace operational maturity policy

Canonical traces are now operationally useful, but export/persistence policy is still undecided.

This phase should:
- decide whether canonical traces remain on-demand only or gain sidecar/export support
- keep raw-plus-canonical retention intact
- add only the smallest operational trace artifact support needed for routine live-loop review

### Phase 13. Institutionalize the review loop

The review/eval foundation and tooling now exist, but recurring review practice is not yet institutionalized.

This phase should define:
- review cadence
- review ownership
- required recurring review questions
- how review findings flow back into harness changes and contract evolution

### Phase 14. Add benchmark and regression packs

Once the review loop is operational, add the first repeatable benchmark/regression layer over:
- canonical traces
- shared run-state envelopes
- review outputs

The target is:
- stable fixture-backed comparisons
- repeatable regression checks
- trace-informed contract evolution

---

## Updated Working Conclusion

The next stretch of work should:
- preserve the current shared harness layer
- treat transcript-edit authority as materially converged
- prevent `backend/harness` from becoming a second semantic authority layer
- move from architectural convergence toward operational maturity

The main technical watchpoint is:
- `backend/harness/run_state.py`

The main program watchpoint is:
- failure to turn trace/review tooling into disciplined recurring practice
