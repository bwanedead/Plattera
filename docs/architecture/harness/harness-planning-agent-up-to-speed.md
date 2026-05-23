# Harness Planning Agent Up-To-Speed Guide

This guide is for a planning/review agent helping evaluate Plattera harness
runs, reason about behavior, and draft engineering handoffs. It is not a live
run script and it is not runtime doctrine.

The role is closest to a technical planning partner: inspect run evidence,
separate model behavior from harness seam failures, preserve architectural
boundaries, and help decide the next smallest useful engineering pass.

Do not start, resume, stop, answer, message, or watch live harness runs unless
the human explicitly asks for that exact action. The human decides when test
runs happen.

---

## 1. Required Reading

Read these first when coming into the work:

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/ethos/architecture-ethos.md`](../../ethos/architecture-ethos.md)
- [`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)
- [`docs/architecture/harness/harness-constitution.md`](./harness-constitution.md)
- [`docs/architecture/harness/agent-sanity-baseline.md`](./agent-sanity-baseline.md)
- [`docs/architecture/harness/transcript-edit-live-loop-testing.md`](./transcript-edit-live-loop-testing.md)
- [`docs/architecture/harness/transcript-edit-domain.md`](./transcript-edit-domain.md)
- [`docs/architecture/harness/delegate-subtask-architecture.md`](./delegate-subtask-architecture.md)
- [`docs/architecture/harness/delegate-subtask-implementation-plan.md`](./delegate-subtask-implementation-plan.md)
- [`practice_deeds/right_of_way_deed_cheatsheet.md`](../../../practice_deeds/right_of_way_deed_cheatsheet.md)

Useful context docs:

- [`docs/architecture/harness/prompt-system-architecture.md`](./prompt-system-architecture.md)
- [`docs/architecture/harness/domain-pack-architecture.md`](./domain-pack-architecture.md)
- [`docs/architecture/harness/domain-pack-constitution.md`](./domain-pack-constitution.md)
- [`docs/architecture/harness/hitl-constitution.md`](./hitl-constitution.md)
- [`docs/architecture/harness/cli-constitution.md`](./cli-constitution.md)
- [`docs/architecture/harness/delegate-subtask-phase6-experiment-report.md`](./delegate-subtask-phase6-experiment-report.md)

---

## 2. What We Are Building

We are building a generic, durable agent harness that can host different
domains through domain packs. The current active test domain is
`transcript_edit`, where the agent reads a deed image and peer T0 drafts,
creates a source-faithful transcript, creates a downstream mapping-ready lane,
records issues/blockers, and publishes a `transcript_edit:output` artifact.

The important architectural line:

- The agent authors semantic work: what matters, what is proved, what is
  blocked, what should be asked of the human, and when the run is complete.
- The harness provides rails: prompt assembly, persistence, tool execution,
  validation, audit, continuity, HITL transport, and mechanical gates.
- Domain packs provide doctrine, tools, closure standards, and adapters.
- Deterministic code must not secretly become the investigator.

When reviewing a proposed change, ask whether it preserves that split. The
harness may enforce that an output exists before `complete_run`; it may not
decide what the deed means.

---

## 3. Product Standard For Transcript-Edit Runs

The practical goal is not a perfect scholarly transcript. The goal is a
handoffable artifact that is honest, source-grounded, and useful to downstream
deed-to-IR / mapping work.

A good transcript-edit run should:

- inspect source image and peer T0 drafts
- build a visible work universe of mission-critical values and blockers
- distinguish source facts from downstream mapping decisions
- localize important visual evidence enough to support exact values
- use HITL for genuinely blocked human decisions
- write both a source-faithful lane and a mapping-ready lane when needed
- record metadata that downstream systems need, not just prose
- publish `transcript_edit:output` before `complete_run`
- stop once the deliverable is handoffable instead of chasing low-value polish

For the current practice deed, the most important expected outcomes are:

- Parcel 1 tie bearing should be `N. 4°00'W., 1638 feet`, not `N. 2°00'W.`
- Parcel 1 acreage should be `1.9 acres`, not `1.4 acres`
- The deed has an intrinsic Range conflict:
  - prefatory/location text uses Range 75 West
  - parcel-start descriptions use Range 74 West
  - HITL can choose `Use R75W` for downstream mapping while the verbatim lane
    preserves the conflicting source text
