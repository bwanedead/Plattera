# Transcript Edit Loop - Holistic Intent and Test Protocol

## Purpose
This document captures the shared intent behind transcript-edit loop testing so agents do not have to rediscover the goal, scope, and success criteria every time a test run is requested.

The loop exists to turn a deed image, through t0 and transcript-edit, into a final edited transcript that is suitable for deed-to-IR and downstream mapping work.

This is the baseline reference for:
- what the loop is supposed to accomplish
- what a successful test run is trying to prove
- what kinds of failures matter
- what is intentionally out of scope

## System Boundary
The current workflow is split into two related domains that share the harness:
- `t0`: upstream initial transcription from deed image to draft transcript artifacts
- transcript-edit loop: post-t0 iterative audit, repair, clarification, and promotion

The longer-term target is a blended continuous workflow, but current testing should treat these as distinct stages with a clear handoff.

## What the Loop Is For
The transcript-edit loop is not just a text cleaner.

Its job is to converge the working transcript toward the deed's mapping-critical truth so the final artifact can be used by deed-to-IR and the mapping engine.

That means the loop should:
- identify inaccuracies in the t0 draft
- detect contradictions or incoherencies in the source deed itself
- surface external dependencies that are required for mapping
- determine whether any unresolved issue actually blocks mapping
- request HITL only when autonomous closure is exhausted

## Progressive Run Understanding
The transcript-edit loop should behave like an accumulating investigation, not a sequence of isolated repair attempts.

Each iteration should inherit and extend a durable understanding of the run, including:
- what artifacts exist in the case
- what has already been inspected
- what mapping-critical items have been identified
- which items are verified, disputed, unresolved, or non-blocking
- what actions have already been attempted
- what those actions learned
- which blockers remain and why

The goal is that later iterations stand on the shoulders of earlier iterations rather than repeatedly rediscovering the same environment.

A healthy run shows additive understanding over time:
- early iterations establish baseline situation awareness
- middle iterations convert that awareness into explicit focus/blocker items
- later iterations resolve, reclassify, or escalate only the blockers that remain materially relevant

If the loop repeatedly revisits the same uncertainty without visible state advancement, that is a convergence defect even if individual actions appear locally reasonable.

## Emergent Focus, Not Scripted Choreography
The loop should not be forced through a rigid, pre-scripted checklist of actions.

The harness should create the right environment for the agent to discover and promote its own focus items when that is the sane next move.

Focus items may represent more than direct closure work:
- a mapping-critical contradiction that needs verification
- a source inconsistency that needs clarification
- an external dependency that needs to be named and tracked
- an investigation target that needs spans, image evidence, or a baseline pass
- an orientation task that needs the case model to be established before closure work begins

That means the loop may legitimately create a new explicit blocker or focus item for:
- need to orient
- need to investigate
- need to establish baseline circumstances
- need to verify a specific region or token
- need to plan before a safe edit can be made

The point is not to hard-code those steps in advance. The point is to let the agent surface them when the case demands them, then persist them as structured work items that later iterations can inherit.

If a planning step is the right next move, it should be expressed as a bounded focus item or blocker-aware move, not treated as a special scripted escape hatch.

## Investigation Brief and Planning Rail
The run should keep two different kinds of work artifacts distinct:
- an investigation brief, which is a living sticky note for case understanding
- a plan, which is a bounded working rail for the next edit or resolution move
- both should be carried together as support state, separate from the canonical ledger and blocker truth
- derived policy signals may sit alongside that support state to bias selection and gating, but they remain posture hints rather than truth

The investigation brief should accumulate what the loop currently knows:
- what artifacts exist
- what has been inspected
- what remains uncertain
- what needs to be verified or oriented
- what has already been attempted
- what the next sensible move appears to be

The brief is additive and editable. It is not the canonical trace of the run.

The plan is more official, but it is still modifiable and bounded. It should help the loop move forward without becoming doctrine. When uncertainty remains, the plan should stay honest and narrow rather than forcing unsupported edits.

The preferred shape is:
- the investigation brief explains the case model
- the focus item or blocker expresses what is still open
- the plan expresses the current safe next move
- the support state bundle stays editable and additive, but never becomes the source of truth

## The Four Layers of Closure
Testing should be organized around the loop's closure model.

### Layer 1: Canonical recovery
Does the working transcript match the canonical source deed content?

### Layer 2: Canonical sanity
If the source itself contains inconsistencies or contradictions, does the loop detect and preserve that reality instead of pretending the source is clean?

### Layer 3: Dependency completeness
Are external references or other context needed to map the deed correctly, even if the transcript itself is accurate?

### Layer 4: Mapping impact
If a layer 1, 2, or 3 issue remains unresolved, does it actually block mapping the deed, or is it only a transcript-quality issue?

The loop should distinguish mapping-critical blockers from details that are annoying but not fatal to downstream mapping.

## What Good Test Runs Should Show
A useful test run should let an agent observe whether the loop:
- starts with orientation and enough baseline understanding to know what kind of work is needed next
- takes inventory before it acts, so the first meaningful step is a deliberate read of the case
- converts inventory into explicit blocker or dependency candidates before requesting help
- self-assigns a focused blocker or investigation target before requesting help
- uses the deed image when it needs to verify critical details
- crops or zooms relevant image regions when that improves confidence
- notices disagreement between parallel t0 drafts
- focuses effort on map-critical details first
- escalates to HITL only after evidence and repair attempts are exhausted
- integrates HITL feedback into the next appropriate action
- terminates with a result that clearly says whether mapping-ready closure was achieved

