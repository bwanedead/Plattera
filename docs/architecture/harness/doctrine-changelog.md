# Doctrine Provenance Changelog

Every doctrine edit gets a row. Format (constitution §6):

```
date | section/law touched | observed behavior that motivated the edit | what changed | intended effect
```

This is the discipline that converts doctrine from an unrefactorable black box into an
annotated artifact. The wording is the weights; this file is the training log. Thirty seconds
per edit. Not optional.

Surfaces covered: the harness trunk (`backend/harness/runtime/prompting/surface.py`), the
domain surfaces (`backend/domains/mapping/prompting/family_branch.py`,
`backend/domains/mapping/transcript_edit/prompting/branch.py`,
`.../surfaces/procedural_guidance.py`, `.../surfaces/startup_context.py`), and the action
contract when its text teaches behavior.

| date | section/law touched | observed behavior that motivated the edit | what changed | intended effect |
|---|---|---|---|---|
| 2026-06-10 | trunk `## Compact claim atoms` (v33→v34) | Field semantics (determined_value compactness, field roles, projection memory) were taught in four drifting near-copies — accreted across sharpening cycles, splitting one behavioral lever into coupled knobs and training skim-as-boilerplate | Stage 1 consolidation: Work-Proximity field bullets + `Field roles` + `Prompt work-graph projection` merged into one canonical `Compact claim atoms` law placed where atoms are taught; ledger: `doctrine-backups/trunk-v33-20260610/stage1-field-semantics-ledger.md` | One tunable articulation of atom field semantics; no nuance dropped (2 blurred duplicates removed, strongest articulations kept verbatim); zero echoes |
| 2026-06-10 | trunk emphasis markers (v34→v35) | 9 IMPORTANT/PLEASE markers had inflated to the point of devaluing each other; PLEASE spent authority instead of asserting it | Stage 2 emphasis budget: markers cut to exactly 3, reserved for false determination, retroactive evidence (newly marked), and the inventory gate (newly marked); every removed marker compensated with harder flat wording; ledger: `doctrine-backups/trunk-v33-20260610/stage2-emphasis-budget-ledger.md` | Scarcity restores marker force; the three reserve slots now actually carry their markers; no guarded clause softened |
| 2026-06-10 | transcript-edit branch (v33→v34) | Branch restated trunk law (orientation/localize-before-earn bullets predate the trunk Evidence Law consolidation), duplicated family-owned forwardability/unresolved-issue law, and carried a PLEASE marker; the geometry-parameter trust model (critical atoms = the raw values that programmatically generate the map) existed nowhere | Stage 4a layer-routing: Earned source-reading standard now binds to the trunk Evidence Law by name (one budgeted echo) and keeps only domain deltas (false visual earning, the-mark-itself, t0 suspects, do-not-normalize-a-guess); family-owned gating sentences dropped; scoped-verdict articulations 3→1; PLEASE → "Be ruthlessly skeptical" + operator-supplied geometry-parameter clause; Structured source readings binds to Compact claim atoms law; ledger: `doctrine-backups/domain-20260610/stage4a-family-branch-ledger.md` | Branch carries domain truth natively instead of re-teaching trunk/family law; marker census 1 IMPORTANT / 0 PLEASE; the skepticism law now says *why* short operative values are sacred (they parameterize the map) |
| 2026-06-10 | trunk `## The Evidence Law` (v35→v36) | The evidence/localization law was taught as five sections plus restatement sites — sediment of successive false-determination incidents; the failure-mode description existed in 5 copies, the medium suite in 5, the honest-fallback posture in 6, splitting the most sensitive behavioral lever into coupled knobs and training skim-as-boilerplate over the most important doctrine | Stage 3 consolidation: Mission-critical exactness + Decisive-detail localization + Defensible evidence rule + Orientation vs claim-local + Evidence-local earned claims merged into one canonical `## The Evidence Law` with named beats; both IMPORTANT paragraphs verbatim; medium suite unioned (no example lost); E34 rendering paragraph routed to locator mechanics; investigation-discipline bullets deduped; zero echoes; ledger: `doctrine-backups/trunk-v33-20260610/stage3-evidence-law-ledger.md` | One tunable articulation of the evidence law, opening with its own one-command compression ("localize first, then determine") and closing with the fourth-wall line; repetition counts 5→1 / 5→1 / 6→2 / 3→1 / 4→1; all 52 kept-verbatim units audited present post-merge |
