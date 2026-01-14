# Notes — Yellow Zone Audit and Gaps

## Context
This run follows the successful completion of `2026-01-12__semantic-index-polish` which implemented 8 stories (S1-S8) hardening the semantic retrieval system.

## Yellow Zone Brief (Original 10 Points)

The following 10 points were identified as critical "yellow zone" items to verify before proceeding to the next phase (hybrid fusion, reranking, agent loop):

1. **Retrieval-time evidence should be readable, not just a locator**
   - Semantic results should include deterministic excerpt/preview
   - Intent: "why this matched" visibility for triage

2. **Retrieval vs reading separation must be explicit and clean**
   - Retrieval-time: lightweight, find candidates, return stable pointers + excerpts
   - Reading-time: expensive, hydrate full entry on demand
   - Intent: retrieve → decide → expand pattern

3. **Manifest must be "truth," not a theoretical file**
   - Builder writes/updates manifest during successful indexing
   - Lane checks manifest during query
   - Intent: detect "index no longer matches reality" explicitly

4. **Model identity semantics must be consistent (no false staleness)**
   - Manifest stores and lane compares same identity concept
   - Intent: avoid friendly name vs revision SHA mismatches

5. **Index load failure modes must be operationally unambiguous**
   - Distinguish: not initialized vs can't load vs stale
   - Intent: app/agent loop needs to know failure type to respond correctly

6. **Updates must be safe and deterministic under real workloads**
   - Upsert/update doesn't rely on brittle HNSW assumptions
   - Intent: new truth replaces old truth cleanly

7. **Tombstones are acceptable short-term, but we need a cleanup story**
   - Deleted vectors shouldn't accumulate unbounded
   - Intent: defined strategy for when/why to compact

8. **HNSW tests must be reliable and not silently skipped**
   - Keep coverage without flaky CI or mysterious crashes
   - Intent: explicit test isolation strategy

9. **Hydration fidelity for FINAL_SEGMENTS must be complete**
   - Semantic hits carry enough metadata to reconstruct CorpusEntryRef
   - Intent: reliably re-open authoritative text from any hit

10. **"Why this matched" trace should be standardized and stable**
    - Consistent provenance: distance, pool, model, policy, dimension
    - Intent: debugging, evaluation, reranking support

## Initial Sanity Check Results

**8 out of 10 points: COMPLETE** (from semantic-index-polish run)
- Points 1, 2, 3, 5, 6, 8, 9, 10: Fully implemented and tested

**2 points: Need documentation/strategy**
- Point 4 (model identity): Uses friendly names consistently, but decision not explicitly documented
- Point 7 (tombstone compaction): Strategy not documented (when/how to compact)

## Run Goals
1. Formally audit all 10 points with evidence (file paths, line numbers)
2. Document model identity decision and rationale
3. Document tombstone compaction strategy
4. Verify all points are satisfied before next phase

## References
- Previous run: `ralph/runs/2026-01-12__semantic-index-polish/`
- Summary of S1-S8: `ralph/runs/2026-01-12__semantic-index-polish/SUMMARY.md`
- Semantic lane code: `backend/retrieval/lanes/semantic/`
- Read service: `backend/retrieval/read_service.py`
