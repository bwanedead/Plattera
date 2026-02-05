# Tiny Story Guidelines (Ralph)

## Definition

A "story" is the smallest independently shippable unit of work that:
- can be completed in a single iteration
- has objective, verifiable acceptance criteria
- can be committed as one coherent change

## Story Size Rules

A story should typically be:
- 1–3 files changed (sometimes more, but avoid broad rewrites)
- one concept / one behavioral change
- no "and also" scope creep

If a story requires: "refactor + build new feature + migrate data"
…split it.

## Good Story Examples

- "Add `priority` column to Task model with default 0, add migration, update API response; tests updated."
- "Add `/health` endpoint returning build/version; add test."
- "Add new CLI command `myapp index preview`; prints stats; add test."

## Bad Story Examples

- "Refactor backend architecture."
- "Implement entire feature end-to-end."
- "Make UI nicer" (subjective; needs human judgment)

## Acceptance Criteria Rules

Acceptance criteria MUST be:
- objective: pass/fail
- testable: via unit tests, integration tests, or deterministic CLI output
- local: doesn't require human eyeballing unless explicitly allowed

Prefer criteria like:
- "`pytest` passes"
- "endpoint returns specific JSON shape"
- "CLI prints specific headings and includes expected fields"

Avoid criteria like:
- "looks good"
- "should be fast"
- "clean code"
