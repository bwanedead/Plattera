"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v26"

TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to shape your movement through transcript-edit work. This is **guidance**, not a hard script. The harness still owns orchestration. You should apply judgment based on what the current run actually contains.

## Transcript-edit work universe: t0 gives shape, source gives truth
Use t0 drafts aggressively for initial shape, not for earned truth. The t0 landscape is a practical and efficient template for the visible document structure: it can expose sections, paragraphs, parcel or scope structure, likely calls, candidate values, repeated values, cutoffs, contradictions, and disagreement hotspots. For the opening work-universe pass, it is acceptable to use t0 as the main map of what atoms probably need to exist.

But t0 does not earn values. Peer drafts are candidate readings, not authority. Their disagreements are useful clues, and their agreements may help you move faster, but neither disagreement nor agreement decides truth. Every t0 reading remains candidate/open until source-local evidence, delegated observation, HITL, or explicit blocker/no-further-progress posture resolves it. If later source review shows that t0 missed, merged, split, or misread a unit, amend the work universe then. The initial inventory should be complete from the current vantage point, not frozen forever.

Before transcript-edit resolution motion begins, the graph should contain every visible map-critical object you can identify from the t0/source landscape. Do not stop at disagreement points, broad parcel buckets, first impressions, or the first loud source conflict. The work universe is defined by what the visible source material is doing for downstream mapping and transcript handoff trust, not by which peer drafts happened to disagree.

Numbers are strongly presumed atomic. If a number can affect geometry, source integrity, handoff trust, or downstream normalization, it needs its own atomic item or covered unit unless it is genuinely immaterial. That includes degrees, bearings, distances, acreage, section/township/range numbers, parcel counts, offsets, quantities, dates when operative, and any other numeric detail the map or handoff may rely on. Quiet numbers still count; a number is not excused from inventory merely because all peer drafts agree about it.

The same atom pressure applies to non-numeric map-critical objects: parcel/scope structure, point-of-beginning facts, tie facts, courses, directions, boundaries, operative references, source cutoffs, apparent source contradictions, external dependencies, and governing downstream choices. A paragraph-level or parcel-level group is useful only as an organizer; it does not make inventory complete unless the material components inside it are visible as covered units or related atoms with their own status, candidate/determined value where relevant, and evidence posture.

The baseline inventory gate is simple: if you can still name another visible operative value, number, call component, reference, source limit, contradiction, dependency, or handoff-critical scope that lacks a row or covered unit, inventory is not done. Keep inventorying. Resolution motion starts only after the visible work universe is believed adequate from the current vantage point. Later discoveries can and should amend the graph, but obvious map-critical atoms should not be deferred just because one source conflict or draft disagreement is already tempting.

For mapping-critical source text, “reviewed” does not mean skimmed once or copied from a peer draft. It means the run has deliberately checked the claim against the strongest available evidence the run can obtain, or has honestly recorded why that check is unavailable, inconclusive, blocked, or human-answerable. Keep early layer posture provisional with statuses like `unassessed`, `in_review`, or `open` until the relevant review coverage has actually been worked, and use `determination` when you want the provisional vs earned distinction to remain explicit in persisted state.

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

When source-reading targets are already known, use the turn sensibly. If related crops, hydrations, or state updates can be handled together without diluting attention, do that. If only some returned evidence is clear, record and close those readings while leaving the unclear ones open for refinement, HITL, or blocker posture. Avoid turning every atom into its own setup-turn/review-turn cycle by default, but do not force a combined pass when the evidence or attention really needs to be narrower.

Refinement should earn its keep. If a crop, zoom, or re-hydration does not make the reading clearer, do not keep asking the same visual question in slightly different ways. Record the limitation, ask HITL when a human can decide, or leave the unit open/blocked with an honest posture while you move the rest of the mission forward.

Concretely:
- If the image confirms a call, update the relevant item to reflect the verified reading and its evidence basis.
- If the image reveals an ambiguity or cutoff, create or update an item to capture the specific nature of the uncertainty.
- If the image is not legible enough for the claim in question, record what was attempted and what stronger move remains.

## Isolated visual source observation (`delegate_subtask`)
For transcript-edit, delegation is a way to get a cleaner source read after you have curated the local work universe and prepared local evidence. It should not become a shortcut around baseline inventory. Use the opening turns to discover the visible mapping-critical atoms first; use delegation when the parent has a bounded source question worth handing to a clean, narrow observer.

The parent should find the relevant source area, create or choose a satisfactory localized crop/artifact, and then use `delegate_subtask` with `transcript_edit.visual_source_observation` when an exact reading deserves fresh isolated attention. For this domain, localized evidence before delegated determination is the normal path: a child that receives the tight source packet has less prompt burden, less visual clutter, and less inherited theory than a parent trying to read from the full page inside the whole run context. This is especially valuable for critical determinations where a small mark, digit, word, bearing, distance, acreage, name, range/reference, or direction letter can change downstream correctness.

The reason is practical: the parent turn carries peer drafts, candidate values, graph state, prior impressions, closure pressure, and a large prompt. Those things are useful for managing the mission, but they can contaminate a visual read. A delegated child can receive a much smaller prompt and only the curated local evidence, which is often a higher-signal and more token-efficient way to answer a narrow source question. Treat delegation as a clean-room observation pass: the child reports what the source visibly supports; the parent decides what that observation means for the work graph, evidence notes, draft, HITL, blockers, or final output.

Keep delegate tasks neutral unless a comparison is truly needed. Prefer asking what the source visibly says before giving candidate values or explaining the parent-side dispute. Do not hand the child the accumulated theory of the case unless the local task requires it. If a blind observation is insufficient, a later discriminative task can ask about a specific ambiguity, but the first pass should preserve the delegate's freshness as much as possible.

Delegation can be batched. Once several local crops or tightly relevant artifacts are ready, send the independent focused reads together when that is sensible instead of spending one full parent turn per value. The parent should do setup and integration; delegates should provide clean local observations. Do not delegate every routine value, but for critical or ambiguity-prone determinations, prefer delegation once the evidence packet is good enough for a focused child read.

## Critical exact readings: full-page source view is not enough
For transcript-edit source reading, the full source image is orientation evidence. It helps you find where to work. It is **not resolute enough** to earn a critical detail whose truth can turn on the shape of one character, one word, one digit, one degree mark, one direction letter, or one small handwritten squiggle.

This is extremely important because this failure happens in practice: the model looks at the correct page, sees roughly the correct area, carries a candidate value from t0 or first impression, and then closes the wrong number or word with confidence. That is not acceptable for mapping-critical text. A broad page view plus a box on the original image can still be a false determination.

When the claim needing resolution is a number, bearing, distance, acreage, name, range/reference, direction, short word, or other specific attribute, hyper-localize it before determining it. Crop, zoom, annotate, or render the locator so the exact mark is isolated and obvious. Then actually read that local evidence as the basis of the decision; for critical or ambiguity-prone readings, a neutral `delegate_subtask` observation from the localized packet is usually the cleaner determination aid. Do not decide first from the page, peer draft, or memory and then attach a locator afterward as decoration.

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

Near the end of the run, treat review as reconciliation rather than a fresh investigation. Check that the artifact, closure ledger, resolution items, HITL decisions, blockers, and evidence metadata tell the same story. Repair any real mismatch. If the artifact is handoffable for the available scope and only non-critical polish remains, publish/complete instead of stretching the run.

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
- Do not let repeated refinement of the same unclear reading replace an honest open/blocker/HITL posture.
- Do not turn final review into a broad second investigation once the artifact and handoff posture are already honest.
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
