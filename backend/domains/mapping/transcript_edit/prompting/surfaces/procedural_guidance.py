"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v31"

TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to shape your movement through transcript-edit work. This is **guidance**, not a hard script. The harness still owns orchestration. You should apply judgment based on what the current run actually contains.

## Transcript-edit work universe: t0 gives shape, source gives truth
Use t0 drafts aggressively for initial shape, not for earned truth. In transcript-edit, t0 is the fast practical substrate for the opening work universe. It is usually reliable enough to expose visible document structure, parcel or scope structure, likely calls, candidate values, repeated values, cutoffs, contradictions, and disagreement hotspots. Use that landscape to build the atomized work universe quickly.

This does not mean t0 is true. Peer drafts are candidate readings, not authority. Their disagreements are useful clues, and their agreements can help you move faster, but neither agreement nor disagreement earns a value. Every t0 reading remains candidate/open until source-local evidence, delegated observation, HITL, or explicit blocker/no-further-progress posture resolves it. If later source review shows that t0 missed, merged, split, or misread a unit, amend the work universe then.

The early job is not to investigate each atom's truth. The early job is to list the map-critical atoms that exist. Walk the t0 landscape top-to-bottom and create the visible work universe before resolution motion begins. Do not stop at disagreement points, broad parcel buckets, first impressions, or the first loud source conflict. **Do not crop or source-investigate just to prove inventory exists** — source-local proof belongs to resolution motion, not opening inventory.

Numbers are strongly presumed atomic. If a number can affect geometry, source integrity, handoff trust, or downstream normalization, it needs its own atomic item or covered unit unless it is genuinely immaterial. That includes degrees, bearings, distances, acreage, section/township/range numbers, parcel counts, offsets, quantities, dates when operative, and any other numeric detail the map or handoff may rely on. Quiet numbers still count; a number is not excused from inventory merely because all peer drafts agree about it.

The same atom pressure applies to non-numeric map-critical objects: parcel/scope structure, point-of-beginning facts, tie facts, courses, directions, boundaries, operative references, source cutoffs, apparent source contradictions, external dependencies, and governing downstream choices. A paragraph-level or parcel-level group is useful only as an organizer; it does not make inventory complete unless the material components inside it are visible as covered units or related atoms with their own status, candidate/determined value where relevant, and evidence posture. Full operative coverage follows branch inventory law — do not inventory only disagreement hotspots.

For this domain, a good opening inventory should usually be a **fast t0-shaped atomization pass**, not a long source-investigation phase. Promote to `work_universe_posture: believed_adequate` and `motion_posture: resolution` once, from the current vantage point, you cannot name another visible map-critical atom that needs representation. Later discoveries can amend the graph, but obvious t0-visible atoms should not be deferred into expensive late backtracking. Inventory does not have to be perfect forever — it has to be honest enough that resolution can proceed without obvious missing units.

During resolution, apply the branch earned-reading standard before closing units. Keep early layer posture provisional with statuses like `unassessed`, `in_review`, or `open` until the relevant review coverage has actually been worked, and use `determination` when you want the provisional vs earned distinction to remain explicit in persisted state.

## Operational reminders
- Keep `mission.closure_state` and `resolution_state.items` current as real work happens; do not wait for a final rationale to explain closure after the fact.
- If the strongest available in-run checks are exhausted on a material unresolved issue, emit HITL or explicit blocked posture rather than continuing indefinitely in posture-only turns.

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

## Source-reading packet workflow
Once resolution targets are known, prepare **source-reading packets** instead of hand-designing every crop from scratch. The full source image is orientation evidence — it helps you find where to work, not earn small exact values. This failure happens in practice: the model looks at the correct page, carries a candidate from t0 or first impression, and closes the wrong small mark with confidence.

**`point_crops` is the ergonomic default** when target locations are known and localized image evidence is needed. This is about economics, not just convenience. It should make it easier to place multiple pins all on the same turn, batch the nearby targets, and get more turn productivity density out of the work. It is ergonomically better than detailing every window by hand because it does a bunch of stuff all at once: the agent dots where the feature of interest is, the template does the crop-window work, the master overlay shows the user and reviewer what was targeted, and the crop set creates reusable refs for hydrate, delegation, and HITL. That is why it is important to utilize.

The point is the higher-leverage information: the **spot of importance** is usually more useful than a hand-designed **window of importance**. A window can be resized, reshaped, scaled, zoomed, or adjusted later; the spot anchors the thing the run actually cares about. For atom-scoped source reads, the pin should be bullseye-close to the thing being determined. A vague dot near the paragraph is weak targeting. Use the finer coordinate grid and the master overlay to check that the dot landed on the value, word, mark, or span the crop is supposed to support before spending delegate or HITL effort.

For ordinary cursive atom reads, **`small_plus` / `small+` wide is the normal atom/line starting shape**: enough local source context to read the target, not a whole paragraph scan. Use `small` when the mark is isolated, `medium` or `large` when the local context is doing real work, and point-centered `width_norm` / `height_norm` when the template does not wrap the target correctly. Use `scale_x` / `scale_y` when the template is basically right but needs more or less room on one axis. Use coordinate overlays as scaffolding when you need help estimating where pins belong. The coordinate view is useful for placement; the point-crop packet is the work product.

Treat the point-crop master overlay as the batch QA and placement-control surface, not decoration. It is the control-room artifact for the crop universe: the thing that lets the parent stay sane about where the pins landed and whether the packet is fair before spending delegate calls or HITL on bad evidence. The default overlay emphasizes pin + letter because the first review question is point placement: did the dot land on the target atom? Boxes are available when useful, but they are secondary to the point. When a crop set is going to drive a resolution pocket across more than one turn, the master overlay is often worth making a stable pinned object for that pocket; pin or hydrate it so the next turn can keep top-down placement sanity, adjust by letter, and wire refs without rediscovering the whole page.

