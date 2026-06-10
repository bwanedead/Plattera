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
