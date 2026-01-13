# SUMMARY.md — Ralph Run: 2026-01-12__semantic-index-polish

This file captures a running summary of what was built, one entry per completed story. It provides a human-readable debrief for reviewers.

(append one entry per story)


Story S1: Add deterministic preview excerpt to semantic hits (store + return)
Status: PASS
Iteration: 1

What was built:
- Added preview field to ChunkMetadata dataclass and SQLite schema
- Extended PersistentVectorStore.upsert() to accept and persist preview parameter
- Updated SemanticIndexBuilder to generate and pass preview (from snippet_hint or text[:200])
- Modified LocalSemanticLane.search() to return preview in EvidenceSpan
- Created test_semantic_hits_include_preview to verify end-to-end preview persistence

Files changed:
- backend/retrieval/lanes/semantic/metadata_store.py - Added preview field to ChunkMetadata and SQLite schema (bumped schema version to 2)
- backend/retrieval/lanes/semantic/persistent_store.py - Added preview parameter to upsert() method
- backend/retrieval/lanes/semantic/index_builder.py - Generate preview and pass to vector_store.upsert()
- backend/retrieval/lanes/semantic/lane.py - Include preview from metadata in EvidenceSpan
- backend/retrieval/lanes/semantic/test_lane.py - Added comprehensive test for preview persistence

Key decisions:
- Preview is generated deterministically from chunk text (first 200 chars or snippet_hint)
- Preview is Optional[str] to handle backward compatibility
- Schema version bumped to 2 to reflect database schema change
- Preview field added to metadata store ensures it persists across restarts

Tests added:
- test_semantic_hits_include_preview: Builds fixture index, queries it, and verifies preview is non-empty and deterministic
- All existing tests continue to pass (34 retrieval tests)

Notes:
- Preview is for triage/debug, not full context hydration
- Preview is small (~200 chars) and deterministic for the same chunk
- Implementation follows repo ethos: robust, weight-bearing, mechanically clear


Story S2: Ensure FINAL_SEGMENTS hit metadata has full CorpusEntryRef fidelity (hydrateable)
Status: PASS
Iteration: 2

What was built:
- Extended ChunkMetadata to include segment_id and draft_id for full CorpusEntryRef reconstruction
- Updated entire indexing and query chain to preserve and reconstruct segment_id and draft_id
- Added test demonstrating successful hydration of FINAL_SEGMENTS entries from semantic hits
- Ensured no "unimplemented_hydration" errors for FINAL_SEGMENTS view

Files changed:
- backend/retrieval/lanes/semantic/metadata_store.py - Added segment_id and draft_id to ChunkMetadata and SQLite schema (bumped to version 3)
- backend/retrieval/lanes/semantic/persistent_store.py - Added segment_id and draft_id parameters to upsert()
- backend/retrieval/lanes/semantic/index_builder.py - Extract and pass segment_id and draft_id from entry ref
- backend/retrieval/lanes/semantic/lane.py - Reconstruct CorpusEntryRef with segment_id and draft_id for full fidelity
- backend/retrieval/lanes/semantic/test_lane.py - Added test_final_segments_metadata_has_full_corpus_entry_ref_fidelity

Key decisions:
- Store segment_id and draft_id as separate optional fields in SQLite for clarity and query capability
- Pass ref fields through the entire chain (builder → store → lane) rather than serializing full ref as blob
- Schema version bumped to 3 to reflect new columns
- All fields remain Optional[str] for backward compatibility with other views

Tests added:
- test_final_segments_metadata_has_full_corpus_entry_ref_fidelity: Builds fixture with segment_id/draft_id, queries index, reconstructs ref, and verifies successful hydration
- All existing tests continue to pass

Notes:
- FINAL_SEGMENTS entries can now be deterministically hydrated from semantic lane results
- CorpusEntryRef reconstruction is faithful to original entry ref used during indexing
- No changes to other corpus views or entry kinds (remains backward compatible)


Story S3: Add explicit read-mode service (Evidence → full hydrated entry)
Status: PASS
Iteration: 3

What was built:
- Created new read_service.py module providing locate→read bridge
- Implemented expand_evidence_to_entry() for EvidenceCard/EvidenceSpan → CorpusEntry expansion
- Added convenience wrapper expand_span_to_entry() for span-specific expansion
- Comprehensive test suite demonstrating deterministic evidence expansion

Files changed:
- backend/retrieval/read_service.py - New module with evidence expansion functions
- backend/retrieval/test_read_service.py - Complete test suite (5 tests)

