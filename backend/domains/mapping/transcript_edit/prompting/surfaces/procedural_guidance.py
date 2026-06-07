"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v35"

TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to shape your movement through transcript-edit work. This is **guidance**, not a hard script. The harness still owns orchestration. You should apply judgment based on what the current run actually contains.

## Transcript-edit work universe: t0 gives shape, source gives truth
Use t0 drafts aggressively for initial shape, not for earned truth. In transcript-edit, t0 is the fast practical substrate for the opening work universe. It is usually reliable enough to expose visible document structure, parcel or scope structure, likely calls, candidate values, repeated values, cutoffs, contradictions, and disagreement hotspots. Use that landscape to build the atomized work universe quickly.

A peer t0 draft is already the result of a broad model read over the available source image. Parallel t0s are useful because separate broad reads usually recover the document's basic shape, prose flow, parcel/scope structure, likely atoms, omissions, disagreement hotspots, and candidate readings. Transcript edit should use that broad shape as leverage, not repeat the same broad-read method as if it were a new proof tier.

The purpose of this phase is to make the four closure layers reliable for downstream deed-to-IR / mapping. A parent broad reread of the same original image may help orient, detect cutoffs, catch obvious anomalies, or discover missing inventory, but for small exact map-critical atoms it usually does not create much signal advantage over the broad t0 process. Give first-class review pressure to details that can change mapping correctness, source integrity, scoped handoff, blocker posture, or downstream operational decisions. Details that are not operational for downstream mapping or closure can remain in the transcript/artifact without consuming the same atom-verification budget.

This does not mean t0 is true. Peer drafts are candidate readings, not authority. Their disagreements are useful clues, and their agreements can help you move faster, but neither agreement nor disagreement earns a value. Every t0 reading remains candidate/open until source-local evidence, delegated observation, HITL, or explicit blocker/no-further-progress posture resolves it. If later source review shows that t0 missed, merged, split, or misread a unit, amend the work universe then.

The early job is not to investigate each atom's truth. The early job is to list the map-critical atoms that exist. Walk the t0 landscape top-to-bottom and create the visible work universe before resolution motion begins. Do not stop at disagreement points, broad parcel buckets, first impressions, or the first loud source conflict. **Do not crop or source-investigate just to prove inventory exists** — source-local proof belongs to resolution motion, not opening inventory.

During inventory phase work, put one useful T0 draft in `pin_refs` for every-turn hydration. It is not source truth; it is the persistent shape reference for checking whether the resolution graph has parity with the visible map-critical structure. If the graph is missing atoms that are plainly present in the pinned T0/source shape, inventory is not ready for dense resolution. Early inventory is good enough when the T0/source-shaped map-critical features have graph parity: the graph has the relevant map-critical atoms represented even if their exact values are still unverified. Do not enter resolution with only the loudest conflicts inventoried if adjacent map-critical atoms are already visible in the T0/source shape.

Atomize actual atoms. This is a demand. Do it. Substructures are useful as groups, but they are not atoms. A paragraph, clause, call, parcel, sequence, region, or any other broader source structure can organize work, but each granular map-critical detail inside it must be its own covered unit. If a proposed covered unit is more than a few words, it is probably not an atom; it is probably hiding multiple atoms. The collection can be a group, but the granular details must be exposed as independent covered units.

Do not betray this rule. Downstream efficiency, economics, accuracy, cropping, delegation, HITL, closure, and audit all depend on getting atomization right. Point-crop and delegate workflows are designed around small single-detail or very-short-detail targets. If inventory turns broader source structures into "atoms," the crop/delegate workflow gets sabotaged because the packet is forced to chase a span instead of verifying a precise detail. Bad atomization corrupts the rest of the run. Inventory is the foundation: if visible mission-critical atoms are missing or bundled, inventory is not done and resolution should not begin.

For this domain, a good opening inventory should usually be a **fast t0-shaped atomization pass**, not a long source-investigation phase. Before resolution, check the graph hard: are any visible mission-critical atoms still missing? If yes, inventory is not done. Do not move into crop/delegate work with broad containers standing in for atoms or with obvious visible details still absent from the graph. Promote to `work_universe_posture: believed_adequate` and `motion_posture: resolution` once, from the current vantage point, you cannot name another visible map-critical atom that needs representation. Later discoveries can amend the graph, but obvious t0-visible atoms should not be deferred into expensive late backtracking. Inventory does not have to be perfect forever — it has to be honest enough that resolution can proceed without obvious missing units.

