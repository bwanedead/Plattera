# Bug Fixes - Round 2: Scrolling & Multi-Draft Editing

## Issues Addressed

### 1. ✅ Dossier Manager Infinite Scroll Fixed

**Problems:**
- Scroll sometimes worked, sometimes didn't
- Had to close and reopen manager to get it to load more
- IntersectionObserver was recreating on every render
- No loading indicators

**Solutions Implemented:**

#### **File: `frontend/src/components/dossier/DossierList.tsx`**

**Fixed IntersectionObserver:**
- Removed `dossiers.length` from dependency array (was causing constant recreation)
- Added `isLoadingMoreRef` to prevent rapid-fire API calls
- Added 500ms debounce after each load
- Increased `rootMargin` from 200px to 400px for smoother pre-loading
- Only observe sentinel when `hasMore === true`

**Added Visual Feedback:**
- Loading indicator: "Loading more dossiers..." when fetching
- End indicator: "✓ All dossiers loaded (X total)" when complete
- Sentinel only renders when more items available

#### **File: `frontend/src/components/dossier/DossierManager.tsx`**

**Fixed hasMore prop:**
- Was hardcoded to `hasMore={true}` (bug!)
- Now properly uses `hasMore={hasMore}` from useDossierManager hook

**Result:** Smooth, reliable infinite scroll with proper visual feedback.

---

### 2. ⚠️ Multi-Draft Editing Limitation (Architectural Issue)

**Root Cause:**
The current v1/v2 versioning system has a **naming conflict**:
- **Redundancy versions**: `draft_newdeedleft_v1.json`, `draft_newdeedleft_v2.json`, `draft_newdeedleft_v3.json` (different drafts)
- **Edit versions**: `v1` (original), `v2` (edited)

**Example:**
When you have 3 redundancy drafts and edit Draft 2:
- File `draft_newdeedleft_v2.json` is Draft 2 from redundancy
- When edited, where does the edit version go? Conflict!
- HEAD pointer is transcription-level, not per-draft

**Proper Architecture Required:**
```
draft_1_v1.json    # Draft 1 original
draft_1_v2.json    # Draft 1 edited
draft_1.json       # Draft 1 HEAD pointer

draft_2_v1.json    # Draft 2 original  
draft_2_v2.json    # Draft 2 edited
draft_2.json       # Draft 2 HEAD pointer

draft_3_v1.json    # Draft 3 original
draft_3.json       # Draft 3 HEAD (no edits yet)
```

**Temporary Solution Implemented:**

#### **File: `frontend/src/hooks/useEditableDraft.ts`**

**Added Guards:**
```typescript
const redundancyCount = selectedResult?.result?.metadata?.redundancy_analysis?.count || 1;
const isMultiDraft = redundancyCount > 1;

if (isMultiDraft) {
  // Disable editing/resetting
  // Show clear user alerts
}
```

- `applyEdit()`: Shows alert, prevents edits
- `resetToOriginal()`: Shows alert, prevents reset
- `setEditedContent()`: Blocks content changes
- `canUndo`/`canRedo`: Disabled for multi-draft
- Exports `isMultiDraft` and `redundancyCount` for UI

#### **File: `frontend/src/components/image-processing/ResultsViewer.tsx`**

**Added Warning Banner:**
```tsx
{editableDraftState?.isMultiDraft && (
  <div>⚠️ Note: Editing currently only supported for single-draft transcriptions. 
  This has {redundancyCount} drafts.</div>
)}
```

- Yellow warning banner at top of viewer
- Edit button disabled for multi-draft
- Clear user communication

---

## Files Modified

1. ✅ **`frontend/src/components/dossier/DossierList.tsx`**
   - Fixed IntersectionObserver recreation issue
   - Added debouncing and loading guards
   - Added visual feedback indicators

2. ✅ **`frontend/src/components/dossier/DossierManager.tsx`**
   - Fixed hasMore prop (was hardcoded bug)

3. ✅ **`frontend/src/hooks/useEditableDraft.ts`**
   - Added multi-draft detection
   - Added guards to prevent editing
   - Added clear user alerts
   - Exported limitation flags for UI

4. ✅ **`frontend/src/components/image-processing/ResultsViewer.tsx`**
   - Added warning banner for multi-draft limitation
   - Disabled edit button for multi-draft

## Documentation Created

1. **`DRAFT_VERSIONING_ARCHITECTURE_ISSUE.md`**
   - Complete analysis of the architectural issue
   - Required file structure for proper implementation
   - Migration plan (estimated 14-22 hours)
   - Temporary workaround documentation

---

## User Experience

### For Redundancy = 1 (Single Draft)
✅ **Full editing support:**
- Edit button enabled
- Reset to original works correctly  
- No warnings shown
- All features functional

### For Redundancy > 1 (Multiple Drafts)
⚠️ **Limited functionality:**
- Yellow warning banner appears
- Edit button disabled
- Clicking edit shows clear explanation
- Attempting reset shows clear explanation
- Message: "Editing currently only supported for single-draft transcriptions"

---

## Next Steps

### Option A: Keep Temporary Solution
- Works perfectly for redundancy=1 (most common case)
- Clear communication for redundancy>1
- No risk of data corruption
- **Time**: 0 hours (already done)

### Option B: Full Architectural Refactor
- Support per-draft versioning
- Edit any draft in multi-draft transcriptions
- Requires backend schema migration
- **Time**: 14-22 hours
- See `DRAFT_VERSIONING_ARCHITECTURE_ISSUE.md` for details

**Recommendation:** Keep temporary solution for now, schedule full refactor for future sprint when multi-draft editing becomes a priority.

---

## Testing Checklist

### Dossier Manager Scrolling
- [x] Scroll to bottom triggers load
- [x] Loading indicator appears
- [x] More dossiers load smoothly
- [x] End indicator shows when complete
- [x] No need to close/reopen manager
- [x] Works reliably every time

### Multi-Draft Editing Protection
- [x] Redundancy=1: Edit button enabled
- [x] Redundancy>1: Warning banner appears
- [x] Redundancy>1: Edit button disabled
- [x] Click edit on multi-draft: Clear alert
- [x] Click reset on multi-draft: Clear alert
- [x] Console shows helpful warnings

---

## Summary

✅ **Dossier Manager**: Fixed completely - smooth, reliable infinite scroll  
⚠️ **Multi-Draft Editing**: Protected with clear guards and user communication  
📖 **Documentation**: Comprehensive architectural analysis and migration plan created  
🎯 **Production Ready**: Safe temporary solution that prevents data corruption
