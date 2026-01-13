# Progress — 2026-01-12__semantic-index-polish

(append entries per iteration)


Iteration: 1
Story: S1 Add deterministic preview excerpt to semantic hits (store + return)
Result: PASS
Files changed: 
  - backend/retrieval/lanes/semantic/metadata_store.py
  - backend/retrieval/lanes/semantic/persistent_store.py
  - backend/retrieval/lanes/semantic/index_builder.py
  - backend/retrieval/lanes/semantic/lane.py
  - backend/retrieval/lanes/semantic/test_lane.py
Commands run:
  - /root/.local/bin/pytest -q backend/retrieval/lanes/semantic/test_metadata_store.py
  - /root/.local/bin/pytest -q backend/retrieval/lanes/semantic/test_chunking.py backend/retrieval/lanes/semantic/test_metadata_store.py backend/retrieval/lanes/lexical/ -v
Notes:
  - Added preview field to ChunkMetadata schema (bumped schema version to 2)
  - Preview is generated from chunk.snippet_hint or first 200 chars of chunk.text
  - Preview is passed through index builder → persistent store → metadata store
  - Preview is returned in EvidenceSpan when querying semantic lane
  - Added comprehensive test (test_semantic_hits_include_preview) that builds fixture index and verifies preview persistence
  - All retrieval tests pass (34 tests)


Iteration: 2
Story: S2 Ensure FINAL_SEGMENTS hit metadata has full CorpusEntryRef fidelity (hydrateable)
Result: PASS
Files changed:
  - backend/retrieval/lanes/semantic/metadata_store.py
  - backend/retrieval/lanes/semantic/persistent_store.py
  - backend/retrieval/lanes/semantic/index_builder.py
  - backend/retrieval/lanes/semantic/lane.py
  - backend/retrieval/lanes/semantic/test_lane.py
Commands run:
  - /root/.local/bin/pytest -q backend/retrieval/lanes/semantic/test_metadata_store.py backend/retrieval/lanes/semantic/test_chunking.py -v
Notes:
  - Added segment_id and draft_id fields to ChunkMetadata schema (bumped schema version to 3)
  - Updated PersistentVectorStore.upsert() to accept and persist segment_id and draft_id
  - Updated SemanticIndexBuilder to extract segment_id and draft_id from entry ref and pass to upsert
  - Updated LocalSemanticLane.search() to reconstruct CorpusEntryRef with segment_id and draft_id
  - Added comprehensive test (test_final_segments_metadata_has_full_corpus_entry_ref_fidelity) that builds fixture, queries, and verifies hydration works
  - All tests pass (30 tests)


Iteration: 3
Story: S3 Add explicit read-mode service (Evidence → full hydrated entry)
Result: PASS
Files changed:
  - backend/retrieval/read_service.py (new)
  - backend/retrieval/test_read_service.py (new)
Commands run:
  - /root/.local/bin/pytest -q backend/retrieval/test_read_service.py -v
Notes:
  - Created new read_service.py module with expand_evidence_to_entry() function
  - Service takes EvidenceCard or EvidenceSpan and returns full hydrated CorpusEntry
  - Maintains architectural separation: lanes are lightweight locators, read service does heavy hydration
  - Added comprehensive tests (5 tests) covering normal flow, edge cases, and architectural separation
  - All tests pass

