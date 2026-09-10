# MAPDEP-BR-029 working-transcript rhythm ledger

Date: 2026-09-10
Surfaces: procedural guidance v44→v45, branch v35→v36, dossier driver v1→v2, apply/save tool specs.

## Replaced wording

| id | source | verbatim | disposition |
|---|---|---|---|
| P1 | procedural `## Save and handoff rhythm` | `Save a transcript-bearing working draft once verified visible progress is mature enough to preserve even if publish/complete remain blocked.` | `dropped: mature-enough gate retired. Replacement is an earlier honest-first-draft command plus “saving does not verify” / “do not wait until the draft looks finished, verified, or publishable.” The exact “even if publish/complete remain blocked” clause was not kept verbatim.` |
| P2 | procedural `## Save and handoff rhythm` | `` `source_transcript_verbatim` remains the first output obligation; the domain branch owns the detailed lane contract and expected payload keys. `` | `merged_into: same obligation plus artifact/authority distinction pointer` |
| P3 | procedural `## Save and handoff rhythm` | `Near the end of the run, treat review as reconciliation rather than a fresh investigation.` | `kept_verbatim` |
| P4 | procedural `## Save and handoff rhythm` | `Check that the artifact, closure ledger, resolution items, HITL decisions, blockers, and evidence metadata tell the same story.` | `merged_into: expanded reconcile list that also names decision provenance, provisional readings, and remaining limitations` |
| P5 | procedural `## Save and handoff rhythm` | `Repair any real mismatch.` | `merged_into: Repair actual discrepancies. Do not reconstruct the entire transcript from accumulated turn history.` |
| P6 | procedural `## Save and handoff rhythm` | `If the artifact is handoffable for the available scope and only non-critical polish remains, publish/complete instead of stretching the run.` | `kept_verbatim` |
| P7 | procedural provisional apply paragraph | `Keep the same decision_id when later evidence revises or earns that decision.` | `kept_verbatim` plus persist-into-working-transcript connector |
| B1 | branch `## Working draft posture` | `A saved working draft is not proof that the investigation is complete.` | `kept_verbatim` |
| B2 | branch `## Working draft posture` | `But once the visible, verified portion of the transcript is mature enough to be useful, saving that working state is often the honest move even if publish / complete remain blocked.` | `dropped: mature-enough gate retired; earlier-draft command plus “saving does not verify” take its place` |
| B3 | branch `## Working draft posture` | `Do not wait for perfect total closure before materializing verified visible progress.` | `merged_into: Do not wait for perfect total closure before the draft exists.` |
| B4 | branch `## Working draft posture` | `Do not treat the saved draft as evidence that the remaining work disappeared.` | `kept_verbatim` |
| B5 | branch `## Working draft posture` | `When you do save, the working artifact should normally materialize transcript-bearing state, not merely note that an investigation happened.` | `merged_into: save or apply; transcript-bearing state and decision provenance` |
| B6 | branch `## Working draft posture` | `Once the working/output artifact, closure ledger, and resolution items agree on the material scope, do not let end-run polish expand into a long audit phase.` | `kept_verbatim` |
| B7 | branch `## Working draft posture` | `A short final reconciliation is healthy: compare the artifact against earned values, blockers, HITL decisions, and handoff metadata.` | `merged_into: compare saved transcript and decision provenance against determinations, provisional readings, HITL, limitations, blockers, handoff metadata` |
| B8 | branch `## Working draft posture` | `After that, repair real inconsistencies and close; do not keep rereading or beautifying non-critical evidence when the downstream handoff is already honest.` | `merged_into: repair discrepancies rather than reconstructing from turn history; no “all decisions earned” bar; then the same close/no-polish close` |
| B9 | branch dangerous mistakes | `Treating a saved working draft as if it proves the underlying investigation has already been done.` | `kept_verbatim` |
| B10 | branch dangerous mistakes | `Saving note-shaped summaries in place of an actual transcript-bearing working state when the mission still needs transcript text.` | `kept_verbatim` |
| D1 | dossier driver | `Save authored work to the chosen segment/run lineage using dossier-qualified refs, and repair every affected segment when a boundary review exposes a split, duplicate, omission, or contradiction.` | `kept_verbatim` plus segment-being-worked / no-all-segments-first sentence |
| B11 | branch `## Closure ledger requirement` | `By the time you save, publish, request HITL, or complete the run, the transcript-edit closure ledger should make each layer explicit:` | `merged_into: By the time you publish, request HITL, or complete the run…` so first-save is not treated as a closure event. Empty-item-ledger save credibility kept. |
| B12 | branch `## Working draft posture` | `The working transcript is the authored artifact the user and deed-to-IR will consume.` | `dropped: that collapsed working draft, published output, and deed-to-IR consumption into one artifact. Replaced by working-revision → publication → deed-to-IR.` |
| X1 | apply tool-spec example | `Range 7 west` → `Range 77 west`; candidates `["7", "77"]`; `seg1-location-range`; `Beginning at the marked corner`; shared `image:derived:example` | `dropped: evaluation-deed contamination. Replaced with synthetic `example-provisional-token` / `[uncertain token]` → `[provisional reading]` / `candidate_a`/`candidate_b` and a separate synthetic evidence ref per decision.` |
| X2 | save / copy-forward / dossier save examples | `NW corner`; `Bearing N 4° 00' W verified.`; `Beginning at the marked corner...` | `dropped: same evaluation-deed motif family. Replaced with `[synthetic source text]` and `Token example-verified-token confirmed.` |

## Added teaching (no source sentence)

| id | home | content |
|---|---|---|
| N1 | procedural save rhythm | earlier honest-first-draft command; initial text may be unresolved; T0 stay candidates; do not wait until the draft looks finished |
| N2 | procedural save rhythm | intended apply-integration paragraph (working transcript as product; do not accumulate a second transcript in resolution summaries) |
| N3 | tool spec + short procedural pointer | apply request mechanics stay in the tool spec; procedural names the action and cadence only |
| N4 | branch authority + procedural pointer | knowing vs persisting, resolve-transition, and no mechanical graph sync live on the branch; procedural keeps write/repair motion |
| N5 | branch dangerous mistakes | second-transcript-in-summaries; implying apply success before the result |
| N6 | tool specs | request/result mechanics and examples only; no new actions or schema |
| N7 | dossier driver | segment-being-worked / do-not-initialize-every-segment-first lives only on the dossier driver |
| N8 | branch working-draft posture | working transcript is the artifact taking shape during investigation; publication carries selected working revisions into the transcript-edit output consumed by deed-to-IR |
| N9 | dossier apply example | every opaque `image:` / `t0:` / `transcript_edit:` evidence ref is dossier-qualified; leaf and dossier decisions share semantic content only |

No silent drops. Publication, closure layers, managed-provenance ownership, and “all decisions earned is not a publication bar” remain intact.
