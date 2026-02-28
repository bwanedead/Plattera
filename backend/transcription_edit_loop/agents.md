# agents.md

## Scope
- Folder: `backend/transcription_edit_loop/`
- Purpose: Typed v0 contracts and deterministic transcript edit application.

## Contracts & invariants
- `EditPlanV0.source_transcript_hash` must match exact UTF-8 hash of source transcript text.
- `plan_fingerprint` must validate against canonical payload hash.
- Apply must refuse on root hash mismatch before any op runs.
- Per-op apply must verify `expected_old.old_excerpt` (and `old_hash` when provided).

## Allowed changes
- Safe: add new validator helpers, extend report metadata, add tests.
- Do not casually change reason codes or hashing canonicalization; tests and downstream consumers rely on these.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/transcription_edit_loop/tests -q`
- Lint: `N/A`
- Build/Run: `N/A`
- Other: `N/A`

## Gotchas
- Locator v0 supports only `anchors` and `offsets` by design.
- `replace_line` exists as an op type but does not imply a line-number locator contract in v0.

## Links
- Docs: `docs/transcription-edit-loop-spec-v0.md`
- Related code: `backend/transcription_edit_loop/contracts.py`
- Related code: `backend/transcription_edit_loop/apply.py`
