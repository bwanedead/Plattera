# Follow-up Issues — 2026-01-14__true-hybrid-rag

Post-completion code review identified yellow-zone footguns requiring cleanup.

---

## Critical Bugs (must fix)

### Issue 1: Rerank ordering is being undone 🔴

**Location**: `backend/retrieval/engine/retrieval_engine.py:163`

**Problem**: After rerank reorders cards, we immediately call `sort_by_score()`, which undoes the rerank.

```python
# Current (WRONG):
if rerank_enabled:
    cards = self.rerank_lane.rerank(query, cards)
    # ... debug annotations ...

cards = sort_by_score(dedupe_by_id(cards))  # <-- UNDOES RERANK!
```

**Why it's wrong**: Rerank's job is to be the final ordering authority. If we sort by score after rerank, we're throwing away the rerank's decision.

**Fix**: Only sort when rerank is disabled; when rerank is enabled, preserve its ordering.

**Test needed**: Verify rerank ordering is preserved (fake rerank that reverses list, assert final order matches)

**Status**: ✅ FIXED - See commit b8ab318

---

## Should Fix (order preservation)

### Issue 2: dedupe_by_id should explicitly preserve order

**Location**: `backend/retrieval/engine/merge.py:37-42`

**Problem**: Uses `dict.values()` which relies on Python 3.7+ insertion order guarantee. Works but not explicit.

```python
# Current (works but implicit):
def dedupe_by_id(cards: List[EvidenceCard]) -> List[EvidenceCard]:
    seen: Dict[str, EvidenceCard] = {}
    for c in cards:
        if c.id not in seen:
            seen[c.id] = c
    return list(seen.values())  # Order preserved in 3.7+ but not obvious
```

**Fix**: Use explicit list append to make order preservation obvious.

**Status**: ✅ FIXED - See commit b8ab318

---

## Design Decisions Documented (not bugs)

### Design Choice 1: Fusion dedupe is interleaving, not cross-lane deduplication

**Current behavior**: Lexical and semantic card IDs never collide (different prefixes), so fusion doesn't actually dedupe across lanes.

**Is this a problem?** No - it's a reasonable v0 design.

**Alternatives considered**:
- Add `stable_id` field for cross-lane deduplication
- Keep per-lane provenance but merge same underlying evidence

**Decision**: Accept current behavior for v0. Same evidence from different lanes stays separate, preserving provenance clarity.

**Status**: Documented only, no change needed

---

### Design Choice 2: Score commensurability (lexical vs semantic ranges)

**Current behavior**:
- Lexical scores: [0.5, 1.0] (from S6 density + position scoring)
- Semantic scores: [-1.0, 1.0] (cosine similarity, typically 0.2-0.9)

**Effect**: Strong semantic (0.8+) beats all lexical, weak semantic (0.2-0.4) ranks below all lexical.

**Is this a problem?** No - it may actually be desirable (weak semantic is often noise).

**Alternatives considered**:
- Normalize per-lane scores to [0, 1] before fusion
- Use lane order as primary, score as secondary
- Let rerank be the final authority

**Decision**: Accept current behavior for v0. Let rerank handle final ordering. Can add normalization later if live retrieval feels wrong.

**Status**: Documented only, no change needed

---

## Tests to Add

### Test 1: Rerank ordering preservation 🔴 CRITICAL

**What**: Verify that when rerank is enabled, its ordering is final and not undone by subsequent sorting.

**Implementation**:
- Create fake rerank lane that reverses card order
- Verify final output matches reversed order
- Verify pre-rerank and post-rerank IDs differ

**Status**: ✅ ADDED - 3 tests in test_rerank_integration.py (commit b8ab318)
- `test_rerank_ordering_is_not_undone_by_subsequent_sort` (CRITICAL)
- `test_rerank_ordering_respects_limit_but_not_score`
- `test_rerank_disabled_allows_score_sorting`

