"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from ..branch import (
    PromptBlock,
    TRANSCRIPT_EDIT_DOMAIN_ID,
)


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v4"

TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to shape your movement through transcript-edit work. This is **guidance**, not a hard script. The harness still owns orchestration. You should apply judgment based on what the current run actually contains.

## Why this guidance exists
Transcript edit often begins from a messy run reality: multiple peer t0 drafts, unclear authored transcript-edit state, uneven evidence coverage, and unresolved uncertainty about what matters for mapping. Effective work usually requires establishing a baseline reality before forcing closure claims.

This guidance exists to help you:
- understand the run before making local edits
- expose the real set of concerns rather than reacting to one fragment at a time
- use mission state as the persistent inventory of work that must be tracked and closed
- move from orientation into deliberate forward progress without improvising a hidden workflow engine

## Starting orientation posture
Early in a run, assume your first responsibility is to understand **what is here**, **what disagrees**, **what is mapping-critical**, and **what is already known or missing**.

That generally means establishing a baseline across the current transcript state:
- what t0 peer drafts exist (refs + optional hydration)
- whether t0 produced redundant parallel drafts and where they disagree once you inspect them
- what source image refs are available and what they show (hydrate to see actual image evidence)
- whether a transcript-edit working or output draft already exists

Do not confuse this with a scripted orientation phase. It is a baseline-establishment responsibility that should happen whenever the run does not yet have a reliable picture of its current state.

## What t0 means in this domain
`t0` is the initial transcription output surface for the dossier or segment in scope. It may produce more than one draft because parallel or redundant transcription passes can expose uncertainty early. When multiple t0 drafts exist, their disagreements are not noise to ignore. They are often strong starting signals for where the transcript may contain real error, ambiguity, or evidence-sensitive text that deserves review.

Treat redundant draft disagreement as:
- a clue about where Layer 1 closure may be open
- a prompt to inspect evidence and determine whether one reading is better supported
- a source of candidate mission-state items when the disagreement touches mapping-relevant text

But do not limit yourself to draft disagreement alone. Mapping-critical content must be reviewed even when redundant drafts happen to agree.

## Establishing mission state
Mission state should become the explicit working inventory for transcript-edit. It is where the run keeps track of what actually needs attention, what is blocking closure, and what remains unresolved across the closure layers.

If no useful mission state exists yet, an early sub-goal should usually be to establish it.

That means identifying and recording the meaningful items of concern, including:
- each material disagreement between redundant drafts that needs adjudication
- each likely transcript/source delta that needs review
- each mapping-critical component of the deed that needs verification, even if no draft disagreement called it out
- each suspected intrinsic source defect
- each suspected external dependency
- each unresolved issue whose mapping-blocking relevance still needs judgment

Mission state should not be noisy trivia. It should be the durable inventory of concerns that matter for getting the transcript deed-to-IR ready.

## Mapping-critical review expectations
Transcript edit is in service of mapping. That means the run should deliberately account for deed content that is likely to matter downstream, not just visible disagreements between drafts.

The exact list depends on the deed, but mapping-critical content commonly includes:
- legal description structure and parcel identity
- calls, bearings, distances, curves, and ties
- monuments, boundary markers, and reference points
- tract, lot, block, subdivision, section, township, range, and survey references
- exceptions, reservations, exclusions, easements, and burden/benefit language
- parent-child parcel relationships or conveyance relationships
- dates, parties, recording references, and document cross-references when they affect operative meaning
- references to external exhibits, plats, prior deeds, or attached schedules

You do not need to force a deterministic review order for these. But the run should not claim transcript readiness while mapping-critical content remains effectively unexamined.

## Recommended movement pattern
The sane pattern is usually:

1. establish run reality and baseline scope
2. populate or refine mission state so the real work inventory exists
3. understand current closure posture across Layers 1–4
4. choose a concrete mission-state item to address
5. use evidence and tool affordances to reduce uncertainty or resolve the item
6. update mission state and closure posture explicitly
7. repeat until the transcript is deed-to-IR ready or the remaining blockers are explicit

This is a **recommended movement pattern**, not a hard-coded controller pipeline. If the run already has a reliable mission state and one urgent blocker is obvious, you may move directly to that item. If the run is still opaque, baseline establishment comes first.

## Baseline closure accounting
As early as practical, form an explicit view of where closure currently stands:
- which Layer 1 issues appear open
- whether any Layer 2 issues are visible
- whether Layer 3 dependencies are already apparent
- which unresolved issues seem likely mapping-blocking under Layer 4

Do not wait for perfect certainty before starting this accounting. The point is to make the current closure posture visible so the run can improve it deliberately.

## How to use mission state well
Mission state should help you think cumulatively, not reactively.

Good mission-state behavior includes:
- creating one item per real unresolved concern rather than one item per vague topic
- keeping each item tied to evidence, artifact refs, or concrete transcript scope where possible
- recording why the item matters for closure or mapping
- updating or retiring items once they are resolved, waived, or reclassified
- using mission state to choose the next target of work instead of forgetting earlier concerns

Bad mission-state behavior includes:
- filling mission state with cosmetic notes
- leaving mapping-critical concerns implicit
- merging unrelated problems into one vague item
- resolving text locally without updating the tracked closure situation

## What not to do
- Do not treat this guidance as a deterministic phase engine.
- Do not assume draft agreement means the text is safe for mapping.
- Do not jump straight to polishing without first understanding the run's real uncertainties.
- Do not leave mission state empty when the run clearly contains multiple open concerns.
- Do not close the run merely because some text looks cleaner; close it only when the transcript state is genuinely deed-to-IR ready or the remaining blockers are explicit.
"""


def build_transcript_edit_procedural_guidance_blocks() -> tuple[PromptBlock, ...]:
    return (
        PromptBlock(
            block_id="transcript_edit_procedural_guidance",
            layer="domain_guidance",
            owner=TRANSCRIPT_EDIT_DOMAIN_ID,
            source_path=TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF,
            version=TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION,
            text=TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT,
        ),
    )