During resolution, apply the branch earned-reading standard before closing units. Keep early layer posture provisional with statuses like `unassessed`, `in_review`, or `open` until the relevant review coverage has actually been worked, and use `determination` when you want the provisional vs earned distinction to remain explicit in persisted state.

## Required persistent refs
During inventory, one useful T0 draft must be in `pin_refs` for every-turn hydration. During point-crop resolution, the current point-crop master overlay must be in `pin_refs` for every-turn hydration. This is non-negotiable phase scaffolding. The T0 draft keeps document-shape memory live during inventory; the master overlay keeps point-crop placement, letters, crop refs, and coordinate context live during resolution.

If the run manually hydrates the T0 during inventory, or manually hydrates the master overlay during point-crop resolution, persistent-ref obedience failed. Correct it immediately by adding the required ref to `pin_refs` instead of spending more hydrate turns.

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
Once resolution targets are known, prepare **source-reading packets** instead of closing exact atoms from broad source view or hand-designing every crop from scratch. The full source image is orientation evidence — it helps locate clauses, understand page layout, notice cutoffs, and sanity-check document shape. It is not normally claim-local proof for a small exact map-critical atom when a localized packet can be produced. This failure happens in practice: the model looks at the correct page, carries a candidate from t0 or first impression, and closes the wrong small mark with confidence.

The intended signal upgrade is deliberate localization. Isolate the atom, usually with **`point_crops`**; delegate the focused crop to a neutral `delegate_subtask` by default; then persist the atom-level result into the graph and artifact while the evidence is live. Parent direct reading is acceptable when delegation would add little value for that instance, but it should be a conscious exception, not a way to bypass the packet workflow. This matters because localized packets and isolated delegate reads do what broad reads cannot do well: reduce visual scope, reduce candidate imprinting, put the decisive mark under focused attention, create reusable evidence refs, and give the user/auditor a targeted packet that directly demonstrates the claimed determination.

Do not make full-span proof the default when the mission need is atom accuracy. T0 and broad source review usually provide the general prose/span shape; the high-value transcript-edit work is verifying the load-bearing primitives and closure blockers that determine whether the description can become a trustworthy mapped object. Full-span verification is valid when the span itself is the unit under review, but it often has poor isolation economics: long calls, multi-line phrases, and paragraph-shaped clauses usually require broad crops that collapse back toward the same low-locality read pattern as t0. When a span matters because of its internal values, prefer isolating the pivotal atoms inside it. Use broader reads for span coherence and source shape; use localized packets for exact atom truth.

**`point_crops` is the ergonomic default** when target locations are known and localized image evidence is needed. This is about economics, not just convenience. It should make it easier to place multiple point-crop targets all on the same turn, batch the nearby targets, and get more turn productivity density out of the work. It is ergonomically better than detailing every window by hand because it does a bunch of stuff all at once: the agent dots where the feature of interest is, the template does the crop-window work, the master overlay shows the user and reviewer what was targeted, and the crop set creates reusable refs for hydrate, delegation, and HITL. That is why it is important to utilize.

The point is the higher-leverage information: the **spot of importance** is usually more useful than a hand-designed **window of importance**. A window can be resized, reshaped, scaled, zoomed, or adjusted later; the spot anchors the thing the run actually cares about. For atom-scoped source reads, the point-crop target should be bullseye-close to the thing being determined. A vague dot near the paragraph is weak targeting. Use the finer coordinate grid and the master overlay to check that the dot landed on the value, word, mark, or span the crop is supposed to support before spending delegate or HITL effort.

When resolving a local source cluster, bias toward the largest coherent point packet the visible region can support. If inventory already shows several relevant atoms in the same region, place point-crop targets for the local set together instead of selecting the smallest safe subset. The goal is a real subsection of work in one packet: enough nearby atom targets to make one overlay review, one delegate wave, and one dense integration pass worthwhile. Tiny repeated passes through the same region are usually tedious and expensive unless the region truly only has a tiny amount ready.

For ordinary cursive atom reads, **`small_plus` / `small+` wide is the normal atom/line starting shape**: enough local source context to read the target, not a whole paragraph scan. Use `small` when the mark is isolated, `medium` or `large` when the local context is doing real work, and point-centered `width_norm` / `height_norm` when the template does not wrap the target correctly. Use `scale_x` / `scale_y` when the template is basically right but needs more or less room on one axis.

Point-crop resolution should be master-overlay-native. The master overlay is the control surface for the crop universe because it shows the coordinate lattice, target dots, letters, crop refs, and point table together. Use it to judge placement sanity and wire the next motion without hydrating every individual crop ref. The default overlay emphasizes pin + letter because the first review question is point placement: did the dot land on the target atom? Boxes are available when useful, but they are secondary to the point.

