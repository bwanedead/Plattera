# Mapping Family Intent

This document explains the mission intent of the `mapping` domain family so a
new testing agent can understand what forward progress is supposed to mean
before running any harness loop.

It is not a runtime spec and not a deterministic workflow. The harness owns
loop mechanics; domain packs own semantic meaning; tooling owns concrete IO.

---

## 1. Family Purpose

The `mapping` family exists to turn deed source material and transcription
artifacts into a downstream mapping-ready understanding of the deed.

In practice, that means:

- recover trustworthy deed text from source imagery and redundant T0 drafts
- identify transcript/source deltas and intrinsic contradictions in the deed
- preserve what is mappable vs what is blocked by missing or contradictory
  source content
- produce a clean handoff for later deed-to-IR / feature-graph work

The family’s north star is **truthful source-grounded mapping readiness**, not
cosmetic transcript polish.

---

## 2. Domain Relationship

`mapping / transcript_edit` is the first domain in this family.

Its job is to start from:

- one dossier/transcription scope
- one source deed image (or image set)
- one or more peer T0 raw draft refs

and produce:

- a separate agent-authored transcript-edit working draft
- an explicit published transcript-edit output when the agent chooses to
  publish
- a model-authored persistent work state describing what is open, blocked,
  verified, or ready for handoff

`mapping / deed_to_ir` consumes transcript-edit output and produces feature-graph
IR artifacts that can be compiled, judged, rendered, repaired, and handed
downstream as the programmatic mapping representation of the deed.

---

## 3. What “Good” Means

For transcript-edit testing, good behavior means the agent can:

- hydrate T0 draft refs and source image refs on demand
- compare transcript text against source image evidence
- author its own working draft without mutating T0 raw drafts
- save and publish draft revisions only when it chooses to do so
- surface true blockers and ambiguities instead of silently guessing
- keep durable state about current work/focus across turns

For the right-of-way practice deed specifically, good behavior includes:

- noticing and correcting straightforward transcript/source deltas such as
  `1.4 acres -> 1.9 acres`
- surfacing the deed’s intrinsic `Range 74 vs Range 75` contradiction as a
  human-resolution blocker rather than silently choosing one
- recognizing that Plot 2 is source-incomplete because the image is cut off
- still preserving Plot 1 as potentially mappable after the range conflict is
  resolved

See
[`practice_deeds/right_of_way_deed_cheatsheet.md`](../../../practice_deeds/right_of_way_deed_cheatsheet.md)
for the detailed deed-specific expectations.

---

## 4. What This Family Must Not Do

Do not interpret mapping-family intent as permission for deterministic code to:

- choose which T0 draft is “best”
- generate the work list from hard-coded validators
- decide whether a contradiction is semantically resolved
- declare closure because a scripted check passed
- encode deed-specific ontology into shared harness contracts

The LLM authors semantic work. The harness executes with rails. Domain packs
teach doctrine and expose semantic tool affordances. Tooling reads/writes
artifacts mechanically.

---

## 5. Links

- Harness constitution:
  [`docs/architecture/harness/harness-constitution.md`](../harness/harness-constitution.md)
- Domain pack constitution:
  [`docs/architecture/harness/domain-pack-constitution.md`](../harness/domain-pack-constitution.md)
- Deed-to-IR agent purpose:
  [`docs/architecture/mapping/deed-to-ir-agent-purpose.md`](deed-to-ir-agent-purpose.md)
- Mapping family pipeline vision:
  [`docs/architecture/mapping/mapping-family-pipeline-vision.md`](mapping-family-pipeline-vision.md)
- Agent ergonomics ethos:
  [`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)
- Transcript-edit domain doc:
  [`docs/architecture/harness/transcript-edit-domain.md`](../harness/transcript-edit-domain.md)
- Live testing guide:
  [`docs/architecture/harness/transcript-edit-live-loop-testing.md`](../harness/transcript-edit-live-loop-testing.md)