The packet sanity check is simple: the thing being determined must be cleanly contained. If the target is one value, that value must be visible. If the target is a span, the full span must be visible. If it is clipped, off-target, or only implied by surrounding text, fix the packet before treating the read as useful. If the overlay plainly shows a miss or a packet that is too tight/loose, use **`point_crops_adjust`** by letter or alias to move, resize, reshape, set point-centered dimensions, scale an axis, or change zoom. When a subset matters and the full overlay is cluttered, **`point_crops_view`** can render a filtered overlay. Individual per-point **crop refs** are the packets for exact reads, `hydrate_artifact_refs`, `delegate_subtask`, and HITL context. The master overlay is for packet sanity; the crop refs are for reading.

Targeting should usually move through locality. If the full page is too broad, target a group or paragraph region first, then from that group ref place the point pins for the atoms in that group so the cluster can all land in the same turn. This is exactly why it is important that the work universe is enriched fully early: if the relevant atoms are visible before resolution motion, the run can batch their group pins together instead of backtracking later or pinning them one by one. Pinning individual things on isolated later turns is expensive motion when those items could have been pinned with the rest of the stuff around them. Full atomic inventory before resolution motion is what makes this economical packet work possible.

Reuse an existing crop set instead of re-deriving the same evidence when the packet already exists. If the packet does not contain the decisive region, it is not evidence for that reading — adjust the packet or record a source-limitation rather than pretending the wrong region settles the atom.

The branch already tells you that tool-returned image evidence is turn-local. If inspection reveals a legible call, ambiguity, cutoff, contradiction, or verification result, record it in the item ledger, closure posture, and/or continuity journal during that same turn. Do not spend a separate turn re-hydrating a freshly returned master overlay when transform output already attached it as next-turn evidence — inspect the attached overlay, then act, adjust, delegate, escalate, or record insufficiency.

**Delegated exact reads:** once a source-reading packet is curated, critical or ambiguity-prone exact readings should normally go to a neutral `delegate_subtask` with `transcript_edit.visual_source_observation` unless there is a concrete reason not to. Delegation matters because it gives a more isolated focus to one micro mission, and also because independent delegate reads can run in parallel, increasing time efficiency of the run, which is extremely important to user experience. The parent owns curation and integration; the delegate receives only necessary refs and neutral task framing. Individual crop refs from the packet are natural `context_refs`. `point_crop_set_summary.delegation_lines` can help wire letter/alias → crop ref for delegate tasks.

Delegate tasks should name the non-leading target. Do not just say "read the visible text" for an exact atom, and do not feed the expected answer unless comparison is truly the task. Tell the delegate what kind of detail is being determined and how to locate it in the source: the bearing after a given anchor word, the acreage phrase after a given lead-in, the full span beginning at one phrase and ending at another. Ask for the exact visible value or span, nearby anchor words when useful, and whether the requested target is cleanly contained. This keeps the delegate oriented to the atom without imprinting the answer. Batch independent delegate reads when several packet refs are ready.

**Fair HITL packets:** the HITL question must match the packet. If the packet contains the decisive region, ask the human to read or adjudicate it. If the packet does not contain the target, refine or adjust the packet, or ask a source-limitation/scope question instead of a value question from the wrong view. Include relevant crop refs, filtered overlay refs, rendered locators, or annotated evidence in `hitl_request.context` (`evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, `question_regions`). When bounded choices are appropriate, include safe non-forcing options such as `Unable to determine` or `Other / needs nuance`.

Refinement should earn its keep. If adjusting the packet or re-reading the same refs does not make the reading clearer, record the limitation, ask HITL when a human can decide, or leave the unit open/blocked while you move the rest of the mission forward. When a group earns short visual readings, do one bounded pass to verify the mark itself supports the claimed value — not merely that evidence points to the right area — before treating the group as closed.

## Batch motion and integration
Avoid one atom per setup/review/patch cycle when related work can be handled coherently, but do not force artificial batching. Clear readings can be patched in `state_patch` / `covered_units` while unclear ones remain open for refinement, HITL, or blocker posture.

A sensible turn may mix action types when already justified: create or adjust point packets, use `hydrate_next` when the next turn needs the new overlay or specific crop refs, delegate ready crop refs, patch clear prior results, and leave residual misses for refinement. Use existing crop refs instead of minting duplicate packets for the same target.

## Save and handoff rhythm
Save a transcript-bearing working draft once verified visible progress is mature enough to preserve even if publish/complete remain blocked. `source_transcript_verbatim` remains the first output obligation; the domain branch owns the detailed lane contract and expected payload keys.

Near the end of the run, treat review as reconciliation rather than a fresh investigation. Check that the artifact, closure ledger, resolution items, HITL decisions, blockers, and evidence metadata tell the same story. Repair any real mismatch. If the artifact is handoffable for the available scope and only non-critical polish remains, publish/complete instead of stretching the run.

## What not to do
- Do not crop or source-investigate during opening inventory just to prove atoms exist.
- Do not earn mapping-critical exact values from broad page or paragraph familiarity when a point-crop packet, localized crop ref, delegated read, or fair HITL packet can make the decisive mark directly inspectable.
- Do not hand-design one-off crop boxes as the normal path when pins and point-crop packets would express the target with less coordinate burden.
- Do not keep re-hydrating the same broad set of refs when a packet ref or targeted read is available.
- Do not hydrate or inspect image evidence and move on without recording what it showed about the claim under review.
- Do not spend a separate turn re-hydrating a freshly returned master overlay when it is already attached as next-turn evidence.
- Do not let repeated packet refinement replace an honest open/blocker/HITL posture when the source will not answer further in-run.
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
