# Transcript-Edit Domain Brief

> **Stale implementation brief warning**
>
> This document is an older architecture/implementation brief and still
> contains legacy `head/final` language. For current transcript-edit runtime
> behavior, tester guidance, and up-to-date semantics, use:
>
> - [`docs/architecture/harness/transcript-edit-domain.md`](./transcript-edit-domain.md)
> - [`docs/architecture/harness/transcript-edit-live-loop-testing.md`](./transcript-edit-live-loop-testing.md)
> - [`docs/architecture/mapping/mapping-family-intent.md`](../mapping/mapping-family-intent.md)

This brief defines the intended domain surface for the first real domain pack:

- `mapping / transcript_edit`

Its purpose is to work backwards from what transcript edit actually needs to accomplish, then define the cleanest domain-layer architecture for doing that without contaminating the harness.

---

## 1. Mission Intent

Transcript edit exists to turn dossier-scoped transcription artifacts into trustworthy transcript decisions for downstream mapping work.

In practical terms, the domain needs to support an agent that can:

- inspect source images
- inspect raw drafts, alignment drafts, consensus drafts, and current heads
- inspect final-selection state
- identify unresolved ambiguities or defects
- gather more evidence where needed
- make or save repairs
- choose or revise version heads / final selections
- decide when the transcript is sufficiently verified for downstream mapping

The domain is not just “edit some text.”
It is “establish trustworthy transcript state for mapping.”

---

## 2. Semantic Mission Facets (Not A Domain Pipeline)

The transcript-edit domain needs to support work that can be **described** as orienting, investigating, repairing, verifying, and handing off. These are **semantic mission facets**—vocabulary for doctrine, projections, and closure—not deterministic orchestration phases.

**Do not** implement them as a scripted state machine, ordered pipeline, or domain-owned controller inside `backend/domains/`. The harness owns loop and orchestration; nuance belongs in `prompting/branch.py`, `state/`, `execution/tool_specs.py` (affordances), and `semantics/` (closure/handoff).

---

## 3. What The Domain Must Accomplish (Facet Lens)

The agent’s work in this domain often involves the following kinds of activity.

### 3.1 Orient

Understand:

- what dossier/run/segment is in scope
- what draft variants exist
- what the current heads and finals are
- what evidence already exists
- what the current unresolved transcript problem is

### 3.2 Investigate

Inspect:

- source images
- image regions/crops
- conflicting drafts
- alignment and consensus outputs
- provenance / version history where needed

### 3.3 Repair

Produce:

- evidence-grounded revised text
- revised per-draft content
- revised head choice

### 3.4 Verify

Decide:

- whether the current text is good enough
- what ambiguity remains
- whether more image or draft evidence is required
- whether human input is required

### 3.5 Handoff

Determine:

- whether the transcript is ready for final selection
- whether the segment is ready for downstream mapping work
- what artifact refs or notes must be handed forward

---

## 4. Domain-Owned Semantics

Transcript edit should own semantic concepts such as:

- transcript ambiguity
- transcript defect
- evidence sufficiency
- candidate repair
- verification posture
- final-selection readiness
- downstream mapping readiness
- human-feedback incorporation for transcript meaning

These are domain semantics.
They do not belong in the harness.

---

## 5. Tool Surface The Domain Needs (Semantic Declarations Only)

The domain pack should declare a semantic tool menu for transcript work.

The important categories are:

### 5.1 Observation tools

- `load_transcript_run_bundle`
  - load dossier/run/head/final/version context in one semantic bundle
- `list_transcript_variants`
  - enumerate raw/alignment/consensus/final candidates
- `load_transcript_variant`
  - fetch one specific draft/version

### 5.2 Image evidence tools

- `image_verify`
  - inspect image evidence for a textual claim
- `image_crop_refine`
  - refine the region when needed
- `load_source_image_context`
  - fetch the image(s) relevant to a transcription or segment

### 5.3 Comparison tools

- `compare_transcript_variants`
  - compare two or more draft candidates
- `compare_transcript_to_image`
  - align a claimed text span to image evidence

### 5.4 Mutation tools

- `save_transcript_edit`
  - save an edited draft variant
- `set_transcript_head`
  - choose the current head when needed
- `set_segment_final`
  - pin a final draft for a segment
- `clear_segment_final`
  - clear final selection when needed

### 5.5 Regeneration/request tools

- `request_alignment_refresh`
- `request_consensus_refresh`
- `request_human_verification`

Implementations belong in **`backend/tooling/`** (see `docs/architecture/harness/domain-pack-constitution.md`). The domain pack holds declarations in `execution/tool_specs.py` only.

---

## 6. Canonical First-Cut Package Shape

The transcript-edit domain uses the **standard domain first-cut** (see `docs/architecture/harness/domain-pack-architecture.md` §2.1):

```text
backend/domains/mapping/transcript_edit/
  __init__.py
  manifest.py
  domain_pack.py

  prompting/
    __init__.py
    branch.py

  state/
    __init__.py
    contracts.py
    projection.py

  execution/
    __init__.py
    tool_specs.py

  semantics/
    __init__.py
    closure.py
    handoff.py
```

Optional later growth (hydration, translator, capability_requirements, feedback, `prompting/surfaces/`, `mission_mode_adapter.py`) only when clearly needed—not as a stand-in for orchestration.

---

## 7. Standardized Conventions All Domains Should Follow

Transcript edit should be the template, not a one-off exception.

All domains should follow these conventions:

1. `manifest.py` is always the identity/capabilities declaration.
2. `domain_pack.py` is always a thin host shell, never a controller.
3. `prompting/branch.py` is always the canonical domain doctrine surface.
4. `state/` is always the semantic state authority.
5. `execution/` is always semantic tool declarations (and an optional `translator.py` when intent-mapping earns a module), never provider wiring.
6. `semantics/` is always domain meaning like closure, feedback, and handoff.
7. Any harness-facing adapter stays small and explicit.

This gives every future domain the same mental map.

---

## 8. What Must Stay Out Of The Domain Pack

Do not add under `backend/domains/mapping/transcript_edit/`:

- concrete tool implementations
- provider/client wiring
- API endpoint orchestration
- persistence logic
- retry/polling logic
- a domain-side workflow engine or scripted facet pipeline
- hidden deterministic prioritization or “next phase” machinery

---

## 9. What Should Be Deleted Or Ignored

The transcript-edit domain should be treated as a fresh native pack effort.

That means:

- do not revive old transcript-edit controller ideas from pycache residue
- do not rebuild a mini-runtime inside the domain
- do not let product service/API details become canonical semantic code
- do not preserve older transcript-edit systems just because they once existed

The current minimal `manifest.py` + `domain_pack.py` + `prompting/branch.py` seed is useful only as a seed.
It should not constrain the new standard if a cleaner structure is needed.

---

## 10. Recommended Next Implementation Order

1. Establish the standard domain-pack constitution and architecture docs.
2. Rebuild transcript edit around the standard shape.
3. Define the transcript-edit semantic tool menu.
4. Define transcript-edit state/projection and closure/handoff semantics.
5. Only then implement concrete tools under `backend/tooling/` (and related composition).

That order keeps semantics and product composition from being tangled together.

---

## 11. One-Line Rule

Build transcript edit as a bounded semantic pack that knows what trustworthy transcript work means, what tools it needs, and when it is ready to hand off — but never tries to become the harness or the product runtime.
