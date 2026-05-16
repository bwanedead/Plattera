"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v20"

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
`t0` is the initial transcription output surface for the dossier or segment in scope. It may produce more than one draft because parallel or redundant transcription passes can expose uncertainty early.

**Peer drafts are candidate readings, not authority.** They are other machines' attempts at the same problem you are solving. Authority for what the deed says is the **source image** (and, when the source is ambiguous or cut off, a HITL answer from a human). Peer drafts are useful primarily as disagreement detectors — places where at least one machine reader was uncertain, which is a signal that a human-grade check against the source image is warranted.

Treat redundant draft disagreement as:
- a **disagreement detector**: a location where the source image should be checked directly
- a source of candidate mission-state items when the disagreement touches mapping-relevant text

Treat redundant draft **agreement** as:
- weak negative evidence only — at best a reason to deprioritize, never a substitute for direct source-image verification when the claim is mapping-critical

Do not limit yourself to draft disagreement alone. Mapping-critical content must be reviewed directly against the source image even when every peer draft happens to agree. Agreement between peer drafts is not a verification basis; the source image (and HITL when the image is insufficient) is.

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
4. treat peer drafts as candidate readings and disagreement detectors only; authority for a mapping-critical claim is the source image, with HITL as the fallback — peer-draft agreement is never a verification basis on its own
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
- When per-scope handoffability is honestly different (for example, one independently usable scope can move forward while another remains blocked), represent that through per-scope items in the ledger with appropriate `blocking` / `no_further_progress` flags and use `resolution.relations` to tie them to Layer 4 of the closure state.

## Transcript-edit run duration pressure
`run_context.iteration` is the current run turn count. In transcript-edit, treat it as an informational budget-pressure signal only. It is not an instruction, not a command to close, not a command to keep checking, and not a substitute for evidence judgment.

Current simple transcript-edit calibration:
- 0-10: `fresh_early_budget` — normal opening budget
- 11-20: `early_mid_budget` — normal working budget
- 21-30: `mid_budget` — mature working budget
- 31-40: `late_budget` — visibly long for this domain shape
- 41-50: `very_late_budget` — high budget pressure
- 51-60: `severe_budget` — severe budget pressure
- 61+: `critical_budget` — critical budget pressure

These labels exist so the run knows how long it has been working under transcript-edit expectations. They do not decide the next action. Use them only as awareness of elapsed budget pressure.

## Audit-sweep gap items
During the audit sweep before close or publish, if you discover that mission-essential visible content was never explicitly covered by any resolution item (for example, a visible sequence of thence-calls in a parcel was only implicitly assumed reviewed), the correct move is to **create a new explicit item for that coverage and work it**, not to annotate existing items to claim coverage they do not actually have. A late audit-gap item is a sign of healthy self-review, not a failure. Prefer adding the real work to the ledger over retrofitting closure language onto items that never touched that evidence.

## Image evidence: record what you see before moving on
The domain branch already tells you that tool-returned image evidence is turn-local. Apply that rule mechanically: if the inspection reveals a legible call, an ambiguity, a cutoff, a contradiction, or a verification result, record it in the item ledger, closure posture, and/or continuity journal during that same turn. A turn that inspects an image and then moves on without recording what was observed is a wasted verification opportunity.

Concretely:
- If the image confirms a call, update the relevant item to reflect the verified reading and its evidence basis.
- If the image reveals an ambiguity or cutoff, create or update an item to capture the specific nature of the uncertainty.
- If the image is not legible enough for the claim in question, record what was attempted and what stronger move remains.

## Critical exact readings: full-page source view is not enough
For transcript-edit source reading, the full source image is orientation evidence. It helps you find where to work. It is **not resolute enough** to earn a critical detail whose truth can turn on the shape of one character, one word, one digit, one degree mark, one direction letter, or one small handwritten squiggle.

This is extremely important because this failure happens in practice: the model looks at the correct page, sees roughly the correct area, carries a candidate value from t0 or first impression, and then closes the wrong number or word with confidence. That is not acceptable for mapping-critical text. A broad page view plus a box on the original image can still be a false determination.

When the claim needing resolution is a number, bearing, distance, acreage, name, range/reference, direction, short word, or other specific attribute, hyper-localize it before determining it. Crop, zoom, annotate, or render the locator so the exact mark is isolated and obvious. Then actually read that local evidence as the basis of the decision. Do not decide first from the page, peer draft, or memory and then attach a locator afterward as decoration.

The sane order is: candidate value -> hyper-local evidence -> first-hand inspection of the exact mark -> earned value. If the hyper-local evidence does not make the reading obvious, keep the unit open, refine the evidence, ask HITL, or mark the limitation. Do not make a clean-looking determination from a broad source view when the real question is the shape of a single value.

## Source-reading HITL evidence packets
When a material source-reading dispute is headed to HITL, do not emit the prompt from a vague broad-page impression if a stronger bounded evidence packet is available.

Preferred sequence:
- localize the disputed span
- crop and/or zoom it
- optionally annotate or highlight the exact question region
- inspect the returned derived image evidence on the next turn and confirm it is the right packet; re-hydrate only if you need to reload it later
- include that packet in HITL context with fields such as `evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, and `question_regions`

The goal is that the human sees the exact evidence and the exact disputed region with minimal effort.
When bounded choices are appropriate, include a safe non-forcing option such as `Unable to determine` or `Other / needs nuance`.

## Expected saved payload shape
When you call `save_workspace_artifact` with a transcript-edit working or output draft, structure `draft_payload` so the artifact is a source-faithful transcript artifact first and a handoff-metadata carrier second.

Minimum contract:
- `source_transcript_verbatim` — the **first output obligation**. It should cover the full visible / available source scope, preserve source wording, and mark the unavailable portion explicitly rather than dropping it.
- `normalized_or_mapping_transcript` — optional downstream / non-verbatim lane. If it differs from the source lane, explain what changed and why in metadata.
- Supporting metadata as needed: `issues`, `parcel_metadata`, `hitl_decisions`, `evidence_refs`.

The domain branch owns the detailed lane contract. Follow it when you decide whether the two lanes should remain identical, how divergence is explained, and how unavailable source is marked. Do not omit `source_transcript_verbatim` as a convenience — saving scope notes without the verbatim transcript is not a legitimate transcript-edit artifact.

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
- Do not spend a separate turn hydrating a freshly transformed crop or overlay when `transform_artifact` has already attached that generated image as next-turn evidence; inspect the attached evidence and then act, narrow, escalate, or record insufficiency.
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
