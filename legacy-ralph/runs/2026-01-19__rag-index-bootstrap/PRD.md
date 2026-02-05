# PRD: RAG index bootstrap and self-heal

## Context
Installing the embedding model should make the RAG system usable immediately, but today missing index artifacts cause the pool to be unavailable and block `/api/index/execute`. Users get stuck even though embeddings are installed.

## Goal
Bootstrap empty RAG index artifacts automatically and self-heal on demand so diagnostics and indexing can run without auto-indexing user documents.

## Non-goals
- Auto-indexing user documents or changing indexing policy.
- Changing embedding installation flow beyond triggering bootstrap.
- Altering retrieval quality, ranking logic, or embedding model selection.

## Users / Use cases
- As a user who just installed embeddings, I want RAG Index Health to become operational without extra steps so I can choose when to index.
- As a user opening the RAG Index panel after files were deleted, I want the system to self-repair and allow indexing actions.

## Scope
- Backend retrieval/semantic index bootstrap helper and index maintenance endpoints.
- Frontend assets install hook and RAG Index panel diagnostics flow.
- UI status messaging for missing artifacts vs missing embeddings.

## Constraints / invariants
- Must not auto-index user docs; only create empty artifacts.
- Bootstrap must be idempotent and non-destructive unless `force=true`.
- `/api/index/diagnose` remains non-mutating.
- Preserve existing pool identifiers and runtime identity rules.
- Avoid broad refactors; keep changes minimal and modular.
- If embeddings are not installed or cannot be loaded, bootstrap returns a stable "embeddings missing" reason (no throw).
- Partial/mismatched artifacts do not mutate by default; `force=true` recreates a coherent set.

## Success criteria
- Installing embeddings triggers a bootstrap call; RAG Index Health no longer reports missing files.
- `/api/index/execute` self-repairs missing artifacts and proceeds to index.
- Opening the RAG Index panel when artifacts are missing triggers a one-time bootstrap and re-diagnose.
- When embeddings are installed but vectors are empty, UI shows "Not Indexed Yet" (not "Unavailable") with an initialize action.

## Edge cases
- Only one artifact missing (manifest, hnsw, or metadata db) should report "needs force repair."
- Manifest identity mismatch with current runtime identity should report "stale identity; needs force rebuild."
- Workspace moved or index folder deleted between sessions.
- Bootstrap called repeatedly from UI without side effects.
- Embeddings not installed or loadable should return "embeddings missing" without mutation.

## Implementation notes (optional)
- Add a single backend helper to ensure empty pool artifacts exist and return a stable report.
- Add a dedicated `/api/index/bootstrap` endpoint; keep diagnose read-only.
- Use the Assets tray install transition to call bootstrap.
- Add a one-time auto-repair flow in RAG Index panel when diagnose indicates missing files.

