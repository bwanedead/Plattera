# Static Governance

This document explains the repo's first-pass linting and lint-adjacent policy layer.

## Framing

In this repo, lint is not just style cleanup. It is one part of a broader static-governance layer used to protect structural sanity:
- prevent new layer violations
- slow monolith growth
- stop convenient-but-harmful shortcuts from becoming normal
- make architectural expectations machine-checkable for both humans and agents

The current implementation is intentionally narrow. It blocks a small set of high-confidence regressions and keeps broader code-health pressure in warning mode until the codebase is ready for stricter rollout.

## Current entrypoints

Frontend package commands in `frontend/package.json`:
- `npm --prefix frontend run lint`
- `npm --prefix frontend run governance`
- `npm --prefix frontend run check`
- `npm --prefix frontend run check:full`

Current implementation files:
- `frontend/eslint.config.mjs`
- `tools/static-governance.mjs`
- `tools/static-governance-config.mjs`
- `.github/workflows/static-governance.yml`

Shared boundary-path definitions now live in `tools/static-governance-config.mjs` so the ESLint layer and the repo governance script do not drift apart when the boundary policy changes.

## What blocks now

### 1. Page-boundary violations
Shared frontend layers must not import page modules directly.

Blocked surfaces:
- `frontend/src/components/**`
- `frontend/src/hooks/**`
- `frontend/src/services/**`
- `frontend/src/utils/**`

Reason:
- pages are route surfaces, not shared dependencies
- allowing imports to flow backward from shared code into pages creates structural drift and brittle coupling

Enforced by:
- `frontend/eslint.config.mjs`
- `tools/static-governance.mjs`

### 2. New root-level legacy test sprawl
New `test_*.py` files at repo root or `backend/` root are blocked unless explicitly allowlisted.

Reason:
- repo-wide testing ethos requires new tests to be co-located with the module they validate
- root-level tests become a dumping ground and blur ownership

Enforced by:
- `tools/static-governance.mjs`

### 3. Growth in known monolith hotspots
Known oversized files are allowed to exist temporarily, but they are not allowed to keep growing past a small baseline margin.

Reason:
- the repo already has legacy hotspots
- a hard global max-lines rule would create immediate noise
- a growth budget prevents further decay without forcing a single giant cleanup

Enforced by:
- `tools/static-governance.mjs`

### 4. New component-level service coupling
Frontend components may not increase direct service imports beyond the current baseline without an explicit policy update.

Reason:
- this protects the repo against agents solving local tasks by pulling transport or persistence concerns into presentation code
- it keeps pressure on routing behavior through hooks or other dedicated orchestration surfaces

Enforced by:
- `tools/static-governance.mjs`

### 5. Backend transport-layer coupling
Backend services and pipelines must not import `api.*` modules.

Reason:
- `backend/api/` is the transport layer
- backend services and pipelines should stay reusable without depending on endpoint modules
- this prevents business logic from reaching upward into request/response code

Enforced by:
- `tools/static-governance.mjs`

## What is warning-only for now

These are visible but not blocking:
- file size warnings
- function size warnings
- complexity warnings

Reason:
- these are useful architectural pressure signals
- the current codebase still has many legacy hotspots
- warning mode gives visibility without making normal work impossible

Current warning surface:
- `npm --prefix frontend run lint`

## Execution surfaces

### Local development
- `npm --prefix frontend run lint`
  - warning-focused structural pressure
- `npm --prefix frontend run governance`
  - blocking repo-specific policy checks
- `npm --prefix frontend run check`
  - recommended local gate for the current rollout

### CI
- `.github/workflows/static-governance.yml`
  - runs frontend lint
  - runs repo governance checks

### Non-blocking baseline
- `npm --prefix frontend run check:full`
  - includes typecheck
  - currently non-blocking because the repo already has unresolved TypeScript errors

## Why typecheck is not blocking yet

`npm --prefix frontend run typecheck` currently fails on pre-existing frontend issues. Until that backlog is reduced, typecheck remains available but does not block CI for this rollout.

This is intentional:
- we want to add real governance now
- we do not want to fake success
- we also do not want to make the repo red on unrelated legacy debt the moment the policy layer is introduced

## How to work with the current rules

If a governance rule fails:
1. Determine whether the failure reflects a real architectural regression.
2. Prefer changing code to satisfy the rule.
3. Only adjust the baseline or allowlist when the exception is deliberate and structurally justified.

If you need to extend the policy layer:
1. Prefer cheap, deterministic, high-signal rules.
2. Start narrow and explicit rather than broad and aspirational.
3. Add documentation here in the same patch.
4. Keep blockers for clear regressions.
5. Keep noisier code-health rules in warning mode until the baseline is ready.

## Next likely expansions

Good next steps:
- touched-file escalation for size and complexity hotspots
- promoting typecheck to blocking once the existing TypeScript backlog is reduced

## Related docs

- `docs/ethos/architecture-ethos.md`
- `docs/ethos/structure-ethos.md`
- `docs/ethos/testing-ethos.md`
- `frontend/agents.md`
- `AGENTS.md`
