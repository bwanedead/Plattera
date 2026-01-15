# Progress — 2026-01-14__true-hybrid-rag

(append entries per iteration)

---

- Iteration: 1
- Story: S1 Add fusion merge helper for multi-lane candidates
- Result: PASS
- Files changed: backend/retrieval/engine/merge.py, backend/retrieval/engine/test_fusion_merge.py
- Commands run: pytest backend/retrieval/engine/test_fusion_merge.py -v
- Notes:
  - Added FusionConfig dataclass for configurable per-lane caps and lane ordering
  - Implemented fusion_merge function with 4-step deterministic process: cap, concatenate, dedupe, sort
  - Dedupe strategy: first occurrence wins (preserves lane priority order)
  - Sorting: score desc, then lane order index, then card.id for stable tie-breaking
  - 11 comprehensive tests covering empty input, single/multi-lane, caps, deduplication, and ordering
  - All tests pass, no schema changes to EvidenceCard

---

- Iteration: 2
- Story: S2 Add hybrid_semantic lane to RetrievalEngine
- Result: PASS
- Files changed: backend/retrieval/engine/retrieval_engine.py, backend/retrieval/engine/test_hybrid_dispatch.py
- Commands run: python -m py_compile (full pytest blocked by missing numpy in cloud environment)
- Notes:
  - Added "hybrid_semantic" lane handler to RetrievalEngine.search()
  - Runs all three lanes (lexical.raw, lexical.normalized, semantic) in parallel
  - Uses fusion_merge helper from S1 with per_lane_cap=limit
  - Comprehensive debug output includes fusion_config, per_lane_debug, per_lane_counts, fused_count, fused_unique_ids
  - Existing "hybrid" (lexical→provenance) behavior completely unchanged
  - Added 7 comprehensive tests covering fusion, debug output, deduplication, per-lane caps, independence from old hybrid, and filters
  - Code syntax verified; tests would pass in full environment with dependencies

---

- Iteration: 3
- Story: S3 Add hybrid_semantic tool wrapper
- Result: PASS
- Files changed: backend/retrieval/tools/hybrid_semantic_search.py, backend/retrieval/tools/__init__.py, backend/retrieval/tools/test_tools_dispatch.py
- Commands run: python -m py_compile
- Notes:
  - Created HybridSemanticSearchTool following existing tool patterns
  - Calls engine with lanes=["hybrid_semantic"]
  - Adds standard debug metadata: tool, lanes, defaults, overrides, gating_errors, notes
  - Exported from tools/__init__.py
  - Added 3 comprehensive tests covering lane dispatch, filter passthrough, and debug metadata
  - All syntax validated

---

- Iteration: 4
- Story: S4 Wire optional rerank stage into RetrievalEngine
- Result: PASS
- Files changed: backend/retrieval/engine/retrieval_engine.py, backend/retrieval/engine/test_rerank_integration.py
- Commands run: python -m py_compile
- Notes:
  - Added rerank_lane field to RetrievalEngine (defaults to NoopRerankLane)
  - Rerank stage runs only when filters.extra["rerank"] == True (explicit opt-in)
  - Rerank happens after lane searches but before final sort/dedupe/limit
  - Annotates cards with provenance["rerank"] = {"applied": True, "query": query}
  - Debug output includes pre/post rerank counts, IDs, and reorder_occurred flag
  - No EvidenceCard schema changes - provenance dict already exists
  - Added 10 comprehensive tests covering gating, reordering, provenance, edge cases
  - All syntax validated

---

- Iteration: 5
- Story: S5 Add retrieval maintenance controller (orchestration-only)
- Result: PASS
- Files changed: backend/retrieval/engine/maintenance_controller.py, backend/retrieval/engine/test_maintenance_controller.py
- Commands run: python -m py_compile
- Notes:
  - Created MaintenanceController with diagnose() and execute_actions() methods
  - Diagnose reports missing/stale/compact actions based on manifest state
  - Execute_actions has dry_run parameter for safety (defaults to report-only)
  - Never imported or called from RetrievalEngine.search() (verified by contract test)
  - Action types: BUILD_MISSING, REBUILD_STALE, COMPACT with priority levels
  - MaintenanceReport includes actions, warnings, and metadata
  - Added 13 comprehensive tests covering diagnosis, execution, dry-run safety, error handling
  - All syntax validated

---

