# Stage 1 Nuance Ledger — Field-semantics merge (trunk v33 → v34)

Governing contract: `docs/ethos/doctrine-refactor-constitution.md` (§2 Nuance Ledger Method).

Scope: the four places teaching atom field semantics in the v33 trunk:
- **A** — tail of `## Work Proximity, Groups, And Atoms` ("Use the compact value fields…" bullet list + proof-object paragraph)
- **B** — `## Compact claim atoms`
- **C** — `## Field roles`
- **D** — `## Prompt work-graph projection`

Result: one canonical section, `## Compact claim atoms`, placed immediately after
`## Work Proximity, Groups, And Atoms` (fields taught at the moment atoms are taught), sections
B/C/D's old homes deleted, A's tail removed. No echoes.

Dispositions: `kept_verbatim` (sentence moved intact), `merged_into: <line>` (content and
register demonstrably present in named line of new text), `dropped: <reason>`.

## Phase A inventory + Phase B dispositions

### A — Work Proximity tail

| ID | Verbatim source | Disposition |
|---|---|---|
| A1 | "Use the compact value fields on atomic items and covered units to make truth visible:" | kept_verbatim → opening paragraph, sentence 2 |
| A2 | "`label` / `title` — what the unit stands for." | kept_verbatim → label bullet |
| A3 | "`value_kind` — a generic hint such as `identifier`, `quantity`, `date`, `decision`, `status`, or `text_span`; no strict enum." | kept_verbatim → value_kind bullet |
| A4 | "`candidate_values` — known possibilities / options / outcomes so far. This list is not exhaustive; if another possibility appears, add it." | merged_into: candidate_values bullet ("the known possibilities / options / outcomes currently in play… not exhaustive truth; if another possibility appears, add it") |
| A5 | "`determined_value` — the earned compact result/outcome, supported by `verification_basis` and evidence. If the atomic row has an answer, put the answer here instead of hiding it in prose." | kept_verbatim → determined_value bullet, sentences 1–2 |
| A6 | "`evidence_refs` and `evidence_locators` — what proves the unit and where the proof sits when the medium allows it." | kept_verbatim → status/evidence bullet |
| A7 | "`closure_summary` and `reopen_triggers` — the short closed-state memory and what would invalidate it later." | merged_into: closure bullet (C6's wording chosen as the more precise articulation; A7 content fully covered) |
| A8 | "The graph row should read like a compact proof object: claim, candidates, determined value, evidence, status, reopen logic." | kept_verbatim → opening paragraph, sentence 3 ("Each graph row should read like…") |
| A9 | "Prose can explain the value, but it should not be the only place the value exists." | kept_verbatim → prose-fields bullet |
| A10 | "If a later turn or the user has to parse paragraphs to find the actual answer, the graph is too thin." | kept_verbatim → IMPORTANT paragraph, final sentence |

### B — Compact claim atoms

| ID | Verbatim source | Disposition |
|---|---|---|
| B1 | "Atomic resolution items and covered units are compact claim atoms, not transcript/document/log/code storage." | kept_verbatim → opening sentence |
| B2 | "An atom should carry a short user-facing `label`, the candidate values currently in play (`candidate_values`, which the UI may render as 'Considering'), the resolved value (`determined_value`), a short `verification_basis`, status, and evidence." | merged_into: field bullets (every named field has its own bullet; "currently in play" + UI 'Considering' carried in candidate_values bullet; "short user-facing" carried by label bullet + UI ordering) |
| B3 | "Long source spans, full output text, and paragraph-level prose belong in saved artifacts — not in `determined_value`." | merged_into: placement paragraph, artifact-law sentence ("Long text belongs in artifacts: long source spans, full output text, and paragraph-level prose go in saved artifacts…") + determined_value bullet ("never whole paragraphs") |
| B4 | "`determined_value` is for compact exact values, short labels, identifiers, statuses, decisions, amounts, dates, or short text spans." | merged_into: determined_value bullet enumeration (union of B4/C4/D6 lists: identifier, quantity, date, status, decision, amount, quoted value, row key, short text span, or another short exact value) |
| B5 | "If the smallest honest exact claim is genuinely long, keep it and explain why in `verification_basis`; otherwise move the long content to an artifact and keep the atom compact." | kept_verbatim → determined_value bullet, final sentence |
| B6 | "UI ordering: `label` first, then `title`, then `unit_id` or `item_id`." | kept_verbatim → label bullet |
| B7 | "IMPORTANT: the work graph is not a notebook. It is the proof skeleton for the agent and for the user-facing review UI." | kept_verbatim → IMPORTANT paragraph (marker retained; Stage 2 owns the emphasis budget) |
| B8 | "When exact claims live only inside paragraphs, the user cannot quickly see what was considered, what was decided, what proves it, or what would reopen it." | kept_verbatim → IMPORTANT paragraph |
| B9 | "Future turns also lose the thread because there is no small object to correct." | kept_verbatim → IMPORTANT paragraph |
| B10 | "The target shape is simple: claim, candidates, determination, evidence, status." | dropped: blurred near-duplicate of A8; A8 is the stronger articulation (adds reopen logic) and was kept verbatim. Constitution §11: pick the strongest articulation, do not average. |
| B11 | "PLEASE do not close an atomic item while the actual answer is hidden only in prose." | kept_verbatim → standalone command line (marker retained; Stage 2 owns the budget) |
| B12 | "If the row is atomic and earned, the compact result belongs in `determined_value`. If the row is a group, the compact results belong in its `covered_units` or in separate related atomic rows." | kept_verbatim → placement paragraph |
| B13 | "Summary prose is commentary; it is not a substitute for a structured value." | kept_verbatim → prose-fields bullet |

### C — Field roles

| ID | Verbatim source | Disposition |
|---|---|---|
| C1 | "Compact skeleton fields let future turns and UI surfaces immediately see what was considered, what was decided, and what evidence supports it. Prose fields preserve reasoning without hiding exact claims inside paragraphs." | kept_verbatim → field-roles lead-in (followed by "The field roles are strict:" — register hardened vs. C's neutral list intro) |
| C2 | "`label`, `value_kind`, `candidate_values`, `determined_value`, `status`, `evidence_refs`, and `evidence_locators` are skeleton fields." | merged_into: bullet structure itself (skeleton fields enumerated as the first five bullets; status/evidence bullet names them "the remaining skeleton fields") |
| C3 | "`candidate_values` is for considered options, not exhaustive truth." | kept_verbatim → candidate_values bullet |
| C4 | "`determined_value` is for compact resolved values only: identifier, quantity, date, status, decision, quoted value, row key, or another short exact value." | kept_verbatim (enumeration extended with B4/D6 union: + amount, short text span) → determined_value bullet |
| C5 | "`summary`, `notes`, `verification_basis`, and `next_needed_step` are prose fields. `verification_basis` explains why the value is earned." | kept_verbatim → prose-fields bullet |
| C6 | "`closure_summary` is the short memory retained after closure; `reopen_triggers` describe what would invalidate or reopen the row." | kept_verbatim → closure bullet |
| C7 | "Long text belongs in artifacts, with graph rows carrying compact values and evidence refs back to those artifacts." | kept_verbatim → placement paragraph, artifact-law sentence |
| C8 | "If an item has mission-relevant exact claims, represent them as compact atoms." | kept_verbatim → placement paragraph, sentence 1 |
| C9 | "If the item itself is atomic, give the item its own `value_kind`, `candidate_values`, `determined_value`, evidence refs, and locators when applicable." | kept_verbatim → placement paragraph |
| C10 | "If the item is a group, put exact values on its covered units or separate related atomic items." | merged_into: B12's wording (the two are duplicates; B12 chosen — names `covered_units` in code voice and includes the atomic-and-earned clause) |
| C11 | "If you need to narrate context, put it in prose fields." | kept_verbatim → placement paragraph |
| C12 | "If text is too long to fit naturally in a compact value field, save it as an artifact or refer to an artifact." | merged_into: artifact-law sentence (B3+C7 carry the full content; C12 adds no distinction beyond them) |
| C13 | "Closed items should prefer `closure_summary` over carrying long `summary` / `notes` into future prompt state." | merged_into: projection paragraph ("prefer `closure_summary` over carrying long `summary` / `notes` into future prompt state") |

### D — Prompt work-graph projection

| ID | Verbatim source | Disposition |
|---|---|---|
| D1 | "The prompt-visible work graph is a compact projection of durable state, not the full notebook. Full state remains in checkpoint/audit; the active prompt keeps the control skeleton hot." | kept_verbatim → projection paragraph, sentences 1–2 |
| D2 | "Compact atoms let future turns, audits, and UI surfaces see what was considered, what was determined, what evidence supports it, and what would require reopening." | dropped: third restatement of the considered/decided/evidence/reopen quartet; B8 (negative form, in the IMPORTANT paragraph) and C1 (positive form, field-roles lead-in) both kept and carry it at equal or greater force. |
| D3 | "Closed items should retain enough compact memory to reopen intelligently without keeping every detail hot in the prompt." | kept_verbatim → projection paragraph |
| D4 | "Use `closure_summary` for a short closure memory when helpful, and `reopen_triggers` for concrete conditions that would require reopening." | merged_into: projection paragraph ("prefer `closure_summary`…, and record concrete `reopen_triggers`") + closure bullet (C6) |
| D5 | "If a later conflict appears, reopen or patch the row rather than silently overwriting the prior determination." | kept_verbatim → projection paragraph, final sentence |
| D6 | "`determined_value` should stay compact: identifiers, amounts, dates, statuses, decisions, quoted values, row keys, or other short exact values." | merged_into: determined_value bullet enumeration (union with B4/C4) |
| D7 | "Whole paragraphs belong in artifacts, notes, or prose fields, not value fields." | merged_into: determined_value bullet ("never whole paragraphs") + artifact-law sentence |

## Emphasis artifacts in scope

- B7 `IMPORTANT` — kept in place (work-graph-not-a-notebook). Stage 2 decides its budget fate.
- B11 `PLEASE` — kept in place (no closing with answer hidden in prose). Stage 2 decides its budget fate.

## Register audit

- "The field roles are strict:" replaces C's neutral list intro — harder, not softer.
- All hard commands preserved as commands; no "consider"/"try to"/"where possible" substitutions introduced.
- No example dropped: the value_kind enum examples, the determined_value enumeration (now the
  union of all three source enumerations), UI 'Considering', and UI ordering all survive.

## Companion test updates (structure tests, not calibration)

- `test_surface.py`: section-geometry tests for `## field roles` / `## prompt work-graph projection`
  replaced by one no-domain-vocabulary test over the merged `## Compact claim atoms` section
  (same banned-term list, union of the three old tests). Lane-section boundary updated
  (now followed by `## Evidence refs vs evidence locators`). All exact-phrase force assertions retained.
