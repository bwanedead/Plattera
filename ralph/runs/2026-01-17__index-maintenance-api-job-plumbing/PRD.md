# PRD: Index Maintenance API + Persisted Job Plumbing (No UI)

## Context
We already have multi-pool index maintenance primitives and doc-slice maintenance flows:
- `safe_open_pool()` + `PoolOpenReport` + `PoolHealthReport` + `PoolMaintenanceReport` (`backend/retrieval/engine/pool_maintenance.py`)
- Slice inventory/diagnose/execute for `FINAL_SEGMENTS` and `EVERYTHING` (head-only v0)
- Stable `DiagnosticReasonCode`
- File-backed jobs pattern exists for image-to-text (`backend/services/image_queue/job_store.py`)

What’s missing is a repo-native API contract + persisted job plumbing so the app can:
- diagnose cheaply and safely (no mutations)
- execute bounded doc-slice maintenance work (so vectors actually populate)
- poll job progress/results (future UI can render without backend changes)

## Goal
Ship backend endpoints under `/api/index` plus a file-backed `IndexMaintenanceJobStore` and background execution plumbing for bounded doc-slice maintenance jobs.

## Non-goals
- No UI components (no panels/buttons/layout).
- No auto-light scheduling / background policy.
- No SSE streaming.
- No “rebuild entire pool” endpoint.
- No non-head draft hydration expansion.
- No dependency additions (keep lightweight; reuse repo patterns).

## Scope
Backend:
- `backend/api/endpoints/index_maintenance.py` (new)
- `backend/api/router.py` (mount prefix `/api/index`)
- `backend/retrieval/engine/pool_maintenance.py` (reuse)
- New job store module (mirror image-to-text job store patterns)
- Background execution using FastAPI background tasks (polling via job endpoint)

Optional:
- Typed frontend API wrapper only (`frontend/src/lib/indexMaintenanceApi.ts`) — no UI.

## Runtime Identity (server-side only)
Endpoints must compute `RuntimeIndexIdentity` internally (frontend never supplies identity):
- Resolve embedding asset info via `resolve_embedding_model(AssetsService())`
- Compute fingerprint via `compute_model_fingerprint(model_info)`
- Chunking policy id by pool:
  - FINAL_SEGMENTS → `FINAL_SEGMENTS_POLICY.policy_id` (`final_segments_v1`)
  - EVERYTHING → reuse the same policy id (`final_segments_v1`) for now

If identity cannot be computed, endpoints return UNAVAILABLE deterministically (no throw).

## API contract (must ship)
Mount `/api/index`:

### GET `/api/index/diagnose`
Query params:
- `pool_identifier` (required): `FINAL_SEGMENTS | EVERYTHING`
- `include_slices` (optional, default false)
- `limit_slices` (optional, default 200; enforce server max)
- `dossier_id` (optional)

Behavior:
- Compute runtime identity server-side
- Call `PoolMaintenanceController(...).diagnose_pool(...)`
- Return stable report shape:
  - always include `pool_open`
  - include `pool_health` when pool open OK
  - include `slice_diagnoses` only when `include_slices=true` (cap at `limit_slices`)
  - include derived `counts` (healthy/missing/stale/unavailable)

No-throw contract:
- final try/except
- on unexpected failure: return deterministic UNAVAILABLE response with `detail=<exception_type>` (no stack traces)

### POST `/api/index/execute` (enqueue job)
Body:
```json
{
  "pool_identifier": "EVERYTHING",
  "mode": "missing_only" | "missing_and_stale",
  "limit": 25,
  "dossier_id": "optional",
  "dry_run": false
}
```

Behavior:
- Compute runtime identity server-side
- `safe_open_pool(pool_identifier)` first
  - if UNAVAILABLE: record a deterministic job result immediately OR return deterministic error (implementation choice; must be stable)
- Diagnose, select slices deterministically:
  - `missing_only`: `SliceStatus.MISSING`
  - `missing_and_stale`: `MISSING | STALE_CONTENT | STALE_IDENTITY`
  - sort by `(dossier_id, entry_id)`
  - enforce hard `limit` and server max (e.g. 100)
- Persist job record and run execution in background:
  - execute slice-by-slice via existing executor surfaces

### GET `/api/index/jobs/{job_id}`
Returns persisted job record:
- status: `QUEUED|RUNNING|SUCCEEDED|FAILED`
- progress counts
- per-slice results (cap returned results if needed; store full results if feasible)

## Persisted job store (file-backed)
Implement `IndexMaintenanceJobStore` in the same style as `ImageToTextJobStore`:
- One JSON file per job
- Index file mapping `job_id -> filename`
- Store under `dossiers_processing_jobs_root("index_maintenance")`

Minimum job fields:
- request: `pool_identifier`, `mode`, `limit`, `dossier_id`, `dry_run`
- computed identity: `embedding_model_fingerprint`, `chunking_policy_id`
- timestamps: `created_at`, `started_at`, `finished_at`
- status enum
- progress: `total`, `done`, `ok`, `failed`
- results: list of per-slice entries:
  - `dossier_id`, `entry_id`
  - `status` (post-execution)
  - `reason_code` (use `DiagnosticReasonCode` where applicable)
  - `detail` (human-readable; avoid stack traces)

## Acceptance criteria
- `GET /api/index/diagnose?pool_identifier=EVERYTHING` returns a stable report (no throw) and can show missing slices on real data.
- `POST /api/index/execute` returns a `job_id`.
- Poll `GET /api/index/jobs/{job_id}` until job finishes.
- Re-run diagnose → missing decreases; pool health reflects nonzero activity.

## Tests (minimum, deterministic)
- API tests:
  - identity computation failure → returns UNAVAILABLE with stable code; never throws
  - execute selection respects deterministic ordering + hard limit
- Job store tests:
  - create/update/reload persists correctly
- Prefer non-HNSW stubs (mirror existing retrieval engine test strategy)


