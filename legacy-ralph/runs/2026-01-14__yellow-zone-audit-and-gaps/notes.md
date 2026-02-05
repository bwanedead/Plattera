# Notes — Yellow Zone Final Hardening

## Context
This run follows the successful completion of `2026-01-12__semantic-index-polish` which implemented 8 stories (S1-S8) hardening the semantic retrieval system.

## Yellow Zone Brief (Original 10 Points)

The following 10 points were identified as critical "yellow zone" items before proceeding to the next phase:

1. **Retrieval-time evidence readable** - ✅ COMPLETE (S1 from semantic-index-polish)
2. **Retrieval vs reading separation** - ✅ COMPLETE (S3 from semantic-index-polish)
3. **Manifest must be truth** - ✅ COMPLETE (S4 from semantic-index-polish)
4. **Model identity semantics consistent** - ⚠️ PARTIAL (uses friendly names, needs fingerprint tracking)
5. **Index load failure modes explicit** - ✅ COMPLETE (S5 from semantic-index-polish)
6. **Updates safe and deterministic** - ✅ COMPLETE (S6 from semantic-index-polish)
7. **Tombstone cleanup story** - ❌ MISSING (no stats API, no compaction, no strategy)
8. **HNSW tests reliable** - ✅ COMPLETE (S7 from semantic-index-polish)
9. **Hydration fidelity FINAL_SEGMENTS** - ✅ COMPLETE (S2 from semantic-index-polish)
10. **"Why this matched" trace** - ✅ COMPLETE (S8 from semantic-index-polish)

## Analysis: What Needs Implementation

**8 out of 10 points are COMPLETE** from previous run.

**2 points need actual implementation:**

### Point 7: Tombstone Compaction (3 stories)
Currently, tombstones accumulate indefinitely with no cleanup mechanism.

**Need to implement:**
- S1: Stats API - `get_stats()` method to monitor tombstone accumulation
- S2: Compaction - `compact()` method to rebuild index without tombstones
- S3: Strategy - `should_compact()` helper + documentation

### Point 4: Model Fingerprint Tracking (1 story)
Currently uses friendly names only (e.g., "all-MiniLM-L6-v2").

**Need to implement:**
- S4: Fingerprint field in manifest + computation + staleness check

## Run Goal
Implement the missing functionality to fully satisfy all 10 yellow-zone points, with:
- Deterministic acceptance criteria
- Comprehensive tests
- Safe implementations (no data loss)
- Clear documentation

## References
- Previous run: `ralph/runs/2026-01-12__semantic-index-polish/`
- Summary of S1-S8: `ralph/runs/2026-01-12__semantic-index-polish/SUMMARY.md`
- Semantic lane code: `backend/retrieval/lanes/semantic/`
- Read service: `backend/retrieval/read_service.py`
