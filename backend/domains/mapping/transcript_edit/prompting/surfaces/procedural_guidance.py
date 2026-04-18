"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v14"

TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to shape your movement through transcript-edit work. This is **guidance**, not a hard script. The harness still owns orchestration. You should apply judgment based on what the current run actually contains.

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

## Operational reminders
- Keep `mission.closure_state` and `resolution_state.items` current as real work happens; do not wait for a final rationale to explain closure after the fact.
- Early in the run, it is usually more honest to keep layers `unassessed`, `in_review`, or `open` than to jump straight to `closed`.
- If a plausible intrinsic source contradiction remains after deliberate review, create a dedicated Layer 2 concern for it rather than leaving it buried inside a broader Layer 1 delta item.
- If the strongest available in-run checks are exhausted on a material unresolved issue, emit HITL or explicit blocked posture rather than continuing indefinitely in posture-only turns.
- When a material blocker is plausibly human-answerable (for example, an intrinsic source contradiction the operator can adjudicate), surface it as its own HITL in addition to any missing-source HITL already emitted. A single continuation-request HITL does not discharge other distinct human-answerable blockers.
- When per-parcel or per-call-group handoffability is honestly scoped (e.g., parcel 1 forwardable, parcel 2 blocked by cutoff), represent that through per-scope items in the ledger with appropriate `blocking` / `no_further_progress` flags and use `resolution.relations` to tie them to Layer 4 of the closure state.

## Audit-sweep gap items
During the audit sweep before close or publish, if you discover that mission-essential visible content was never explicitly covered by any resolution item (for example, a visible sequence of thence-calls in a parcel was only implicitly assumed reviewed), the correct move is to **create a new explicit item for that coverage and work it**, not to annotate existing items to claim coverage they do not actually have. A late audit-gap item is a sign of healthy self-review, not a failure. Prefer adding the real work to the ledger over retrofitting closure language onto items that never touched that evidence.

## Image evidence: record what you see before moving on
The domain branch already tells you that hydrated image evidence is turn-local. Apply that rule mechanically: if the inspection reveals a legible call, an ambiguity, a cutoff, a contradiction, or a verification result, record it in the item ledger, closure posture, and/or continuity journal during that same turn. A turn that inspects an image and then moves on without recording what was observed is a wasted verification opportunity.

Concretely:
- If the image confirms a call, update the relevant item to reflect the verified reading and its evidence basis.
- If the image reveals an ambiguity or cutoff, create or update an item to capture the specific nature of the uncertainty.
- If the image is not legible enough for the claim in question, record what was attempted and what stronger move remains.

## Source-reading HITL evidence packets
When a material source-reading dispute is headed to HITL, do not emit the prompt from a vague broad-page impression if a stronger bounded evidence packet is available.

Preferred sequence:
- localize the disputed span
- crop and/or zoom it
- optionally annotate or highlight the exact question region
- re-hydrate the derived evidence and confirm it is the right packet
- include that packet in HITL context with fields such as `evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, and `question_regions`

The goal is that the human sees the exact evidence and the exact disputed region with minimal effort.
When bounded choices are appropriate, include a safe non-forcing option such as `Unable to determine` or `Other / needs nuance`.

## What not to do
- Do not treat one peer draft as the implicit winner because it reads best.
- Do not inventory only the disagreements while leaving agreed-but-operative deed content effectively unreviewed.
- Do not keep re-hydrating the same broad set of refs when a more targeted move is available.
- Do not leave a source cutoff, contradiction, or geometry-bearing uncertainty implicit.
- Do not mark a layer `closed` from an opening pass or a partial sample of visible claims.
- Do not treat a broad region glance as earned verification for every material claim inside that region if the specific claim was not clearly legible.
- Do not jump straight from a broad read to a saved draft without first creating and working a concrete item ledger.
- Do not investigate forever without saving a truthful working draft once a verified visible portion has become mature enough to preserve.
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
