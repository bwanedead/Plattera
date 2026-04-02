# Domain Runtime Adapter Architecture

This document defines the one-way plugin boundary between the generic harness and domain-owned runtime adapters.

Its purpose is to keep the harness generic while still letting each domain provide its own adapter implementation, without turning the harness into a domain-semantic importer.

The core rule is simple:

- the harness owns generic composition and execution contracts
- each domain owns its adapter implementation
- runners and registries select adapters by generic metadata, not by importing domain semantics into the harness

---

## 1. Boundary Rule

The domain runtime adapter is a plugin seam, not a second runtime.

It exists so the harness can:

- discover the right domain adapter
- pass a generic run envelope into that adapter
- receive a generic execution result back
- keep domain semantics out of shared harness code

The harness may know about:

- adapter interfaces
- generic lifecycle contracts
- registry metadata
- run envelopes and result envelopes

The harness must not know about:

- domain doctrine
- domain state meaning
- domain closure meaning
- domain tool semantics
- domain prompt text
- domain-specific workflow law

If a shared harness module needs to understand those things, the boundary has already failed.

---

## 2. Ownership Map

### 2.1 Harness side

Owns the generic rails:

- adapter contract shape
- registry lookup rules
- composition order
- lifecycle dispatch
- envelope validation
- error propagation
- generic trace and result handling

### 2.2 Domain side

Owns the domain-specific implementation:

- adapter implementation
- domain manifest metadata
- prompt surfaces
- semantic state contracts
- tool declarations
- closure and handoff meaning
- any thin domain-facing adapter shim

### 2.3 Tooling side

Owns concrete realization:

- provider wiring
- service integration
- persistence mechanics
- image and artifact operations
- refresh and mutation mechanics

The adapter may request these capabilities, but it does not own their mechanics.

---

## 3. Resolution Flow

The expected flow is:

1. The harness loads generic runtime config.
2. A registry resolves a domain adapter from generic identity metadata.
3. The harness composes a generic run envelope.
4. The domain adapter translates that envelope into domain-owned surfaces.
5. The adapter returns a generic execution result or generic follow-up request.
6. The harness persists and routes the result through generic runtime rails.

Only the adapter implementation should know the domain semantics needed to interpret the envelope.

Registries may read domain manifests or plugin metadata.
They may not become semantic decision engines.

---

## 4. Invariants

- The harness imports generic contracts, not domain semantics.
- The domain adapter implements the generic contract, but its internals stay domain-owned.
- Registry selection is metadata-driven, not work-semantic.
- The adapter is thin enough that the domain package still reads as a semantic bundle, not a runtime species.
- Generic composition stays in the harness, not inside the domain adapter.
- Failure modes must remain explicit: missing adapter, invalid metadata, or incompatible envelope should fail clearly.

---

## 5. Anti-Patterns

- A domain adapter that becomes a hidden controller loop.
- A registry that ranks or routes based on domain meaning instead of generic metadata.
- Harness code that imports `state/`, `semantics/`, or `prompting/` modules from a domain package.
- An adapter that owns persistence, provider wiring, or service orchestration instead of delegating to tooling.
- A generic composer that grows domain-specific branching.
- Compatibility layers that preserve retired adapter species as a parallel architecture.

If the adapter starts making semantic decisions for the domain, it is too large.

---

## 6. Future Domain Package Shape

Domain adapters should sit on top of the standard domain package shape documented in `domain-pack-architecture.md` and `domain-pack-constitution.md`.

The adapter seam should not replace the semantic package shape.
It should expose it.

Use the domain package to define:

- what the mission means
- what evidence means
- what closure means
- what handoff means

Use the adapter to make that package usable by the harness.

---

## 7. Checklist

Before accepting a new adapter seam, ask:

1. Does the harness still only know generic contracts?
2. Does registry selection depend on metadata rather than domain semantics?
3. Is the adapter a thin translation layer, not a controller?
4. Are prompt, state, semantics, and tooling still owned in the right packages?
5. Can the adapter be swapped without rewriting the harness?
6. Does the failure path stay explicit and debuggable?
7. Is there any domain-specific branching leaking into shared runtime code?

If any answer is no, the boundary is not clean enough.