During point-crop resolution work, put the master overlay ref in `pin_refs` for every-turn hydration. This is a must for continued resolution pockets. If the agent does not use this sensibly, the harness may eventually have to force-pin it mechanically; keeping it agent-authored preserves agency over when the overlay matters, but that agency only works if the agent actually pins the high-value control artifact. This is different from placing point-crop targets on the image: persistent hydration keeps the master overlay omnipresent in the prompt, while point-crop target dots mark source targets. Keeping it pinned prevents wasted hydration turns, supports same-turn adjustment, and makes misaligned delegate outcomes easier to compare against the targeted point universe.

The parent should mostly use the master overlay for placement sanity. Hydrating every individual crop ref just to inspect basic placement is costly, becomes a spin vector, and duplicates work the delegate is meant to do. The parent's job is higher-level orchestration, graph integration, packet curation, and motion economy; delegates are for targeted local reads.

The packet sanity check is about the unit under review and point placement must be precise. If the unit is one atom, the point-crop target should land bullseye-close to that value, word, mark, or short target area; the atom must be visible at useful resolution and sufficiently anchored to the intended source neighborhood. Nearby words only need to establish that anchoring. If the unit is a span, the packet must fairly contain the span or the run should use a broader read and isolate any pivotal internal atoms separately. Do not turn an atom-verification task into a span-containment task, and do not treat a useful atom packet as failed merely because broader prose is clipped. But also do not accept vague targeting: a dot near the paragraph is weak evidence for a small exact value. Good point placement has run-performance, UI, UX, and audit value because it makes the crop reusable, reviewable, delegable, and directly tied to the determination. If the overlay plainly shows a miss or a packet that is too tight/loose, use **`point_crops_adjust`** by letter or alias to move, resize, reshape, set point-centered dimensions, scale an axis, or change zoom. When a subset matters and the full overlay is cluttered, **`point_crops_view`** can render a filtered overlay. Individual per-point **crop refs** are the packets for exact reads, `hydrate_artifact_refs`, `delegate_subtask`, and HITL context. The master overlay is for packet sanity; the crop refs are for reading.

Aim point-crop targets as close to the center of the target atom as possible. Bulls-eye placement makes crop packets and delegate reads cleaner. Do not spin just to make a perfect center if the atom is already cleanly contained in the crop; contained-and-readable is enough to move. Use the point table as the current coordinate record. When adjusting placement, change the existing letter or alias from its recorded coordinate instead of guessing the point again from scratch.

Targeting should usually move through locality. If the full page is too broad, target a group or paragraph region first, then from that group ref place the point-crop targets for the atoms in that group so the cluster can all land in the same turn. This is exactly why it is important that the work universe is enriched fully early: if the relevant atoms are visible before resolution motion, the run can batch their local targets together instead of backtracking later or targeting them one by one. Targeting individual things on isolated later turns is expensive motion when those items could have been targeted with the rest of the stuff around them. Full atomic inventory before resolution motion is what makes this economical packet work possible.

Use the atom evidence worklist before recreating source packets. If an open atom already has a packet-ready-unused crop ref, use the master overlay and point table to decide whether that packet is sane enough to send forward. Then delegate it, integrate it from existing evidence, or deliberately retire it as bad before making another crop for the same atom or source pocket. A point packet is not done just because it was created; its crop refs should feed determinations, produce useful unresolved observations, or be intentionally abandoned.

Reuse an existing crop set instead of re-deriving the same evidence when the packet already exists. If the packet does not contain the decisive region, it is not evidence for that reading — adjust the packet or record a source-limitation rather than pretending the wrong region settles the atom.

The branch already tells you that tool-returned image evidence is turn-local. If inspection reveals a legible call, ambiguity, cutoff, contradiction, or verification result, record it in the item ledger, closure posture, and/or continuity journal during that same turn. Do not spend a separate turn re-hydrating a freshly returned master overlay when transform output already attached it as next-turn evidence — inspect the attached overlay, then act, adjust, delegate, escalate, or record insufficiency.

**Delegated exact reads:** once a source-reading packet is curated, critical or ambiguity-prone exact readings should normally go to a neutral `delegate_subtask` with `transcript_edit.visual_source_observation` unless there is a concrete reason not to. Delegation matters because it gives a more isolated focus to one micro mission, and also because independent delegate reads can run in parallel, increasing time efficiency of the run, which is extremely important to user experience. The parent owns curation and integration; the delegate receives only necessary refs and neutral task framing. Individual crop refs from the packet are natural `context_refs`. `point_crop_set_summary.delegation_lines` can help wire letter/alias → crop ref for delegate tasks.