---

### Test 2: Graceful degradation when semantic index missing

**What**: Verify `hybrid_semantic` returns lexical-only results when semantic index is not initialized.

**Implementation**:
- Mock semantic lane to return empty with `reason: "index_not_initialized"`
- Verify lexical results still returned
- Verify debug preserves semantic failure reason

**Status**: ✅ ADDED - test_hybrid_semantic_graceful_degradation_without_index (commit b8ab318)

---

## Fix Summary

| Issue | Priority | Type | Status |
|-------|----------|------|--------|
| Rerank ordering undone | 🔴 Critical | Bug | ✅ FIXED (b8ab318) |
| dedupe_by_id order preservation | 🟡 Should fix | Code clarity | ✅ FIXED (b8ab318) |
| Rerank ordering test | 🔴 Critical | Test gap | ✅ ADDED (b8ab318) |
| Graceful degradation test | 🟡 Should add | Test gap | ✅ ADDED (b8ab318) |
| Fusion dedupe semantics | ℹ️ Info | Design choice | Documented |
| Score commensurability | ℹ️ Info | Design choice | Documented |

---

## Code Investigation Results

### Semantic Lane Graceful Degradation ✅ VERIFIED GOOD

**Investigation**: Checked `LocalSemanticLane.search()` behavior when index missing.

**Result**: Already gracefully degrades - returns empty cards with debug reason, does NOT throw.

```python
if load_result.status == IndexLoadStatus.NOT_INITIALIZED:
    return RetrievalResult(
        query=query,
        cards=[],
        debug={"lane": self.lane_name, "reason": "index_not_initialized", ...}
    )
```

**Conclusion**: `hybrid_semantic` will automatically fall back to lexical-only if semantic index missing.

---

### Semantic Score Range ✅ VERIFIED

**Investigation**: Checked score calculation in `LocalSemanticLane`.

**Finding**:
- Uses HNSW with `space="ip"` (inner product)
- Distance from HNSW ∈ [0, 2] for normalized embeddings
- Score = `1.0 - distance` ∈ [-1, 1]
- Typical real queries: [0.2, 0.9]

**Conclusion**: Score ranges are known and behavior is acceptable for v0.

---

## Next Actions

1. Fix rerank ordering bug (Priority 1)
2. Add rerank ordering preservation test (Priority 1)
3. Make dedupe_by_id order preservation explicit (Priority 2)
4. Add graceful degradation test (Priority 2)

---

## Codex Follow-Up: True hybrid RAG footgun hardening

### What was addressed
- MaintenanceController now reports unimplemented checks/actions explicitly and no longer implies silent success.
- Diagnose checks all index files (manifest/hnsw/metadata) and uses should_compact() for compaction signal.
- Staleness detection compares manifest to a provided RuntimeIndexIdentity (no lane logic duplication).
- COMPACT action executes; BUILD/REBUILD explicitly report missing inventory instead of pretending success.
- Fusion tie-breaks honor semantic lane prefixes (e.g., semantic:local) and dedupe semantics are explicit with optional stable_key_fn.
- Tests updated to avoid HNSW crashes and reflect rerank/limit behavior.

### Files updated
- `backend/retrieval/engine/maintenance_controller.py`
- `backend/retrieval/engine/test_maintenance_controller.py`
- `backend/retrieval/engine/merge.py`
- `backend/retrieval/engine/test_fusion_merge.py`
- `backend/retrieval/engine/test_rerank_integration.py`
- `ralph/runs/2026-01-14__true-hybrid-rag/SUMMARY.md`
- `ralph/runs/2026-01-14__true-hybrid-rag/progress.md`

### Tests run
- `pytest backend/retrieval/engine/ -v`
- `pytest backend/retrieval/tools/ -v`
- `pytest backend/retrieval/lanes/semantic/ -m "not hnsw" -v`
  - Result: all passed (Biopython deprecation warning only).
