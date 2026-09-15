# MAPDEP-BR-034 working-initialization rhythm ledger

Date: 2026-09-15
Surfaces: procedural guidance v47→v48, branch v36→v37, dossier driver v2→v3, startup context v5→v6.
Tool specs: unchanged (no contradiction with BR-033 mechanical contract).

## Why the author-first opening changed

BR-033 added `initialize_working_transcript`: an exact T0 copy into `rev:0001` with an empty decision ledger and unverified-candidate posture. Live teaching still opened the save rhythm as “author an honest first transcript,” so the agent was trained to re-type a full T0 through `save_workspace_artifact`. That opening was replaced — not appended — so initialization is the native economical bootstrap when an exact T0 is a useful source-shaped baseline. Full-save authoring remains available even when a technically copyable T0 exists.

Selecting a T0 as copy source is not truth ranking, consensus, verification, earning, or graph resolution. Transport conditions (lineage, hydration, copyable text) are necessary but not sufficient.

## Replaced wording

| id | source | verbatim | disposition |
|---|---|---|---|
| P1 | procedural `## Save and handoff rhythm` | `Once you understand the available source well enough to author an honest first transcript — including unresolved or provisional readings — create a transcript-bearing working revision.` | `replaced: author-first opening retired. Continue an existing lineage; otherwise initialize from an exact in-scope T0 when it is a useful source-shaped baseline. Phrase “create a transcript-bearing working revision” kept as the initialize-path outcome.` |
| P2 | procedural `## Save and handoff rhythm` | `Saving it does not verify those readings.` | `kept_verbatim` |
| P3 | procedural `## Save and handoff rhythm` | `Do not wait until the draft looks finished, verified, or publishable.` | `kept_verbatim` plus “known uncertainty or correctable transcription errors do not prevent initialization; they are why the working artifact exists.” |
| P4 | procedural `## Save and handoff rhythm` | `T0 peers remain candidate material: do not pick a best, longest, or consensus draft, and do not treat agreement as evidence.` | `merged_into` the new opening: choosing the copy source is not ranking that peer as truth; not best/longest/consensus/authoritative; agreement is not evidence. Same-section restatement dropped so one knob remains. |
| P5 | procedural `## Save and handoff rhythm` | `Preserve source wording, uncertainties, and cutoffs honestly.` | `kept_verbatim` |
| P6 | procedural `## Save and handoff rhythm` | `Do not manufacture certainty to make the initial draft look finished.` | `kept_verbatim` |
| P7 | procedural `## Save and handoff rhythm` | `` `source_transcript_verbatim` remains the first output obligation; the domain branch owns the detailed lane contract, the artifact/authority distinction, and expected payload keys. `` | `kept_verbatim` plus final-output-standard clause: working text may begin unverified; published output must still satisfy source-observed / provenance / uncertainty / handoff obligations; initialization must not weaken that standard. |
| P8 | procedural `## Save and handoff rhythm` | `The working transcript is the product taking shape during the investigation.` | `kept_verbatim` |
| P9 | procedural `## Save and handoff rhythm` | `When a coherent group of readings is ready to integrate, apply those decisions to the current working revision with `apply_transcript_edits` while their evidence and uncertainty are still clear.` | `kept_verbatim` plus “source-supported corrections and unchanged-text confirmations subsequently enter through `apply_transcript_edits`, using the returned exact working revision.” |
| P10 | procedural `## Save and handoff rhythm` | `Do not accumulate a second transcript in resolution summaries and leave the artifact to be reconstructed at the end.` | `kept_verbatim` |
| P11 | procedural `## Save and handoff rhythm` | `That loses decisions, makes final reconciliation expensive, and prevents the user and downstream agent from seeing what the run has actually established.` | `kept_verbatim` |
| P12 | procedural `## Save and handoff rhythm` | `Use `apply_transcript_edits` for corrections and source-supported confirmations. Cadence is judgment: do not require one write per atom, a write every turn, or a fixed batch size.` | `kept_verbatim` |
| P13 | procedural `## Save and handoff rhythm` | `Request shape, identity-verification (`expected_text == replacement_text`), uncertainty fields, lane rules, and the nonbatchable contract live in the tool spec.` | `kept_verbatim` |
| P14 | procedural `## Save and handoff rhythm` | `The branch owns the artifact/authority distinction: a graph update is not a persisted transcript edit.` | `kept_verbatim` |
| P15 | procedural `## Save and handoff rhythm` | `After a successful apply result, use the returned exact revision for subsequent edits.` | `kept_verbatim` |
| P16 | procedural `## Save and handoff rhythm` | `If an apply is refused, retain the investigation's valid findings and repair the request using the actual current revision — do not reread the source merely because a write failed.` | `kept_verbatim` |
| P17 | procedural `## Save and handoff rhythm` | `Keep graph updates concise; do not duplicate the complete decision ledger inside resolution summaries.` | `kept_verbatim` |
| P18 | procedural `## Save and handoff rhythm` | `Near the end of the run, treat review as reconciliation rather than a fresh investigation.` | `kept_verbatim` |
| P19 | procedural `## Save and handoff rhythm` | remaining reconciliation / no-all-decisions-earned / do-not-reconstruct / publish-instead-of-stretching close | `kept_verbatim` |
| B1 | branch `## Working draft posture` | `The working transcript is the artifact taking shape during investigation.` | `kept_verbatim` |
| B2 | branch `## Working draft posture` | `Publication carries selected working revisions into the transcript-edit output consumed by deed-to-IR.` | `kept_verbatim` |
| B3 | branch `## Working draft posture` | `The resolution graph tracks investigation and remaining work; it is not a second transcript.` | `kept_verbatim` |
| B4 | branch `## Working draft posture` | `A saved working draft is not proof that the investigation is complete, and saving does not verify unresolved or provisional readings.` | `kept_verbatim` |
| B5 | branch vocabulary | `Do not elevate one t0 file, vote/average peers into truth...` | `merged_into: “Do not elevate one t0 file into earned truth…” plus “Copying one exact T0 as an unverified working baseline is not elevation.”` |
| B6 | branch dangerous mistakes | `Treating one peer t0 draft as the default winner before comparing it against other peers and source evidence.` | `replaced: treating a copied T0 baseline as the default winner, or giving the copy-source draft truth weight because it was selected for transport.` |
| B7–B12 | branch remainder of working-draft posture + saved-payload contract + other dangerous mistakes | (unchanged sentences) | `kept_verbatim` |
| D1 | dossier driver | `Every transcription run listed under a segment is a peer candidate. No run is automatically best, longest, consensus, or authoritative. Compare and select from evidence.` | peer-not-authoritative kept. Compare/select is not an initialize prerequisite. Investigation reconciles evidence; publication is the final revision/provenance reconciliation. |
| D2 | dossier driver | `Save authored work to the chosen segment/run lineage using dossier-qualified refs, and repair every affected segment when a boundary review exposes a split, duplicate, omission, or contradiction.` | `merged_into: same save/repair sentence, now when the agent needs to author the segment’s starting artifact, even if a technically copyable T0 exists.` |
| D3 | dossier driver | `Establish and edit the working revision for the segment being worked.` | `kept_verbatim` |
| D4 | dossier driver | `Do not require every segment to be initialized before useful work can proceed.` | `kept_verbatim` plus “do not initialize every dossier segment merely as setup.” |
| D5 | dossier driver | `Before dossier publication, reconcile the full ordered instrument: every topology segment must have one explicitly chosen exact working revision` | `kept_verbatim` plus “from evidence” so compare/select lives on publication, not initialize. |
| D6 | dossier driver | one-instrument continuity + boundary-window paragraphs | `kept_verbatim` |
| S1 | leaf startup capabilities | `` `save_workspace_artifact` saves a working transcript revision. `` `` `publish_workspace_artifact` promotes a working revision to output. `` | `replaced: capability inventory now names initialize, save-as-authored-fallback, copy-forward, apply, and publish. Hydrate/transform/point-crop inventory kept.` |
| S2 | dossier startup capabilities | save/copy-forward/publish-only capability sentence | `replaced: same five-capability inventory with dossier-qualified initialize + apply; publish still requires one exact qualified working revision per topology segment.` |