- Parcel 2 is genuinely cut off; if no continuation source exists, Parcel 2
  should be blocked/scoped rather than guessed
- Parcel 1 should remain forwardable once the range decision is resolved

---

## 4. Performance We Want

The harness should make the agent productive, not merely careful.

Desired behavior:

- Each turn should produce meaningful motion: evidence, state, HITL, artifact,
  publication, or a clear terminal posture.
- The agent should work in sensible chunks. If several related crops,
  hydrations, or delegated reads can be done in one turn, it should do that.
- Batching is not the goal by itself. Turn motion density is the goal.
- The agent should use `hydrate_next` to request refs it will need on the next
  turn instead of burning a turn just to ask for hydration.
- The agent should use `pin_refs` when a stable artifact needs to stay hot
  across several turns.
- The agent should use `delegate_subtask` when a small isolated reading or
  observation can benefit from a smaller prompt and cleaner attention.
- The agent should stop retrying low-value crops or localizations after a
  bounded no-gain pattern and either patch the honest blocker, ask HITL, or move
  on.
- After a handoffable output exists and critical blockers have explicit posture,
  every extra turn is costly. Final review should be bounded.

For this practice deed, a sane complete run has often been roughly 30 to 40
turns. That is not a hard cap. The important thing is whether the run is gaining
truth or only extending polish/audit motion. Runs over 40 turns deserve scrutiny;
runs under 20 turns may be too shallow unless they are unusually direct.

---

## 5. Common Failure Modes

### Broad source evidence used as exact proof

The agent may determine a critical detail from a full-page source image or broad
crop, then later attach a locator as decoration. That is backward.

For exact critical visual values, the intended sequence is:

1. candidate
2. claim-local evidence
3. inspect decisive detail
4. determine or block

Evidence is the method of determination, not retroactive citation.

### Candidate imprinting

Peer T0 drafts and graph candidates are useful, but they can bias small visual
reads. The `N. 2` versus `N. 4` bearing error is the signature example.

Delegate subtasks are intended to reduce this by giving a clean, narrow prompt
and curated refs to a subagent.

### Salient blocker tunnel vision

The first loud issue should orient the inventory, not define the whole mission.
The agent should not spend many turns chasing one blocker while quiet
mission-critical values remain implicit.

### Over-serialized turns

Bad pattern:

- crop one atom
- next turn inspect one crop
- next turn patch one value
- repeat for every small value

Better pattern:

- create a few sensible related crops
- request or pin the refs needed next
- inspect related returned evidence in one turn
- patch all clear atoms together
- refine only leftovers

### Late-run polish spiral

Once the output is materially handoffable, late turns should be reserved for
real correctness protection, output publication, or explicit blocker posture.
Do not let evidence/UX polish become the mission after the deliverable exists.

### Contract seam failure mistaken for reasoning failure

If the agent emits a sane intent shape but the parser rejects it, that is often
a contract ergonomics issue. Preserve the raw emitted payload and propose a
bounded contract fix rather than blaming reasoning.

Examples from recent work:

- native multi-action `actions` arrays needed to be accepted cleanly
- per-action `@this.result.*` hydration placeholders needed to resolve
- nested surface payloads needed recursive discovery for tool specs and
  subtask profiles

---

## 6. How To Review A Run

Primary files:

```text
backend/harness/cli_artifacts/cli_runs/<run_id>/done.json
backend/harness/cli_artifacts/cli_runs/<run_id>/audit/review.md
backend/harness/cli_artifacts/cli_runs/<run_id>/audit/human/timeline.md
backend/harness/cli_artifacts/cli_runs/<run_id>/audit/turn_000N.json
backend/dossiers_data/artifacts/transcript_edit/<dossier_id>/<transcription_id>/<workspace_id>/
```

Review order:

