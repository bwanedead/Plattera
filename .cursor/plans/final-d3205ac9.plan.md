<!-- d3205ac9-abbf-49b0-8534-98e0a5aeb47d cdb55875-1721-488f-a1d3-464effb323e3 -->
# Final Draft & Dossier Selection Overhaul

### Goals

- Final overrides at every level (draft, run, section/segment, dossier).
- Deterministic auto-display when no final: prefer av2 > av1 > v2 > v1.
- Consensus is only considered at run level and above; never for draft-level fallback.
- Dossier view stitches per-section selections using the same rules (default run = lowest index).
- Non-breaking, modular, and testable changes.

### Data and ID Conventions

- Continue storing per-segment finals in `backend/dossiers_data/state/{dossier_id}/final_registry.json` via `FinalRegistryService`.
- Use strict versioned IDs across UI fetches:
- Raw: `{baseTid}_v{n}_v{1|2}`
- Alignment: `{baseTid}_draft_{n}_v{1|2}`
- Consensus (run-level and above only): `{baseTid}_consensus_{llm|alignment}_v{1|2}`
- Prefer existence flags over stored heads when computing the latest (fallback) to avoid stale pointers; use heads to disambiguate ties.

### Selection Precedence by Level

- Draft view:
- If a final is set for the segment: auto-show that final (strict ID). No fallback on 404 (surface error to user).
- Otherwise, resolve within the selected draft only: alignment v2 → alignment v1 → raw v2 → raw v1.
- Never consider consensus for draft-level fallback.
- Run view:
- If final is set: auto-show final (strict ID). No fallback on 404.
- Else fallback: consensus LLM (prefer newer) → consensus alignment (prefer newer) → best flag → longest → first.
- For non-consensus picks, translate to strict ID using version metadata.
- Segment (section) view:
- Choose run with lowest `position`/index.
- Apply run view rules above.
- Dossier view:
- For each segment, apply segment rules; stitch in segment order.
- Pass `dossierId` to text fetch to avoid cross-dossier collisions.

### Frontend Changes

- Introduce `frontend/src/services/dossier/versionResolver.ts`:
- `pickStrictVersionedId(run, draft)`: returns strict ID using existence/head flags with precedence av2 → av1 → v2 → v1.
- `pickConsensusStrictId(run, type)`: returns latest LLM/alignment consensus strict ID where applicable.
- Update `selectionResolver.ts`:
- Always check finals first (use registry-exposed `run.metadata.final_selected_id` or fetch via `dossierApi` if absent).
- Draft-level: if no final, resolve within that draft only via `versionResolver.pickStrictVersionedId`.
- Run/Segment-level: use `pickConsensusStrictId` first, else `pickStrictVersionedId` for best/longest.
- Dossier-level: `stitchToText` using strict IDs and pass `dossier.id` to `textApi.getDraftText`.
- Update `stitchingPolicy.ts`:
- Use run with lowest index (position asc) for default.
- Apply finals override; otherwise compute strict IDs via `versionResolver`.
- Update `textApi.ts` cache invalidation:
- Also listen to `dossier:final-set` to invalidate affected entries.
- Verify `FinalDraftSelector.tsx` provides a strict versioned `currentDraftId` when invoking `setFinalSelection`; if not strict, convert via `versionResolver`.

### Backend Validation (no breaking changes)

- `management_service.py` already exposes `run.metadata.final_selected_id` by consulting `FinalRegistryService` with head.json fallback.
- `view_service._load_transcription_content_scoped()` supports strict versioned IDs for raw, alignment, and consensus.
- Finals endpoints are routed (`backend/api/router.py`); finalization endpoint stitches with finals-first policy and per-segment fallback.

### Error Handling & UX

- For finals: strict loading (no auto-fallback) to avoid hiding misconfigurations; show clear UI message if not found.
- For fallback paths: attempt best-effort resolution and surface minimal warnings in console/logs.

### Tests

- Frontend unit tests for `versionResolver` and `selectionResolver` (draft/run/segment/dossier cases, finals-first, consensus-only at run+).
- Backend tests:
- Finalization endpoint successfully writes snapshot honoring finals and policy fallback.
- `FinalRegistryService` CRUD and persistence.
- E2E smoke: selecting a final updates auto-view at all levels and appears in stitched dossier view.

### Documentation

- Update `FINAL_SELECTION_IMPLEMENTATION.md` to document precedence and strict IDs.
- Add a short developer playbook for adding future version types without touching policy consumers.

### Key Files to Change

- Frontend: `frontend/src/services/dossier/selectionResolver.ts`, `frontend/src/services/dossier/stitchingPolicy.ts`, `frontend/src/services/textApi.ts`, new `frontend/src/services/dossier/versionResolver.ts`, optionally `frontend/src/components/image-processing/FinalDraftSelector.tsx` (normalize ID before set).
- Backend: none required (verify only).

### To-dos

- [ ] Create versionResolver with strict ID helpers and precedence rules
- [ ] Apply finals-first and strict IDs in selectionResolver across modes
- [ ] Use run index 1 and strict IDs; finals-first in stitchingPolicy
- [ ] Invalidate textApi caches on dossier:final-set event
- [ ] Normalize currentDraftId to strict ID in FinalDraftSelector before set
- [ ] Verify backend view_service handles all strict ID forms
- [ ] Add unit tests for versionResolver and selectionResolver precedence
- [ ] Add tests for finalize endpoint and FinalRegistryService CRUD
- [ ] Add E2E flow: select finals, verify run/segment/dossier views and stitching
- [ ] Update FINAL_SELECTION_IMPLEMENTATION.md with precedence and examples