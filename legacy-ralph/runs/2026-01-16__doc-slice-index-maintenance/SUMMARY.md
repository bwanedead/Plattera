# SUMMARY.md — Ralph Run: 2026-01-16__doc-slice-index-maintenance

This file captures a running summary of what was built, one entry per completed story. It provides a human-readable debrief for reviewers.

---

## Final Summary (append when run complete)

### Overview
<1-2 paragraph summary of what the entire run accomplished>

### Total changes
- Files created: <count>
- Files modified: <count>
- Tests added: <count>

### Architecture decisions
- <bullet: key technical choices made>

### Known limitations
- <bullet: deferred work>


---

## Story S1: Make EVERYTHING view draft-aware: entry_id becomes canonical draft_id (head-only v0) + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Draft-aware EVERYTHING view entry ids using the head-only draft_id format
- Deterministic test covering EVERYTHING ref identity contract

### Files changed
- `backend/corpus/views/everything.py` - emit draft-aware entry_id/draft_id for transcript heads
- `backend/corpus/test_virtual_corpus.py` - add draft-aware EVERYTHING enumeration test
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S1 as passing

### Key decisions
- Reused the canonical draft_id format as the entry_id to keep doc-slice identity stable

### Tests added
- 1 new tests in `backend/corpus/test_virtual_corpus.py`

### Notes
- Head-only behavior is preserved while upgrading identity vocabulary
---

## Story S2: Make transcript hydration draft-aware for head-form draft_ids (fallback to existing behavior) + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Draft-aware transcript hydration for head-form draft_ids with legacy fallback
- Deterministic test verifying draft-aware hydration matches legacy content/hash

### Files changed
- `backend/corpus/hydrate.py` - resolve head-form draft_id and hydrate transcripts
- `backend/corpus/test_virtual_corpus.py` - add draft-aware hydration test
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S2 as passing

### Key decisions
- Parse head-form draft_ids in the hydrator to keep identity handling centralized

### Tests added
- 1 new tests in `backend/corpus/test_virtual_corpus.py`

### Notes
- Draft-aware hydration stays compatible with legacy transcript refs
---

## Story S3: Add doc-slice label enumeration: list_labels_for_entry(pool,dossier,entry_id) in VectorMetadataStore + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Entry-level label enumeration in the vector metadata store
- Deterministic test covering entry-specific label listing

### Files changed
- `backend/retrieval/lanes/semantic/metadata_store.py` - add list_labels_for_entry API
- `backend/retrieval/lanes/semantic/test_metadata_store.py` - add list_labels_for_entry test
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S3 as passing

### Key decisions
- Filtered by pool, dossier, and entry to support doc-slice replace operations

### Tests added
- 1 new tests in `backend/retrieval/lanes/semantic/test_metadata_store.py`

### Notes
- Non-HNSW test path used per semantic lane testing strategy
---

## Story S4: Add delete_entry_slice(pool,dossier,entry_id): tombstone all vectors for that entry slice + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Entry-level slice deletion in the persistent vector store
- HNSW-backed test verifying tombstoned entry slices no longer return in queries

### Files changed
- `backend/retrieval/lanes/semantic/persistent_store.py` - add delete_entry_slice API
- `backend/retrieval/lanes/semantic/test_persistent_store.py` - add delete_entry_slice test
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S4 as passing

### Key decisions
- Reused metadata entry-level label enumeration to drive HNSW tombstoning

### Tests added
- 1 new tests in `backend/retrieval/lanes/semantic/test_persistent_store.py`

### Notes
- Test uses small k to avoid hnswlib ef edge cases
---

## Story S5: Persist per-slice indexed state: add indexed_entry_state table + store methods + schema bump tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Indexed entry state table with schema version bump
- Store APIs and deterministic test coverage for indexed entry state upsert/get

