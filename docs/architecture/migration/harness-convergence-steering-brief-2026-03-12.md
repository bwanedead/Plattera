# Harness Convergence Steering Brief & Refactor Review

Date: 2026-03-12
Status: Active steering brief for ongoing convergence work
Primary references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/migration/harness-delta-ledger.md`
- `docs/architecture/migration/harness-decisions.md`

## Steering Correction

This brief predates later convergence implementation work and should be read with these corrections:
- transcript-edit authority is now materially converged and hardened in code; it is no longer the primary unfinished architecture layer
- the main technical watchpoint is `backend/harness/run_state.py` thinness and derivation drift
- the main program gap is operational maturity, not missing shared primitives
- Ralph and `legacy-ralph/` are out of scope for this harness-convergence program

Use the roadmap, delta ledger, and decisions log as the current authoritative steering surfaces when this brief conflicts with later migration records.

## Purpose

This document is a steering brief for agents continuing the harness refactor.

It is intended to:
- assess the current convergence slice honestly
- identify what is genuinely solid vs what is still incomplete
- call out legacy and compatibility surfaces still in play
- define the highest-value next steps for full convergence

It is not intended to:
- declare convergence finished
- imply the current refactor is unsound
- erase useful Plattera-specific harness strengths in the name of generic purity

The right posture is:
- preserve what is weight-bearing
- harden what is still ambiguous
- remove duplicated authority
- finish convergence before claiming the new harness is mature enough for serious live-loop reliance

---

## Executive Summary

The refactor is directionally strong and meaningfully advances the harness architecture.

The repo now has:
- a real architecture/migration docs spine
- a shared `backend/harness/` layer
- canonical trace schema + adapters for both main loop families
- a shared terminal taxonomy
- a minimal shared run-state envelope
- transcript-edit authority clarification with initial implementation work
- a lightweight review/eval foundation over canonical traces

This is no longer a "we should probably converge later" situation.
Convergence is underway and already structurally visible in code.

However, the migration is **not yet complete**.

The main incomplete areas are:
- transcript-edit authority hardening is not finished
- waiting/resume authority still leaks through compatibility fields and cache fields
- shared run-state currently duplicates some transcript-edit domain projection logic
- canonical traces are normalized read models, not yet a full runtime-native trace system
- legacy compatibility seams remain active in several places

The refactor should be judged as:
- **architecturally sane**
- **structurally useful**
- **not yet fully converged**
- **ready for the next hardening phase, not yet ready to be declared done**

---

## Current Assessment

## 1. What is clearly good and should be preserved

### 1.1 The migration is contract-led rather than patch-led

The docs spine under `docs/architecture/` is a real improvement.

The following are doing the right job:
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/harness/canonical-trace-schema.md`
- `docs/architecture/harness/shared-terminal-taxonomy.md`
- `docs/architecture/harness/transcript-edit-state-authority.md`
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/migration/harness-decisions.md`

This matches the intended convergence method:
- define the contracts first
- normalize vocabulary first
- move implementation toward those contracts

### 1.2 The shared harness layer is real and still relatively lean

`backend/harness/` is not currently a giant abstraction dump.

Its strongest pieces are:
- `backend/harness/tracing/schema.py`
- `backend/harness/tracing/builder.py`
- `backend/harness/tracing/service.py`
- `backend/harness/terminal_taxonomy.py`
- `backend/harness/review/reporting.py`
- `backend/harness/review/tool.py`

This layer currently behaves like:
- a shared contract + normalization package
- a shared review/read-model package

That is good.

### 1.3 The terminal taxonomy seam is good sharing

`backend/harness/terminal_taxonomy.py` is the right kind of shared layer:
- small
- explicit
- pure
- reused by both families
- low-drama

This is a model for future shared seams.

### 1.4 The canonical trace work is genuinely valuable

The trace adapters are doing what a healthy convergence slice should do:
- normalize existing observability artifacts
- avoid rewriting runtime loops first
- preserve raw artifacts as the underlying forensic layer

This matches the accepted decisions:
- adapter-first
- read-only first
- raw-plus-canonical retention

### 1.5 Transcript-edit authority is much clearer than before

The introduction of `backend/agents/transcript_edit/state_projection.py` is a real improvement.

The system is visibly moving toward:
- `decision_ledger` as unresolved closure truth
- `blocker_registry` as blocker/HITL lifecycle truth
- pending prompt fields as projections/cache
- terminalization as read model

That is the correct direction.

---

## 2. What is still incomplete or immature

These are not abstract concerns.
They are the main remaining maturity gaps that matter before declaring the harness converged.

### 2.1 Transcript-edit authority convergence is not finished

The authority docs are ahead of the runtime.

The current state is:
- the authority split is defined
- parts of it are implemented
- compatibility fields still remain live at the public boundary
- core loop logic still reads cache fields in important places

That means the system is in:
- **guided convergence**

not yet:
- **structurally singular authority**

In practical terms:
- `resume_pending_feedback_*` is still part of the public resume contract
- controller bootstrap still reconciles registry state and compatibility fields
- runtime control flow still branches on `state.pending_feedback_prompt_id` in important places
- API resume logic still reconstructs waiting posture from multiple inputs

This is acceptable for a migration slice.
It is not acceptable as the final authority model.

### 2.2 Shared run-state is drifting toward duplicated domain logic

`backend/harness/run_state.py` is useful, but it is currently the clearest new drift risk.

The issue is not that the file exists.
The issue is that it re-derives transcript-edit semantics that already have a domain-owned projection seam.

Most notably:
- transcript-edit waiting feedback projection is defined in `backend/agents/transcript_edit/state_projection.py`
- `backend/harness/run_state.py` currently reimplements a near-equivalent waiting projection

That creates:
- duplicated authority rules
- future drift risk
- a shared layer that knows too much about a domain-owned policy seam

`run_state.py` should remain a thin shared read-model builder, not become a second place where transcript-edit truth is reinterpreted.

### 2.3 Canonical traces are not yet the full observability standard

Current trace work is strong but still limited in a very specific way:
- it is primarily a normalized derivative layer over persisted artifacts
- it is not yet a universally emitted/persisted runtime-native trace stream

This means traces are currently excellent for:
- review
- comparison
- diagnostics
- contract analysis

But still incomplete for:
- comprehensive operational replay
- first-class trace persistence/export policy
- runtime-native trace enrichment
- fully standardized cross-run observability infrastructure

This should be described honestly as:
- **trace normalization foundation built**

not:
- **complete trace system finished**

### 2.4 Review/eval foundation exists, but the outer loop is not yet institutionalized

The review layer is useful and promising.
It is not yet a full operational practice.

Still missing:
- routine review cadence
- recurring multi-run review ownership
- explicit benchmark packs
- regression tracking over review outputs
- documented loop for converting review findings into harness changes

Right now the repo has the beginnings of the outer loop.
It does not yet have outer-loop maturity.

### 2.5 Migration tracking docs need to stay tighter

At least one current problem exists already:
- implementation and tests moved faster than some ledger entries and status language

If the migration docs drift from reality, the whole convergence program weakens.

That means:
- the docs spine is good
- the steering discipline still needs to stay active

---

## 3. Match Against Harness Best Practices

Relative to the harness-engineering concepts reviewed earlier, the refactor currently scores as follows.

### Strong match

- explicit shared contracts
- typed normalization layers
- shared terminal vocabulary
- explicit state ownership discussion
- blocker-aware architecture
- artifact-first continuity
- traces as normalized observability substrate
- review/eval foundation as outer-loop precursor

### Partial match

- complete run observability
- unified continuity semantics
- singular state authority across all relevant seams
- full harness-wide blocker envelope operationalization
- fully mature improvement loop over traces

### Not yet at target

- runtime-native canonical trace persistence/emission
- singular transcript-edit waiting/resume authority from boundary to runtime
- elimination of compatibility-field dependency
- cleaned shared run-state ownership model
- full convergence of live operational paths onto the new harness vocabulary

---

## Legacy / Compatibility / Vestigial Surface Review

This section is important.
Not every old surface needs deletion right now.
Some are historical-only.
Some are compatibility seams still serving a purpose.
Some are active legacy that should now be intentionally retired.

## 1. Historical legacy: `legacy-ralph/`

`legacy-ralph/` appears to be historical process/archive material, not an active runtime harness dependency.

Assessment:
- historical
- not part of current runtime convergence
- not an urgent cleanup target

Recommendation:
- keep as historical archive unless there is a repo-cleanup reason to move/archive it later
- do not spend active convergence energy here now

## 2. Active legacy harness seam: `agent_kernel.run_kernel`

The `Agent Kernel` package still exports `run_kernel`, and the README explicitly describes it as:
- legacy/autopilot harness
- deterministic regression/smoke usage

Assessment:
- still active
- intentionally retained
- not vestigial in the strict sense
- but no longer the architectural north star

Recommendation:
- keep only if its role is explicitly narrow:
  - deterministic smoke harness
  - regression harness
  - compatibility surface
- do not allow new feature work to accumulate there as if it were the primary loop architecture
- add a future migration/deprecation decision when practical

## 3. Active compatibility seam: transcript-edit pending prompt fields

Examples:
- `resume_pending_feedback_prompt_id`
- `resume_pending_feedback_decision_key`
- `resume_pending_feedback_prompt`
- runtime cache fields like `pending_feedback_prompt_id`

Assessment:
- active compatibility layer
- not vestigial
- still load-bearing in current runtime behavior
- must not be mistaken for "already retired"

Recommendation:
- keep as compatibility only
- continue shrinking their authority role
- plan explicit deprecation criteria

## 4. Active compatibility seam: `backend/transcript_edit` vs `backend/transcription_edit_loop`

The current repo contains both:
- `backend/transcript_edit/`
- `backend/transcription_edit_loop/`

And `backend/transcript_edit/` currently re-exports from `transcription_edit_loop`.

Assessment:
- active compatibility seam
- not yet cleaned up
- easy to ignore because it is quiet
- real legacy overlap that should eventually be resolved

This also shows up in:
- `backend/api/transcription_edit_cli.py`

Recommendation:
- do not delete hastily
- explicitly decide which package name is canonical long-term
- once confirmed, move consumers and deprecate the shadow compatibility package

This is one of the clearest remaining legacy surfaces in the codebase.

## 5. Old transcript-edit API path

The repo still has:
- `backend/api/endpoints/transcription_edit.py`

alongside:
- `backend/api/endpoints/transcript_edit_agent.py`

Assessment:
- likely active older loop/API surface
- not necessarily harmful today
- but it is an old parallel path and should be treated as such

Recommendation:
- clarify whether it remains supported product surface or legacy compatibility endpoint
- if legacy, mark it explicitly and stop architectural evolution there

## 6. Controller facade compatibility layer

`backend/agents/controller/controller.py` is now a stable facade/compat surface over split runtime modules.

Assessment:
- this is a healthy compatibility seam
- not vestigial
- worth preserving as public surface stability

Recommendation:
- keep
- do not treat as cleanup target unless public API policy changes

---

## Steering Judgment

The current refactor should be judged as:

### Sane

Yes.
It is a structurally serious refactor.
It follows the right ordering.
It improves architecture rather than just moving lines around.

### Sound

Mostly yes.
The main shared seams are good and the tests back up the new contract layer.

### Architecturally complete

No.
Not yet.

This is the start of shared harness maturity, not the end state.

### Ready for live-loop usage

Conditionally.

The new architecture is strong enough to continue building toward live loops.
But it is not yet mature enough to claim:
- full convergence
- fully singular transcript-edit authority
- complete trace-operational maturity

So the correct stance is:
- proceed
- but finish the hardening/migration work before calling the harness fully converged

---

## Highest-Value Next Steps

These are ordered by architectural value, not by convenience.

### 1. Finish transcript-edit authority hardening

This is the most important remaining convergence task.

Specifically:
- reduce public resume dependence on standalone pending-prompt fields
- replace cache-field branching with registry-derived projections where practical
- define a single resumability projection, not just a waiting-feedback projection
- make compatibility fields projection-only in both meaning and control flow

Do not claim authority convergence is complete before this is done.

### 2. Make `backend/harness/run_state.py` thinner

This is the cleanest near-term refactor target in the shared layer.

Goal:
- shared run-state should consume domain-owned projection helpers or normalized trace outputs
- shared run-state should not restate transcript-edit authority rules

This is likely the highest-leverage cleanup inside the new `backend/harness` package.

### 3. Decide the derivation model for shared run-state

A decision now needs to be made:

Should shared run-state be derived primarily from:
- raw payloads,
- canonical traces,
- or loop-family owned projection builders?

Current hybrid behavior is workable but should not be allowed to harden into accidental architecture.

### 4. Define and implement the first true trace operationalization step

Pick one concrete next move:
- persisted canonical sidecars
- trace export artifacts
- trace API access
- review-cache persistence

Without this, the trace layer remains strong but mostly analytical.

### 5. Clarify active vs legacy transcript-edit surfaces

Make an explicit architectural decision for:
- `backend/transcript_edit/`
- `backend/transcription_edit_loop/`
- `backend/api/endpoints/transcription_edit.py`
- `backend/api/transcription_edit_cli.py`

This does not necessarily mean immediate deletion.
It does mean:
- canonical surface must be named
- compatibility surface must be explicitly labeled
- new work should stop landing on the old path

### 6. Keep migration docs exact

Required discipline:
- update `harness-delta-ledger.md` when implementation meaningfully advances
- do not overstate completion
- do not let the docs lag the code for more than one migration slice

### 7. Stand up the real outer loop

The next maturity step after hardening is operational, not just structural.

Make recurring review real:
- multi-run trace reviews
- reason-code clustering
- verification-missing review
- repeated-action/churn review
- documented cadence and ownership

---

## Guidance For Refactor Agents

Use this as the working steering stance:

### Do

- preserve the shared contracts under `docs/architecture/harness/`
- preserve the shared terminal taxonomy seam
- preserve the canonical trace builder/adapters pattern
- preserve transcript-edit’s domain-native closure/blocker strengths
- reduce duplicated authority and duplicated derivation
- prefer explicit projections over ad hoc compatibility logic
- keep raw artifacts authoritative and canonical traces additive

### Do not

- declare convergence complete
- add more domain semantics into `backend/harness` than necessary
- treat compatibility fields as final architecture
- add new features onto explicitly legacy surfaces without an intentional decision
- flatten transcript-edit’s useful domain structure into generic harness mush

### When in doubt

Ask:
- is this shared harness infrastructure or domain policy?
- is this a canonical owner or a projection?
- are we reducing duplicated authority or adding another copy?
- are we making the harness more observable and more analyzable, or just more layered?

---

## Verification Snapshot

Relevant tests were reported passing for this migration slice, including:
- `pytest backend/harness -q`
- `pytest backend/agents/transcript_edit/test_state_authority.py backend/api/test_transcript_edit_agent_endpoints.py backend/api/test_transcript_edit_agent_cli.py -q`

These results support:
- shared tracing foundation
- terminal taxonomy
- run-state envelope
- review tooling
- transcript-edit state-authority slice

Passing tests do **not** imply convergence is finished.
They imply the current migration slice is real and enforceable.

---

## Final Steering Conclusion

The refactor is:
- good
- real
- useful
- not done

It has moved Plattera from:
- architecture aspiration

to:
- architecture migration with real shared seams

The next job is not another broad redesign.

The next job is to:
- finish authority hardening
- keep the shared harness layer thin
- resolve remaining legacy/compatibility ambiguity
- operationalize traces and review as the real outer improvement loop

Only after those are done should the system be described as having reached full harness convergence for serious live-loop reliance.