## Added teaching (no source sentence)

| id | home | content |
|---|---|---|
| N1 | procedural save rhythm | initialize from an exact in-scope T0 when it is a useful source-shaped baseline; transport conditions are necessary but not sufficient |
| N1b | branch vocabulary + dangerous mistakes | copying one exact T0 as unverified baseline is not elevation; the mistake is giving the copy truth weight, not selecting a transport source |
| N1c | dossier + procedural | copy-source selection does not require exhaustive peer reconciliation; ordinary investigation reconciles evidence; publication is the final revision/provenance reconciliation |
| N1d | startup inventory | capability lines describe what each action does; when-to-choose lives in procedural guidance |
| N2 | procedural save rhythm | copy-source ≠ truth ranking / verification / earning / graph resolution |
| N3 | procedural save rhythm | initialization copies both lanes, empty decision ledger, verifies nothing |
| N4 | procedural save rhythm | existing working lineage is continued, not reinitialized |
| N5 | procedural save rhythm | full-save remains available even if a technically copyable T0 exists; init is the normal economical path when it fits, not a mandatory phase or gate |
| N6 | procedural save rhythm | published output standard is not weakened by an unverified baseline |
| N7 | branch working-draft posture | initialization materializes an unverified candidate baseline; does not satisfy final source-observed obligation |
| N8 | dossier driver | one dossier-qualified exact T0 ref names the segment/run lineage; init only the segment being worked |
| N9 | startup context | compact live tool-family inventory including initialize and apply |

## Pre-commit correction

The first BR-034 draft overcorrected: copyable T0 implied mandatory initialize, save was copy-impossible-only, and reconciliation was parked at publication. Correction dispositions:

| id | change |
|---|---|
| C1 | Dropped `usable means copy-transport fitness`. Transport conditions remain necessary, not sufficient. |
| C2 | Save is available when the agent needs to author the initial artifact, even if a technically copyable T0 exists. |
| C3 | Agent may decline a severely deficient, mismatched, or unhelpful baseline without adjudicating every reading, and without a scoring checklist. |
| C4 | Investigation reconciles evidence and peer disagreements; publication is the final revision/provenance reconciliation. Copy-source selection does not require exhaustive peer reconciliation. |
| C5 | Startup capability lines no longer say save is only available when no T0 can be copied. |
| C6 | Adjacent duplicate `apply_transcript_edits` paragraph removed; cadence and tool-spec pointer stay on the canonical apply sentence. |
| C7 | Branch elevation / no-ranking law kept. |
| C8 | Dossier “work only on the segment currently being handled” replaced with mutation-scoped lineage edits; adjacent-segment inspection remains allowed for continuity. |

## Intentionally not changed

- BR-033 persistence / initialization mechanics
- tool-spec request/result contracts
- closure / publication policy
- isolated-fork and harness mechanics
- evaluation-deed facts (none introduced)

No silent drops. BR-029/030 force (working transcript as product, graph as investigation ledger, saving does not verify, apply as integration path, cadence as judgment, final review as reconciliation) remains in the same procedural home.