## Observability and Flow Sanity
Testing is not only about the final result. It is also about whether the loop's sequence of actions makes sense as a human-readable reasoning process.

The tester should be able to answer, for any major step:
- what the loop did
- why it did it
- what evidence or condition led to that action
- what outcome followed
- whether that outcome moved the case closer to closure

If existing observability already captures that, use it. If not, the test outcome should be to expand observability until the step-by-step story is visible enough to evaluate.

What to look for:
- an initial inventory/orientation phase before repair pressure starts
- explicit focus selection before deeper action
- evidence gathering before escalation
- visible state progression across iterations
- bounded, explainable HITL prompting rather than instant escalation
- a visible chain from action to outcome to next action

What to treat as a defect:
- HITL requested on iteration 1 before orientation or inventory
- the loop acting without a visible reason for the action
- the loop taking a step that does not appear to reduce uncertainty or improve closure
- repeated rediscovery without state advancement
- inability to reconstruct why a decision was made from logs, traces, and emitted events

Testing rule:
If the reason for a step is missing, or the step did not materially advance the case model, the loop is not observable enough yet.

## Expected Run Shape
A healthy transcript-edit run usually follows this broad pattern:
1. orient to the available artifacts and current case state
2. establish a mapping-critical inventory of facts, uncertainties, and dependencies
3. promote the highest-value unresolved items into explicit focus/blocker work
4. attempt autonomous closure using available evidence and tools
5. update the run understanding based on outcomes
6. escalate only those remaining blockers that are both material and locally exhausted

Runs do not need to follow this mechanically, but major deviations should be explainable in observability.

## Escalation Doctrine
HITL is appropriate only when all of the following are true:
- the loop has oriented to the case enough to know the relevant work shape
- the relevant item has been identified as an explicit blocker or dependency
- available autonomous evidence-gathering steps have been attempted or ruled out
- the unresolved point remains material to mapping closure
- the request is bounded enough that user input will directly unlock the next state transition

Good HITL requests are the result of disciplined narrowing, not generic help-seeking.

## What Success Means
A test is successful when the harness demonstrates that the loop can:
- move from t0 draft input to a refined final transcript
- converge or fail honestly with clear reasons
- preserve unresolved blockers when they cannot be safely closed
- avoid treating low-value transcription noise as a mapping blocker
- produce a final artifact that deed-to-IR can actually consume
- make the sequence of major decisions and outcomes legible enough that a human can follow the case from start to finish

Success is not "the loop never asks for help."
Success is "the loop knows what matters, tries the right things, and reports the truth about what remains."

## What Is Not the Main Goal of These Tests
These tests are not primarily meant to:
- benchmark raw speed
- compare model vendors
- validate deed-to-IR output geometry
- prove every deed can be fully closed automatically
- check generic OCR quality in isolation

Those can be useful later, but the current target is harness behavior, iteration quality, evidence use, and closure discipline.

## Canonical Practice Fixture
The current practice deed is the legal-text image scenario used to exercise the loop under a known range contradiction.

Use it to observe:
- disagreement between t0 drafts
- image verification behavior
- layer 2 contradiction handling
- HITL prompt generation
- feedback consumption and re-entry into the loop

## Run Output Files

When a run finishes, the same recap is projected to human-readable files:
- Stable last run: `dossiers_data/state/transcript_edit/run_feed/latest_transcript_edit_run.json`
- Recent runs feed: `dossiers_data/state/transcript_edit/run_feed/transcript_edit_recent_runs.json`

The stable file is the quickest way to inspect the most recent recap and final freshness posture.
The recent-runs feed is the quick comparison surface for the last few completions.

## Recommended Reading Order
If an agent is about to run a test, it should read these in order:
1. This doc
2. `docs/agent-testing/transcript-edit-loop-cli-testing.md`
3. `docs/agent-testing/practice-deed-t0-setup.md`
4. `docs/agent-testing/hitl-loop-behavioral-intent.md`
5. `docs/transcript-edit-live-validation-path-2026-03-08.md`

For deeper implementation context, use:
- `docs/transcript-edit-loop-orchestration.md`
- `docs/transcript-edit-loop-focus-cycle-architecture-2026-03-05.md`
- `docs/transcription-edit-loop-spec-v0.md`

## Agent Testing Rule of Thumb
When an agent is asked to test the loop, the test should answer:
- Did the loop understand the deed well enough to begin with?
- Did it inventory and orient before it tried to close anything?
- Did it turn that inventory into a more complete durable case state?
- Did it focus on the right blockers?
- Did it verify critical details instead of guessing?
- Did it use HITL only when needed?
- Did it preserve enough truth for downstream mapping?
- Can I reconstruct the full step chain, with reasons and outcomes, from the observability we already have?
- Did each iteration either increase understanding or reduce a materially relevant blocker?

If the answer to those questions is unclear, the test was not aimed at the right thing.

## Links
- CLI test protocol: `docs/agent-testing/transcript-edit-loop-cli-testing.md`
- t0 fixture setup: `docs/agent-testing/practice-deed-t0-setup.md`
- HITL behavioral intent: `docs/agent-testing/hitl-loop-behavioral-intent.md`
- Live validation path: `docs/transcript-edit-live-validation-path-2026-03-08.md`
- Orchestration reference: `docs/transcript-edit-loop-orchestration.md`
- Focus-cycle architecture: `docs/transcript-edit-loop-focus-cycle-architecture-2026-03-05.md`
