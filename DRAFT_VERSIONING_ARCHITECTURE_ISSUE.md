# Critical Architectural Issue: Draft-Specific Versioning

## Problem Statement

The current v1/v2 versioning system has a **naming conflict** between:
1. **Redundancy versions**: `draft_newdeedleft_v1.json`, `draft_newdeedleft_v2.json`, `draft_newdeedleft_v3.json` (different drafts from redundancy)
2. **Edit versions**: `v1` (original), `v2` (edited)

### Current Behavior (BROKEN for redundancy > 1)

When user has 3 redundancy drafts and edits Draft 2:

**File Structure:**
```
draft_newdeedleft/
  raw/
    draft_newdeedleft_v1.json  ← Draft 1 (redundancy)
    draft_newdeedleft_v2.json  ← Draft 2 (redundancy) 
    draft_newdeedleft_v3.json  ← Draft 3 (redundancy)
    draft_newdeedleft.json     ← HEAD pointer (transcription-level, not draft-specific)
```

**What happens when editing Draft 2:**
- User edits `draft_newdeedleft_v2.json`
- System creates a single `v2` edit version (where does it go?)
- HEAD pointer is transcription-level, not draft-specific
- **Result**: Resetting reverts the wrong draft or doesn't work at all

### Required Architecture (CORRECT)

Each draft needs its own versioning:

```
draft_newdeedleft/
  raw/
    # Draft 1 versions
    draft_1_v1.json           ← Draft 1 original
    draft_1_v2.json           ← Draft 1 edited (if user edited it)
    draft_1.json              ← Draft 1 HEAD pointer
    
    # Draft 2 versions  
    draft_2_v1.json           ← Draft 2 original
    draft_2_v2.json           ← Draft 2 edited (if user edited it)
    draft_2.json              ← Draft 2 HEAD pointer
    
    # Draft 3 versions
    draft_3_v1.json           ← Draft 3 original
    draft_3.json              ← Draft 3 HEAD pointer (no edits yet, points to v1)
    
  # Per-draft HEAD metadata
  draft_1_head.json           ← { "raw": { "head": "v2" } }
  draft_2_head.json           ← { "raw": { "head": "v2" } }
  draft_3_head.json           ← { "raw": { "head": "v1" } }
```

---

## Impact Analysis

### Files Requiring Refactor

#### Backend

1. **`backend/services/dossier/edit_persistence_service.py`**
   - Change from transcription-level to draft-level versioning
   - Update file paths: `{tid}_v1.json` → `draft_{index}_v1.json`
   - Update HEAD management: per-draft instead of per-transcription
   - Methods to update:
     - `_run_dir()` → `_draft_dir()`
     - `save_raw_v2()` → accept draft_index parameter
     - `revert_to_v1()` → accept draft_index parameter
     - `set_raw_head()` → accept draft_index parameter

2. **`backend/services/dossier/view_service.py`**
   - Update `_load_transcription_content_scoped()` to:
     - Parse draft index from draft_id
     - Load from `draft_{index}_v1.json` or `draft_{index}_v2.json`
     - Check per-draft HEAD pointer

3. **`backend/services/dossier/progressive_draft_saver.py`**
   - Update `save_draft_result()` to use new naming scheme
   - Change from `{tid}_v{index+1}.json` to `draft_{index+1}_v1.json`

4. **`backend/services/dossier/management_service.py`**
   - Update draft enumeration logic
   - Update longest draft detection

#### Frontend

5. **`frontend/src/services/textApi.ts`**
   - Update getDraftText/getDraftJson to request correct draft-specific paths

6. **`frontend/src/services/imageProcessingApi.ts`**
   - Update `saveDossierEditAPI` to pass draft index
   - Update `revertToV1API` to pass draft index

7. **`frontend/src/hooks/useEditableDraft.ts`**
   - Extract draft index from selectedDraft
   - Pass draft index to save/revert APIs

---

## Recommended Implementation Plan

### Phase 1: Backend Schema Migration

1. Create migration script to rename existing files:
   ```python
   # For each transcription with redundancy > 1:
   #   {tid}_v1.json → draft_1_v1.json
   #   {tid}_v2.json → draft_2_v1.json
   #   {tid}_v3.json → draft_3_v1.json
   #   Create draft_1_head.json, draft_2_head.json, etc.
   ```

2. Update `EditPersistenceService` to use draft-specific paths

3. Update `ViewService` to read from draft-specific paths

### Phase 2: API Updates

1. Update `/api/dossier/edits/save` to accept `draft_index`
2. Update `/api/dossier/versions/revert-to-v1` to accept `draft_index`
3. Update `/api/dossier-management/drafts/{draft_id}` to parse draft index

### Phase 3: Frontend Updates

1. Extract draft index from `selectedDraft` in hooks
2. Pass draft index to all edit/revert API calls
3. Update textApi to construct correct draft-specific URLs

### Phase 4: Testing

1. Test editing Draft 1 with redundancy=3
2. Test editing Draft 2 with redundancy=3
3. Test editing Draft 3 with redundancy=3
4. Test reverting each independently
5. Test alignment with mixed edited/unedited drafts

---

## Temporary Workaround (Current Release)

Until the full refactor is complete:

### Option A: Disable Editing for Redundancy > 1

Add guard in `useEditableDraft.ts`:
```typescript
// At top of hook
const redundancyCount = selectedResult?.result?.metadata?.redundancy_analysis?.count || 1;
if (redundancyCount > 1) {
  console.warn('⚠️ Editing not supported for redundancy > 1 due to architectural limitation');
  // Return disabled state
  return {
    editableDraftState: initialState,
    applyEdit: () => {},
    resetToOriginal: async () => {},
    // ... all no-ops
  };
}
```

### Option B: Document Limitation Clearly

Add warning banner in UI when redundancy > 1:
```tsx
{redundancyCount > 1 && (
  <div className="edit-limitation-warning">
    ⚠️ Note: Editing is currently only supported for single-draft transcriptions.
    Multi-draft editing coming soon.
  </div>
)}
```

---

## Estimated Effort

- **Backend refactor**: 8-12 hours
  - Schema migration script: 2 hours
  - EditPersistenceService updates: 3 hours
  - ViewService updates: 2 hours  
  - ProgressiveDraftSaver updates: 2 hours
  - Testing: 2 hours

- **Frontend refactor**: 4-6 hours
  - API updates: 2 hours
  - Hook updates: 2 hours
  - Testing: 2 hours

- **Migration & deployment**: 2-4 hours
  - Data migration: 2 hours
  - Rollback plan: 1 hour
  - Production deployment: 1 hour

**Total**: 14-22 hours for complete implementation

---

## Decision Required

Choose one approach:

1. **Full Refactor** (14-22 hours) - Proper architecture, supports all use cases
2. **Temporary Disable** (30 minutes) - Quick fix, limits functionality
3. **Document Only** (10 minutes) - No code changes, user awareness

**Recommendation**: Option 2 (Temporary Disable) for immediate release, schedule Option 1 (Full Refactor) for next sprint.
