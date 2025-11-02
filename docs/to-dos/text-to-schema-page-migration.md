# TODO: Migrate Text→Schema workspace to a dedicated page

Status: deferred (tracked for a future sprint)

## Current State
- The Text→Schema workspace lives as a component: `frontend/src/components/TextToSchemaWorkspace.tsx`.
- It is rendered by `frontend/pages/index.tsx` by toggling application mode (`'text-processing'`).
- Global styles already exist at `frontend/styles/workspaces/text-to-schema.css` and are imported via `styles/main.css`.
- There is no dedicated Next.js page route; deep-linking to the workspace is not available.

## Rationale
- Modularity and separation of concerns: each workspace should own a page and lifecycle.
- Deep-linking/bookmarking: `/text-to-schema` (optionally `/text-to-schema/[dossierId]`).
- Simpler navigation and fewer implicit state transitions in `index.tsx`.

## End State
- Add a page `frontend/pages/text-to-schema.tsx` that renders `TextToSchemaWorkspace`.
- Navigation from Home and the Image workspace routes to `/text-to-schema`.
- Optional: support URL params (e.g., `?dossierId=`) to preload a finalized dossier snapshot.

## Implementation Steps
1. Create `frontend/pages/text-to-schema.tsx`:
   - Minimal wrapper component that renders `TextToSchemaWorkspace`.
   - Wire `onExit` to route back to `/`.
2. Update navigation:
   - In `frontend/pages/index.tsx`, change the "Text to Schema" button handler to `router.push('/text-to-schema')`.
   - In `ImageProcessingWorkspace`, pass `onNavigateToTextSchema={() => router.push('/text-to-schema')}`.
3. Keep the legacy toggle path in `index.tsx` temporarily for rollback; remove once verified.
4. Optional enhancements (later):
   - Accept `dossierId` query param to preload finalized `stitched_text`.
   - Add breadcrumbs/header actions specific to this workspace.

## Rollout / Backout
- Rollout: Add page and route buttons; keep legacy flow for a version or two.
- Backout: Revert to original toggle-based handlers; no data migrations required.

## Risks & Mitigations
- Unexpected state reset when moving to page-level lifecycle.
  - Mitigation: Preserve workspace state via `workspaceStateManager`; rehydrate on mount.
- Broken links or navigation from other components.
  - Mitigation: Keep legacy flow until links are fully verified.

## Acceptance Criteria
- Visiting `/text-to-schema` renders the same workspace with identical behavior.
- Home card and Image workspace button open `/text-to-schema`.
- Back/Exit returns to `/` cleanly.
- No regressions to existing Text→Schema features or styling.

## Notes
- Remove the temporary `frontend/pages/text-schema.tsx` (if present) during migration to avoid confusion.


