# Follow-On Summary — Post-Review Improvements

## Context

After completing the main Ralph run (S1-S5), a review agent analyzed the SUMMARY.md and identified one valid gap that warranted immediate attention before declaring the yellow-zone complete.

## Review Agent Critique Assessment

The review agent raised several points:

**A) SQLite schema upgrades/migrations** ✅ VALID GAP - Addressed in this follow-on
**B) Compaction is manual-only** ⚠️ DOCUMENTED LIMITATION - Not a gap, intentional design
**C) Fingerprint definition limitations** ⚠️ DOCUMENTED LIMITATION - Not a gap, operational fingerprint is sufficient
**D) Orchestration layer missing** ⚠️ FUTURE PHASE - Not in scope for yellow-zone hardening

### Valid Gap Identified: Schema Version Mismatch Detection

**Problem:** The metadata store declared `METADATA_SCHEMA_VERSION = 3` and tracked it in the `schema_version` table, but did NOT check for mismatches when opening existing databases. This meant:
- Schema version was written on first DB creation
- But if code evolved and schema changed, existing DBs would silently use old schema
- This is a footgun: silent schema corruption instead of explicit failure

**Review agent was correct:** This gap needed addressing to prevent future pain when schema evolves.

---

## What Was Implemented (Follow-On)

### Schema Version Mismatch Detection

**File:** `backend/retrieval/lanes/semantic/metadata_store.py`

**Change:** Enhanced `_ensure_schema()` method (lines 141-157) to check schema version compatibility:

```python
# Check schema version compatibility
cursor.execute("SELECT version FROM schema_version LIMIT 1")
row = cursor.fetchone()
if row is None:
    # New DB: insert current schema version
    cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (METADATA_SCHEMA_VERSION,))
else:
    # Existing DB: verify schema version matches
    existing_version = row[0]
    if existing_version != METADATA_SCHEMA_VERSION:
        raise RuntimeError(
            f"Metadata store schema version mismatch: "
            f"database has version {existing_version}, "
            f"but code expects version {METADATA_SCHEMA_VERSION}. "
            f"Rebuild the index or downgrade code to match DB version."
        )
```

**Behavior:**
- ✅ **New databases:** Insert current schema version (as before)
- ✅ **Existing databases with matching version:** Continue normally
- ✅ **Existing databases with mismatched version:** Fail fast with clear error message

**Error Message Includes:**
- Detected version in database
- Expected version in code
- Actionable remediation: "rebuild the index or downgrade code"

### Test Coverage

**File:** `backend/retrieval/lanes/semantic/test_metadata_store.py`

**Test:** `test_schema_version_mismatch_detection()`

**What it validates:**
- Creates DB with old schema version (version 2)
- Attempts to open with current code (expects version 3)
- Verifies RuntimeError is raised
- Validates error message contains:
  - "schema version mismatch"
  - "database has version 2"
  - "code expects version 3"
  - "rebuild"

---

## Impact Assessment

### What This Fixes

**Before:**
- Schema version tracked but not enforced
- Code evolution → silent schema mismatch → undefined behavior
- Debugging nightmare when fields missing/wrong type

**After:**
- Schema version explicitly enforced
- Mismatch → immediate failure with actionable error
- Prevents silent corruption

### What This Doesn't Implement (Intentional)

**Not implemented: Automatic migrations**
- Reason: Migrations add complexity and risk
- Current approach: Explicit failure + rebuild requirement
- Future: Can add migrations if needed, but explicit failure is safer starting point

**Not implemented: Schema version in manifest**
- Reason: Manifest and metadata DB are separate concerns
- Manifest tracks index identity (model, policy, pool)
- Metadata DB schema is orthogonal

### Backward Compatibility

**Existing indexes (schema version 3):** ✅ Continue working normally
**Old indexes (schema version < 3):** ⚠️ Will fail with clear error, require rebuild

This is **intentional breaking behavior** for safety - better to fail explicitly than corrupt silently.

---

## Review Agent Critiques Not Addressed (And Why)

### B) Compaction is manual-only

**Status:** Documented as known limitation in main SUMMARY.md

**Why not addressed:**
- Manual trigger is intentional for this phase
- Orchestration layer (agent commands, UI triggers, background jobs) is **next phase work**
- We have the primitives: `get_stats()`, `should_compact()`, `compact()`
- Caller/orchestrator is deliberately out of scope

### C) Fingerprint definition (manifest hash, not model file checksums)

**Status:** Documented as known limitation in main SUMMARY.md

**Why not addressed:**
- Current fingerprint (asset_id + manifest hash) is **good enough** for operational staleness detection
- Cryptographic model file checksums would be stronger but add complexity
- Can be improved later if needed
- Not a correctness gap, just a "stronger would be better" observation

### D) Orchestration layer (when to build/rebuild/compact)

**Status:** Explicitly future phase work

**Why not addressed:**
- This is **agent orchestration loop** work (the next major phase)
- Current scope: build solid primitives
- Next scope: agent loop that calls those primitives
- Review agent correctly identified this as "next wave" not "gap"

---

## Final Yellow-Zone Status

### All 10 Points + Schema Mismatch Detection

1. ✅ Retrieval-time evidence readable
2. ✅ Retrieval vs reading separation
3. ✅ Manifest is truth
4. ✅ Model identity consistent (fingerprints)
5. ✅ Index load failure modes unambiguous
6. ✅ Updates safe and deterministic
7. ✅ Tombstone cleanup strategy complete
8. ✅ HNSW tests reliable
9. ✅ Hydration fidelity complete
10. ✅ Provenance trace standardized
11. ✅ **Schema version mismatch detection** (follow-on)

### Production Readiness

**All yellow-zone correctness points are complete**, including the schema mismatch footgun fix.

The semantic retrieval foundation is now:
- ✅ Solid and well-tested
- ✅ Safe from silent schema corruption
- ✅ Ready for next phase (hybrid fusion, reranking, agent orchestration)

---

## Files Changed (Follow-On)

**Modified:**
- `backend/retrieval/lanes/semantic/metadata_store.py` - Added schema version mismatch check
- `backend/retrieval/lanes/semantic/test_metadata_store.py` - Added mismatch detection test

**Lines of code:**
- Implementation: ~15 lines (error detection + message)
- Test: ~40 lines (setup old DB + validate error)

---

## Commits

**Main run commits:** S1 through S5 (5 commits)
**Follow-on commit:** 1 commit (schema mismatch detection)

**Total commits this branch:** 6 functional commits + run state updates

---

## Next Steps (Unchanged)

The next phase remains:
1. Hybrid retrieval fusion (lexical + semantic lanes)
2. Reranking/verification
3. Agent orchestration loop (maintenance controller)
4. Evaluation framework

The yellow-zone is now **fully hardened** and ready to support those next layers.
