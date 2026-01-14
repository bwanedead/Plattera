# SUMMARY.md — Ralph Run: 2026-01-14__yellow-zone-audit-and-gaps

This file captures a running summary of what was built, one entry per completed story. It provides a human-readable debrief for reviewers.

(append one entry per story)

---

## Story S1: Add tombstone statistics API to PersistentVectorStore
**Status:** PASS
**Iteration:** 1

### What was built
- Added `count_tombstoned_chunks()` method to VectorMetadataStore for querying deleted chunks
- Enhanced `get_stats()` method in PersistentVectorStore to return comprehensive statistics
- Created `test_get_stats()` validating stats accuracy across multiple operations

### Files changed
- `backend/retrieval/lanes/semantic/metadata_store.py` - Added count_tombstoned_chunks() method (lines 343-356)
- `backend/retrieval/lanes/semantic/persistent_store.py` - Enhanced get_stats() to include tombstoned_count, tombstone_ratio, pool_identifier (lines 185-208)
- `backend/retrieval/lanes/semantic/test_persistent_store.py` - Added test_get_stats() validating stats after insertions, updates, deletions (lines 377-447)

### Key decisions
- Tombstone ratio calculated as tombstoned / total_chunks (handles empty index gracefully with 0.0)
- Stats API queries metadata store for accurate counts (no estimation)
- Included pool_identifier in stats for operational context
- Test validates stats evolution through: empty → 10 inserts → 3 updates → full deletion

### Tests added
- test_get_stats() in test_persistent_store.py (70 lines)
- Validates all 5 stat fields: active_chunks, total_vectors, tombstoned_count, tombstone_ratio, pool_identifier
- Tests edge cases: empty index, 100% tombstoned index

### Notes
- Provides visibility needed for Point 7 (tombstone compaction strategy)
- Stats API enables operators to monitor tombstone accumulation
- Foundation for S2 (compaction) and S3 (should_compact helper)

---

## Story S2: Implement compact() method to rebuild index without tombstones
**Status:** PASS
**Iteration:** 2

### What was built
- Added `list_all_active_chunks()` to VectorMetadataStore to enumerate all active chunks with metadata
- Added `delete_tombstones()` to VectorMetadataStore to permanently remove tombstoned metadata entries
- Added `get_vectors(labels)` to HnswVectorStore to retrieve vectors by labels using hnswlib.get_items()
- Implemented `compact()` method in PersistentVectorStore that rebuilds HNSW index without tombstones
- Created 3 comprehensive tests validating compaction behavior

### Files changed
- `backend/retrieval/lanes/semantic/metadata_store.py` - Added list_all_active_chunks() and delete_tombstones() methods
- `backend/retrieval/lanes/semantic/hnsw_store.py` - Added get_vectors() method to retrieve vectors by labels  
- `backend/retrieval/lanes/semantic/persistent_store.py` - Implemented compact() method with sequential label remapping
- `backend/retrieval/lanes/semantic/test_persistent_store.py` - Added test_compact_removes_tombstones, test_compact_empty_index, test_compact_all_tombstones

### Key decisions
- Compaction retrieves vectors from HNSW using get_items() before rebuilding (no re-embedding needed)
- New labels are sequential (0, 1, 2, ...) for compactness and cache locality
- Metadata updates happen per-chunk (upsert_chunk) for transaction safety
- Tombstones are permanently deleted from metadata after compaction
- Old HNSW store is replaced in-place (destructive operation)
- Returns stats: chunks_retained, tombstones_removed, old_total_vectors, new_total_vectors

### Tests added
- test_compact_removes_tombstones(): Normal compaction with 10 chunks, 5 tombstones
  - Validates stats before/after compaction
  - Confirms all active chunks still retrievable
  - Verifies no duplicate chunk_ids after compaction
- test_compact_empty_index(): Edge case - compacting empty index returns 0s
- test_compact_all_tombstones(): Edge case - all chunks tombstoned, results in empty index

### Notes
- Solves Point 7 (tombstone compaction) - provides actual compaction mechanism
- Safe by design: retrieves vectors before rebuilding, preserves all active data
- No data loss: vectors re-added with new labels, metadata updated atomically
- Foundation for S3 (should_compact helper and strategy documentation)
- Compaction is manual trigger only (no automatic compaction yet)

---

## Story S3: Add should_compact() helper and document compaction strategy
**Status:** PASS
**Iteration:** 3

