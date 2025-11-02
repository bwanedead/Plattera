# Draft Editing & Persistence Architecture

## Overview

This document describes the v1/v2 versioning architecture for draft editing, alignment coherence, and the clean separation of concerns implemented across the system.

---

## Architecture Principles

### ✅ Separation of Concerns
- **API Layer** (`frontend/src/services/imageProcessingApi.ts`): Pure API calls, no business logic
- **Business Logic** (`frontend/src/hooks/*`): State management and workflows
- **UI Layer** (`frontend/src/components/*`): Presentation and user interaction
- **Backend Services** (`backend/services/dossier/*`): Persistent storage and version management

### ✅ Clean Module Boundaries
Each module has a single, well-defined responsibility:
- `imageProcessingApi.ts`: HTTP communication with backend
- `useEditableDraft.ts`: Draft editing state and history management
- `useAlignmentState.ts`: Alignment workflow orchestration
- `edit_persistence_service.py`: Version file management (v1, v2, HEAD)
- `view_service.py`: Draft content retrieval with HEAD awareness

---

## Phase 1: Reset to Original Implementation

### Problem Identified
The "Reset to Original" button only cleared frontend state but never called the backend to revert the HEAD pointer from v2 back to v1. This caused edits to persist incorrectly after navigation.

### Solution Implemented

#### **File: `frontend/src/services/imageProcessingApi.ts`**
**Added: `revertToV1API` function**
```typescript
export const revertToV1API = async (params: {
  dossierId: string;
  transcriptionId: string;
  purge?: boolean;
}): Promise<{ success: boolean }>
```
- **Responsibility**: Single-purpose API call to backend version endpoint
- **Location**: Properly placed in API service layer
- **Design**: Clean parameters, typed return, proper error handling

#### **File: `frontend/src/hooks/useEditableDraft.ts`**
**Modified: `resetToOriginal` function**
- **Added**: User confirmation dialog for unsaved changes
- **Added**: Backend API call to revert HEAD pointer
- **Added**: Dossier refresh trigger after successful revert
- **Added**: Comprehensive error handling with user feedback
- **Pattern**: Optimistic update (frontend first) with backend synchronization

#### **File: `frontend/src/components/image-processing/ResultsViewer.tsx`**
**Modified: Reset button handlers**
- **Changed**: Synchronous onClick to async onClick
- **Added**: Proper await for resetToOriginal calls
- **Improved**: Tooltip clarity about v2 deletion

---

## Phase 2: Alignment Using Current HEAD

### Problem Identified
Alignment was using stale cached text from `redundancy_analysis.individual_results[].text` which was captured during initial transcription. Edits saved to v2 were not reflected in alignment results.

### Solution Implemented

#### **File: `frontend/src/hooks/useAlignmentState.ts`**
**Modified: `handleAlign` function**

**Key Changes**:
1. **Added Dynamic Fetch**: Before alignment, fetch current versions from backend
2. **HEAD-Aware Loading**: For redundancy=1 (common case), fetch base transcription ID to get HEAD pointer
3. **Fallback Handling**: Graceful degradation to cached text if fetch fails
4. **Proper Logging**: Comprehensive console output for debugging

**Algorithm**:
```typescript
// For redundancy=1 (single draft editing supported)
if (rawDraftResults.length === 1) {
  // Fetch HEAD pointer - respects v1/v2 edits
  text = await textApi.getDraftText(transcriptionId, transcriptionId, dossierId);
} else {
  // For redundancy>1, fetch specific versioned drafts
  // Note: Edit versioning architecture limitation documented
  text = await textApi.getDraftText(transcriptionId, `${transcriptionId}_v${index + 1}`, dossierId);
}
```

---

## Backend Integration

### Version Management Flow

**File Structure**:
```
backend/dossiers_data/views/transcriptions/{dossier_id}/{transcription_id}/
├── raw/
│   ├── {transcription_id}_v1.json    # Original version (immutable)
│   ├── {transcription_id}_v2.json    # Edited version (if exists)
│   └── {transcription_id}.json       # HEAD pointer copy (updated by set_raw_head)
├── head.json                         # HEAD pointer metadata
└── consensus/
    ├── llm_{transcription_id}.json   # LLM consensus (if generated)
    └── alignment_{transcription_id}.json  # Alignment consensus (if generated)
```

### Edit Persistence Service (`backend/services/dossier/edit_persistence_service.py`)

**Key Methods**:
- `save_raw_v2()`: Creates/overwrites v2 with edited content and sets HEAD to v2
- `revert_to_v1()`: Sets HEAD back to v1 and optionally purges v2 files
- `set_raw_head()`: Updates HEAD pointer and refreshes pointer copy
- `_update_pointer_copy()`: Creates `{transcription_id}.json` as copy of current HEAD

### View Service (`backend/services/dossier/view_service.py`)

**Method**: `_load_transcription_content_scoped()`

**HEAD-Aware Loading Logic**:
1. When requesting `{transcription_id}.json` (no version suffix):
   - Returns HEAD pointer copy
   - Automatically respects current HEAD (v1 or v2)
2. When requesting `{transcription_id}_v1.json` or `{transcription_id}_v2.json`:
   - Returns specific version (bypasses HEAD)
   - Falls back to HEAD pointer if specific version not found

---

## Current Limitations & Future Enhancements

### Documented Limitation: Edit Versioning with Redundancy > 1

**Issue**: The current v1/v2 naming scheme has a conflict with redundancy naming:
- **Redundancy**: `{tid}_v1.json`, `{tid}_v2.json`, `{tid}_v3.json` (multiple drafts)
- **Edit Versions**: `{tid}_v1.json` (original), `{tid}_v2.json` (edited)

