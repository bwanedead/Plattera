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
