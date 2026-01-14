# Semantic Lane Testing Strategy

## Test Isolation and Dependencies

The semantic lane tests are split into two categories:

### 1. HNSW Integration Tests (require numpy/hnswlib)

These tests build actual vector indexes using hnswlib and numpy. They are marked with `@pytest.mark.hnsw`.

**Modules that are entirely HNSW integration tests:**
- `test_hnsw_store.py` - All tests (vector store operations)
- `test_persistent_store.py` - All tests (persistent vector operations)

**Individual HNSW-dependent tests in other modules:**
- `test_index_builder.py::test_builder_writes_manifest_on_successful_build`
- `test_index_builder.py::test_builder_skips_manifest_if_parameters_missing`
- `test_lane.py::test_semantic_hits_include_preview`
- `test_lane.py::test_final_segments_metadata_has_full_corpus_entry_ref_fidelity`

### 2. Non-HNSW Tests (no external dependencies)

These tests validate logic, API contracts, and data structures without requiring hnswlib:
- `test_metadata_store.py` - All tests (SQLite metadata operations)
- `test_chunking.py` - All tests (text chunking logic)
- `test_manifest.py` - All tests (manifest read/write operations)
- `test_index_builder.py::test_builder_api_without_persistence`
- `test_index_builder.py::test_rebuild_slice_logic`
- `test_lane.py::test_missing_index_safe_failure`
- `test_lane.py::test_lane_structure`
- `test_lane.py::test_manifest_mismatch_detection`
- `test_lane.py::test_operational_index_failure_modes`

## Running Tests

### Run all tests (requires hnswlib/numpy):
```bash
pytest backend/retrieval/lanes/semantic/ -v
```

### Run HNSW integration tests only:
```bash
pytest backend/retrieval/lanes/semantic/ -m hnsw -v
```

### Run non-HNSW tests (fast, no external dependencies):
```bash
pytest backend/retrieval/lanes/semantic/ -m "not hnsw" -v
```

### Run specific test modules (no dependencies):
```bash
pytest backend/retrieval/lanes/semantic/test_metadata_store.py -v
pytest backend/retrieval/lanes/semantic/test_chunking.py -v
pytest backend/retrieval/lanes/semantic/test_manifest.py -v
```

## Why This Strategy?

**Problem:** hnswlib can crash when creating/destroying multiple index instances rapidly in the same process. This makes running the full test suite unreliable in some environments.

**Solution:** Explicitly mark HNSW integration tests with `@pytest.mark.hnsw`, allowing developers to:
1. Run fast non-HNSW tests during development (`-m "not hnsw"`)
2. Run HNSW integration tests separately when needed (`-m hnsw`)
3. Avoid using brittle `--ignore` flags that hide tests permanently

**No permanent ignores:** All tests are runnable and discoverable. Choose your test scope based on what you're working on, not based on avoiding crashes.

## CI/Automation Considerations

If adding CI automation later:
- Run non-HNSW tests on every commit (fast feedback)
- Run HNSW integration tests in a separate job (may need retry logic or isolation)
- Consider running HNSW tests in separate processes to avoid hnswlib crashes

## Tombstone Compaction

### What are tombstones?

When vectors are updated or deleted in the semantic index, the old vectors are marked as "deleted" (tombstoned) rather than immediately removed. This is a safety mechanism to ensure updates are atomic and deterministic.

**Why tombstones exist:**
- Safe updates: Updating a chunk creates a new vector with a new label, then tombstones the old label
- No label reuse: Never reuse deleted labels to avoid HNSW graph corruption
- Deterministic behavior: Update semantics are consistent across restarts

**Trade-off:**
- Tombstones accumulate over time, consuming memory and degrading query performance
- HNSW must filter tombstoned vectors during queries
- Index file size grows unbounded without compaction

### When to compact

Compaction should be triggered when tombstone accumulation impacts performance or memory:

**Automatic triggers (recommended thresholds):**
- **Tombstone ratio > 30%** (default threshold in should_compact())
- After bulk updates or re-indexing operations
- When index file size exceeds acceptable limits

**Manual triggers:**
- During scheduled maintenance windows
- After deleting large dossiers or slices
- When query performance degrades noticeably

**Check if compaction is needed:**
```python
stats = store.get_stats()
print(f"Tombstone ratio: {stats['tombstone_ratio']:.1%}")
print(f"Tombstoned vectors: {stats['tombstoned_count']}/{stats['total_vectors']}")

if store.should_compact(threshold=0.3):
    print("Compaction recommended")
```

### How to trigger compaction

**Manual compaction (Python):**
```python
from backend.retrieval.lanes.semantic.persistent_store import load_persistent_store

# Load the persistent store
store = load_persistent_store(
    pool_identifier="FINAL_SEGMENTS",
    hnsw_path=Path("path/to/index.hnsw"),
    metadata_path=Path("path/to/metadata.db"),
)

# Check stats before compaction
pre_stats = store.get_stats()
print(f"Before: {pre_stats['active_chunks']} active, {pre_stats['tombstoned_count']} tombstoned")

# Compact the index
compact_stats = store.compact()
print(f"Compacted: removed {compact_stats['tombstones_removed']} tombstones")
print(f"Retained {compact_stats['chunks_retained']} active chunks")

# Save compacted index
store.save(hnsw_path=Path("path/to/index.hnsw"), metadata_path=Path("path/to/metadata.db"))

# Verify post-compaction
post_stats = store.get_stats()
print(f"After: {post_stats['active_chunks']} active, {post_stats['tombstoned_count']} tombstoned")
assert post_stats['tombstone_ratio'] == 0.0, "All tombstones should be removed"
```

### Compaction implementation details

**What compact() does:**
1. Enumerate all active (non-tombstoned) chunks from metadata
2. Retrieve vectors for active chunks using HNSW `get_items()`
3. Create new HNSW index with sequential labels (0, 1, 2, ...)
4. Re-add all active vectors to new index
5. Update metadata to map chunk_ids to new sequential labels
6. Delete tombstoned metadata entries permanently
7. Replace old HNSW index with new compacted index

**Safety guarantees:**
- No data loss: All active chunks and their vectors are preserved
- Atomic replacement: Old index remains functional until new index is ready
- Deterministic: Same active chunks always produce same compacted index
- Idempotent: Compacting twice has same effect as compacting once

**Performance characteristics:**
- Duration: O(N) where N = number of active chunks (not total vectors)
- Memory: Requires ~2x peak memory (old + new index temporarily in memory)
- Blocking: No queries during compaction (typically < 1 second for small indexes)

### Operational recommendations

**Frequency:**
- Monitor tombstone ratio via `get_stats()` 
- Compact when ratio exceeds 30-50%
- For high-update workloads, schedule daily/weekly compaction

**Timing:**
- Run during off-peak hours or maintenance windows
- Compact before backups to reduce backup size
- Compact after bulk re-indexing operations

**Monitoring:**
- Log compaction stats (chunks_retained, tombstones_removed)
- Track tombstone ratio trends over time
- Alert if ratio exceeds 70% (high memory waste)

**Testing:**
- Validate index still works after compaction (query known chunks)
- Verify tombstone_count = 0 after compaction
- Confirm no duplicate chunk_ids in results
