<!-- d3205ac9-abbf-49b0-8534-98e0a5aeb47d 4c4fdb69-232a-40e1-a52c-e47ded8674f4 -->
# Finalized Dossier → Text to Schema Integration

## Scope

- Replace "Use Final Draft" with a "Finalized Dossier" selector in the Text→Schema control panel
- Selecting a finalized dossier loads its stitched text into the viewer
- Converting to schema uses the selected finalized dossier text
- Persist schema results to disk, associated with the dossier

## Frontend

1) TextToSchemaWorkspace (`frontend/src/components/TextToSchemaWorkspace.tsx`)

- Load list via `finalizedApi.listFinalized()` on mount
- Add state: `finalizedList`, `finalizedLoading`, `selectedFinalizedId`
- On select: `finalizedApi.getFinal(id)`, set `finalDraftText` and metadata; switch to Original tab
- Pass props to control panel: list, loading, selected id, onSelect handler

2) Control Panel (`frontend/src/components/text-to-schema/TextToSchemaControlPanel.tsx`)

- Replace input mode with: `finalized` | `direct-input` (default `finalized`)
- Render dropdown of finalized dossiers; show loaded status and char count
- Keep direct text input as alternative path
- Process button uses currently active text (finalized loaded or direct input)

3) Persist selection between sessions

- Store `selectedFinalizedId` and `finalDraftText` in `workspaceStateManager` (`textToSchema` domain)
- On mount, if `selectedFinalizedId` exists, try to reload snapshot (optional best-effort)

## Backend

1) Save schema results associated to dossier

- Add endpoint `POST /api/text-to-schema/save` with body: `{ dossier_id, snapshot_generated_at?, model_used, structured_data, original_text, metadata }`
- Service: `SchemaPersistenceService` (new file `backend/services/text_to_schema/schema_persistence_service.py`)
- Path: `backend/dossiers_data/processing_jobs/text_to_schema/{dossier_id}/schema_{ts}.json`
- also write/maintain pointer `latest.json`
- Append entry in an index `backend/dossiers_data/state/text_to_schema_index.json` (atomic)

2) Extend existing convert endpoint to accept optional `dossier_id`

- If `dossier_id` provided, include it in response metadata; FE will call save endpoint after successful convert

## Wiring Convert + Save

- FE: After `convert_text_to_schema` success, if `selectedFinalizedId` is set, call save endpoint with dossier id, model, structured_data, original_text, metadata
- On save success, show inline non-blocking confirmation (no browser modal)

## Types & Contracts

- Snapshot fields already defined
- Schema save object fields:
- `dossier_id`, `saved_at`, `model_used`, `original_text_sha256`, `structured_data`, `original_text_length`, optional `source`: `finalized_dossier` with `dossier_title`, `generated_at`

## UI Indicators

- Control panel shows the selected finalized dossier (title, timestamp)
- Results tabs unchanged; Original shows loaded text; converting populates schema tabs

## Tests

- Backend: unit tests for `SchemaPersistenceService` (atomic write, index update)
- Backend: endpoint tests: save accepts and writes; convert returns metadata
- Frontend: simple happy-path test for dropdown select loads text; conversion triggers save when selectedFinalizedId exists

## Files Touched

- frontend/src/components/TextToSchemaWorkspace.tsx
- frontend/src/components/text-to-schema/TextToSchemaControlPanel.tsx
- frontend/src/services/dossier/finalizedApi.ts (already exists)
- frontend/src/services/textToSchemaApi.ts (add `saveSchemaForDossier`)
- frontend/src/services/workspaceStateManager.ts (add selectedFinalizedId)
- backend/api/endpoints/text_to_schema.py (accept optional dossier_id; add `/save` route)
- backend/services/text_to_schema/schema_persistence_service.py (new)

## Acceptance

- User can pick a finalized dossier from dropdown, preview text
- "Convert to Schema" uses that text and, on success, persists schema to `{dossier_id}` location
- No browser prompts; UI reflects selection and save non-intrusively

### To-dos

- [ ] Wire finalized list/loading and selection in TextToSchemaWorkspace
- [ ] Replace input source toggle with finalized dropdown + direct input
- [ ] Persist selectedFinalizedId in workspaceStateManager
- [ ] Allow dossier_id in convert endpoint metadata
- [ ] Create POST /api/text-to-schema/save to persist schema
- [ ] Implement SchemaPersistenceService with atomic write and index
- [ ] FE calls save endpoint after convert when finalized selected
- [ ] Add tests for schema persistence and endpoints
- [ ] Add tests for finalized selection & convert-save flow