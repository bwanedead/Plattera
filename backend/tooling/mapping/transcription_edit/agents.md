# agents.md

## Scope
- Folder: `backend/tooling/mapping/transcription_edit/`
- Purpose: Deterministic mapping-family transcript-edit tooling (contracts/apply/validators/section/span-seed helpers).

## Contracts & invariants
- `EditPlanV0.source_transcript_hash` must match exact UTF-8 hash of source transcript text.
- `plan_fingerprint` must validate against canonical payload hash.
- Apply must refuse on root hash mismatch before any op runs.
- Per-op apply must verify `expected_old.old_excerpt` (and `old_hash` when provided).
- Locator v0 supports only `anchors` and `offsets`.

## Allowed changes
- Safe: deterministic validator/apply/contract improvements with matching tests.
- Do not add runtime orchestration or controller semantics here.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/tooling/mapping/transcription_edit/tests -q`
- Lint: `N/A`
- Build/Run: `N/A`
- Other: `N/A`

## Gotchas
- Keep this package deterministic and execution-focused; semantic authorship belongs to domain-pack agent logic.
- If a helper is universal across families, move it toward `backend/tooling/shared/` instead of growing mapping-local scope.

## Links
- Docs: `docs/architecture/harness/transcription-edit-loop-disposition.md`
- Related code: `backend/services/workflows/mapping/transcription_edit/`
