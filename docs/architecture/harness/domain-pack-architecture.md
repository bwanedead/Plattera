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

- the harness owns generic machinery (`backend/harness/`)
- the domain pack owns mission semantics (`backend/domains/`)
- tooling owns concrete tool handlers and service integration (`backend/tooling/`)

The domain layer should be capable, but thin.
Simplicity is better than complexity.

---

## 2. Standard Layout

### 2.1 Default first-cut shape (canonical starting point)

Use this **exact** tree for a new real domain unless a smaller seed is explicitly chosen. Do not grow beyond it until the responsibility is earned.

```text
backend/domains/
  <family>/
    <domain>/
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

### 2.2 Optional growth (only when earned)

```text
      state/
        hydration.py

      execution/
        translator.py
        capability_requirements.py

      semantics/
        feedback.py

      prompting/
        surfaces/

      mission_mode_adapter.py
```

Add `prompting/surfaces/` only when multiple distinct authored prompt surfaces are genuinely needed—not to encode a deterministic phase pipeline. Mission “facets” (e.g. orient/repair/verify) belong in doctrine and semantics, not in a scripted domain runtime.

Co-located `test_*.py` under the domain are allowed when the domain earns focused tests; they are not part of the default skeleton.

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
- what good and bad reasoning look like in this world
- vocabulary and guardrails the agent should respect

It does **not** own harness loop law, orchestration order, or deterministic “phase” scripts. The harness composes prompts; the domain supplies bounded doctrine text and semantic context shapes elsewhere (`state/`, `semantics/`).

This file should remain a human-readable source of truth.

### 3.4 `prompting/surfaces/`

Optional.

Only add this when the domain truly has distinct prompt surfaces that need separate authored text, such as:

- orientation
- repair
- verification
- handoff

Do not split prompt text prematurely.

When an extra prompt surface is earned, it should usually express a different authored granularity from `branch.py` itself, such as run-shaping procedural guidance or handoff-local doctrine. Keep these surfaces suggestive and semantic; they must not become a hidden controller script.

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

When coercion helpers grow, keep the **public lens** in `projection.py` (scope merge + assembly) and move parsing/coercion into a sibling module such as `projection_coerce.py` so the lens file stays inspectable.

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

## 4. Tooling Boundary

The domain pack must not own real tool handlers or service wiring.

Canonical home for concrete implementations: **`backend/tooling/`** (e.g. `backend/tooling/<family>/…`), holding:

- real tool handlers
- service integration
- endpoint/service orchestration
- persistence operations
- image operations
- compare/load/mutate logic
- refresh/regeneration logic

The domain declares **what** tools mean and **what** shapes are expected; tooling implements **how** they run. Additional composition layers may exist at the app edge; they do not replace the domains vs tooling split.

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

A brand-new domain should start with the **default first-cut shape** in §2.1 when it is a “real” domain (not a tiny experimental stub). That includes `state/contracts.py`, `state/projection.py`, `execution/tool_specs.py`, `semantics/closure.py`, and `semantics/handoff.py` alongside `manifest.py`, `domain_pack.py`, and `prompting/branch.py`.

Smaller seeds (manifest + domain_pack + branch only) are acceptable only when explicitly intentional; they should grow into the standard shape as soon as the domain carries real semantic state or tool menus.

Then add optional modules from §2.2 only when needed.

This keeps the domain layer standardized and slim—not a second harness.

---

## 8. Transcript-Edit As The First Real Domain

Transcript edit is the reference implementation for the default first-cut shape. Its mission intent is spelled out in `docs/architecture/harness/transcript-edit-domain-brief.md` and aligns with the transcription/dossier artifact model (`docs/transcription-dossier-system-spec.md`).

It owns semantic bundles only: doctrine, state contracts, projection lens, semantic tool specs, closure meaning, handoff meaning.

Concrete loaders, savers, image ops, and refresh requests live in **`backend/tooling/`**, not under `backend/domains/mapping/transcript_edit/`.

---

## 9. One-Line Rule

Every domain should look like the same clean semantic shell: manifest, doctrine, state meaning, execution translation, and closure/handoff semantics — never a second runtime hiding under a softer name.
