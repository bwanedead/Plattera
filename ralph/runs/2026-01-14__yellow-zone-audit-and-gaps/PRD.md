# PRD: Yellow Zone Final Hardening - Implement Missing Functionality

## Context
Following the successful completion of the semantic-index-polish run (S1-S8), we have a production-ready semantic retrieval system. A "yellow zone cloud" brief identified 10 critical correctness points. Initial analysis revealed **8 out of 10 points are already complete**, but 2 points need actual implementation:

1. **Point 7 (Tombstone compaction):** Tombstones accumulate but no compaction mechanism exists
2. **Point 4 (Model identity):** Uses friendly names only; needs fingerprint tracking for robust staleness detection

## Goal
Implement the missing functionality to fully satisfy all 10 yellow-zone correctness points, specifically:
- Tombstone statistics API for visibility
- Compaction mechanism to remove tombstones
- Model fingerprint tracking for robust staleness detection

## Non-goals
- Automatic compaction triggers (implement tooling, manual trigger only for now)
- Changing working implementations for Points 1, 2, 3, 5, 6, 8, 9, 10
- UI/frontend changes
- Performance optimization beyond compaction

## Users / Use cases
- As an operator, I need to monitor tombstone accumulation and trigger compaction when needed
- As a developer, I need robust staleness detection that catches model weight changes, not just name changes
- As a system admin, I need clear guidance on when/why to compact indexes

## Scope
- Backend retrieval system:
  - `backend/retrieval/lanes/semantic/persistent_store.py` (stats, compaction)
  - `backend/retrieval/lanes/semantic/metadata_store.py` (tombstone queries)
  - `backend/retrieval/lanes/semantic/manifest.py` (fingerprint field)
  - `backend/retrieval/lanes/semantic/embeddings.py` (fingerprint computation)
  - `backend/retrieval/lanes/semantic/index_builder.py` (write fingerprint)
  - `backend/retrieval/lanes/semantic/lane.py` (check fingerprint)
- Documentation:
  - `backend/retrieval/lanes/semantic/agents.md` (compaction strategy)
  - Inline docstrings for new methods
- Tests:
  - `backend/retrieval/lanes/semantic/test_persistent_store.py` (stats, compaction tests)
  - `backend/retrieval/lanes/semantic/test_manifest.py` (fingerprint tests)
  - `backend/retrieval/lanes/semantic/test_lane.py` (staleness tests)

## Constraints / invariants
- Compaction must be safe (no data loss)
- Compaction must preserve all active chunk_ids and retrievability
- Model fingerprint must be deterministic for same model
- All existing tests must continue to pass
- Preserve all ethos principles (evidence-first, deterministic, safe failure modes)
- Backward compatible: old manifests without fingerprint still work (degrade gracefully)

## Success criteria
- Stats API returns accurate tombstone counts
- Compaction removes all tombstones and index continues to work
- Fingerprint tracking catches model weight changes
- All 10 yellow-zone points are verifiably complete
- All existing tests pass plus new tests for stats/compaction/fingerprint
- Clear documentation for operators on compaction strategy

## Edge cases
- Compaction with no tombstones (no-op, safe)
- Compaction with 100% tombstones (empty index after)
- Manifest without fingerprint field (backward compat, fallback to name-only comparison)
- Fingerprint computation failure (log warning, proceed without fingerprint)
- Compaction interrupted mid-process (needs atomic rebuild or rollback)

## Implementation notes
### Point 7 (Tombstone compaction):
1. **Stats API:** `get_stats()` returns `{active_chunks, total_vectors, tombstoned_count, tombstone_ratio, pool_identifier}`
2. **Compaction:** `compact()` rebuilds HNSW from metadata, remaps labels sequentially, updates metadata store
3. **Strategy:** `should_compact(threshold=0.3)` returns True when tombstone_ratio > 30%
4. **Documentation:** agents.md explains what tombstones are, when to compact, how to trigger manually

### Point 4 (Model fingerprint):
1. **Fingerprint field:** Add `embedding_model_fingerprint: Optional[str]` to SemanticIndexManifest
2. **Computation:** Embedding provider computes fingerprint (model name + architecture hash or version)
3. **Staleness check:** Lane compares fingerprints; mismatch = stale (even if friendly names match)
4. **Fallback:** If no fingerprint in manifest, fall back to friendly name comparison (backward compat)

### Implementation approach:
- S1: Stats API first (enables visibility into problem)
- S2: Compaction implementation (solves the problem)
- S3: should_compact() helper + docs (makes it usable)
- S4: Fingerprint tracking (independent, can run parallel to S1-S3)
- S5: Final validation (proves everything works)