1. `done.json`: terminal class, reason code, iterations, latest refs.
2. `audit/review.md`: quick tool sequence and parse/repair count.
3. `audit/human/timeline.md`: human-readable turn flow.
4. Final `working/rev_000N.json` and `output/output.json`: actual deliverable.
5. Specific `turn_000N.json` files for failures, long turns, rejected patches,
   malformed action plans, or surprising decisions.

Always check:

- Did `transcript_edit:output` exist before `complete_run`?
- Did the final artifact include source-faithful and mapping-ready lanes?
- Did metadata include `issues`, `hitl_decisions`, `parcel_metadata`, and
  `evidence_refs`?
- Did the agent correctly preserve R74 in the verbatim lane while using R75W in
  the mapping lane after HITL?
- Did it correctly classify Parcel 2 as blocked/incomplete?
- Did it get `N. 4°00'W.` and `1.9 acres` right?
- Did it use claim-local evidence, delegate subtasks, batching, hydration, and
  pinning appropriately?
- Did it waste turns after the artifact was already handoffable?
- Did any failure come from model reasoning, prompt doctrine, tool mechanics,
  parser/contract seams, or operator/tester workflow?

Do not over-index on terminal success. A run can complete and still reveal
important seam or performance issues.

---

## 7. What Success Looks Like

A strong run usually has this shape:

- early orientation and baseline inventory
- explicit work graph with critical values and blockers
- local evidence for exact critical values
- appropriate HITL for non-source-resolvable decisions
- concise artifact materialization
- working revision saved
- output published
- one bounded final review or direct completion

The final artifact should be handoffable without requiring a human to read the
whole timeline to understand the important decisions. Timeline and audit prove
how it got there; artifact metadata carries what downstream needs.

---

## 8. Current Known Mechanical Watchpoints

As of the recent `practice-row-live-20260522-41` run, the system is close but
not done.

Observed good signs:

- run completed in 31 turns
- `transcript_edit:output` was published
- final artifact carried `issues`, `hitl_decisions`, `parcel_metadata`,
  `evidence_refs`, source-faithful transcript, and mapping-ready transcript
- main practice-deed values were correct
- native multi-action batching worked for two range crops
- `delegate_subtask` was reachable

Observed issues to address before heavily judging delegation:

- `delegate_subtask` failed with `subtask_result_too_large` at max 900 chars.
  The subtask path is reachable, but its first real use did not produce a
  usable observation. Likely fix: make projection/truncation bounded and
  useful rather than failing the subtask, or tighten child output instructions
  and caps.
- `hydrate_next` after save/publish used `@this.result.revision_ref` and
  `@this.result.published_ref`, but actual result fields were
  `working_draft_ref` and `output_ref`. This is a placeholder/schema teaching
  mismatch.
- Some turns still emitted `operator_progress_message: none`.
- One turn hit `finish_reason: length` and an unrecovered parse failure before
  the run recovered.
- Prompt/context size remains significant even after first-pass compaction.

These are coding-brief candidates, not reasons to discard the architecture.

---

## 9. Delegate Subtask Standard

`delegate_subtask` is generic harness infrastructure. It is not a transcript
read tool hard-coded into shared runtime.

Use case:

- parent agent curates the evidence packet
- child subagent gets only the small local task and selected refs
- child returns a bounded observation
- parent integrates or rejects the observation through normal state/artifact/HITL
  channels

Why this matters:

- reduces candidate imprinting from peer drafts and graph state
- reduces cognitive load for tiny visual/source reads
- reduces parent prompt cost for isolated determinations
- can be batched for several independent local observations

Important boundaries:

- no confidence fields
- no deterministic state mutation from subtask results
- child results are observations, not truth
- parent remains responsible for determining, patching, publishing, and closing
- blind reads should stay blind unless the parent explicitly wants a
  discriminative comparison

When reviewing a run, check whether delegation was used where it would help:

- critical exact visual reads
- localized handwriting or short phrase ambiguity
- several independent local observations after crops exist
- cases where parent context may be biasing the read

Also check whether delegation was used badly:

- child prompt included candidate values unnecessarily
- child got too much broad context
- parent treated the child result as automatic truth
- failures were not visible in timeline
- output was too verbose or unbounded

---

## 10. Engineering Brief Style

