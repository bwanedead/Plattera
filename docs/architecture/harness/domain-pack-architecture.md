# Domain Pack Architecture

This document defines the standard architecture convention for domain packs in Plattera.

Its purpose is to make every domain:

- organized the same way
- easy to inspect
- easy to extend
- cleanly separated from harness mechanics
- resistant to controller/runtime corruption

This is the canonical starting-point proposal for the domain layer.

---

## 1. North Star

A domain pack should be a **sleek semantic shell** on top of the generic harness.

That means:

- the harness owns generic machinery
- the domain pack owns mission semantics
- product composition owns concrete tooling realization

The domain layer should be capable, but thin.
Simplicity is better than complexity.

---

## 2. Standard Layout

Recommended standard layout for every domain:

```text
backend/domains/
  <family>/
    <domain>/
      __init__.py
      manifest.py
      domain_pack.py
      mission_mode_adapter.py        # only when the domain needs a harness-facing adapter
      prompting/
        __init__.py
        branch.py
        surfaces/                    # optional; only when distinct prompt surfaces are earned
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

This is a target convention, not a commandment that every domain must start with every file on day one.

Start minimal.
Add only the modules the domain has actually earned.

---

## 3. Responsibilities By Module

### 3.1 `manifest.py`

Owns stable identity and declared shape:

- `domain_id`
- `family_id`
- display name
- prompt source refs
- declared capability/tool requirements
- optional supported mission modes

This file should stay small and declarative.

### 3.2 `domain_pack.py`

Thin host shell only.

It groups the domain’s authored surfaces:

- manifest
- prompt branch blocks
- adapter references
- semantic surface references

It should not become a controller.

### 3.3 `prompting/branch.py`

Canonical domain doctrine source.

This is where the domain says:

- what the mission world is
- what counts as evidence here
- what risks matter
- what closure means here
- how harness choreography manifests in this world

This file should remain a human-readable source of truth.

### 3.4 `prompting/surfaces/`

Optional.

Only add this when the domain truly has distinct prompt surfaces that need separate authored text, such as:

- orientation
- repair
- verification
- handoff

Do not split prompt text prematurely.

### 3.5 `state/contracts.py`

Own the domain’s semantic state model.

Examples:

- unresolved transcript ambiguities
- candidate interpretations
- verification posture
- final-selection readiness
- domain-local notes or evidence refs

One canonical state authority per domain.

### 3.6 `state/projection.py`

Own derived read models for the domain.

This is where generic harness state plus opaque payload becomes a clean domain view for prompts, tools, and review surfaces.

Projection is not truth.
It is a shaped view over truth.

### 3.7 `state/hydration.py`

Own focus-context hydration from artifacts into semantic context.

Examples:

- load the current transcript run bundle
- hydrate source-image evidence refs
- build the domain-local context packet for a specific unresolved item

Hydration is about assembling domain-relevant facts, not deciding what they mean.

### 3.8 `execution/tool_specs.py`

Own semantic tool declarations only.

Each tool spec should answer:

- what is the tool called
- what is it for
- what arguments should the agent provide
- what shape comes back

Do not implement the product/provider realization here.

### 3.9 `execution/translator.py`

Own explicit execution translation:

- domain-local intent -> declared tool request
- tool result -> domain evidence/update surface

This is the domain’s execution grammar seam.

It should be deterministic, explicit, and small.

### 3.10 `execution/capability_requirements.py`

Own the domain’s declared needs from the outside world.

Examples:

- image verification capability
- draft persistence capability
- final-selection capability
- consensus/alignment refresh capability

This file explains what the domain needs, not how the system implements it.

### 3.11 `semantics/closure.py`

Own domain closure meaning only.

For transcript edit, this is where “verified enough for downstream mapping” belongs.

### 3.12 `semantics/feedback.py`

Own how human feedback changes domain meaning.

Not transport.
Not HITL mechanics.
Only semantic incorporation rules.

### 3.13 `semantics/handoff.py`

Own when and how the domain is ready to hand off to downstream work.

This is where downstream readiness meaning belongs.

### 3.14 `mission_mode_adapter.py`

Optional and thin.

Use this only when the domain needs a harness-facing adapter for mission runtime.

Its role is:

- package domain surfaces into generic harness containers
- translate generic cycle requests into domain-owned surfaces

It must not become a hidden mission controller.

---

## 4. Tooling / Composition Boundary

The domain pack should not own real tool/provider wiring.

Instead, use a separate composition layer outside `backend/domains/` for:

- API endpoint bindings
- service-object wiring
- provider/client setup
- environment- and product-specific realization

Suggested direction:

```text
backend/domain_composition/
  <family>/
    <domain>/
      tool_bindings.py
      providers.py
      runtime_wiring.py
```

This path is a proposal, not a current repo truth.
The important rule is the boundary, not the exact folder name.

---

## 5. Prompting Convention

All domains should follow the same prompt architecture convention:

- `prompting/branch.py` is the canonical domain doctrine file
- any additional prompt surfaces go under `prompting/surfaces/`
- prompt text remains source-of-truth prose
- harness remains the final composer

The domain pack owns doctrine.
The harness owns cross-layer assembly.

---

## 6. What Domains Should Share

All domains should inherit the same architecture convention, not one giant shared ontology.

Shared across domains:

- package layout convention
- manifest conventions
- prompt ownership convention
- execution translation pattern
- separation between state / execution / semantics
- composition boundary rule

Not shared across domains:

- domain ontology
- closure meaning
- evidence meaning
- tool semantics
- handoff meaning

---

## 7. Minimal First-Cut Domain

A brand-new domain should start small.

The first cut should usually be:

```text
manifest.py
domain_pack.py
prompting/branch.py
execution/tool_specs.py
mission_mode_adapter.py      # only if the domain must plug into mission runtime immediately
```

Then add:

- `state/` when the domain gains real semantic state
- `semantics/` when closure/feedback/handoff need explicit code
- `prompting/surfaces/` only when there are multiple substantive prompt tasks

This keeps the domain layer from becoming overbuilt before it proves its needs.

---

## 8. Transcript-Edit As The First Real Domain

Transcript edit is a good first domain because its mission is clear:

- inspect source images and transcript variants
- identify unresolved text ambiguities
- make evidence-grounded repairs
- decide final selections
- reach a verified enough state for downstream mapping

That means transcript edit should own:

- transcript-specific doctrine
- transcript-specific state/projection
- transcript-specific tool menu semantics
- transcript-specific closure and handoff semantics

It should not own:

- dossier persistence engines
- alignment engines
- consensus engines
- API orchestration
- generic loop mechanics

---

## 9. One-Line Rule

Every domain should look like the same clean semantic shell: manifest, doctrine, state meaning, execution translation, and closure/handoff semantics — never a second runtime hiding under a softer name.