**Current Support**:
- ✅ Redundancy = 1: Full edit versioning supported
- ⚠️ Redundancy > 1: Alignment uses cached text (edit versioning not supported)

**Future Enhancement** (requires architectural refactor):
```
Proposed structure:
├── raw/
│   ├── {tid}_draft1_v1.json       # Draft 1 original
│   ├── {tid}_draft1_v2.json       # Draft 1 edited
│   ├── {tid}_draft1.json          # Draft 1 HEAD pointer
│   ├── {tid}_draft2_v1.json       # Draft 2 original
│   ├── {tid}_draft2_v2.json       # Draft 2 edited
│   └── {tid}_draft2.json          # Draft 2 HEAD pointer
```

---

## Testing Checklist

### Phase 1: Reset to Original
- [ ] Make edit and save (creates v2)
- [ ] Navigate away and back
- [ ] Click "Reset to Original"
- [ ] Verify confirmation dialog appears
- [ ] Confirm reset
- [ ] Verify edits removed in UI
- [ ] Navigate away and back
- [ ] Verify original v1 still showing (v2 deleted)

### Phase 2: Alignment with Edits
- [ ] Make edit to draft and save
- [ ] Run alignment
- [ ] Verify aligned results reflect edits
- [ ] Verify consensus draft includes edited content
- [ ] Navigate away and back
- [ ] Re-run alignment
- [ ] Verify consistency maintained

---

## Error Handling

### User-Facing Errors
All operations include user-friendly error messages:
- Confirmation dialogs before destructive operations
- Alert dialogs with specific error details
- Fallback to cached data when backend unavailable
- Console logging for debugging

### Graceful Degradation
- API failures fall back to cached text
- Missing v2 falls back to v1
- Frontend state maintained even if backend sync fails

---

## Summary of Changes

### Files Modified

1. **`frontend/src/services/imageProcessingApi.ts`**
   - Added `revertToV1API` function
   - Clean API layer separation

2. **`frontend/src/hooks/useEditableDraft.ts`**
   - Updated `resetToOriginal` to call backend
   - **Fixed:** Confirmation dialog now detects saved edits from previous sessions (not just current unsaved changes)
   - **Fixed:** Changed from `dossiers:refresh` to targeted `draft:reverted` event to prevent dossier manager scroll jump
   - **Added:** Comprehensive logging with emoji markers for easy tracking
   - **Added:** State inspection logging to debug edit detection
   - Added error handling

3. **`frontend/src/hooks/useAlignmentState.ts`**
   - Added dynamic draft fetching
   - Implemented HEAD-aware loading for redundancy=1
   - Added comprehensive logging

4. **`frontend/src/components/image-processing/ResultsViewer.tsx`**
   - Updated reset buttons to handle async operations
   - **Added:** Event listener for `draft:reverted` to reload current draft without disturbing dossier manager
   - **Fixed:** Automatic UI refresh after reset - no need to manually re-click draft
   - **Fixed:** Dossier manager no longer scrolls/jumps when reset is triggered
   - Improved tooltips

5. **`backend/api/router.py`**
   - Registered version management endpoints
   - Clean router organization

### No Files Created
All changes made to existing files, respecting the existing architecture and avoiding code duplication or "dumping ground" patterns.

---

## Bug Fixes Applied (User Testing Round 1)

### Issue 1: No Confirmation Dialog for Saved Edits
**Problem:** When user made edits in previous session and saved them (creating v2), the confirmation dialog didn't appear on reset because it only checked `hasUnsavedChanges` (current session).

**Fix:** Added `hasSavedEdits` check that compares original vs edited content:
```typescript
const hasSavedEdits = editableDraftState.originalDraft.content !== editableDraftState.editedDraft.content;
const hasAnyEdits = hasUnsavedChanges || hasSavedEdits;
```

### Issue 2: Dossier Manager Scroll Jump
**Problem:** `dossiers:refresh` event caused entire dossier manager to reload and lose scroll position.

**Fix:** Replaced with targeted `draft:reverted` custom event that only reloads the currently displayed draft:
```typescript
const event = new CustomEvent('draft:reverted', {
  detail: { dossierId, transcriptionId }
});
document.dispatchEvent(event);
```

### Issue 3: UI Not Updating Immediately After Reset  
**Problem:** User had to manually re-click draft to see v1 content after reset.

**Fix:** Added event listener in `ResultsViewer` that automatically re-fetches and updates the current draft when `draft:reverted` fires.

### Issue 4: Insufficient Logging
**Problem:** Difficult to debug what was happening during reset operation.

**Fix:** Added comprehensive logging with emoji markers:
- 🔴 Button click
- 🔍 State inspection
- ⚠️ Confirmation dialogs
- ✅/❌ Success/failure markers
- 🔄 Process steps
- 📋 Context info
- 🏁 Completion markers

---

## Architectural Benefits

### ✅ Modularity
Each component has a single responsibility and clear boundaries.

### ✅ Scalability
New features can be added without modifying unrelated code.

### ✅ Maintainability
Clear separation makes debugging and updates straightforward.

### ✅ Testability
Isolated components can be tested independently.

### ✅ Consistency
Follows established patterns throughout the codebase.

---

## Conclusion

This implementation solves both identified issues (reset button persistence and alignment coherence) while maintaining clean architecture, proper separation of concerns, and scalability. The solution is production-ready for redundancy=1 scenarios (the common case) and documents the architectural limitation for redundancy>1 scenarios, paving the way for future enhancement.

