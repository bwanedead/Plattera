# Transcript-Edit Loop Refactor Progress

Date: March 5, 2026  
Scope: Phase 4 - Resolver-directed evidence execution + deterministic guardrails

## 1) Accepted baseline chain
1. `29aed1a` transcript-edit: phase1 closure consistency + HITL gating
2. `08b97d7` transcript-edit: phase2 generic HITL override handling (historical/superseded direction)
3. `360e0b2` transcript-edit: pivot to focus-cycle semantic resolver
4. `d144c9a` transcript-edit: phase3 true focus resolver contract

## 2) Phase 4 objective
Make `gather_more_evidence` an executed runtime path and lock deterministic runtime rails so one focus-cycle stays one focused decision item.

## 3) Phase 4 implementation summary
- Added `evidence_executor.py`:
  - typed `evidence_request` normalization (`open_spans`, `image_verify`, `retrieve_dependency_evidence`)
  - deterministic dispatch execution
  - repeat-budget protection per `decision_key + transcript_hash + evidence_kind`
- Hardened `iteration_pipeline.py`:
  - deterministic focus selection with feedback priority bump only when ledger still marks that key unresolved mapping-blocking
  - resolver one-item scope enforcement (`decision_key` mismatch is rejected/downgraded)
  - move acceptance helpers for:
    - `mark_resolved_no_edit`
    - `mark_blocked`
    - `apply_edit_plan`
  - wired `gather_more_evidence` through `evidence_executor` path
  - removed fallback behavior that inferred semantic move from planner plan/no-plan outside resolver move contract
- Hardened `focus_packet.py` with explicit payload budgeting:
  - capped span count/length
  - capped image-result count/length
  - decision-key-scoped attempts only
  - bounded feedback fields and memory summary
- Added key-specific unresolved helper in `decision_ledger.py`:
  - `is_unresolved_mapping_blocking_decision(...)`

## 4) Identity and authority posture
- `decision_key` now remains explicit across focus packet, resolver outcome, evidence request execution, and continuity entries for focused work.
- `closure_update_hint` remains advisory and does not directly mutate authoritative ledger truth.

## 5) Tests added/updated
- Added:
  - `backend/agents/transcript_edit/test_evidence_executor.py`
  - `backend/agents/transcript_edit/test_focus_packet.py`
  - `backend/agents/transcript_edit/test_iteration_guardrails.py`
- Updated:
  - `backend/agents/transcript_edit/test_decision_ledger.py` (key-specific unresolved helper coverage)
  - `backend/agents/transcript_edit/test_controller.py` (closure hint remains advisory)

## 6) Docs updated in-phase
- Updated:
  - `docs/transcript-edit-loop-focus-cycle-architecture-2026-03-05.md`
  - `docs/transcript-edit-loop-orchestration.md`
- Added:
  - `docs/transcript-edit-loop-refactor-progress-2026-03-05.md` (this file)

## 7) Transitional status after Phase 4
- Dependency retrieval execution remains explicit but unsupported until retrieval stage wiring is introduced.
- Resolver quality remains bounded by packet quality and prompting discipline; deterministic guardrails now gate acceptance and execution behavior.

## 8) Phase 5 objective
Prove closed-world convergence behavior and honest terminalization without adding dependency retrieval.

## 9) Phase 5 implementation summary
- Added deterministic convergence helper module:
  - `backend/agents/transcript_edit/progress_evaluation.py`
- Controller now classifies progress from:
  - finding signature
  - mapping-blocking closure signature/count
  - new-signal counters
  - apply->re-audit confirmation gate
- Loop state expanded for convergence tracking:
  - progress reason
  - previous blocking signature/count
  - previous signal counter
  - pending apply re-audit baseline
  - focus stagnation continuity fields
- Iteration pipeline tightened:
  - no-progress reason now includes deterministic subtype
  - image/evidence signals count only when ledger blocking signature materially changes
  - apply marks pending re-audit and baseline blocking count
- Terminal summary now explicitly classifies:
  - `closure_achieved`
  - `optional_quality_remaining_only`
  - `blocked_dependency_evidence_missing`
  - `blocked_human_feedback_needed`
  - `blocked_mapping_ambiguity_unresolved`
  - `blocked_no_safe_autonomous_move`
- Terminal payload now includes:
  - `unresolved_dependency_items`
  - `unresolved_ambiguity_items`
  - `human_feedback_pending`
  - `pending_feedback_prompt_ids`
  - `terminal_classification`

## 10) Dependency stance (explicit)
- Dependency retrieval remains deferred.
- Dependency-bound unresolved mapping blockers are preserved and reported at terminal state; they are not auto-resolved in this phase.

## 11) Phase 5 tests added/updated
- Added:
  - `backend/agents/transcript_edit/test_progress_evaluation.py`
- Updated:
  - `backend/agents/transcript_edit/test_controller.py`
  - `backend/agents/transcript_edit/test_terminalization.py`

## 12) Closed-world milestone claim
Phase 5 establishes the closed-world proof point:
- loop continuation now depends on material progress signals
- apply is not treated as closure progress until re-audit confirms improvement
- terminal outputs distinguish ambiguity blockers, dependency blockers, pending HITL, and optional-only leftovers

## 13) Phase 6 objective
Harden live-run runtime behavior for long evidence phases: focus/evidence coherence, wait-log sanity, bounded retries/timeouts, and clearer call accounting.

## 14) Phase 6 implementation summary
- Added richer evidence progress/result accounting in reporting payloads:
  - `llm_call_seq`, `phase_attempt`, `decision_key`, `evidence_kind`, `check_id`
- Hardened image verification runtime behavior:
  - sparse thresholded wait updates (15/30/60/120s style) instead of frequent heartbeat spam
  - explicit long-running/degraded/timeout/failed stage signaling
  - bounded per-check retries with deterministic failure classification
  - compact diagnostics payload for failures (decision/evidence/check/call/retry/error context)
- Improved focus/evidence coherence visibility:
  - check-level decision key + focus decision key are surfaced
  - focus fallback to broader checks is explicitly logged when no direct focus findings exist
- Preserved architectural boundary:
  - no dependency retrieval expansion
  - no major prompt redesign

## 15) Phase 6 tests added/updated
- Added:
  - `backend/agents/transcript_edit/test_image_verification_runtime.py`
- Updated:
  - `backend/agents/transcript_edit/test_run_reporting.py`
- Full transcript-edit suite remains green after these changes.
