# Raptor 3 Ethos

Raptor 3 is a mental model for turning a messy but functional system into a cohesive native system.

The image behind the name is the visible progression from a first engine full of exposed tubes, add-ons, and external routing, to a later engine whose functions have been internalized into a cleaner integrated form. The lesson is not "make it look minimal." The lesson is: remove accidental exterior complexity by redesigning the system until the remaining parts feel essential, native, and load-bearing.

This ethos applies to code, prompts, doctrine, docs, UI flows, harness contracts, and process design.

---

## Core Idea

A Raptor 3 system has one coherent trunk.

It does not feel like:

- a new shell wrapped around an old engine
- a series of patches stacked into a permanent adapter chain
- a doctrine pile where every past failure left a new paragraph
- a compatibility layer that quietly became the real system
- a surface that is simpler only because the complexity was hidden somewhere unowned

It feels like one native machine:

- each responsibility has one canonical home
- the active contract is the real contract
- old scaffolding is retired when it stops being needed
- shared concerns are genuinely shared, not copied
- domain-specific concerns live at domain seams
- every remaining part earns its place

Raptor 3 is subtractive and integrative. It removes exposed clutter by redesigning the shape, not by sweeping complexity under a rug.

---

## What It Is Not

Raptor 3 is not cosmetic minimalism.

Do not confuse it with:

- deleting useful clarity just to reduce line count
- compressing language until important behavioral nuance disappears
- hiding complexity behind vague helpers or catch-all modules
- preserving two systems while declaring one of them "legacy"
- renaming without changing ownership
- creating an elegant facade over a tangled substrate

The system may still have real complexity. The goal is that the complexity is in the right place, expressed through native structures, and no larger than the problem actually requires.

---

## Native System Tests

When applying this ethos, ask:

1. What is canonical now?
2. What old surface stopped being canonical?
3. Is there one home for this responsibility?
4. Did we delete or retire anything real?
5. Are we carrying compatibility ballast without a retirement trigger?
6. Did the change reduce translation layers, or just move them?
7. Is the public contract the same contract the system actually uses?
8. Are deterministic layers still mechanical, or did they gain semantic authority?
9. Can a future maintainer understand the main path without learning three eras of history?

If the answer is unclear, the system is probably not Raptor 3 yet.

---

## Positive Signals

A change is moving toward Raptor 3 when it creates:

- fewer concepts doing the same job
- fewer adapter hops between intent and execution
- fewer prompt or docs sections that restate the same rule in different words
- clearer ownership boundaries
- direct use of the native contract
- deletion of old files, exports, shims, or compatibility branches
- stronger tests around the canonical path
- smaller surfaces because duplication was removed, not because meaning was lost
- a system that is easier to extend without adding a new patch layer

The strongest signal is not that a file became shorter. It is that the system has fewer live shapes to reason about.

---

## Negative Signals

Flag these patterns aggressively:

- "new API over old substrate" as an end state
- parallel old and new paths with no retirement point
- helper modules whose main job is preserving retired vocabulary
- compatibility branches in canonical modules
- docs that still teach old grammar as if it is live
- domain-specific glue inside a generic trunk
- generic surfaces shaped around one historical domain
- doctrine sections that are really incident patches
- tests that keep old behavior alive because the new behavior never fully took over
- refactors that add more indirection but do not make anything deletable

These patterns can be acceptable during migration, but only when they are named as temporary and have an exit.

---

## Raptor 3 For Doctrine

Doctrine is especially prone to becoming Raptor 1: exposed tubes everywhere.

Every time an agent fails, it is tempting to add another warning. Over time, the prompt stops being a coherent method and becomes a stack of micro-corrections. That can make behavior worse: the important principles become needles in a haystack of local reminders.

Raptor 3 doctrine should aim for:

- one integrated articulation of the method
- fewer repeated cautions
- clear priority order among values
- examples only when they clarify the general principle
- domain-specific guidance at domain surfaces
- generic action-contract guidance in generic harness surfaces
- no incident-specific wording unless the incident reveals a general failure mode

The goal is not to strip doctrine down until it is vague. The goal is to preserve the behavioral force while merging overlapping warnings into stronger, more memorable principles.

Good doctrine reads like a coherent operating philosophy. Bad doctrine reads like a changelog of mistakes.

---

## Raptor 3 For Code

Code should move toward a direct native path.

Prefer:

- canonical contracts over aliases
- typed seams over duck-typed folklore
- responsibility-based modules over catch-all utilities
- shared mechanical rails over copied local checks
- domain semantics outside shared trunks
- deletion of retired paths once callers are migrated

Avoid:

- compatibility helpers in the hot path
- hidden fallback chains that make behavior hard to predict
- central modules that become museums of every past shape
- "temporary" shims with no owner or expiry
- deterministic code that starts deciding semantic truth

The codebase should not need archaeology to understand the current system.

---

## Raptor 3 For Harness Work

In harness work, this ethos reinforces the constitution:

- harness owns mechanics
- domains own semantics
- the agent authors motion
- deterministic code provides rails, validation, memory, execution, and observability
- deterministic code must not silently author inventory, focus, blockers, truth, or closure

A native harness has one trunk for shared mechanics. It does not preserve domain-private adapters as generic law, and it does not keep old loop metaphors alive inside the current runtime.

If a harness refactor leaves the old engine running inside the new shell, call it mixed or patchwork. If it makes the native path direct and makes old pieces deletable, it is converging.

---

## Review Template

Use this short review shape when applying the ethos:

```text
Verdict: converging / mixed / patchwork

Canonical path:
- What is the native path now?
- Is it the path actually used at runtime?

Subtraction:
- What became deletable?
- What was actually deleted?
- What compatibility remains, and when should it retire?

Ownership:
- Does each responsibility have one home?
- Did shared code stay generic?
- Did domain meaning stay at domain seams?

Clarity:
- Are there fewer live concepts to learn?
- Did the change compress meaning without losing behavior?
- Is the system more direct than before?

Risks:
- Any hidden old substrate?
- Any semantic authority moved into deterministic code?
- Any docs or tests still teaching the old path?
```

---

## North Star

The target is not a tiny system.

The target is a system where the visible shape matches the real shape:

- no secret old engine
- no permanent dual paths
- no spaghetti adapter stack
- no doctrine dumping ground
- no generic trunk polluted by one domain's private needs
- no accidental complexity pretending to be essential

Raptor 3 means the system has been redesigned until the essential parts are integrated, native, and obvious.
