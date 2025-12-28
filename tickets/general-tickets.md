## Plattera Desktop – General Tickets

### Ticket: PLSS download modals can stack

- **Status**: Open  
- **Area**: PLSS download UI (modal vs. overlay)  
- **Files involved (current behavior)**:  
  - `frontend/src/components/visualization/backgrounds/CleanMapBackground.tsx`  
  - `frontend/src/components/visualization/backgrounds/MapBackground.tsx`  
  - `frontend/src/components/plss/PLSSDownloadOverlay.tsx`  
  - `frontend/src/hooks/usePlssData.ts`

#### Problem

During testing on **v0.9.4–0.9.5**, starting a PLSS download can occasionally produce **two stacked modals**:

1. A **map-scoped `PLSSDownloadModal`** (prompt or error) owned by `CleanMapBackground` / `MapBackground`.  
2. The **global PLSS progress overlay** (`PLSSDownloadOverlay`), which also renders a `PLSSDownloadModal`.

When the user clicks “Download PLSS data…”, the map-level prompt modal does not always unmount before the overlay opens, so the overlay can appear on top of (or at the same time as) the underlying prompt/error modal. This breaks the “single-owner” rule for progress UI and feels messy / confusing.

The underlying causes are:

- There are **two distinct owners** of `PLSSDownloadModal` (map prompt vs. global overlay).  
- `usePlssData.downloadData()` currently **dispatches `plss:open-modal` immediately**, which lets the overlay try to open before the map prompt has definitely gone away.  
- React state / monitor activation are asynchronous, so there is a race window where both modals can be mounted.

#### Proposed solution (to implement in a future release)

**Goal:** Ensure there is **only ever one PLSS download modal at a time**, with a clear ownership rule:

- Map components own **prompt + error** states.  
- The global overlay owns **active progress** (downloading / parquet / indexing).

**Concrete changes (recommended path):**

1. **Keep** the per-download overlay reset in `usePlssData.downloadData()`:  
   - `localStorage.removeItem(\`plss:overlayDismissed:${state.state}\`)`  
   - This ensures each new download can show the overlay again even if the user dismissed it previously.

2. **Remove or relocate** the eager overlay-open event from the hook:
   - Today we do:
     - `document.dispatchEvent(new Event('plss:open-modal'))` inside `downloadData()`.
   - This is UI policy living in a state hook and is the primary source of the race.  
   - **Fix:** either remove this dispatch entirely and rely on the overlay’s **auto-open** behavior when the monitor reports `active && isProgressPhase`, or move this responsibility into the **map components** so the prompt can unmount first.

3. **Guarantee prompt unmount before overlay open** (if we keep the event):
   - In `CleanMapBackground.tsx` / `MapBackground.tsx`, change the “Download” handler to:
     - First dismiss/clear the prompt modal state.
     - Then call `downloadData()` (which will reset overlay dismissal and, if we still want it, dispatch `plss:open-modal`).
   - This guarantees only one owner is active at any time: prompt modal → unmount → overlay modal.

4. **Add a small invariant comment near these code paths** documenting the single-owner rule:
   - “PLSS download prompt + errors are map-owned; active progress is overlay-owned. Never render both modals simultaneously.”

Once implemented, this ticket can be regression-tested by:

- Fresh install, no existing PLSS data.  
- Start a PLSS download from the map.  
- Verify that:
  - You see **one** prompt modal → on confirm, it unmounts.  
  - Then you see **one** overlay modal for progress.  
  - No stacked or underlying modals are present at any point.

