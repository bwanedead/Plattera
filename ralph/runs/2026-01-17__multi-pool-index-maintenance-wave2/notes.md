# Notes — 2026-01-17__multi-pool-index-maintenance-wave2

Handoff brief (repo reality):
- Baseline already done (do not redo):
  - Doc-slice primitives exist: list_labels_for_entry, delete_entry_slice, indexed_entry_state (schema v4), builder writes indexed state.
  - Inventory→Diagnose→Execute exists for FINAL (v0) and is hardened (stable reason codes, no partial state writes, idempotent deletes, runtime_identity required for HEALTHY).
  - MaintenanceController already handles pool existence checks + can emit COMPACT recommendation (via should_compact()).

This wave focuses on:
- Story A: Safe pool-open boundary wrapper used by MaintenanceController; never throws; returns PoolOpenReport with stable DiagnosticReasonCode.
- Story B: EVERYTHING pool maintenance end-to-end (head-only v0), with explicit view selection (no implicit defaults).
- Story C: Stable pool health report shape reusing existing stats/compaction signal (no reimplementation).
- Story E: Structured logging (replace stderr prints) in maintenance paths.

Deferred (do NOT implement):
- Atomic-ish rebuild hole reduction (build-first-then-delete is a footgun without generations/snapshots).



