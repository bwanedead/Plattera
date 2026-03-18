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
- starts with orientation and baseline understanding instead of jumping directly to edits
- uses the deed image when it needs to verify critical details
- crops or zooms relevant image regions when that improves confidence
- notices disagreement between parallel t0 drafts
- focuses effort on map-critical details first
- escalates to HITL only after evidence and repair attempts are exhausted
- integrates HITL feedback into the next appropriate action
- terminates with a result that clearly says whether mapping-ready closure was achieved

## What Success Means
A test is successful when the harness demonstrates that the loop can:
- move from t0 draft input to a refined final transcript
- converge or fail honestly with clear reasons
- preserve unresolved blockers when they cannot be safely closed
- avoid treating low-value transcription noise as a mapping blocker
- produce a final artifact that deed-to-IR can actually consume

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
- Did it focus on the right blockers?
- Did it verify critical details instead of guessing?
- Did it use HITL only when needed?
- Did it preserve enough truth for downstream mapping?

If the answer to those questions is unclear, the test was not aimed at the right thing.

## Links
- CLI test protocol: `docs/agent-testing/transcript-edit-loop-cli-testing.md`
- t0 fixture setup: `docs/agent-testing/practice-deed-t0-setup.md`
- HITL behavioral intent: `docs/agent-testing/hitl-loop-behavioral-intent.md`
- Live validation path: `docs/transcript-edit-live-validation-path-2026-03-08.md`
- Orchestration reference: `docs/transcript-edit-loop-orchestration.md`
- Focus-cycle architecture: `docs/transcript-edit-loop-focus-cycle-architecture-2026-03-05.md`
