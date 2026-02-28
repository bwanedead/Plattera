# Transcription Edit Loop Spec v0

## Scope
- Canonical contract for typed edit plans and deterministic apply semantics.
- Python-first implementation with Pydantic models in `backend/transcription_edit_loop/contracts.py`.

## Design
- Canonical source of truth: Pydantic models.
- JSON schema is derived from models when needed.
- Drift safety is enforced at two levels:
1. Root-level source transcript hash.
2. Per-op expected old excerpt/hash checks.

## Models
- `EditLoopStartRequestV0`
  - Flexible entry surface:
    - `source_transcript_ref` OR `source_text` (exactly one required)
    - optional `source_image_refs`
    - `mode`: `audit_only | repair | repair_then_promote`
- `CanonicalTranscriptInputV0`
  - Materialized canonical text + source hash used by loop internals.
- `EditPlanV0`
  - Required fields:
    - `source_transcript_ref`
    - `source_transcript_hash`
    - `ops[]`
    - `plan_id`, `summary`
  - Includes:
    - `plan_fingerprint` (deterministic hash over plan payload excluding fingerprint field)
- `EditOpV0` union
  - Supported op types:
    - `replace_span`
    - `replace_line`
    - `replace_clause`
    - `rewrite_section`
  - v0 semantics note:
    - all four op types currently use the same replacement apply primitive.
    - op type is still captured for policy/review/routing.
  - Shared metadata:
    - `change_class`: `normalization | semantic | structural`
    - `confidence`: `low | medium | high`
    - `review_required`
    - `reason`, `evidence_refs`
    - `target` locator
    - `expected_old` drift contract
- `LocatorV0` union
  - `anchors` (preferred): `start_anchor`, `end_anchor`, `occurrence`
  - `offsets` (fallback): `start_char`, `end_char`
- `ApplyReportV0`
  - Deterministic apply output including:
    - root status/reason
    - per-op status/reasons
    - output transcript text/hash

## Hashing
- Transcript hash: exact UTF-8 bytes of canonical transcript text.
- Plan fingerprint: SHA256 over canonical JSON (`sort_keys=True`, compact separators, UTF-8).

## Apply Semantics
`apply_plan(plan, transcript_text)` runs in this order:
1. Compute current transcript hash.
2. Reject plan if hash differs from `plan.source_transcript_hash`.
3. For each op in order:
   - resolve locator span
   - verify `expected_old.old_excerpt` is present in resolved span
   - if `expected_old.old_hash` exists, verify it
   - apply replacement
4. Return `ApplyReportV0`.

Failure reason codes used by apply:
- Root:
  - `source_transcript_hash_mismatch`
- Per-op:
  - `root_hash_mismatch`
  - `locator_not_found`
  - `drift_mismatch`
  - `old_hash_mismatch`
  - `cross_section_edit_not_supported` (section-preserving apply path)

## Bootstrap Normalization
`materialize_canonical_input(request)` supports:
- Direct text (`source_text`) -> `inline://source_text` canonical source ref.
- Artifact reference (`source_transcript_ref`) that resolves JSON payloads with:
  - top-level `text`, or
  - `sections[].body` / `sections[].text` (joined with blank lines).

## Section-Preserving Output (RAG compatibility)
- Persisted edited transcript artifacts should remain section-based:
  - `{"sections":[{"id":"...","body":"..."}], ...}`
- The adapter path uses:
  - `sections_to_text_with_index_map()` for deterministic text view + section spans
  - `apply_plan_to_sections()` for safe writeback into section bodies
- v0 currently refuses edits that cross section boundaries in one operation.

## Promotion Policy (v0 Target)
- Auto-apply can be allowed when:
  - all ops are `normalization`
  - confidence is `high`
  - no review required flags
  - post-apply validators pass
- Otherwise require review before promotion.

## Current Implementation
- Contracts: `backend/transcription_edit_loop/contracts.py`
- Apply engine: `backend/transcription_edit_loop/apply.py`
- Section adapter: `backend/transcription_edit_loop/section_adapter.py`
- Persistence: `backend/transcription_edit_loop/persistence.py`
- Validators scaffold: `backend/transcription_edit_loop/validators.py`
- Run service: `backend/transcription_edit_loop/run_service.py`
- Tests: `backend/transcription_edit_loop/tests/test_apply.py`
- Tests: `backend/transcription_edit_loop/tests/test_sections_and_run.py`
