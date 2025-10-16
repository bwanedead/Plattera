<!-- d3205ac9-abbf-49b0-8534-98e0a5aeb47d c5e12a39-003d-4cd2-8c1b-36d95539c0c5 -->
# Dossier Finalization & Text→Schema Integration

### Objectives

- Persist finalized dossier snapshots with strong provenance and associations to their source dossier.
- Provide a discovery API for finalized dossiers (robust, rebuildable).
- Enable finalization from stitched dossier view and the Dossier Manager context menu.
- Add a Text→Schema workspace dropdown to select a finalized dossier and load stitched or per-section content.

### Backend (modular services)

1) FinalizationService (new file, used by finalize endpoint)

- Inputs: `dossier_id`
- Builds snapshot: stitched_text, sections[], selection_map[], counts, errors, sha256, timestamps, dossier title
- Writes to `.../views/transcriptions/{dossier_id}/final/dossier_final_{ts}.json` and updates pointer `dossier_final.json`
- Updates `backend/dossiers_data/state/finalized_index.json` (atomic write). Index entry: { dossier_id, title, latest_generated_at, text_length, section_count, has_errors }

2) Endpoint updates

- Extend existing POST `/api/dossier/finalize` to use FinalizationService and include `sections` + `selection_map` in response
- Add GET `/api/dossier/finalized/list` to return index (scan directory if index missing)
- Keep existing GET `/api/dossier/final/{dossier_id}`

### Frontend

1) Dossier Manager

- Add “Finalize Dossier” to context menu of each dossier item (not inline button to avoid clutter)
- When in stitched dossier view, keep the primary “Finalize Dossier” button (already present)
- After success, show toast with CTA: “Open in Text→Schema” and dispatch refresh events

2) Text→Schema workspace

- Add a dropdown: “Select finalized dossier” using GET `/api/dossier/finalized/list`
- On select: GET `/api/dossier/final/{id}` and allow user to choose:
- Process stitched_text
- Process per-section
- Wire save endpoints (future): POST schema version under `processing_jobs/text_to_schema/{dossier_id}`

### Data Contracts

- Final snapshot JSON fields:
- dossier_id, dossier_title, generated_at
- stitched_text
- sections: [{ segment_id, order, transcription_id, draft_id_used, text }]
- selection_map: [{ segment_id, transcription_id, draft_id_used, version_type, version_num, size_bytes }]
- counts: { segments, text_length }
- errors: []
- sha256

### Non-breaking & SoC

- FinalizationService encapsulates assembly and persistence; endpoints thin wrappers
- Index is additive, optional (fallback to scan)
- Text→Schema consumes read-only snapshots; editing continues in Dossier Manager

### Follow-ups

- Pagination in `/finalized/list` for large sets
- Schema persistence endpoints and UI
- Section-level navigation in Text→Schema

### To-dos

- [ ] Create FinalizationService to write snapshot and update index
- [ ] Extend finalize endpoint to include sections + selection_map
- [ ] Add endpoint to list finalized dossiers
- [ ] Add Finalize action to Dossier Manager context menu
- [ ] Add dropdown to select finalized dossier in Text→Schema
- [ ] Load stitched or per-section content after select
- [ ] Add toast/CTA to open in Text→Schema post-finalize
- [ ] Backend tests for FinalizationService and index
- [ ] Frontend tests for finalize action and Text→Schema selection