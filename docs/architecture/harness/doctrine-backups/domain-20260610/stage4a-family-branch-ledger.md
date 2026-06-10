# Stage 4a Nuance Ledger — Branch layer-routing and dedup (branch v33 → v34)

Governing contract: `docs/ethos/doctrine-refactor-constitution.md` (§2, §4, §5, §7.2).

Scope: `backend/domains/mapping/transcript_edit/prompting/branch.py` only.
`family_branch.py` is the law owner for the duplicated family content and is **untouched**
(v6 stands). Quotes below are from branch v33. Dispositions: `kept_verbatim`,
`merged_into: <target>`, `dropped: <reason>`, `register_hardened: <new text>`.

Layer-routing rationale: trunk Stages 1–3 created named canonical laws
(`## The Evidence Law`, `## Compact claim atoms`). The branch's restatements of those laws
predate the consolidation; binding to the law by name with the domain delta stated natively
is free density on both surfaces (constitution layer-routing audit: domain restating trunk
law collapses up).

## Family-owned content duplicated in branch

| ID | Verbatim source (branch) | Disposition |
|---|---|---|
| A1 | "Not every unresolved issue blocks mapping.\nNot every unresolved issue is harmless." (Gating logic) | dropped: verbatim duplicate of `family_branch.py` "## Family doctrine for unresolved issues" lines, which is the law owner. The branch Gating section keeps its actual job: layer 1–3 vs layer 4 classification. |
| A2 | "A whole-scope \"blocked\" verdict and a narrower \"this portion is blocked while another portion can proceed\" are different statements; prefer the one that is more honest about what the downstream pipeline can actually consume." (Gating logic) | merged_into: Layer 4 home — its unique clause ("what the downstream pipeline can actually consume") appended to the existing "Preserve partial handoffability explicitly" paragraph: "Prefer the statement that is most honest about what the downstream pipeline can actually consume." The third articulation of the scoped-verdict rule (after the mission bullet and the Layer 4 paragraph) is thereby retired. |

## Peer-agreement family (branch-side echo)

