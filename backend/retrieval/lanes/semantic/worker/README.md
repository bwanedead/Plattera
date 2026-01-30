# Semantic Worker (HNSW) - Interface Contract

## Scope
- Folder: `backend/retrieval/lanes/semantic/worker/`
- Purpose:
  - Provide crash-isolated, persistent HNSW vector search for semantic retrieval
  - Define TCP IPC contract between main process and worker

## Ops
- `ping`: health check
- `stats`: index metadata
- `knn`: nearest neighbor query
- `reload`: reload manifest + hnsw index
- `shutdown`: graceful stop

## Request Schema (JSON, one message per line)
- `request_id`: string
- `op`: `ping|stats|knn|reload|shutdown`
- `pool_identifier`: `FINAL_SEGMENTS|EVERYTHING`
- `k`: int (knn only)
- `ef`: int | null (knn only)
- `embedding_dim`: int (knn only)
- `vector_b64`: base64 float32 (knn only)
- `manifest_fingerprint`: string | null

## Response Schema (JSON, one message per line)
- `request_id`: string
- `status`: `ok|busy|error`
- `reason_code`: string | null
- `results`: list of `[label:int, distance:float]` (knn only)
- `worker_stats` (optional):
  - `total_vectors`: int
  - `embedding_dim`: int
  - `manifest_fingerprint`: string | null
  - `uptime_s`: float

## Reason Codes (stable)
- `semantic_worker_unavailable`
- `semantic_worker_crashed`
- `semantic_worker_timeout`
- `semantic_worker_busy`
- `semantic_worker_manifest_mismatch`
- `semantic_worker_in_backoff`
- `semantic_worker_malformed_request`
- `semantic_worker_reload_failed`
- `semantic_worker_port_in_use`

## Lifecycle Policy (main process)
- Lazy start on first semantic query.
- On failure: restart worker, retry once.
- Backoff on repeated failure (1s, 2s, 5s, 10s... cap 60s).
- During backoff: return empty semantic results + reason code.

## Ports
- Default host: `127.0.0.1`
- Default ports:
  - `FINAL_SEGMENTS`: `9351`
  - `EVERYTHING`: `9352`
- Override with env:
  - `HNSW_WORKER_PORT_FINAL_SEGMENTS`
  - `HNSW_WORKER_PORT_EVERYTHING`
  - `HNSW_WORKER_HOST`

## Timeouts / Budgets
- `HNSW_WORKER_QUERY_BUDGET_MS` (default `1500`) caps end-to-end query time (includes one retry).
- `HNSW_WORKER_CLIENT_TIMEOUT_SEC` (default `3`) socket timeout per request.
- `HNSW_WORKER_REQUEST_TIMEOUT_SEC` (default `10`) worker-side queue wait timeout.
