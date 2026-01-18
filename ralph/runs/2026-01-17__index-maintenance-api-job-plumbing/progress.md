# Progress — 2026-01-17__index-maintenance-api-job-plumbing

(append entries per iteration)


- Iteration: unknown
- Story: S1 Add file-backed IndexMaintenanceJobStore (mirrors ImageToTextJobStore patterns) + models + deterministic tests
- Result: PASS
- Files changed: backend/services/index_maintenance/job_models.py, backend/services/index_maintenance/job_store.py, backend/services/index_maintenance/__init__.py, backend/services/index_maintenance/test_job_store.py
- Commands run: .\.venv\scripts\activate.ps1; python -m pytest -q backend/services/index_maintenance/test_job_store.py; python -m pytest -q backend/api/test_index_maintenance.py
- Notes:
  - Job store persists per-job JSON and index mapping under dossiers_processing_jobs_root("index_maintenance").

---

- Iteration: unknown
- Story: S2 Server-side RuntimeIndexIdentity helper for /api/index (compute fingerprint + policy id; deterministic UNAVAILABLE on failure) + tests
- Result: PASS
- Files changed: backend/api/endpoints/index_maintenance.py, backend/api/test_index_maintenance.py
- Commands run: .\.venv\scripts\activate.ps1; python -m pytest -q backend/services/index_maintenance/test_job_store.py; python -m pytest -q backend/api/test_index_maintenance.py
- Notes:
  - Identity computation stays server-side with stable UNAVAILABLE fallback.

---

- Iteration: unknown
- Story: S3 Add GET /api/index/diagnose endpoint mounted at /api/index (stable report + counts + caps) + deterministic tests
- Result: PASS
- Files changed: backend/api/endpoints/index_maintenance.py, backend/api/router.py, backend/api/test_index_maintenance.py
- Commands run: .\.venv\scripts\activate.ps1; python -m pytest -q backend/services/index_maintenance/test_job_store.py; python -m pytest -q backend/api/test_index_maintenance.py
- Notes:
  - Diagnose response always includes pool_open and derived counts; slices are capped.

---

- Iteration: unknown
- Story: S4 Add POST /api/index/execute: enqueue job, deterministic slice selection, background execution, persisted progress + tests
- Result: PASS
- Files changed: backend/api/endpoints/index_maintenance.py, backend/api/test_index_maintenance.py
- Commands run: .\.venv\scripts\activate.ps1; python -m pytest -q backend/services/index_maintenance/test_job_store.py; python -m pytest -q backend/api/test_index_maintenance.py
- Notes:
  - Selection ordering is deterministic and job records persist progress/results.

---

- Iteration: unknown
- Story: S5 Add GET /api/index/jobs/{job_id}: return persisted job record (with optional result capping) + tests
- Result: PASS
- Files changed: backend/api/endpoints/index_maintenance.py, backend/api/test_index_maintenance.py
- Commands run: .\.venv\scripts\activate.ps1; python -m pytest -q backend/services/index_maintenance/test_job_store.py; python -m pytest -q backend/api/test_index_maintenance.py
- Notes:
  - Job fetch returns deterministic 404 for missing IDs.

---

- Iteration: unknown
- Story: S6 Optional: typed frontend API wrapper (no UI) for diagnose/execute/getJob
- Result: PASS
- Files changed: frontend/src/lib/indexMaintenanceApi.ts
- Commands run: .\.venv\scripts\activate.ps1; python -m pytest -q backend/services/index_maintenance/test_job_store.py; python -m pytest -q backend/api/test_index_maintenance.py
- Notes:
  - Minimal wrapper added under frontend/src/lib without UI wiring.
