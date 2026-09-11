# MAPDEP-BR-030 visual-observation integration ledger

Date: 2026-09-10
Surfaces: procedural guidance v45→v47; `transcript_edit.visual_source_observation` preamble (narrow context); branch unchanged at v36.

## Replaced wording

| id | source | verbatim | disposition |
|---|---|---|---|
| P1 | procedural workflow-chain `determined_value` | `Deed-to-IR consumes those values as machine parameters and does not re-litigate them; what you earn here is what gets built.` | `dropped:` no-relitigation and “what you earn here is what gets built” overstated downstream finality. `merged_into:` Deed-to-IR relies on the transcript and its recorded determinations to construct geometry; a wrong earned reading can propagate; accurate text and honest uncertainty affect downstream reliability. No-rescue stays at the provisional point of use (N10). |
| P13 | procedural workflow-chain slogan | `delegate reads → earned values` | `dropped:` implied automatic earning. `merged_into:` `delegate observations → evidence-grounded determinations → honest closure`. Causal ceiling sentence kept. |
| P14 | procedural workflow-chain close | `delegates answer in one word, values patch, closure earns itself` | `dropped:` “closure earns itself” implied automatic closure. `merged_into:` `delegates report what the packet supports, and honest determinations make honest closure possible`. |
| P2 | procedural run-sanity economic loop | `integrate clear reads, and repeat until the atom set is resolved` | `merged_into:` `integrate clear or honestly qualified reads, and repeat until the atom set is resolved as far as honest evidence allows` |
| P3 | procedural delegate integration | `Integrate the requested reading when the target is present, the packet and visible anchor actually support it, and no material contradiction remains.` | `dropped:` the “no material contradiction remains” gate forced consensus before integrate. `merged_into:` integrate when target, packet, and visible anchor support the reading; that is still only an observation. |
| P15 | procedural delegate integration | `Earn it only if nothing credible already contests the same detail; if a prior credible observation disagrees, do not let this result silently replace it.` | `dropped:` treated a historical contest as a permanent earn bar. `merged_into:` earn only when source evidence supports the reading and material uncertainty has been resolved; if credible observations still conflict, keep the selected reading provisional; later discriminating evidence may revise or earn, with a record of why the earlier alternative no longer holds. Does not require consensus, another observation, or immediate resolution. |
| P4 | procedural delegate integration | `A material divergence from a candidate or an overlapping observation is grounds for corroboration, not automatic acceptance or rejection` | `merged_into:` still not automatic acceptance or rejection; corroboration is useful only when it can distinguish alternatives, not as a mandatory extra check. |
| P5 | procedural delegate integration | `The parent should reconcile packet-placement concerns against the master overlay rather than paying to reread every crop.` | `kept_verbatim` inside the work-group sanity paragraph. |
| P6 | procedural delegate integration | `A delegate result is an observation, not a self-authenticating determination. \`status: completed\` says the observation call completed; it does not earn a value.` | `kept_verbatim` as the opening of the integration paragraph. |
| P7 | procedural delegate integration | packet-outcome / harvesting / span-tile / refine-only sentences from the prior integration paragraph | `kept_verbatim` after the disagreement paragraph. |
| P8 | procedural delegate task framing | structured outcome fields, packet-scoped `absent`, attempted observation window, clipped-edge / crop-local / non-leading rules | `kept_verbatim` in the existing task-framing paragraph. |
| P9 | procedural overlay review | master overlay as placement control; do not hydrate every crop; inspect one named crop when needed | `kept_verbatim` in the source-reading packet workflow; echoed once at integration as current-work-group sanity, not a new overlay law. |
| P10 | procedural provisional apply | `when observers disagree or evidence is incomplete, you may write a best-current transcript reading as \`determination: provisional\` with \`uncertainty_reasons\`, credible \`candidate_values\` when they exist, and evidence refs` | `merged_into:` same permission plus appropriate existing `uncertainty_reasons`, honest `verification_basis`, and evidence refs that support or contest the selection. |
| P11 | procedural provisional apply | `Applying a provisional reading does not make it earned.` / same `decision_id` / persist through `apply_transcript_edits` / do not leave best-current text only in the graph / do not sample unchanged evidence to manufacture agreement / do not force immediate HITL solely because a provisional value exists | `kept_verbatim` |
| P12 | procedural provisional apply | `Publication readiness and mapping relevance remain agent-authored closure judgments.` | `merged_into:` `Whether uncertainty permits handoff remains your existing scoped closure judgment.` |
| D1 | visual_source_observation preamble | `The parent may have generated a crop by placing a point on a master overlay. That point and crop are an observation packet, not proof that the requested atom is inside it. Point placement or crop extent can be imperfect: the packet may be off-target, too tight, unreadable, or missing enough surrounding context to interpret the mark.` | `merged_into:` `The supplied evidence may be a crop from a larger document, whose placement or context may be imperfect`, then the same packet-not-proof and packet-limitation list. Conditional because the profile also accepts broader source evidence. |
| P16 | procedural refinement | `When a group earns short visual readings, do one bounded pass to verify the mark itself supports the claimed value — not merely that evidence points to the right area — before treating the group as closed.` | `dropped:` the extra-pass / close-gate. `merged_into:` assess the mark itself during ordinary integration; do not introduce a second read merely because a group is about to close; further inspection follows a concrete unresolved question. |
| P17 | procedural workflow-chain | `A delegate can only verify what its crop shows.` | `merged_into:` `A delegate can only verify what its supplied evidence packet shows.` Packet-bounded observation law and surrounding atom/crop rationale kept. Pre-commit coherence with the profile’s broader allowed evidence; version stays v47. |

## Added teaching (no source sentence)

| id | home | content |
|---|---|---|
| N1 | procedural integration | whole-observation coherence; preserve delegate-reported qualification; supported integration is still only an observation; earn only when present material uncertainty is resolved |
| N2 | procedural integration | work-group sanity on observations already in hand; no per-atom sanity turn, mandatory crop reread, or document-wide sweep after every wave |
| N3 | procedural integration | inspect a particular crop only when a concrete unresolved question warrants it |
| N4 | procedural integration | preserve disagreement; PLEASE do not silently let the latest answer replace the earlier one; neither recency, majority, familiarity, nor observer confidence is source truth; further check only when it can distinguish |
| N5 | procedural integration | matching observations to the same detail is agent judgment; no mechanical comparison |
| N6 | procedural integration | no immediate adjudication duty; if further investigation is uneconomic, preserve uncertainty and continue |
| N7 | procedural provisional apply | a text correction does not itself resolve uncertainty |
| N8 | procedural provisional apply | keep graph honest; no second contested-value ledger; do not duplicate complete decision provenance into graph prose |
| N9 | procedural provisional apply | no defensible selection → preserve unresolved/source limitation; continuing is not permission to fabricate |
| N10 | procedural provisional apply | provisional record available for later review and deed-to-IR investigation; mapping sanity may revisit; geometric convenience does not establish source text |

## Preserved unchanged

- Branch earned-reading standard, provisional-vs-earned posture, Layer 4 scoped closure, and BR-029 working-draft / publication / deed-to-IR wording (v36).
- Delegate-task framing: packet-scoped `absent`, structured fields, opportunistic `source_visible_text`, clipped-edge, crop-local targeting.
- Overlay-native placement review and “do not hydrate every crop.”
- BR-029 save-and-handoff rhythm, apply cadence, and no “all decisions earned” publication bar.
- Profile result schema, no-confidence rule, completed≠earned, and packet-scoped `target_presence`.

No silent drops. No evaluation-deed facts, phrases, candidate values, or answer patterns were added.
