# Testing Ethos

This document defines how we write tests in this repo to preserve long-term sanity.
It is meant to be broadly reusable across projects.

## The point of tests

Tests exist to prevent **rot**.

A good test suite is weight-bearing: small, stable, and aimed at the failure modes that matter.
We do not write tests to “look thorough.” We write tests to protect invariants.

## Where tests live (critical)

**Tests must be co-located with the module they validate.**  
Avoid placing new tests in the repo root unless there is a strong reason.

Examples:
- `backend/corpus/` tests go in `backend/corpus/test_*.py`
- `backend/retrieval/` tests go in `backend/retrieval/test_*.py`
- `backend/agents/` tests go in `backend/agents/test_*.py`

Reason: root-level tests become a dumping ground. Co-location keeps ownership clear and stops scope sprawl.

## What a “good test” looks like

A good test is:

- **Deterministic** (same input → same output)
- **Focused** (asserts a small number of important truths)
- **Non-brittle** (doesn’t fail because of irrelevant formatting or incidental ordering)
- **Readable** (future-you can understand why it exists)
- **Boundary-oriented** (tests behavior at public seams, not private internals)

## Weight-bearing invariants (what we test first)

Prioritize tests that protect things that cause real damage if they break:

- “This module never throws in normal failure scenarios.”
- “This ID / hash / reference is stable and deterministic.”
- “Enumeration returns the expected set.”
- “Hydration returns a consistent shape.”
- “Missing data returns safe empty output + an explicit reason/provenance.”
- “This transformation preserves meaning-critical fields.”

## External dependencies: prefer isolation, allow integration

**Default stance:** tests should avoid external dependencies because they reduce determinism and increase friction.

But this is not a law. Some things genuinely require dependencies.

So we separate test types:

### Unit-ish tests (default)
- Run locally with minimal setup
- No network calls
- No paid APIs
- No large downloads
- Use stubs/noops or small fixtures

### Integration tests (allowed and useful)
- Use real dependencies (DB, embeddings, external services, GPU, etc.)
- Clearly labeled and optionally skipped by default
- Run when the dependency is available, and give high-value confidence

Practical rule: **if a dependency is required, make it explicit** and keep the test’s purpose narrow.

## Speed: prefer fast feedback, but don’t sacrifice truth

Fast tests matter because they keep the feedback loop tight.  
But speed is not the goal—**truth is.**

So:
- Prefer fast tests for everyday development.
- Allow slower tests when they validate something high-value.
- When a test is slow, make that an intentional choice (label it, isolate it, run it less often).

A good pattern is a “pyramid”:
- many quick tests for core invariants
- fewer slower tests for realistic end-to-end confidence

## Prefer realistic small fixtures over deep mocking

When testing storage or pipelines, it’s often better to build a minimal realistic fixture than to mock everything.

Pattern:
- Create a temp directory
- Write minimal fixture files (JSON, images, etc.)
- Point your code at the temp root
- Assert behavior at the boundary

This yields tests that are both realistic and stable.

## Don’t encode implementation details

Tests should not lock us into internal architecture.

Avoid:
- asserting incidental intermediate steps
- asserting private method calls
- asserting exact internal helper usage

Prefer:
- asserting observable behavior at the public API
- asserting stable shapes and invariants

## Failure is data: return reasons, not mystery

When something fails (missing file, corrupt artifact, unsupported mode), tests should confirm:

- it failed safely (no exception unless explicitly desired)
- the output carries an explicit reason or provenance marker
- downstream code can distinguish “missing” from “no match” from “unimplemented”

## Naming and organization

- Use descriptive names: `test_<feature>_<invariant>.py` or `test_<invariant>.py`
- Each test name should describe the invariant, not the implementation.
- Keep tests short; use helper functions to build fixtures.

## Minimalism rule

If a test doesn’t protect an invariant, delete it.

A small, high-signal suite beats a large, noisy one.
