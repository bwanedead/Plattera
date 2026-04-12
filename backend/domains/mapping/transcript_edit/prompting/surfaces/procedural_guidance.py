"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v9"

TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to shape your movement through transcript-edit work. This is **guidance**, not a hard script. The harness still owns orchestration. You should apply judgment based on what the current run actually contains.

## Why this guidance exists
Transcript edit often begins from a messy run reality: multiple peer t0 drafts, partial image evidence, unclear authored transcript-edit state, and several possible places where closure could fail. The generic harness doctrine tells you to orient, itemize, investigate, verify, and close honestly. This block tells you how to apply that discipline to transcript-edit specifically.

## A sane transcript-edit opening posture
Early in a transcript-edit run, you usually need to establish:
- which peer drafts exist
- whether a transcript-edit working/output artifact already exists
- which source image refs exist
- where the likely high-signal disagreements or source-sensitive claims are

That does **not** mean repeatedly loading everything over and over.
It means becoming clear about the landscape quickly enough that you can start turning real transcript concerns into explicit work.

## What t0 means in this domain
`t0` is the initial transcription output surface for the dossier or segment in scope. It may produce more than one draft because parallel or redundant transcription passes can expose uncertainty early. When multiple t0 drafts exist, their disagreements are not noise to ignore. They are often strong starting signals for where the transcript may contain real error, ambiguity, or evidence-sensitive text that deserves review.

Treat redundant draft disagreement as:
- a clue about where Layer 1 closure may be open
- a prompt to inspect evidence and determine whether one reading is better supported
- a source of candidate mission-state items when the disagreement touches mapping-relevant text

But do not limit yourself to draft disagreement alone. Mapping-critical content must be reviewed even when redundant drafts happen to agree.

## How to turn transcript-edit reality into work
In transcript-edit, a good work inventory should cover the visible mapping-significant claims and problems that stand between the run and trustworthy transcript reality.

That often means explicit review work for:
- a material disagreement between peer drafts
- a likely transcript/source delta
- a geometry-bearing line or tightly scoped call group that must be checked against the image
- a section / township / range / survey or other operative reference
- parcel structure, parcel count, or legal-description organization
- an acreage or quantity-bearing statement
- an apparent source contradiction
- a visibly incomplete or cut-off source segment
- an external dependency that prevents confident closure

Each item should stay concrete enough that you can answer:
- what claim or span is in question
- what evidence currently bears on it
- what would count as stronger verification
- whether it is resolved, still open, or potentially blocking

The generic harness already teaches the universal work method: build the work universe, choose an active item, get the next discriminating truth, and update durable state from that work. Transcript-edit adds what those items typically are and what kinds of evidence/closure matter here.

Do not treat a saved working draft as proof that this work happened.
The work is the investigation and verification of concrete items.
The draft is just a materialization of the current best state after that work.

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
Peer agreement is a clue about where review may go faster; it is not proof that the operative claim is already covered.

## Recommended transcript-edit movement
The transcript-edit-specific inflection on top of the generic harness method is usually:

1. inventory the visible mapping-significant claims, disagreements, contradictions, cutoffs, and dependencies that stand between the run and transcript trust
2. treat peer draft agreement as a clue, not proof, when the point is material
3. keep early layer posture provisional with statuses like `unassessed`, `in_review`, or `open` until the relevant review coverage has actually been worked, and use `determination` when you want that provisional vs earned distinction to remain explicit in persisted state
4. inspect the strongest available transcript-edit evidence for the active item
5. if the item is mapping-critical and the source is not trivially legible, make a targeted move (crop/zoom/annotate) rather than another broad pass
6. update the work inventory and the four-layer closure posture with what that evidence actually supports
7. once enough of the visible portion is deliberately verified, author a working draft for that verified state even if later publish / complete remains blocked

This is transcript-edit guidance, not a hard-coded controller pipeline.

## Use the closure ledger explicitly
Transcript-edit should not rely on a vague final rationale to explain closure.
As work progresses, keep the four closure layers explicit in `mission.closure_state` when that ledger is available:
- Layer 1: is the transcript/source delta closed or still open?
- Layer 2: does an intrinsic source contradiction remain?
- Layer 3: is outside material still required?
- Layer 4: do the remaining unresolved issues block mapping?

If a layer cannot be closed, say what kind of stopping posture applies:
- still open
- requires HITL
- no further progress from current evidence
- non-blocking despite remaining open

For transcript-edit specifically, publish and complete can be hard-enforced against that ledger. Do not attempt those actions unless the ledger is explicit and marked ready for the corresponding move.
Also keep `resolution_state.items` populated with the concrete concerns you have actually investigated; major moves such as save, HITL, publish, and complete should not happen with an empty work ledger.
Early in the run, it is usually more honest to keep layers `unassessed`, `in_review`, or `open` than to jump straight to `closed`.

## What not to do
- Do not treat one peer draft as the implicit winner because it reads best.
- Do not inventory only the disagreements while leaving agreed-but-operative deed content effectively unreviewed.
- Do not keep re-hydrating the same broad set of refs when a more targeted move is available.
- Do not leave a source cutoff, contradiction, or geometry-bearing uncertainty implicit.
- Do not mark a layer `closed` from an opening pass or a partial sample of visible claims.
- Do not jump straight from a broad read to a saved draft without first creating and working a concrete item ledger.
- Do not investigate forever without saving a truthful working draft once a verified visible portion has become mature enough to preserve.
- Do not publish or complete merely because a caveat was mentioned somewhere; closure still depends on whether the unresolved issue is genuinely non-blocking.
- Do not leave the closure ledger stale while making substantive progress.
- Do not let generic posture maintenance replace transcript-edit-specific evidence work on peer drafts, source imagery, or closure layers.
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
