# Domain Pack Constitution

This document defines the non-negotiable architectural constitution for Plattera domain packs.

It exists to prevent a specific class of regression:

- domain packages quietly becoming hidden controller loops
- product/tool/provider wiring being mistaken for domain semantics
- harness mechanics leaking down into the domain layer
- mission-specific policy being spread across ad hoc files instead of one bounded semantic bundle

The harness owns generic machinery (`backend/harness/`).
The domain pack owns mission semantics (`backend/domains/`).
Concrete tool and service realization lives in tooling (`backend/tooling/`) and other composition edges as the repo evolves.

That three-way split is not optional. Do not fold tooling into domain packs “for convenience.”

---

## 1. Core Rule

A domain pack is a **bounded semantic bundle**.

It may define:

- what the mission means
- what evidence means
- what closure means
- what handoff means
- what feedback means
- what tools/capabilities the agent should be able to use

It may not define:

- loop machinery
- runtime law
- transport mechanics
- persistence mechanics
- trace mechanics
- provider/client wiring
- product-specific orchestration

If a domain package starts behaving like a runtime species, it is out of bounds.

---

## 2. Native Shape Rule

The native shape of a domain pack is intentionally small.

The minimum viable shell is:

- `manifest.py`
- `domain_pack.py`
- `prompting/branch.py`

That seed is enough to define:

- domain identity
- domain doctrine
- the thin host shell the harness can wear

Everything else must earn its seat by responsibility, not by habit.

---

## 3. What The Domain Pack Owns

The domain pack may own only semantic surfaces such as:

- domain identity and manifest
- domain doctrine prompt blocks
- domain state meaning
- domain projection/read-model shaping
- focus-context hydration from artifacts into domain meaning
- execution translation from semantic intent into declared tool/capability requests
- closure semantics
- feedback semantics
- handoff semantics
- capability requirements
- a thin harness-facing adapter seam when needed

These are semantic responsibilities.
They are not runtime mechanics.

---

## 4. What The Domain Pack Must Never Own

The domain pack must not own:

- its own loop
- its own retry engine
- its own budget engine
- its own session manager
- its own persistence substrate
- its own trace substrate
- API client wiring as canonical semantic code
- product service orchestration
- provider/model selection machinery
- compatibility museums for retired domain systems

It also must not reclaim agent authorship through deterministic scripting such as:

- scripted work ranking
- scripted focus choice
- scripted next-step planning
- deterministic blocker truth
- deterministic closure truth

The domain pack may teach doctrine.
It may not secretly become the investigator.

---

## 5. One Canonical Home Per Responsibility

Each important semantic concern should have one obvious home.

Examples:

- doctrine -> `prompting/`
- state meaning -> `state/`
- execution translation -> `execution/`
- closure / feedback / handoff -> `semantics/`

Do not scatter one concept across many helper layers.
Do not create a stack of wrappers that all partly own the same thing.

---

## 6. Tooling Rule (`backend/tooling/`)

The domain pack may declare **semantic tool surfaces** (see `execution/tool_specs.py`):

- tool IDs
- what each tool is for
- what inputs the agent should provide
- what outputs the domain expects back, at a semantic level

The domain pack must not own **concrete tool implementation**:

- real tool handlers
- API endpoint wiring and orchestration
- service object construction
- vendor/client setup
- filesystem integration details
- compare/load/mutate/refresh logic
- retry, polling, or regeneration mechanics

Those belong in `backend/tooling/` (and related product composition), not under `backend/domains/`.

The domain names what the mission needs semantically.
Tooling fulfills it mechanically.

---

## 7. Prompt Ownership Rule

Domain prompt text must live in domain-owned prompt source files.

The default initial surface is:

- `prompting/branch.py`

Optional additional prompt files may be added only when a domain truly has multiple prompt surfaces that need separate authored text.

The domain pack may localize harness law for its world.
It must not restate or override the harness trunk.

Prompt doctrine must remain:

- human-readable
- bounded
- clearly domain-owned

---

## 8. State Rule

Each domain should converge on one canonical semantic state authority.

That state may include:

- domain-specific unresolved items
- domain-specific evidence posture
- domain-specific verification posture
- candidate repairs
- handoff readiness

But it should not be spread across several competing semantic stores.

Projection/read models should be derived from that state, not become alternate truth stores.

---

## 9. Adapter Rule

A harness-facing domain adapter is allowed.

Its job is narrow:

- translate between generic harness containers and domain-owned semantic surfaces

It must not:

- define alternate runtime law
- sneak a mini-controller back into the system
- become the practical source of harness mechanics

If an adapter starts doing more than translation and bounded packaging, it is too big.

## 9.1 Agent-Ergonomic Domain Surface Rule

Domain-owned prompt/tool surfaces should also follow
[`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md).

If the agent repeatedly expresses a domain tool intent in a stable, sane,
unambiguous shape, the domain may evolve its semantic tool contract or expose
a narrow ergonomic alias for that shape.

That evolution must stay within the domain layer's responsibility:

- the domain names the semantic contract and documents the accepted request
  shape
- tooling/harness adapters may normalize that shape mechanically
- ambiguous near-miss requests should be rejected or bounced for repair, not
  guessed
- no adapter or tool wrapper may infer domain conclusions, rank evidence, or
  choose next work on the agent's behalf

In short: **pave the agent's repeated sane dirt paths, but only with explicit,
bounded contracts and deterministic normalization underneath**.

---

## 10. Transcript-Edit Motivating Example

Mission facets such as **orient**, **investigate**, **repair**, **verify**, and **handoff** are **semantic descriptions of the work**, not a deterministic domain-side pipeline. The harness still owns orchestration; the domain owns doctrine, state meaning, projections, tool affordances, and closure/handoff semantics—not scripted phase machines.

For transcript edit specifically, the domain pack may own semantics like:

- what counts as transcript evidence
- what counts as a meaningful ambiguity
- what counts as sufficient verification for downstream mapping
- how human feedback changes transcript meaning
- when a segment is ready for final selection or handoff

It must not own:

- dossier persistence mechanics
- image-processing engines
- alignment engines
- consensus engine realization
- finalization pipeline mechanics

Those are system/product capabilities the domain may request through declared tool surfaces.

---

## 11. Deletion Rule

If an older transcript-edit or mission-specific system is no longer canonical:

- delete it
- do not preserve it as a parallel fallback architecture
- do not wrap it under softer names and keep it load-bearing

The target is one clean native domain-pack system, not a compatibility museum.

---

## 12. Review Questions

Every substantial domain-pack change should be reviewed with these questions:

1. Is this still a bounded semantic bundle?
2. Did any loop/runtime machinery creep into the domain package?
3. Did product/tool/provider realization creep into semantic code?
4. Is there one canonical home per semantic responsibility?
5. Did deterministic code start authoring work, focus, blockers, or closure?
6. Are prompts still clearly domain doctrine rather than mixed runtime/product instructions?
7. Is there any older parallel domain system still being preserved without a hard reason?

If any answer is no, the design is drifting out of bounds.

---

## 13. One-Line Rule

Keep each domain pack a thin semantic skin on top of the harness: doctrine, state meaning, semantic tool declarations, closure, feedback, and handoff only—never runtime machinery or concrete tool/product realization (that lives in `backend/tooling/`).
