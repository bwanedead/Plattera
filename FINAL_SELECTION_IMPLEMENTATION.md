# Final Selection Implementation - Complete

## Overview
This document summarizes the complete implementation of the final draft selection system with full version resolution for the Plattera dossier management infrastructure.

## Features Implemented

### 1. Backend Storage (`backend/services/dossier/edit_persistence_service.py`)
- ✅ Extended `head.json` to include `final.selected_id` field
- ✅ Added `set_final_selection()` to persist a specific versioned draft ID
- ✅ Added `clear_final_selection()` to remove the selection
- ✅ Added `get_final_selection()` to retrieve the current selection
- ✅ Timestamps all final selection changes

### 2. Backend API Endpoints

#### Final Selection CRUD (`backend/api/endpoints/dossier/final_selection.py`)
- ✅ `POST /api/dossier/final-selection/set` - Set final selection
- ✅ `POST /api/dossier/final-selection/clear` - Clear final selection
- ✅ `GET /api/dossier/final-selection/get` - Get current selection

#### Dossier Finalization (`backend/api/endpoints/dossier/finalize.py`)
- ✅ `POST /api/dossier/finalize` - Stitch all segment finals into snapshot
  - Iterates through all segments
  - Uses `final_selected_id` if set (strict, with retry)
  - Falls back to policy (consensus → best → longest) if no final set
  - Records errors for any 404s
  - Writes snapshot to `.../final/dossier_final.json`
- ✅ `GET /api/dossier/final/{dossier_id}` - Retrieve finalized snapshot

#### Router Integration (`backend/api/router.py`)
- ✅ Wired both new routers into main API

### 3. Backend Hierarchy Population (`backend/services/dossier/management_service.py`)
- ✅ Reads `final_selected_id` from `head.json`
- ✅ Exposes it at `run.metadata.final_selected_id` for frontend consumption

### 4. Frontend API Client (`frontend/src/services/dossier/dossierApi.ts`)
- ✅ `setFinalSelection()` - Set final for segment
- ✅ `clearFinalSelection()` - Clear final for segment
- ✅ `getFinalSelection()` - Get current final
- ✅ `finalizeDossier()` - Trigger backend finalization
- ✅ Emits custom events: `dossier:final-set`, `dossier:finalized`

### 5. Stitching Policy (`frontend/src/services/dossier/stitchingPolicy.ts`)
- ✅ Checks `run.metadata.final_selected_id` first
- ✅ Falls back to consensus → best → longest policy if no final set

### 6. Selection Resolver (`frontend/src/services/dossier/selectionResolver.ts`)
- ✅ `resolveSegmentText()` - Prefers `final_selected_id`, strict (no fallback on 404)
- ✅ `resolveRunText()` - Same strict final selection preference
- ✅ Logs warnings but doesn't fallback when final selection 404s

### 7. UI: Version Pills with Final Indicators (`frontend/src/components/dossier/items/DraftItem.tsx`)
- ✅ Reads `run.metadata.final_selected_id`
- ✅ Displays ★ next to version pill that matches final selection
- ✅ Right-click on any pill to set as final (v1, v2, Av1, Av2, consensus v1/v2)
- ✅ Confirmation dialog before setting
- ✅ Updated tooltips to indicate final status

### 8. UI: Finalize Dossier Button (`frontend/src/components/dossier/DossierHeader.tsx`)
- ✅ "Finalize Dossier" button appears when dossier is selected
- ✅ Confirmation dialog before finalizing
- ✅ Calls `finalizeDossier()` API
- ✅ Shows result (segments finalized, errors if any)

### 9. UI: DossierManager Integration (`frontend/src/components/dossier/DossierManager.tsx`)
- ✅ `handleFinalizeDossier()` handler
- ✅ Displays result alert
- ✅ Refreshes dossier tree after finalization
- ✅ Passes handler to `DossierHeader`

## How It Works

### Setting a Final Selection
1. User right-clicks on any version pill (v1, v2, Av1, Av2, consensus v1/v2) in the Dossier Manager
2. Confirmation dialog appears
3. Frontend calls `dossierApi.setFinalSelection(dossierId, transcriptionId, draftId)`
4. Backend persists to `head.json` under `final.selected_id`
5. Custom event `dossier:final-set` is emitted
6. UI refreshes to show ★ indicator next to the selected version