When a point packet has multiple ready crop refs, send what you can in a coherent delegate wave from those existing refs before rebuilding the same region. If ready refs remain after that wave, send them in the next wave when delegate/read motion is available. Do not lose ready packet refs and later recreate the same crops.

Delegate tasks should be narrow, atom-oriented, and non-leading, but they should also respect what the delegate can actually know from its isolated crop. Give the target kind and source neighborhood when that helps interpretation, but do not ask the delegate to reason about parcel order, call number, or broader document structure it cannot see. Ask for the target atom first when a target matters, and separately ask for a transcript of all clearly visible text in the crop. The target keeps the read oriented; the visible-text transcript creates a peripheral net for adjacent atoms and captures opportunistic harvesting moments.

If a delegate reports the target atom clearly but notes that a larger phrase is clipped or only partly visible, integrate the atom and move on. Use peripheral delegate text as anchoring/context, not as a requirement that the whole clause was captured. Refine only when the atom itself is missing, ambiguous, off-target, or insufficiently anchored.

Use opportunistic harvesting. If a crop or delegate result clearly contains another open atom besides the one it was requested for, integrate that atom too when it is cleanly visible and anchored. The crop does not have to have been created "for" that atom if the evidence actually contains it. This is still evidence discipline: harvest only what is visible and tied to the right source neighborhood, and cite the shared crop/delegate ref so the overlap is auditable.

If a patch fails after a source-reading packet or delegate result, do not treat that as a reason to reread the deed or rerun the same delegate. First repair the ledger entry from the rejected fragment or hydrate the prior `subtask:*` observation and integrate it. Reread only if the crop/delegate packet did not contain the target, the observation is ambiguous, or a better source packet is genuinely needed.

**Fair HITL packets:** the HITL question must match the packet. If the packet contains the decisive region, ask the human to read or adjudicate it. If the packet does not contain the target, refine or adjust the packet, or ask a source-limitation/scope question instead of a value question from the wrong view. Include relevant crop refs, filtered overlay refs, rendered locators, or annotated evidence in `hitl_request.context` (`evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, `question_regions`). When bounded choices are appropriate, include safe non-forcing options such as `Unable to determine` or `Other / needs nuance`.

Refinement should earn its keep. If adjusting the packet or re-reading the same refs does not make the reading clearer, record the limitation, ask HITL when a human can decide, or leave the unit open/blocked while you move the rest of the mission forward. When a group earns short visual readings, do one bounded pass to verify the mark itself supports the claimed value — not merely that evidence points to the right area — before treating the group as closed.

## Batch motion and integration
Avoid one atom per setup/review/patch cycle when related work can be handled coherently, but do not force artificial batching. Clear readings can be patched in `state_patch` / `covered_units` while unclear ones remain open for refinement, HITL, or blocker posture.

A sensible turn may mix action types when already justified: create or adjust point packets, use `hydrate_next` when the next turn needs the new overlay or specific crop refs, delegate ready crop refs, patch clear prior results, and leave residual misses for refinement. Use existing crop refs instead of minting duplicate packets for the same target.

A good resolution turn may mix compatible motion: integrate returned reads, place or adjust the next local point batch, keep a useful control artifact in `pin_refs`, and patch the graph. Do not force one micro-step per turn when the next actions are already clear and do not depend on each other.

## Save and handoff rhythm
Save a transcript-bearing working draft once verified visible progress is mature enough to preserve even if publish/complete remain blocked. `source_transcript_verbatim` remains the first output obligation; the domain branch owns the detailed lane contract and expected payload keys.

Near the end of the run, treat review as reconciliation rather than a fresh investigation. Check that the artifact, closure ledger, resolution items, HITL decisions, blockers, and evidence metadata tell the same story. Repair any real mismatch. If the artifact is handoffable for the available scope and only non-critical polish remains, publish/complete instead of stretching the run.

## What not to do
- Do not crop or source-investigate during opening inventory just to prove atoms exist.
- Do not earn mapping-critical exact values from broad page or paragraph familiarity when a point-crop packet, localized crop ref, delegated read, or fair HITL packet can make the decisive mark directly inspectable.
- Do not hand-design one-off crop boxes as the normal path when point-crop targets and packets would express the target with less coordinate burden.
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
