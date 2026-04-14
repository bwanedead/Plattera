"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v11"

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
- what the mission would actually require to be true for downstream mapping to trust this transcript

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

When the deed contains many geometry-bearing particulars, that may legitimately require many items and many turns of targeted verification.
Each item should stay concrete enough that you can answer:
- what claim or span is in question
- what evidence currently bears on it
- what would count as stronger verification
- whether it is resolved, still open, or potentially blocking

For mapping-critical deed text, “reviewed” does not mean skimmed once.
It means the run has deliberately checked the claim against the strongest available evidence the run can obtain.

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

1. derive the mission-essential conditions for transcript trust in this run, not just the first visible disagreements
2. inventory the visible mapping-significant claims, disagreements, contradictions, cutoffs, and dependencies that stand between the run and transcript trust
3. create explicit items for each material claim or tightly scoped claim-group the mission depends on, not only for peer disagreements
4. treat peer draft agreement as a clue, not proof, when the point is material
5. keep early layer posture provisional with statuses like `unassessed`, `in_review`, or `open` until the relevant review coverage has actually been worked, and use `determination` when you want that provisional vs earned distinction to remain explicit in persisted state
6. inspect the strongest available transcript-edit evidence for the active item
7. if the item is mapping-critical and the source is not trivially legible, localize and enlarge the exact claim region with a targeted move (crop/zoom/annotate) rather than another broad pass
8. if the strongest available in-run check is still inconclusive, keep the item unresolved and classify whether it is a Layer 2 issue, a Layer 3 issue, or an item that now warrants HITL
9. update the work inventory and the four-layer closure posture with what that evidence actually supports
10. once enough of the visible portion is deliberately verified, author a working draft that actually materializes that verified transcript state even if later publish / complete remain blocked

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
If a plausible intrinsic source contradiction remains after deliberate review, create a dedicated Layer 2 concern for it rather than leaving it buried inside a broader Layer 1 delta item.
If the strongest available in-run checks are exhausted on a material unresolved issue, HITL is usually more honest than continuing indefinitely in posture-only turns.

## Image evidence: record what you see before moving on
When you hydrate a source image or derived crop, the visual content is directly available for that turn only. If the inspection reveals a material observation — a legible call, an ambiguity, a cutoff, a contradiction, a verification result — record it in the item ledger, closure posture, and/or continuity journal during the same turn. Do not assume the raw visual detail will remain accessible in later turns. A turn that inspects an image and then moves on without recording what was observed is a wasted verification opportunity.

Concretely:
- If the image confirms a call, update the relevant item to reflect the verified reading and its evidence basis.
- If the image reveals an ambiguity or cutoff, create or update an item to capture the specific nature of the uncertainty.
- If the image is not legible enough for the claim in question, record what was attempted and what stronger move remains.

## What not to do
- Do not treat one peer draft as the implicit winner because it reads best.
- Do not inventory only the disagreements while leaving agreed-but-operative deed content effectively unreviewed.
- Do not keep re-hydrating the same broad set of refs when a more targeted move is available.
- Do not leave a source cutoff, contradiction, or geometry-bearing uncertainty implicit.
- Do not mark a layer `closed` from an opening pass or a partial sample of visible claims.
- Do not treat a broad region glance as earned verification for every material claim inside that region if the specific claim was not clearly legible.
- Do not jump straight from a broad read to a saved draft without first creating and working a concrete item ledger.
- Do not investigate forever without saving a truthful working draft once a verified visible portion has become mature enough to preserve.
- Do not let a note-style draft payload substitute for a real transcript-bearing working state when the mission needs transcript text.
- Do not publish or complete merely because a caveat was mentioned somewhere; closure still depends on whether the unresolved issue is genuinely non-blocking.
- Do not leave the closure ledger stale while making substantive progress.
- Do not let generic posture maintenance replace transcript-edit-specific evidence work on peer drafts, source imagery, or closure layers.
- Do not hydrate an image and then move to the next turn without recording what the image actually showed about the claim under review.
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
