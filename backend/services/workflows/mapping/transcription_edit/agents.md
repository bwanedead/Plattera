# agents.md

## Scope
- Folder: `backend/services/workflows/mapping/transcription_edit/`
- Purpose: Workflow/application support for transcript-edit runs (artifact persistence and run registry).

## Contracts & invariants
- Keep this layer focused on runtime/application support, not semantic domain authorship.
- Deterministic capability logic remains in `backend/tooling/mapping/transcription_edit/`.
- Registry payload keys and run status fields are API-consumed; keep them additive/backward-safe.
- Persistence writes must stay atomic and UTF-8.

## Allowed changes
- Safe: persistence pathing, artifact IO hardening, registry resilience, run bookkeeping fixes.
- Do not add controller-style loop semantics or domain decision logic here.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/tooling/mapping/transcription_edit/tests/test_run_registry.py backend/tooling/mapping/transcription_edit/tests/test_sections_and_run.py -q`
- Lint: `N/A`
- Build/Run: `N/A`
- Other: `N/A`

## Gotchas
- Keep orchestration minimal in this layer; pipeline-local repair flow should compose tooling + persistence directly.
- If support primitives become family-shared, move them upward to `backend/services/workflows/mapping/` or `backend/services/workflows/shared/`.

## Links
- Docs: `docs/architecture/harness/transcription-edit-loop-disposition.md`
- Related code: `backend/tooling/mapping/transcription_edit/`
- Related code: `backend/pipelines/image_to_text/pipeline.py`
