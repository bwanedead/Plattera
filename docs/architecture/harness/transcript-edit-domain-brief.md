# Transcript-Edit Domain Brief

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

## 2. What The Domain Must Accomplish

The transcript-edit domain needs to let the agent do five kinds of work.

### 2.1 Orient

Understand:

- what dossier/run/segment is in scope
- what draft variants exist
- what the current heads and finals are
- what evidence already exists
- what the current unresolved transcript problem is

### 2.2 Investigate

Inspect:

- source images
- image regions/crops
- conflicting drafts
- alignment and consensus outputs
- provenance / version history where needed

### 2.3 Repair

Produce:

- evidence-grounded revised text
- revised per-draft content
- revised head choice

### 2.4 Verify

Decide:

- whether the current text is good enough
- what ambiguity remains
- whether more image or draft evidence is required
- whether human input is required

### 2.5 Handoff

Determine:

- whether the transcript is ready for final selection
- whether the segment is ready for downstream mapping work
- what artifact refs or notes must be handed forward

---

## 3. Domain-Owned Semantics

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

## 4. Tool Surface The Domain Needs

The domain pack should declare a semantic tool menu for transcript work.

The important categories are:

### 4.1 Observation tools

- `load_transcript_run_bundle`
  - load dossier/run/head/final/version context in one semantic bundle
- `list_transcript_variants`
  - enumerate raw/alignment/consensus/final candidates
- `load_transcript_variant`
  - fetch one specific draft/version

### 4.2 Image evidence tools

- `image_verify`
  - inspect image evidence for a textual claim
- `image_crop_refine`
  - refine the region when needed
- `load_source_image_context`
  - fetch the image(s) relevant to a transcription or segment

### 4.3 Comparison tools

- `compare_transcript_variants`
  - compare two or more draft candidates
- `compare_transcript_to_image`
  - align a claimed text span to image evidence

### 4.4 Mutation tools

- `save_transcript_edit`
  - save an edited draft variant
- `set_transcript_head`
  - choose the current head when needed
- `set_segment_final`
  - pin a final draft for a segment
- `clear_segment_final`
  - clear final selection when needed

### 4.5 Regeneration/request tools

- `request_alignment_refresh`
- `request_consensus_refresh`
- `request_human_verification`

These tools are semantic declarations only.
Their concrete implementation belongs in product composition, not in the domain pack.

---

## 5. Recommended Transcript-Edit Package Shape

Recommended target:

```text
backend/domains/mapping/transcript_edit/
  __init__.py
  manifest.py
  domain_pack.py
  mission_mode_adapter.py
  prompting/
    __init__.py
    branch.py
    surfaces/
      orient.py
      repair.py
      verify.py
      handoff.py
  state/
    __init__.py
    contracts.py
    projection.py
    hydration.py
  execution/
    __init__.py
    tool_specs.py
    translator.py
    capability_requirements.py
  semantics/
    __init__.py
    closure.py
    feedback.py
    handoff.py
  test_*.py
```

This is the target shape.
The initial implementation can start smaller.

---

## 6. Recommended First-Cut Implementation

To keep the first cut slim, start with:

```text
manifest.py
domain_pack.py
mission_mode_adapter.py
prompting/branch.py
execution/tool_specs.py
state/contracts.py
state/projection.py
semantics/closure.py
semantics/handoff.py
```

Then add:

- `prompting/surfaces/` when prompt surfaces truly diverge
- `state/hydration.py` once artifact hydration gets non-trivial
- `execution/translator.py` when semantic tool-call translation needs code
- `semantics/feedback.py` when human feedback incorporation becomes explicit

---

## 7. Standardized Conventions All Domains Should Follow

Transcript edit should be the template, not a one-off exception.

All domains should follow these conventions:

1. `manifest.py` is always the identity/capabilities declaration.
2. `domain_pack.py` is always a thin host shell, never a controller.
3. `prompting/branch.py` is always the canonical domain doctrine surface.
4. `state/` is always the semantic state authority.
5. `execution/` is always semantic tool declaration and translation, not provider wiring.
6. `semantics/` is always domain meaning like closure, feedback, and handoff.
7. Any harness-facing adapter stays small and explicit.

This gives every future domain the same mental map.

---

## 8. What Should Be Deleted Or Ignored

The transcript-edit domain should be treated as a fresh native pack effort.

That means:

- do not revive old transcript-edit controller ideas from pycache residue
- do not rebuild a mini-runtime inside the domain
- do not let product service/API details become canonical semantic code
- do not preserve older transcript-edit systems just because they once existed

The current minimal `manifest.py` + `domain_pack.py` + `prompting/branch.py` seed is useful only as a seed.
It should not constrain the new standard if a cleaner structure is needed.

---

## 9. Recommended Next Implementation Order

1. Establish the standard domain-pack constitution and architecture docs.
2. Rebuild transcript edit around the standard shape.
3. Define the transcript-edit semantic tool menu.
4. Define transcript-edit state/projection and closure/handoff semantics.
5. Only then wire concrete tool realization outside the domain pack.

That order keeps semantics and product composition from being tangled together.

---

## 10. One-Line Rule

Build transcript edit as a bounded semantic pack that knows what trustworthy transcript work means, what tools it needs, and when it is ready to hand off — but never tries to become the harness or the product runtime.