Canonical homes kept: the Starting-resources warning ("Do not let t0 drafts imprint the
answer" — positional, unique content) and the vocabulary entry ("T0 peer drafts vs authored
edit output" — the strongest compact articulation). Anti-pattern/dangerous-mistakes entries
stay (different genre, per Stage 3 precedent).

| ID | Verbatim source | Disposition |
|---|---|---|
| A3 | "Peer disagreement is one source of candidate work, and peer agreement is not a verification basis; neither substitutes for direct source-image checks on mapping-critical claims." (Reality-first review standard, sentence 2) | dropped: restates the vocabulary entry clause-for-clause ("peer agreement is never verification on its own" + "substitute peer drafts for direct source-image checks on mapping-critical claims"). The kept sentence 1 already carries the local reminder "even when every peer draft happens to agree." |

## Earned source-reading standard (trunk-handle binding + emphasis)

| ID | Verbatim source | Disposition |
|---|---|---|
| A4 | "For mapping-critical visual claims, an earned determination means source-local evidence makes the reading clear enough to defend." | kept_verbatim |
| A5 | "This domain is especially vulnerable to **false visual earning**: it is common to look at the correct image region, reason from the correct source, and still promote the wrong small mark, digit, direction, or word. That failure is worse than leaving a unit open because a wrong earned source reading can silently poison the normalized lane and the downstream handoff." | kept_verbatim (the domain's sharpest unique articulation — visual medium + normalized-lane stakes) |
| A6 | "Stable law:" list intro | dropped: list dissolved into prose; the law's name is now the trunk's (one deliberate budgeted echo: "The trunk Evidence Law governs every mapping-critical source reading at full force: localize first, then determine.") |
| A7 | "orientation evidence helps find the area; it does not earn a small exact value" | dropped: restates the trunk Evidence Law orientation beat ("Orientation evidence helps you find the right area. Claim-local evidence earns the exact atom."); covered by the binding line. Companion test pin updated. |
| A8 | "verify the claimed mark itself supports the value, not merely that the evidence points to the right area" | kept_verbatim (domain delta: the mark itself — also referenced by procedural guidance) |
| A9 | "do not decide from t0, transcript text, memory, or first impression and then attach evidence afterward" | kept_verbatim (domain suspects list is the delta; test-pinned) |
| A10 | "localized source evidence must support the value before it is earned" | dropped: restates the trunk law's one-command compression ("localize first, then determine"), present in the binding line. |
| A11 | "if the strongest available check is still inconclusive, keep the item unresolved, ask HITL, or mark blocked / no-further-progress — do not normalize a guess" | kept_verbatim ("do not normalize a guess" is domain-native force; normalization is a domain concept) |
| A12 | "PLEASE be extra skeptical of candidate numbers, degrees, bearings, distances, directions, acreage, and other short operative values that came from t0 drafts or first impression." | register_hardened: "Be ruthlessly skeptical of candidate numbers, degrees, bearings, distances, directions, acreage, and other short operative values that came from t0 drafts or first impression — these are the raw parameters that programmatically generate the downstream geometry, so a wrong one is a wrong map." (PLEASE removed per emphasis budget — pleading → ban-grade adverb; the appended clause is new world-model content from the operator: the geometry-parameter trust model, placed at its sharpest point of use.) |
| A13 | "If the localized source evidence does not make the claimed value obvious, do not earn it. One wrong short value can corrupt downstream geometry while looking superficially polished." | kept_verbatim |
| A14 | "**IMPORTANT:** critical source readings must not be earned from broad reads alone. The order is: treat the candidate as suspect, obtain claim-local source evidence, inspect it, then decide. If the evidence is not clear enough to defend, keep the unit open, refine posture, ask HITL, or block it. Broad page or paragraph familiarity plus confidence is not earned source reading." | kept_verbatim — the branch's single reserved IMPORTANT (false visual earning is this domain's #1 failure mode; the suspect→localize→inspect→decide order is the Evidence Law's sane order in domain words and earns its local presence) |

Branch marker census after 4a: 1 IMPORTANT, 0 PLEASE.

## Structured source readings (trunk-handle binding)

| ID | Verbatim source | Disposition |
|---|---|---|
| A15 | "Exact mapping-critical readings should appear as structured values, not only prose." | kept_verbatim, extended with the law binding: "— the trunk Compact claim atoms law governs here." |
| A16 | "If an atomic item earns a short source reading, governing choice, identifier, quantity, boundary fact, or trust posture, put that answer in `determined_value` with an appropriate `value_kind`, candidate values when there were alternatives, and the evidence refs/locators that support it. If a group stands over several readings, put each reading in `covered_units` or separate related atomic items." | kept_verbatim (domain enumeration of what counts as a reading) |
| A17 | "The summary can explain the reading, but the graph must show the value directly so a human reviewer can compare value-to-evidence without digging through paragraphs." | first clause dropped: restates trunk Compact claim atoms ("Prose can explain the value, but it should not be the only place the value exists"); remainder kept_verbatim ("the graph must show the value directly so a human reviewer can compare value-to-evidence without digging through paragraphs" — the value-to-evidence comparison framing is unique). |

## Untouched (verified, not edited)

Mission, starting resources, vocabulary, four layers, reality-first list, deliberate layer
assessment, provisional vs earned, mapping-critical inventory law, closure ledger
requirement, output contract, working draft posture, dangerous mistakes, definition of done.

## Companion test updates

- `test_transcript_edit_pack.py` line pinning "orientation evidence helps find the area" →
  updated to the binding line ("the trunk evidence law governs every mapping-critical source
  reading"). All other pinned branch phrases survive verbatim.

## Echo audit

One deliberate budgeted echo created (the Evidence Law binding line, named per constitution
§4 callback pattern). Three accidental echoes retired (A1, A3, A7/A10 restatements).

## Register audit

- No clause softened. A12's PLEASE became a flat ban-grade command ("Be ruthlessly
  skeptical"), strictly harder.
- The one IMPORTANT kept verbatim at the domain's highest-stakes law.
- New content added (geometry-parameter clause in A12) is operator-supplied world-model
  truth, not invented doctrine.
