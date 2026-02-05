# PRD: Golden Example — Add /health endpoint

## Context
This is a toy “golden example” run to prove the Ralph run folder format and templates are usable end-to-end.

## Goal
Add a simple health check endpoint in the backend and a minimal test that verifies it.

## Non-goals
- No UI changes.
- No auth, no version/build metadata.
- No infra/CI changes.

## Users / Use cases
- As a developer, I want a `/health` endpoint so that I can quickly verify the API process is responsive.

## Scope
- Backend API (FastAPI) only.

## Constraints / invariants
- Must obey `CLAUDE.md` repo rules.
- Keep changes minimal and localized.

## Success criteria
- A GET to `/health` returns a JSON object with at least `{ "status": "ok" }`.
- A deterministic test exists and passes locally (e.g. via `python -m pytest -q`).

## Edge cases
- Endpoint must be reachable without auth (if auth exists elsewhere).
- Test should not depend on an external running server process.