### What was built
- Added `should_compact(threshold=0.3)` method to PersistentVectorStore
- Comprehensive docstring documenting compaction strategy (when/why/how + operational impact)
- Extensive "Tombstone Compaction" section in agents.md (130+ lines)
- Test validating threshold logic across multiple tombstone ratios

### Files changed
- `backend/retrieval/lanes/semantic/persistent_store.py` - Added should_compact() with 35-line docstring documenting complete compaction strategy
- `backend/retrieval/lanes/semantic/agents.md` - Added "Tombstone Compaction" section with what/when/how/operational guidance
- `backend/retrieval/lanes/semantic/test_persistent_store.py` - Added test_should_compact_threshold testing threshold logic

### Key decisions
- Default threshold: 30% (based on memory/performance trade-off)
- should_compact() is simple wrapper over get_stats() for clarity
- Documentation emphasizes operational concerns: when to run, blocking operation, memory usage
- agents.md includes Python code examples for manual compaction
- Clear separation: should_compact() = decision helper, compact() = actual operation

### Tests added
- test_should_compact_threshold(): Validates threshold logic across scenarios
  - Empty index (0% tombstones) → False
  - 10 chunks, no updates (0% tombstones) → False  
  - 2/12 (16.7% tombstones) → False for 30%, True for 10%
  - 5/15 (33.3% tombstones) → True for 30%, False for 50%
  - 100% tombstoned → True for all thresholds

### Notes
- **Point 7 (tombstone compaction) COMPLETE:** Full solution delivered
  - S1: Stats API for visibility
  - S2: Compaction implementation
  - S3: should_compact() helper + comprehensive documentation
- Documentation is production-ready: operators have clear guidance on when/how to compact
- agents.md section includes: what tombstones are, when to compact, manual trigger examples, implementation details, operational recommendations
- Compaction strategy is explicit: monitor ratio, compact at 30-50%, run during off-peak hours

---

## Story S4: Add model fingerprint tracking to manifest for robust staleness detection
**Status:** PASS
**Iteration:** 4

### What was built
- Added `embedding_model_fingerprint` field to SemanticIndexManifest (Optional[str])
- Created `compute_model_fingerprint()` function to generate deterministic fingerprints from model_info
- Updated IndexBuilder to accept and write fingerprint to manifest
- Enhanced Lane staleness detection to compare fingerprints (with backward compat fallback)
- Added 3 tests validating fingerprint round-trip, backward compat, and mismatch detection

### Files changed
- `backend/retrieval/lanes/semantic/manifest.py` - Added embedding_model_fingerprint field to dataclass, to_dict(), from_dict()
- `backend/retrieval/lanes/semantic/embeddings.py` - Added compute_model_fingerprint() using asset_id + manifest hash
- `backend/retrieval/lanes/semantic/index_builder.py` - Added fingerprint parameter to build_index_for_dossier(), writes to manifest
- `backend/retrieval/lanes/semantic/lane.py` - Enhanced _check_manifest_mismatch() to compare fingerprints, falls back to model_id
- `backend/retrieval/lanes/semantic/test_manifest.py` - Added test_manifest_includes_fingerprint, test_manifest_without_fingerprint_backward_compat
- `backend/retrieval/lanes/semantic/test_lane.py` - Added test_staleness_detects_fingerprint_mismatch

### Key decisions
- Fingerprint = asset_id + hash(manifest_content) for determinism
- Optional field for backward compatibility (old manifests have fingerprint=None)
- Staleness check: if fingerprint available, use it; otherwise fall back to model_id
- Fingerprint comparison catches model weight changes even if friendly name unchanged
- SHA256 hash truncated to 16 chars for compactness

### Tests added
- test_manifest_includes_fingerprint(): Validates fingerprint preserved in round-trip
- test_manifest_without_fingerprint_backward_compat(): Old manifests (no fingerprint) load correctly
- test_staleness_detects_fingerprint_mismatch(): Lane detects stale index via fingerprint mismatch

### Notes
- **Point 4 (model identity semantics) COMPLETE:** Robust staleness detection implemented
- Fingerprints prevent false negatives (model weights changed but name same)
- Backward compatible: existing indexes without fingerprints continue working
- Fingerprint is deterministic: same model → same fingerprint across runs
- Future improvement: could include model file checksums for even stronger detection
