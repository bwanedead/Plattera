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