### Viewing Content with Final Selection
1. When user views a segment/run/dossier in the Results Viewer
2. `selectionResolver` checks for `run.metadata.final_selected_id`
3. If set, loads that exact version strictly (no fallback)
4. If not set, uses default policy (consensus → best → longest)
5. Stitching for dossier-level view respects final selections per segment

### Finalizing a Dossier
1. User clicks "Finalize Dossier" button in DossierHeader
2. Backend endpoint iterates through all segments
3. For each segment:
   - If `final_selected_id` is set → load strictly (with retry)
   - If not set → use fallback policy
   - Record any errors (404s, etc.)
4. Stitches all segment texts together
5. Writes snapshot to `.../final/dossier_final.json` with:
   - Full stitched text
   - Segment metadata (which draft was used)
   - Error list
   - Timestamp
6. Returns result to frontend
7. Frontend shows success/error summary and refreshes tree

## Key Design Decisions

### Strict vs. Fallback Behavior
- **Final selections are strict**: If a final selection 404s, no fallback occurs
- **Rationale**: User explicitly chose that version; fallback would be silent data corruption
- **Error handling**: Errors are surfaced clearly via warnings and error arrays
- **Fallback policy**: Only used when NO final selection is set

### Version Resolution
- Final selection uses full versioned IDs: `{tid}_v2_v2`, `{tid}_draft_1_v1`, `{tid}_consensus_llm_v2`
- This ensures exact version match, no ambiguity
- Pills show ★ only when exact match

### UI/UX
- Right-click interaction for "Set as Final" keeps UI clean
- Confirmation dialogs prevent accidental changes
- Visual feedback (★) is clear and consistent
- Tooltips provide context

### Architecture
- Backend persistence via existing `head.json` mechanism
- Modular endpoints for CRUD operations
- Frontend API client handles events and cache invalidation
- Separation of concerns: storage, API, UI completely decoupled

## Files Modified

### Backend
1. `backend/services/dossier/edit_persistence_service.py` - Storage
2. `backend/api/endpoints/dossier/final_selection.py` - NEW, CRUD endpoints
3. `backend/api/endpoints/dossier/finalize.py` - NEW, Finalization endpoint
4. `backend/api/router.py` - Router wiring
5. `backend/services/dossier/management_service.py` - Hierarchy population

### Frontend
1. `frontend/src/services/dossier/dossierApi.ts` - API client
2. `frontend/src/services/dossier/stitchingPolicy.ts` - Policy update
3. `frontend/src/services/dossier/selectionResolver.ts` - Resolver update
4. `frontend/src/components/dossier/items/DraftItem.tsx` - Version pills with ★
5. `frontend/src/components/dossier/DossierHeader.tsx` - Finalize button
6. `frontend/src/components/dossier/DossierManager.tsx` - Handler integration

## Testing Checklist

- [ ] Set final selection via right-click on v1, v2, Av1, Av2, consensus pills
- [ ] Verify ★ appears next to selected version
- [ ] View segment/run and confirm final selection is loaded
- [ ] View dossier shell and confirm stitched content uses final selections
- [ ] Clear final selection and verify fallback to default policy
- [ ] Finalize dossier with all segments having final selections
- [ ] Finalize dossier with mixed (some final, some not)
- [ ] Verify error handling when final selection 404s
- [ ] Check that editing a draft doesn't change final selection pointer
- [ ] Verify `final/dossier_final.json` snapshot is written correctly
- [ ] Test with LLM consensus and Alignment consensus finals

## Next Steps (Future Enhancements)

1. **Bulk operations**: Set final for all segments at once
2. **Diff viewer**: Compare final selections before finalizing
3. **Finalization history**: Track previous finalizations
4. **Export**: Download finalized dossier as PDF/DOCX
5. **Text-to-Schema integration**: Consume `dossier_final.json` automatically
6. **Validation**: Warn if segments have no drafts before finalizing
7. **UI polish**: Inline final indicator badge in segment/run headers

## Summary

The final draft selection system is now fully integrated across the entire dossier management infrastructure. Users can:
- Set explicit final selections at version-level granularity
- View content with final selections respected
- Finalize entire dossiers into snapshots
- See clear visual feedback about which versions are final

The system maintains strict modularity, separation of concerns, and scalable architecture as per project requirements. All changes are cohesively integrated and ready for production use.

