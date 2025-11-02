# TODO: Migrate Text→Schema workspace to a dedicated page

- Problem:
  - Text→Schema is currently rendered as a component via `pages/index.tsx` with mode toggles.
  - No deep-linkable route; navigation and state are implicit in a single page.

- Plan (phased):
  1. Create `frontend/pages/text-to-schema.tsx` that renders `TextToSchemaWorkspace`.
  2. Update Home and Image workspace navigation to `router.push('/text-to-schema')`.
  3. Keep legacy toggle path temporarily for rollback; remove once verified.
  4. Optional: accept `?dossierId=` for preloading finalized snapshot.

- Acceptance Criteria:
  - `/text-to-schema` loads the existing workspace with identical behavior.
  - Home card and Image workspace button open `/text-to-schema`.
  - Back/Exit returns to `/` cleanly.

- Notes:
  - No data migrations required. Workspace state stored via `workspaceStateManager`.
  - Remove `frontend/pages/text-schema.tsx` (temporary) when done to avoid confusion.


