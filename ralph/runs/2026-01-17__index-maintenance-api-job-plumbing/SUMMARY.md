# SUMMARY.md — Ralph Run: 2026-01-17__index-maintenance-api-job-plumbing

This file captures a running summary of what was built, one entry per completed story. It provides a human-readable debrief for reviewers.

---

## Final Summary (append when run complete)

### Overview
<1-2 paragraph summary of what the entire run accomplished>

### Total changes
- Files created: <count>
- Files modified: <count>
- Tests added: <count>

### Architecture decisions
- <bullet: key technical choices made>

### Known limitations
- <bullet: deferred work>


---

## Story S1: Add file-backed IndexMaintenanceJobStore (mirrors ImageToTextJobStore patterns) + models + deterministic tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Added job models and a file-backed IndexMaintenanceJobStore under processing_jobs/index_maintenance
- Added deterministic roundtrip test for create/update/reload

### Files changed
- `backend/services/index_maintenance/job_models.py` - add job/request/progress/result models
- `backend/services/index_maintenance/job_store.py` - add file-backed store
- `backend/services/index_maintenance/__init__.py` - export job store/model symbols
- `backend/services/index_maintenance/test_job_store.py` - add job store roundtrip test

### Key decisions
- Mirrored image-to-text job store patterns with per-job JSON + index map

### Tests added
- 1 new tests in `backend/services/index_maintenance/test_job_store.py`

### Notes
- Store root uses dossiers_processing_jobs_root("index_maintenance") by default

---

## Story S2: Server-side RuntimeIndexIdentity helper for /api/index (compute fingerprint + policy id; deterministic UNAVAILABLE on failure) + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Added runtime identity resolution for index maintenance endpoints (server-side only)
- Deterministic UNAVAILABLE fallback when identity computation fails

### Files changed
- `backend/api/endpoints/index_maintenance.py` - add identity helper and stable fallback handling
- `backend/api/test_index_maintenance.py` - add identity failure test coverage

### Key decisions
- Identity computation is centralized and never exposed to the client

### Tests added
- 1 new tests in `backend/api/test_index_maintenance.py`

### Notes
- Chunking policy id is shared between FINAL_SEGMENTS and EVERYTHING (v0)

---

## Story S3: Add GET /api/index/diagnose endpoint mounted at /api/index (stable report + counts + caps) + deterministic tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Added GET /api/index/diagnose with stable report shape, counts, and slice caps
- Mounted index maintenance router under /api/index

### Files changed
- `backend/api/endpoints/index_maintenance.py` - add diagnose endpoint and report serialization
- `backend/api/router.py` - mount index maintenance router
- `backend/api/test_index_maintenance.py` - add diagnose slice limiting test

### Key decisions
- Counts are derived from the full diagnosis list even when slices are capped

### Tests added
- 1 new tests in `backend/api/test_index_maintenance.py`

### Notes
- pool_open is always present; pool_health/slices only when available

---

## Story S4: Add POST /api/index/execute: enqueue job, deterministic slice selection, background execution, persisted progress + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Added POST /api/index/execute with deterministic slice selection + background execution
- Persisted job progress/results via IndexMaintenanceJobStore

### Files changed
- `backend/api/endpoints/index_maintenance.py` - add execute endpoint and job runner
- `backend/api/test_index_maintenance.py` - add selection ordering + job creation tests

### Key decisions
- Slice selection is sorted by (dossier_id, entry_id) and hard-limited server-side

### Tests added
- 2 new tests in `backend/api/test_index_maintenance.py`

### Notes
- UNAVAILABLE pool/identity failures are recorded as failed jobs

---

## Story S5: Add GET /api/index/jobs/{job_id}: return persisted job record (with optional result capping) + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Added GET /api/index/jobs/{job_id} with optional result capping
- Deterministic 404 for missing job IDs

### Files changed
- `backend/api/endpoints/index_maintenance.py` - add job fetch endpoint with caps
- `backend/api/test_index_maintenance.py` - add 404 job fetch test

### Key decisions
- Job fetch never mutates stored results; caps are applied on response only

### Tests added
- 1 new tests in `backend/api/test_index_maintenance.py`

### Notes
- Response includes results_returned and results_total for pagination hints

---

## Story S6: Optional: typed frontend API wrapper (no UI) for diagnose/execute/getJob
**Status:** PASS
**Iteration:** unknown

### What was built
- Added typed frontend API helpers for diagnose, execute, and job fetch

### Files changed
- `frontend/src/lib/indexMaintenanceApi.ts` - add minimal index maintenance client

### Key decisions
- Reused existing API base resolution pattern for consistency

### Tests added
- 0 new tests in `frontend/src/lib/indexMaintenanceApi.ts`

### Notes
- No UI wiring added