Engineering briefs should be copy-pastable to a coding agent. They need enough
context that a new agent can work without rediscovering the whole history.

Good brief structure:

1. Goal
2. Background / why this matters
3. Current observed failure with run id and file references
4. Scope boundaries
5. Architecture constraints
6. Tracks / implementation requirements
7. Files likely involved
8. Tests required
9. Acceptance criteria
10. Explicit non-goals

Always include harness constitution boundaries when the work touches agent
semantics:

- deterministic code validates and transports
- agent authors semantic work
- no hidden state patches
- no scripted truth selection
- no domain ontology in shared harness unless it is opaque domain payload

For behavior-sensitive doctrine work, do not hand the coding agent broad edit
authority unless explicitly approved. Doctrine wording is a high-leverage
behavior surface and should usually be planned/reviewed closely with the human.

Briefs should be specific but not over-script behavior. We prefer principles
that preserve agent judgment over checklists that make the model literal or
awkward.

---

## 11. How We Decide What To Do Next

Prefer the smallest pass that removes the current blocker to a better test.

Useful triage categories:

- Runtime bug: accepted action should work but fails mechanically.
- Contract ergonomics: agent expresses sane intent in a rejected or awkward
  shape.
- Prompt/doctrine issue: agent understands tools but chooses poor behavior.
- Observability gap: run might be fine/bad, but audit cannot show it clearly.
- Product behavior issue: output is not handoffable or run takes too long.
- Model limitation: even isolated evidence still produces wrong reads.

Do not treat every observed flaw as a code change. Some are run variability,
operator/tester workflow issues, or domain doctrine tuning. Some are product
workflow features for later, such as a UI correction channel.

---

## 12. Current Near-Term Backlog

High priority before judging another delegate-focused run:

1. Fix delegated subtask oversized-result behavior.
2. Fix or teach correct `hydrate_next` placeholders for save/publish results.

Next likely behavior hardening:

3. Improve consistency of `operator_progress_message`.
4. Continue monitoring prompt-size buckets and context compaction.
5. Encourage but do not force sensible batching/delegation in live runs.

Later product work:

6. User/operator correction UI and smooth agent repair loop.
7. Cheaper model experiments, once behavior is stable on the main model.
8. More deeds to test overfitting and domain generality.
9. Deed-to-IR domain integration after transcript-edit handoff is stable.

---

## 13. Reporting Template

When reporting on a run, use this shape:

```text
Run: <run_id>
Terminal: <status> / <reason_code>
Iterations: <n>
Output: <working/output refs>
HITL: <prompts and answers>

Bottom line:
<one paragraph>

Correctness:
- <known expected values and whether they matched>

Efficiency:
- <turn count, wasted pockets, batching/delegation/hydrate-next usage>

Artifacts:
- <whether output and metadata are handoffable>

Seam issues:
- <parser, hydrate, subtask, prompt truncation, rejected patch, missing refs>

Recommendations:
- <next one to three concrete actions>
```

Keep findings grounded in run files. Cite exact turns or artifact paths when
possible.

---

## 14. Planning Agent Operating Rules

- Do not run live harness tests unless explicitly asked.
- Do not edit runtime code unless the human asks you to implement.
- If asked to review coding-agent work, look for architecture, correctness,
  tests, and harness-determinism issues.
- If asked to plan, produce clear handoff briefs rather than vague proposals.
- If a behavior change is doctrine-sensitive, surface wording carefully and
  avoid over-formal checklists unless the human asks for them.
- Preserve raw evidence of agent near-miss payloads when diagnosing contract
  issues.
- Prefer concise, high-signal recommendations over broad rewrites.
- Keep the product goal in view: handoffable, honest output beats endless
  polish.

---

## 15. Mental Model

The harness should feel like a well-run operations desk:

- the agent decides what work matters
- tools make evidence and artifacts available
- state keeps truth from drifting
- HITL brings the human in when needed
- delegation handles small isolated observations without loading the whole case
- batching and hydration keep turns dense
- output publication is the handoff line

The run is successful when the next stage can consume the artifact with known
limits recorded honestly. It does not have to be perfect. It has to be
defensible, forwardable, and not secretly wrong on the mission-critical parts.
