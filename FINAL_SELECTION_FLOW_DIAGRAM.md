# Final Selection System - Flow Diagram

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INTERACTIONS                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Right-click on version pill (v1, v2, Av1, Av2, consensus)     │
│  → Confirmation dialog                                          │
│  → Call dossierApi.setFinalSelection(dossierId, tid, draftId)  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND API CLIENT (dossierApi.ts)                           │
│  ├─ POST /api/dossier/final-selection/set                      │
│  └─ Emit event: dossier:final-set                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  BACKEND ENDPOINT (final_selection.py)                         │
│  └─ EditPersistenceService.set_final_selection()               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  STORAGE (head.json)                                            │
│  {                                                              │
│    "final": {                                                   │
│      "selected_id": "{tid}_draft_2_v1",                        │
│      "set_at": "2025-10-08T12:34:56"                           │
│    }                                                            │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  UI REFRESH                                                     │
│  ├─ Dossier Manager reloads hierarchy                          │
│  ├─ management_service.py populates run.metadata.final_selected│
│  └─ DraftItem.tsx shows ★ next to matching pill                │
└─────────────────────────────────────────────────────────────────┘
```

## Viewing Flow (Content Resolution)

```
┌─────────────────────────────────────────────────────────────────┐
│  USER CLICKS ON SEGMENT/RUN/DOSSIER IN DOSSIER MANAGER         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  SELECTION RESOLVER (selectionResolver.ts)                     │
│  ├─ Check run.metadata.final_selected_id                       │
│  ├─ If set → Load that exact draftId (strict, no fallback)     │
│  └─ If not set → Use policy (consensus → best → longest)       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  TEXT API (textApi.ts)                                          │
│  └─ GET /api/dossier-views/draft-text?...                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  BACKEND VIEW SERVICE (view_service.py)                        │
│  └─ _load_transcription_content_scoped(draftId)                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  RESULTS VIEWER                                                 │
│  └─ Display text content                                        │
└─────────────────────────────────────────────────────────────────┘
```

## Dossier Finalization Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  USER CLICKS "FINALIZE DOSSIER" BUTTON                          │
│  → Confirmation dialog                                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND (DossierHeader.tsx)                                  │
│  └─ dossierApi.finalizeDossier(dossierId)                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  BACKEND FINALIZE ENDPOINT (finalize.py)                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  For each segment:                                      │   │
│  │  1. Get latest run                                      │   │
│  │  2. Check final_selected_id                             │   │
│  │  3a. If set → Load strictly (with retry)                │   │
│  │  3b. If not set → Use fallback policy                   │   │
│  │  4. Collect text or record error                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  → Stitch all segment texts                                     │
│  → Write to .../final/dossier_final.json                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  SNAPSHOT FILE (dossier_final.json)                            │
│  {                                                              │
│    "dossier_id": "...",                                         │
│    "text": "... full stitched content ...",                    │
│    "segments": [                                                │
│      {                                                          │
│        "segment_id": "seg1",                                    │
│        "transcription_id": "tid1",                              │
│        "draft_id_used": "tid1_draft_2_v1",                     │
│        "text_length": 1234                                      │
│      }                                                          │
│    ],                                                           │
│    "errors": [],                                                │
│    "generated_at": "2025-10-08T12:45:00"                       │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  RESULT DISPLAY                                                 │
│  → Alert with segments count and errors                         │
│  → Dossier tree refresh                                         │
└─────────────────────────────────────────────────────────────────┘
```

## Stitching Policy Decision Tree

```
                    Segment N
                        │
                        ▼
        ┌───────────────────────────┐
        │ Has final_selected_id?     │
        └───────────────────────────┘
                 │            │
            Yes  │            │  No
                 ▼            ▼
        ┌─────────────┐  ┌──────────────────┐
        │ Load exactly│  │ Use policy:      │
        │ that draftId│  │ 1. Consensus     │
        │ (strict)    │  │ 2. Best flag     │
        └─────────────┘  │ 3. Longest       │
                 │       └──────────────────┘
                 │                │
                 ▼                ▼
        ┌─────────────┐  ┌──────────────────┐
        │ 404?        │  │ Found draft?     │
        └─────────────┘  └──────────────────┘
            │    │              │      │
          Yes   No             Yes    No
            │    │              │      │
            ▼    ▼              ▼      ▼
        ┌─────────────┐  ┌──────────────────┐
        │ Log warning │  │ Add to stitched  │
        │ Skip segment│  │ content          │
        │ Add error   │  └──────────────────┘
        └─────────────┘
```

## Version Pill UI State

```
Draft Item in Dossier Manager:
┌────────────────────────────────────────────┐
│ Draft 2                                    │
│ ┌────────────────────────────────────────┐ │
│ │ Versions:  ★v1  v2  Av1  Av2          │ │
│ └────────────────────────────────────────┘ │
│                                            │
│ Legend:                                    │
│ ★ = Final selection for this segment      │
│ Bold/colored = Currently viewed            │
│ Right-click any pill to set as final      │
└────────────────────────────────────────────┘
```

## State Management

```
Backend State (head.json per transcription):
{
  "raw_heads": {
    "tid_v1": "v1",
    "tid_v2": "v2"
  },
  "alignment_heads": {
    "tid_draft_1": "v1",
    "tid_draft_2": "v2"
  },
  "consensus": {
    "llm": {"head": "v2"},
    "alignment": {"head": "v1"}
  },
  "final": {
    "selected_id": "tid_draft_2_v1",  ← NEW
    "set_at": "2025-10-08T12:34:56"   ← NEW
  }
}

Frontend State (run.metadata):
{
  ...,
  "metadata": {
    "final_selected_id": "tid_draft_2_v1"  ← Populated by backend
  }
}
```

## Error Handling

```
Scenario: Final selection 404s during finalization
┌────────────────────────────────────────────┐
│ Backend detects 404 after retries          │
└────────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────────┐
│ Add to errors array:                       │
│ {                                          │
│   "segment_id": "seg1",                    │
│   "transcription_id": "tid1",              │
│   "draft_id": "tid1_draft_2_v1",          │
│   "reason": "Draft not found (404)"       │
│ }                                          │
└────────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────────┐
│ Continue with remaining segments           │
└────────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────────┐
│ Return result with errors array            │
└────────────────────────────────────────────┘
                  │
                  ▼
┌────────────────────────────────────────────┐
│ Frontend displays:                         │
│ "✅ Finalized 3 segments                   │
│  ⚠️ 1 error"                               │
└────────────────────────────────────────────┘
```

## Integration Points

### 1. Text-to-Schema Pipeline
```
Text-to-Schema needs dossier text →
Read .../final/dossier_final.json →
Use "text" field as input
```

### 2. Editing Workflow
```
User edits a draft →
Edit persisted to v2 file →
Final selection pointer unchanged →
User must explicitly update final if desired
```

### 3. Alignment Reruns
```
User reruns alignment →
New Av1 created →
Final selection pointer unchanged →
User must explicitly update final if desired
```

This ensures explicit, intentional control over what is considered "final."

