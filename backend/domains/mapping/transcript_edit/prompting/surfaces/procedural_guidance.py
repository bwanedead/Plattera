"""Procedural guidance for transcript_edit without hard-coding a runtime script."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py"
)
TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_VERSION = "v38"

TRANSCRIPT_EDIT_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to shape your movement through transcript-edit work. This is **guidance**, not a hard script. The harness still owns orchestration. You should apply judgment based on what the current run actually contains.

## The workflow chain
This domain is one machine with a dependency chain, not a pile of tools. Understand what each stage feeds, because the quality ceiling of every stage is set by the stage before it:

**t0 shape → atom inventory → point targets → crop packets → delegate reads → earned values → honest closure → real geometry.**

- An atom is a **single value at a single spot on the page** — one number, one word, one mark that must be independently verified. The mapping-critical atoms are the raw parameters that will programmatically generate the final map: bearings, distances, directions, quantities, acreage, identifiers, monument names. If a parameter is wrong, the map is wrong; the prose between parameters is webbing — trust it by default, investigate it when it looks weird, but spend verification budget on the values that become geometry.
- A point crop can only land on a point. The whole crop apparatus — point targeting, template windows, the master overlay, adjustment — is built for single localized marks, not spans. To the degree an "atom" is actually a span, to that degree the point-crop machinery is being sabotaged: the window cannot contain the claim, the dot stops meaning anything, and the packet stops being evidence.
- A delegate can only verify what its crop shows. The delegate's entire world is the packet you curated; a precise atom gives the delegate one mark to read and report. A span-shaped atom forces the delegate to adjudicate text it cannot fully see — that is how delegate answers get muddy. Still ask delegates for all clearly visible text: the span is requested for opportunistic harvesting of nearby atoms, never as the determination target.
- A `determined_value` is only as trustworthy as the read that earned it, and closure is only as honest as its determined values. Deed-to-IR consumes those values as machine parameters and does not re-litigate them; what you earn here is what gets built.

Every stage inherits the previous stage's discipline or its corruption. Atomize precisely and the machine runs clean: points land, crops read, delegates answer in one word, values patch, closure earns itself.

## Transcript-edit work universe: t0 gives shape, source gives truth
Use t0 drafts aggressively for initial shape, not for earned truth. T0 is the fast substrate for visible document structure, local clusters, likely mission-critical atoms, omissions, contradictions, cutoffs, disagreement hotspots, and candidate readings. Use that broad shape as leverage; do not repeat the same broad-read method as if it were a new proof tier. A parent broad reread may orient or catch missing inventory, but for small exact map-critical atoms it usually does not beat the T0-shaped opening process.

The early job is not to investigate each atom's truth. The early job is to list the mission-critical atoms that exist. Walk the T0/source shape top-to-bottom and build the visible work universe before resolution motion begins. Do not stop at disagreement points, broad buckets, first impressions, or the loudest conflict. **Do not crop or source-investigate just to prove inventory exists** — source-local proof belongs to resolution motion, not opening inventory.

This does not mean T0 is true. Peer drafts are candidate readings, not authority. Their disagreements are useful clues, and their agreements can help you move faster, but neither agreement nor disagreement earns a value. Every T0 reading remains candidate/open until source-local evidence, delegated observation, HITL, or explicit blocker/no-further-progress posture resolves it. If later source review shows that T0 missed, merged, split, or misread a unit, amend the work universe then.

Atomize actual atoms. This is a demand. Do it. Use T0 wording as the placeholder for atom registration; source proof earns or corrects it later. Atoms are granular exact details. A full call must NOT be a covered unit. NO EXCEPTIONS. If a call contains multiple unit-differentiated or independently checkable details, each detail is its own covered unit: one bearing/orientation detail, one distance/measurement detail, one quantity, one boundary/location detail, one named/identified reference, etc. The full call can only be a group or organizer. For the love of god, do not make the full call the atom; each exact item inside the call is the atom. DO NOT BREAK THIS. IF THIS IS VIOLATED IT CORRUPTS THE ENTIRE RUN: crops chase spans, delegates get muddy, closure lies, and downstream mapping inherits fake certainty.

When T0 shows an atom, do not leave the atom blank. Put the T0 representation in `candidate_values` as the placeholder for targeting and review. Candidate values are NOT earned truth; source proof later earns, corrects, or rejects them. This matters because the placeholder makes point-crop targeting more intuitive, gives the graph a tangible atom shape for the user to inspect, and gives future turns more context for reference and anchoring until an earned `determined_value` replaces it.

Broader source structures are useful as groups, but they are not atoms. If a proposed covered unit is more than a few words, assume it is probably hiding multiple atoms until proven otherwise. Each granular mission-critical detail must be exposed as its own covered unit so it can be verified, delegated, blocked, reopened, or closed by itself. Before resolution, check the graph hard: if visible mission-critical atoms are missing or bundled, inventory is not done.

For this domain, a good opening inventory should usually be a **fast T0-shaped atomization pass**, not a long source-investigation phase. Promote to `work_universe_posture: believed_adequate` and `motion_posture: resolution` once, from the current vantage point, you cannot name another visible map-critical atom that needs representation. Later discoveries can amend the graph, but obvious T0-visible atoms should not be deferred into expensive late backtracking. Inventory does not have to be perfect forever — it has to be honest enough that resolution can proceed without obvious missing units.

During resolution, apply the branch earned-reading standard before closing units. Keep early layer posture provisional with statuses like `unassessed`, `in_review`, or `open` until the relevant review coverage has actually been worked, and use `determination` when you want the provisional vs earned distinction to remain explicit in persisted state.

## Required persistent refs
Turn 1 inventory setup: put one useful T0 draft in `pin_refs` for every-turn hydration. The first continued point-crop resolution pocket must likewise put the current point-crop master overlay in `pin_refs`. Do not treat this as optional housekeeping. These are the two high-value control artifacts for the two phases: T0 keeps document-shape memory live while inventory is being built; the master overlay keeps the crop universe live while resolution is being earned.

`pin_refs` means durable attention support: the harness mechanically carries the ref forward and auto-surfaces/hydrates it before future choose-action turns until it is unpinned or expires. This matters because losing those control artifacts makes the run stupid and expensive. Without pinned T0, inventory drifts, misses visible atoms, and starts resolving from an incomplete work universe. Without pinned master overlay, point-placement memory disappears, the agent burns turns rehydrating or re-guessing, delegate outcomes become harder to compare against the targeted point universe, and crop spin gets worse.

If the run manually hydrates the T0 during inventory, or manually hydrates the master overlay during point-crop resolution, persistent-ref obedience failed. Correct `pin_refs` immediately instead of spending more hydrate turns.

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
Once resolution targets are known, use **source-reading packets** for exact atom truth. Broad source view and T0 give orientation and span shape; they usually do not earn small exact values. Do not turn atom verification into full-span proof. If the span itself is the unit, use a broader read; if the span matters because of internal details, isolate the pivotal atoms. The intended signal upgrade is deliberate localization: reduce visual scope, reduce candidate imprinting, put the decisive mark under focused attention, create reusable evidence refs, and give the user/auditor a targeted packet that directly demonstrates the claimed determination.

**`point_crops` is the ergonomic default** when target locations are known and localized image evidence is needed. This is about economics, not just convenience. It lets the agent mark the spot of importance, lets templates handle the crop window, produces a master overlay for review, and creates reusable crop refs for `hydrate_artifact_refs`, `delegate_subtask`, HITL, and audit. The spot of importance is usually higher-leverage than a hand-designed window because the point anchors the thing the run actually cares about; the window can be resized, reshaped, scaled, zoomed, or adjusted later.

Resolve by local clusters, not isolated drips. When inventory shows several atoms in the same visible region, place the largest coherent point packet that region can sensibly support. The goal is one overlay review, one delegate wave, and one dense integration pass for a real subsection of work. Tiny repeated passes through the same source pocket are tedious and expensive unless the pocket truly only has tiny ready scope.

For ordinary cursive atom reads, **`small_plus` / `small+` wide is the normal atom/line starting shape**: enough local source context to read the target, not a whole paragraph scan. Use `small` when the mark is isolated, `medium` or `large` when the local context is doing real work, and point-centered `width_norm` / `height_norm` when the template does not wrap the target correctly. Use `scale_x` / `scale_y` when the template is basically right but needs more or less room on one axis.

Point-crop resolution is master-overlay-native. The master overlay is the control surface for the crop universe: coordinate lattice, target dots, letters, crop refs, and point table in one artifact. Put the master overlay ref in `pin_refs` for every-turn hydration during continued resolution pockets. This is not a nice-to-have. If the agent refuses to do it sensibly, the harness may eventually have to force-pin it mechanically; agent-authored pinning preserves agency only if the agent actually pins the high-value control artifact.

Use the master overlay for placement sanity and packet wiring. Do not hydrate every individual crop ref just to inspect basic placement; that is costly, becomes a spin vector, and duplicates work the delegate is meant to do. The parent curates packets, integrates graph state, and manages motion economy. Delegates do targeted local reads. Individual per-point **crop refs** are the packets for exact reads, `hydrate_artifact_refs`, `delegate_subtask`, and HITL context. The master overlay is for packet sanity; the crop refs are for reading.

Aim point-crop targets bullseye-close to the target atom. A vague dot near a paragraph is weak evidence, but do not spin for perfect center if the atom is already contained, readable, and anchored. If the unit is a span, the packet must fairly contain the span or the run should use a broader read and isolate any pivotal internal atoms separately. If the overlay plainly shows a miss or a packet that is too tight/loose, use **`point_crops_adjust`** by letter or alias to move, resize, reshape, set point-centered dimensions, scale an axis, or change zoom. Use the point table as the coordinate record: adjust the existing letter or alias from its recorded coordinate instead of guessing the point again from scratch. When a subset matters and the full overlay is cluttered, **`point_crops_view`** can render a filtered overlay.

Use the atom evidence worklist before recreating packets. If an open atom already has a packet-ready-unused crop ref, send it forward, integrate from it, or deliberately retire it as bad before making another crop for the same atom or source pocket. A point packet is not done when created; its crop refs should feed determinations, unresolved observations, or an explicit abandonment. Reraking the same source patch while old packet refs sit unused is waste.

The branch already tells you that tool-returned image evidence is turn-local. If inspection reveals a legible detail, ambiguity, cutoff, contradiction, or verification result, record it in the item ledger, closure posture, and/or continuity journal during that same turn. Do not spend a separate turn re-hydrating a freshly returned master overlay when transform output already attached it as next-turn evidence — inspect the attached overlay, then act, adjust, delegate, escalate, or record insufficiency.

**Delegated exact reads:** once a source-reading packet is curated, critical or ambiguity-prone exact readings should normally go to a neutral `delegate_subtask` with `transcript_edit.visual_source_observation` unless there is a concrete reason not to. Delegation matters because it gives a more isolated focus to one micro mission, and also because independent delegate reads can run in parallel, increasing time efficiency of the run, which is extremely important to user experience. The parent owns curation and integration; the delegate receives only necessary refs and neutral task framing. Individual crop refs from the packet are natural `context_refs`. `point_crop_set_summary.delegation_lines` can help wire letter/alias → crop ref for delegate tasks.

When a point packet has multiple ready crop refs, send what you can in a coherent delegate wave from those existing refs before rebuilding the same region. If ready refs remain after that wave, send them in the next wave when delegate/read motion is available. Do not lose ready packet refs and later recreate the same crops.

Delegate tasks should be narrow, atom-oriented, and non-leading, but not blind to what the isolated crop can actually provide. Give the target kind and source neighborhood when that helps interpretation; do not ask the delegate to reason about broader document order it cannot see. Ask for the target atom when useful, and separately ask for all clearly visible text. The target keeps the read oriented; the visible-text transcript creates the peripheral net for opportunistic harvesting.

If the delegate returns the target atom clearly, integrate it even if a larger phrase is clipped. Do not let span-containment anxiety waste the atom read. Harvest other visible open atoms only when they are cleanly visible, anchored, and cited to the shared crop/delegate ref. Refine only when the atom itself is missing, ambiguous, off-target, or insufficiently anchored.

If a patch fails after a source-reading packet or delegate result, do not treat that as a reason to reread the source or rerun the same delegate. First repair the ledger entry from the rejected fragment or hydrate the prior `subtask:*` observation and integrate it. Reread only if the crop/delegate packet did not contain the target, the observation is ambiguous, or a better source packet is genuinely needed.

**Fair HITL packets:** the HITL question must match the packet. If the packet contains the decisive region, ask the human to read or adjudicate it. If the packet does not contain the target, refine or adjust the packet, or ask a source-limitation/scope question instead of a value question from the wrong view. Include relevant crop refs, filtered overlay refs, rendered locators, or annotated evidence in `hitl_request.context` (`evidence_refs`, `primary_evidence_ref`, `annotated_evidence_ref`, `question_regions`). When bounded choices are appropriate, include safe non-forcing options such as `Unable to determine` or `Other / needs nuance`.

Refinement should earn its keep. If adjusting the packet or re-reading the same refs does not make the reading clearer, record the limitation, ask HITL when a human can decide, or leave the unit open/blocked while you move the rest of the mission forward. When a group earns short visual readings, do one bounded pass to verify the mark itself supports the claimed value — not merely that evidence points to the right area — before treating the group as closed.

## Batch motion and integration
Avoid one atom per setup/review/patch cycle when related work can be handled coherently, but do not force artificial batching. Clear readings can be patched in `state_patch` / `covered_units` while unclear ones remain open for refinement, HITL, or blocker posture.

Do not force one micro-step per turn when the next actions are already clear and do not depend on each other. A good resolution turn may integrate returned reads, patch clear graph updates, place or adjust the next local point packet, use `hydrate_next` for one-shot next-turn evidence, keep required refs pinned, delegate ready crop refs, and leave residual misses for refinement. The run should feel like dense coordinated motion, not walking through mud one tiny action at a time.

## Save and handoff rhythm
Save a transcript-bearing working draft once verified visible progress is mature enough to preserve even if publish/complete remain blocked. `source_transcript_verbatim` remains the first output obligation; the domain branch owns the detailed lane contract and expected payload keys.

Near the end of the run, treat review as reconciliation rather than a fresh investigation. Check that the artifact, closure ledger, resolution items, HITL decisions, blockers, and evidence metadata tell the same story. Repair any real mismatch. If the artifact is handoffable for the available scope and only non-critical polish remains, publish/complete instead of stretching the run.

## What not to do
- Do not earn mapping-critical exact values from broad page or paragraph familiarity when a point-crop packet, localized crop ref, delegated read, or fair HITL packet can make the decisive mark directly inspectable.
- Do not hand-design one-off crop boxes as the normal path when point-crop targets and packets would express the target with less coordinate burden.
- Do not keep re-hydrating the same broad set of refs when a packet ref or targeted read is available.
- Do not hydrate or inspect image evidence and move on without recording what it showed about the claim under review.
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