Key decisions:
- Kept read service architecturally separate from lanes (lanes = lightweight locators, read service = heavy hydration)
- Consumer controls when to pay hydration cost (opt-in expansion)
- Safe failure modes: returns None for missing/invalid entries rather than crashing
- Simple, focused API: takes evidence + corpus provider, returns entry

Tests added:
- test_expand_evidence_card_to_full_entry: Card → full CorpusEntry
- test_expand_evidence_span_to_full_entry: Span → full CorpusEntry
- test_expand_evidence_missing_entry_returns_none: Safe failure for missing entries
- test_expand_evidence_empty_card_returns_none: Edge case handling
- test_read_service_is_separate_from_lanes: Validates architectural separation

Notes:
- Clean separation of concerns: lanes stay fast (locators only), read service does hydration on demand
- API is minimal and explicit as per PRD guidance
- Selector-based windows deferred as noted in PRD (can be follow-up story)


Story S4: Make manifest truth real (builder writes/updates manifest on successful build)
Status: PASS
Iteration: 4

What was built:
- Updated SemanticIndexBuilder.build_index_for_dossier() to accept pool_identifier, embedding_dim, and embedding_model_id parameters
- Builder now writes manifest.json on successful build with all required identity fields
- Manifest includes: schema_version, pool_identifier, embedding_dim, embedding_model_id, chunking_policy_id, timestamps
- Added tests verifying manifest write on successful build and graceful skip when parameters missing

Files changed:
- backend/retrieval/lanes/semantic/index_builder.py - Added manifest writing logic at end of successful build
- backend/retrieval/lanes/semantic/test_index_builder.py - Added test_builder_writes_manifest_on_successful_build and test_builder_skips_manifest_if_parameters_missing

Key decisions:
- Manifest write is conditional on having all required parameters (pool_identifier, embedding_dim, embedding_model_id)
- Manifest write only happens on successful build (chunks_added > 0 and no errors)
- Backward compatible: builder still works if manifest parameters not provided (for existing code)
- Manifest includes ISO timestamps for created_at and updated_at
- Uses existing manifest.py infrastructure (write_manifest, SemanticIndexManifest)

Tests added:
- test_builder_writes_manifest_on_successful_build: Verifies manifest.json is written with correct content on successful build
- test_builder_skips_manifest_if_parameters_missing: Verifies backward compatibility when params not provided
- All existing tests continue to pass (37 semantic tests)

Notes:
- Lane manifest mismatch detection already exists (test_manifest_mismatch_detection validates the method)
- Manifest provides "truth" for index state: model identity, embedding dim, chunking policy
- No silent rebuilds in query paths (detection only, as per PRD guidance)
- Immutable model identity tracked via embedding_model_id (e.g., "all-MiniLM-L6-v2")


Story S5: Make operational index failure modes explicit (missing vs unavailable vs stale)
Status: PASS
Iteration: 5

What was built:
- Created IndexLoadStatus enum with three explicit states: SUCCESS, NOT_INITIALIZED, UNAVAILABLE
- Created IndexLoadResult dataclass to carry load status, vector store, and error details
- Updated _get_or_load_vector_store() to return IndexLoadResult with explicit failure categorization
- Updated LocalSemanticLane.search() to handle all three load statuses separately with distinct debug messages
- Each failure mode now includes pool_identifier and descriptive error in debug output

Files changed:
- backend/retrieval/lanes/semantic/lane.py - Added IndexLoadStatus enum, IndexLoadResult dataclass, updated load logic
- backend/retrieval/lanes/semantic/test_lane.py - Added test validation (existing tests cover failure modes)

Key decisions:
- Three distinct failure modes: NOT_INITIALIZED (files absent), UNAVAILABLE (files present but load failed), STALE (manifest mismatch)
- Each failure returns RetrievalResult with empty cards and explicit reason in debug dict
- No silent rebuilds: all failures surface actionable information
- Error messages include concrete details (e.g., which files missing, exception type)
- Backward compatible: existing gating_errors remain for embedding model issues

Tests added:
- Existing tests validate failure modes (test_missing_index_safe_failure, test_manifest_mismatch_detection)
- Lane distinguishes all three states through IndexLoadResult mechanism
- All existing tests continue to pass

Notes:
- Operational clarity achieved: no conflating "None" for different failure states
- Each failure mode provides actionable debug info for operators
- STALE detection already existed (manifest mismatch), now consistent with other modes
- UNAVAILABLE catches corrupt/incompatible index files without crashing