### Files changed
- `backend/retrieval/lanes/semantic/metadata_store.py` - add indexed_entry_state schema + APIs
- `backend/retrieval/lanes/semantic/test_metadata_store.py` - add indexed entry state test and schema version update
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S5 as passing

### Key decisions
- Modeled per-slice state as a keyed table for fast diagnose lookups

### Tests added
- 1 new tests in `backend/retrieval/lanes/semantic/test_metadata_store.py`

### Notes
- Schema version is now 4; older metadata DBs will require rebuild
---

## Story S6: Write indexed_entry_state after slice rebuild: builder stores indexed_signature and runtime identity + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- Builder writes indexed_entry_state per entry slice using content_hash and identity fields
- Deterministic test verifying indexed entry state write after indexing

### Files changed
- `backend/retrieval/lanes/semantic/index_builder.py` - write indexed_entry_state after entry indexing
- `backend/retrieval/lanes/semantic/test_index_builder.py` - add indexed_entry_state test with stub vector store
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S6 as passing

### Key decisions
- Used a stub vector store in tests to avoid HNSW multi-instance crashes while validating metadata writes

### Tests added
- 1 new tests in `backend/retrieval/lanes/semantic/test_index_builder.py`

### Notes
- indexed_entry_state writes only when content_hash and model fingerprint are available
---

## Story S7: InventoryProvider v0 for FINAL_SEGMENTS: enumerate slices and compute desired_signature (content_hash) + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- InventoryProvider that enumerates FINAL_SEGMENTS slices with desired_signature
- Deterministic test validating desired_signature equals content_hash

### Files changed
- `backend/retrieval/engine/inventory_provider.py` - add inventory provider and slice model
- `backend/retrieval/engine/test_inventory_provider.py` - add inventory provider test
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S7 as passing

### Key decisions
- Derived desired_signature directly from hydrated entry.content_hash for determinism

### Tests added
- 1 new tests in `backend/retrieval/engine/test_inventory_provider.py`

### Notes
- Inventory is scoped to FINAL_SEGMENTS for v0
---

## Story S8: Diagnose v0: compare inventory desired_signature vs indexed_entry_state to classify missing/stale/healthy/unavailable + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- SliceDiagnoser that classifies doc slices using inventory + indexed_entry_state
- Deterministic tests for missing/stale/healthy transitions and unavailable slices

### Files changed
- `backend/retrieval/engine/inventory_provider.py` - include unavailable slices for diagnose
- `backend/retrieval/engine/diagnose.py` - add diagnose logic and status model
- `backend/retrieval/engine/test_diagnose.py` - add diagnose tests
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S8 as passing

### Key decisions
- Diagnose relies on inventory slices with explicit unavailable reasons rather than silent skips

### Tests added
- 2 new tests in `backend/retrieval/engine/test_diagnose.py`

### Notes
- Identity mismatch is detected when runtime fingerprint or policy differs from indexed state
---

## Story S9: Execute v0: rebuild exactly one doc slice (delete_entry_slice + rebuild + update state) + tests
**Status:** PASS
**Iteration:** unknown

### What was built
- SliceExecutor to rebuild a single doc slice via delete_entry_slice + per-entry rebuild
- Deterministic test verifying stale slice rebuilds to healthy while other slices remain intact

### Files changed
- `backend/retrieval/engine/execute.py` - add execution orchestration for entry slices
- `backend/retrieval/engine/test_execute.py` - add execute test with stub vector store
- `backend/retrieval/lanes/semantic/index_builder.py` - add per-entry indexing helper
- `backend/retrieval/engine/inventory_provider.py` - report unavailable slices for diagnose
- `ralph/runs/2026-01-16__doc-slice-index-maintenance/prd.json` - mark S9 as passing

### Key decisions
- Used a stub vector store in tests to avoid HNSW crashes while validating tombstones and state updates

### Tests added
- 1 new tests in `backend/retrieval/engine/test_execute.py`

### Notes
- Execute path remains explicit; diagnose does not perform rebuilds
