# Domain Authoring Shape

This document defines the future-facing package shape for new domains in Plattera.

It is the canonical authoring shape for a domain that needs to stay a bounded semantic bundle on top of the generic harness.

The target is not a mini-runtime.
The target is a domain package that is easy to inspect, easy to extend, and hard to turn into a hidden controller.

---

## 1. Native Shape

A real domain should start from the standard first-cut tree and grow only by earned responsibility:

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

Optional growth should remain sparse and justified:

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

      runtime_adapter/
        __init__.py
        composition.py
```

The domain should stay visually small. If the package starts looking like a runtime subsystem, it is drifting.

---

## 2. Module Responsibilities

### 2.1 `manifest.py`

Owns stable identity and declared shape:

- domain id
- family id
- display name
- declared prompt sources
- declared capability needs
- optional mission-mode metadata

It should stay declarative.

### 2.2 `domain_pack.py`

Owns the thin host shell.

It gathers the domain-owned surfaces into a package the harness can load, but it does not become a controller.

### 2.3 `prompting/branch.py`

Owns the canonical domain doctrine source.

This is the human-readable surface for:

- what the mission world is
- what counts as evidence
- what risks matter
- what good and bad reasoning look like
- what vocabulary and guardrails the domain uses

Do not use it to script runtime phases or loop mechanics.

### 2.4 `prompting/surfaces/`

Optional and only when genuinely needed.

Use separate prompt surfaces only when the domain truly has distinct authored texts that cannot remain inside `branch.py`.

### 2.5 `state/contracts.py`

Owns the canonical semantic state model.

This is where the domain decides what its stable state actually is.

### 2.6 `state/projection.py`

Owns derived read models.

It should shape state for prompts, tools, and review surfaces without becoming a second truth store.

### 2.7 `state/hydration.py`

Owns domain-relevant assembly of artifact-backed context into semantic context.

### 2.8 `execution/tool_specs.py`

Owns semantic tool declarations only.

Describe what a tool is for and what shape it expects, but do not implement the tool.

### 2.9 `execution/translator.py`

Owns explicit intent translation:

- domain intent to declared tool request
- tool result to domain evidence/update surface

Keep it small and deterministic.

### 2.10 `execution/capability_requirements.py`

Owns the domain's declared needs from the outside world.

### 2.11 `semantics/closure.py`

Owns domain closure meaning.

### 2.12 `semantics/handoff.py`

Owns readiness and meaning for downstream transfer.

### 2.13 `semantics/feedback.py`

Owns how human feedback changes domain meaning.

### 2.14 `runtime_adapter/`

Optional and thin.

Use this only when the domain needs a harness-facing adapter seam.

It should package domain surfaces into generic runtime containers and translate generic requests into domain-owned surfaces.

The adapter implementation is domain-owned, but it may import harness-owned composition contracts. The dependency direction must stay one-way: `domain -> harness contracts`, never `harness -> domain semantics`.

---

## 3. Authoring Rules

- Keep domain doctrine prose human-readable and bounded.
- Keep one canonical semantic state authority per domain.
- Keep execution translation explicit and small.
- Keep closure, feedback, and handoff in semantic modules, not in transport code.
- Keep concrete tool handlers and service wiring outside the domain package.
- Keep adapter seams thin enough that the domain still reads as a semantic bundle.

The domain should declare meaning.
The harness and tooling should realize that meaning.

---

## 4. Package Principles

### 4.1 One concern, one home

Each major concern should have one obvious place to live.

Examples:

- doctrine -> `prompting/`
- state meaning -> `state/`
- execution translation -> `execution/`
- closure / feedback / handoff -> `semantics/`

Do not scatter one concern across multiple helper layers.

### 4.2 Grow by earned responsibility

Do not add optional modules until the concern genuinely exists.

The default shape is intentionally small.
Growth should follow responsibility, not habit.

### 4.3 Keep the package inspectable

The package should be understandable by opening a few files, not by tracing a web of helpers.

If the domain cannot be described in a few canonical surfaces, the shape is too loose.

---

## 5. Anti-Patterns

- A domain package that contains its own loop or runtime law.
- Prompt text scattered across helper functions.
- A state module that turns into a second truth store.
- Execution modules that also perform provider wiring or persistence.
- A semantics module that silently becomes transport or orchestration code.
- A catch-all utility layer that owns unrelated domain responsibilities.
- A compatibility museum that keeps old domain species alive indefinitely.

If the package starts to look like "just one more subsystem," it has already lost the shape.

---

## 6. Checklist For New Domains

Before calling a domain shape complete, verify:

1. Does the package start with the standard first-cut tree?
2. Is `manifest.py` declarative and stable?
3. Is `domain_pack.py` only a thin host shell?
4. Is `prompting/branch.py` the canonical doctrine source?
5. Is `state/contracts.py` the canonical semantic state authority?
6. Is `state/projection.py` only a read model, not truth?
7. Are tool specs semantic only, with implementation elsewhere?
8. Are closure, handoff, and feedback owned in `semantics/`?
9. Is any adapter seam thin and explicit?
10. Does the package still read like a semantic bundle instead of a runtime species?

If the answer to any of these is no, the domain is not finished shaping yet.
