<!-- 75efeb73-8f5e-4072-aad9-869a7f0ada9d bf4ad4ec-844f-47ab-a3f0-4d930f40e774 -->
# Complete Dossier Purge and Small-Window UX Improvements

### Backend

- Centralize purge logic
- Create `backend/services/dossier/purge_service.py` with `purge_dossier(dossier_id, scrub_jobs=True)` that:
- Collects transcription IDs via associations file, falls back to `TranscriptionAssociationService`, and (last resort) scans `dossiers_data/views/transcriptions/{dossier_id}`.
- Removes per-dossier data: `management/dossier_{id}.json`, `associations/assoc_{id}.json`, `views/transcriptions/{id}/`, `state/{id}/`, optional `navigation/{id}/`.
- Deletes images for all associated transcription IDs from `images/{original,processed}` and legacy flat JSON drafts under `views/transcriptions` root.
- When `scrub_jobs=True`, rewrites `dossiers_data/processing_jobs/image_to_text/jobs.jsonl` without lines that reference the dossier id.
- Returns a structured summary (removed paths and counts) and logs it at info level.

- Wire purge service
- Update `DossierManagementService.delete_dossier` to call `purge_dossier` (single source of truth) and keep existing return semantics.
- Normalize static images log in `backend/main.py` to print `images_root.resolve()`.

- Logging
- Add one-line purge summary: ids removed, counts per category (files/dirs/images/jobs).
- Log a notice if any category was missing (already deleted) to ease debugging.

### Frontend

- Ensure “Delete Selected” is always visible in bulk view
- In `frontend/src/components/dossier/bulk/BulkDeleteView.tsx`, make the outer wrapper the scroll container and keep the bottom action bar sticky with a higher `z-index`. Remove inner list overflow.
- Optional: add concise console logs for bulk delete start/progress/finish.

### Acceptance

- Deleting any dossier removes all dossier-specific objects from: `management/`, `associations/`, `views/transcriptions/{id}/`, `state/{id}/`, optional `navigation/{id}/`, images for its transcription IDs, and legacy flat drafts. Processing job entries referencing the dossier are scrubbed.
- Bulk delete button visible on smaller windows; progress remains unchanged.

### Notes

- Processing job scrubbing is enabled by default for full data removal; we can gate behind a setting if desired.
- The purge service codifies all locations; future storage additions should extend it to remain complete.

### To-dos

- [ ] Add POST /dossier-management/bulk with delete action
- [ ] Call ImageStorageService.delete_images inside delete_dossier
- [ ] Add BulkDeleteRequest/Response Pydantic models
- [ ] Publish SSE per deletion; handle dossier:deleted in FE
- [ ] Update useDossierManager.bulkDelete tombstones, progress, fallback
- [ ] Enhance ConfirmDeleteModal: progress, background, cancel remaining
- [ ] Ensure footer bulk path clears filters and reloads
- [ ] Add per-attempt timeout to dossierApi requests
- [ ] Ensure tombstones filtered until hard reload confirms
- [ ] Add tests: bulk delete purges images; FE progress UX smoke