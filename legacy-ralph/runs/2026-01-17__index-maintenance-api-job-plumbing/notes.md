# Notes — 2026-01-17__index-maintenance-api-job-plumbing

Baseline already exists (do not redo):
- Multi-pool maintenance primitives:
  - `safe_open_pool()` + `PoolOpenReport` + `PoolHealthReport` + `PoolMaintenanceReport` (`backend/retrieval/engine/pool_maintenance.py`)
  - Slice inventory/diagnose/execute for FINAL_SEGMENTS and EVERYTHING (head-only v0)
  - Stable `DiagnosticReasonCode`
- File-backed jobs pattern exists for image-to-text:
  - `backend/services/image_queue/job_store.py`

This run ships (no UI):
- FastAPI endpoints under `/api/index`:
  - GET diagnose (cheap, safe)
  - POST execute (enqueue + run bounded doc-slice work)
  - GET jobs/{job_id} (poll progress/results)
- Server-side runtime identity computation (policy id explicit; EVERYTHING reuses FINAL_SEGMENTS policy id in v0)
- Persisted IndexMaintenanceJobStore (file-backed, deterministic)
- Deterministic tests (prefer stubs; no HNSW-heavy tests required for API/job plumbing)


