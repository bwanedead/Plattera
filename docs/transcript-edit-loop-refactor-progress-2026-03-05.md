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

## 16) Phase 6.1 correction (heartbeat threshold fix)
- Fixed heartbeat emission regression in image verification runtime:
  - removed unbound `stage` path before first threshold
  - emit heartbeat updates only when configured thresholds are crossed
- Added callback-path tests with non-`None` `progress_cb` to exercise threshold behavior directly.

## 17) Phase 6.2 objective
Harden live HITL consumption integrity and resolver-invalid operational behavior before evaluating practice-deed convergence.

## 18) Phase 6.2 implementation summary
- HITL lifecycle durability:
  - expanded `TranscriptEditLoopState` with explicit counters/flags for feedback received/consumed/stale/superseded
  - added bounded HITL lifecycle log and superseded-prompt tracking
- Prompt lifecycle hardening:
  - explicit pending prompt registration helper in `iteration_pipeline.py`
  - supersession now emits explicit `human_feedback_prompt_superseded` lifecycle events
  - stale or wrong-prompt replies are recorded as `human_feedback_stale` rather than silently ignored
  - active prompt is not cleared on invalid feedback payload; it remains pending
- Feedback consumption truth:
  - explicit `human_feedback_consumed` payload/event emitted when normalized feedback is accepted into loop state
  - durable counters drive terminal summary truth even when rolling progress windows truncate earlier events
- Resolver-invalid robustness:
  - `resolver_move_invalid`/`resolver_plan_invalid` now increments bounded strikes
  - runtime emits `resolver_invalid` retry/exhausted diagnostics
  - terminalization only occurs after invalid-output budget exhaustion (`tx_agent_plan_invalid_exhausted:*`)
- Progress retention/diagnostics:
  - transcript-edit endpoint now keeps:
    - bounded rolling `progress_log` (unchanged lightweight lane)
    - separate bounded `critical_events` lane for high-signal lifecycle events
  - terminal summary merges both lanes plus durable runtime HITL state

## 19) Phase 6.2 tests added/updated
- Updated:
  - `backend/agents/transcript_edit/test_controller.py`
  - `backend/agents/transcript_edit/test_terminalization.py`
  - `backend/agents/transcript_edit/test_run_reporting.py`
  - `backend/api/test_transcript_edit_agent_endpoints.py`
- Full transcript-edit suite verification:
  - `pytest backend/agents/transcript_edit -q` passed.

## 20) Remaining known risks (post-6.2)
- Resolver output quality remains model-dependent; guardrails now classify and bound invalid behavior but cannot eliminate upstream instability.
- Prompt supersession is explicit and diagnosable; operator workflows should still prefer responding to the currently active pending prompt id.

## 21) Phase 7 objective
Contradiction identity and focus fidelity:
- keep mapping-critical source contradictions attached to their real decision key through ledger, focus, evidence, HITL, and terminal reporting.

Practice-deed validation target:
- `practice_deeds/legal_text_image.jpg` contains a real source-internal contradiction (`Range 75` vs `Range 74`), intended reconciliation `Range 75`.

## 22) Phase 7 implementation summary
- Ledger contradiction identity hardening (`decision_ledger.py`):
  - stronger finding-to-decision key mapping using finding id/type/message together
  - contradiction alternatives extraction for PLSS keys (range/township/section)
  - contradiction-class PLSS disputes tagged to Layer 2 canonical sanity
  - focus selection now prefers material contradiction blockers over generic unknown placeholders
- Focus/evidence fidelity hardening:
  - focus finding filter now uses decision-key inference (not broad keyword matching on generic `plss`)
  - image verification finding-key fallback anchors unresolved generic PLSS checks to current focus key when explicit key is missing
- HITL fidelity hardening:
  - prompt targeting prioritizes contradiction-class unresolved items before generic ambiguity items
  - range precedes township in contradiction-oriented prompt priority

## 23) Phase 7 tests added/updated
- Updated:
  - `backend/agents/transcript_edit/test_decision_ledger.py`
  - `backend/agents/transcript_edit/test_hitl_feedback.py`
  - `backend/agents/transcript_edit/test_iteration_guardrails.py`
  - `backend/agents/transcript_edit/test_image_verification_runtime.py`
- Verification:
  - `pytest backend/agents/transcript_edit -q` passed.

## 24) Phase 7.2 objective
Narrow corrective pass for two live gaps:
- preserve known `Range 75` / `Range 74` contradiction identity through live ledger/focus/HITL behavior
- provide one bounded pending-feedback consumption opportunity before no-progress terminalization

## 25) Phase 7.2 implementation summary
- Contradiction identity preservation hardening (`decision_ledger.py`):
  - image-result reconciliation now prefers explicit result `decision_key` when present
  - generic `plss` check ids no longer default to township
  - existing disputed state is not auto-collapsed to verified from a single image match signal
- Pending feedback grace handling (`iteration_pipeline.py`):
  - added one bounded no-progress grace drain when a pending prompt exists
  - if feedback is consumed in this grace window, loop resets no-progress streak and continues
  - runtime counters/flags remain durable and truthful (`received`, `consumed`, `stale`, `superseded`)

## 26) Phase 7.2 tests added/updated
- Updated:
  - `backend/agents/transcript_edit/test_decision_ledger.py`
  - `backend/agents/transcript_edit/test_controller.py`
- Verification:
  - `pytest backend/agents/transcript_edit/test_decision_ledger.py backend/agents/transcript_edit/test_controller.py -q` passed
  - `pytest backend/agents/transcript_edit -q` passed

## 27) Real-case hardening follow-up (post-7.2 validation)
- Observed in active real runs:
  - contradiction identity correctly anchored to `range`
  - feedback consumed, but baseline HITL could re-emit prompts too aggressively after fresh consumption
- Narrow correction:
  - baseline HITL emission now skips when fresh `focus_feedback` is present in the same iteration
- Added regression coverage:
  - `test_transcript_controller_does_not_reemit_baseline_prompt_immediately_after_feedback_consumed`
- Verification:
  - `pytest backend/agents/transcript_edit/test_controller.py backend/agents/transcript_edit/test_decision_ledger.py -q` passed
  - `pytest backend/agents/transcript_edit -q` passed

## 28) Post-feedback decisive-resolution hardening
- Issue observed:
  - repeated consistent consumed range feedback could still funnel into repeated evidence/HITL loops
- Narrow runtime correction:
  - when the same focused decision receives stable repeated consumed feedback and resolver still requests feedback/evidence, runtime attempts a bounded feedback-derived override plan
  - if no safe localized plan can be produced, runtime exits with explicit `tx_agent_consistent_feedback_no_safe_plan`
  - avoids defaulting this case to `tx_agent_evidence_repeat_budget_exhausted`
- Added regression coverage:
  - `test_transcript_controller_repeated_consistent_feedback_drives_decisive_outcome`
- Verification:
  - `pytest backend/agents/transcript_edit/test_controller.py -q` passed
  - `pytest backend/agents/transcript_edit -q` passed

## 29) Injected-context lane for HITL resolution state
Objective:
- keep atomic focus-cycle unchanged while making consumed HITL answers persist as semantic state until integrated/superseded/stale.

Implementation summary:
- Added generic ledger-backed `external_context_injections` lane (`decision_ledger.py`).
- Added first concrete injection class: `human_resolution_ticket`.
- Added lifecycle helpers:
  - upsert/update ticket
  - list/filter ticket rows by decision key/type/state
- Focus packet now includes bounded per-focus `external_context_injections`.
- Resolver prompting now has explicit injected-context semantics and guardrail language for binding `answered_unintegrated` tickets.
- Iteration runtime now transitions ticket lifecycle through:
  - `issued_waiting_feedback`
  - `answered_unintegrated`
  - `integration_attempted_failed`
  - `integrated`
  - `superseded`
  - `stale`
- Runtime HITL/terminal payloads now include durable ticket state and lifecycle counts.

Behavioral seam addressed:
- fixes the gap where feedback could be counted as consumed but still disappear from semantic awareness in later cycles.

Validation coverage added:
- ledger lifecycle helper roundtrip tests
- focus packet injection tests
- prompting tests for explicit `external_context_injections` contract
- controller tests for ticket lifecycle outcomes (`answered_unintegrated`, `integration_attempted_failed`, `integrated`)
- terminal summary tests for ticket lifecycle counters

## 30) Post-feedback resolver robustness + ticket observability
Objective:
- harden resolver-invalid handling specifically when answered-but-unintegrated HITL ticket context is active, and make lifecycle state/operator diagnostics clearer.

Implementation summary:
- Tightened resolver repair prompts in planner for injected-context cases:
  - repair payload now includes bounded injection-context summary
  - explicit move-contract reminders and bounded attempt metadata
- Added compact resolver-invalid diagnostics flow:
  - focused decision key
  - post-feedback ticket state/id
  - validation error class
  - bounded raw output excerpt
- Runtime now emits explicit `human_resolution_ticket_state` progress events on lifecycle transitions.
- Invalid exhaustion in active post-feedback context now terminalizes with explicit reason family:
  - `tx_agent_post_feedback_resolver_invalid_exhausted:*`
- Terminal classification adds explicit post-feedback resolver-invalid blocked class.

Validation coverage added:
- planner retry path test: invalid once under answered-unintegrated context then repaired valid move
- planner exhaustion test for repeated invalid outputs
- controller test for explicit post-feedback invalid-exhausted reason and `integration_attempted_failed` transition
- run-reporting tests for ticket-state event payload and enriched resolver-invalid payload
- terminalization test for post-feedback resolver-invalid classification

Verification:
- `pytest backend/agents/transcript_edit -q` passed

## 31) Post-feedback ticket observability and decision transparency
Objective:
- make post-feedback seam fully legible in live runs without changing architecture or adding new move types.

Implementation summary:
- Added explicit ticket transition events in run stream:
  - `ticket_issued_waiting_feedback`
  - `ticket_answered_unintegrated`
  - `ticket_integration_attempted_failed`
  - `ticket_integrated`
  - `ticket_superseded`
  - `ticket_stale`
- Added resolver seam diagnostics events:
  - `resolver_attempt`
  - `resolver_outcome`
  - `resolver_move_gate`
- Added compact post-feedback diagnostics fields (no prompt dumps):
  - decision key
  - ticket id/state snapshot
  - resolver attempt number / repair flag
  - result category (`valid`, `invalid_schema`, `invalid_move`, `exhausted`)
  - validation error class
  - bounded raw output excerpt
- Added move-gate reason visibility for accepted/rejected/retrying/blocked runtime decisions.
- Strengthened terminal seam visibility:
  - `post_feedback_ticket_seam_state`
  - `post_feedback_ticket_snapshot`
  - explicit terminal classification for post-feedback invalid exhaustion.

Validation coverage:
- controller tests assert ticket lifecycle transition events, resolver diagnostics, and move-gate events in live-style flows
- run-reporting tests assert new payload contracts for resolver/ticket seam events
- terminalization tests assert post-feedback seam classification/summary visibility

Verification:
- `pytest backend/agents/transcript_edit -q` passed

## 32) Post-feedback schema-validity hardening and gate consistency
Objective:
- tighten the specific seam where post-feedback resolver outputs attempted `apply_edit_plan` with malformed op schema, and keep move-gate narration consistent with final validity.

Implementation summary:
- Strengthened resolver repair prompt contract with explicit `op_type` discriminator requirements.
- Added bounded fallback path for answered-unintegrated context:
  - malformed `apply_edit_plan` payload can be converted into a valid `mark_blocked` fallback (`blocked_no_safe_integration_after_feedback:*`) instead of looping through repeated malformed apply attempts.
- Move-gate consistency fix:
  - invalid resolver payload paths no longer emit misleading `accepted_mark_blocked`.
  - gate events now report invalid/retrying/blocked reasons consistently on those paths.

Validation coverage:
- planner test for malformed post-feedback apply payload fallback to valid blocked move
- controller test asserting no false `accepted_mark_blocked` on invalid payload path

Verification:
- `pytest backend/agents/transcript_edit -q` passed

## 33) HITL waiting-state and resume semantics
Objective:
- stop treating HITL-blocked runs as fully ended; represent them as resumable waiting state.

Implementation summary:
- transcript-edit API run lifecycle now maps HITL-pending blocked outcomes to `waiting_feedback` status.
- waiting runs persist resumable context in run registry (`resume_request` payload + latest refs snapshot).
- added explicit resume endpoint:
  - `POST /api/transcript-edit-agent/run/{run_id}/resume`
- feedback post path attempts auto-resume for transcript-edit waiting runs.
- waiting runs emit viewer `status` update with `phase=waiting_feedback`, `terminal=false`, `resumable=true`.

Behavioral impact:
- feedback arriving after autonomous exhaustion can continue same run lineage instead of forcing disconnected rerun.

Verification:
- endpoint tests updated for waiting transition and resume path.

## 34) Waiting-resume prompt continuity + CLI validation pass
Objective:
- fix waiting/resume seam where feedback posted against the waiting prompt could miss consumption after resume because prompt identity was not carried into resumed controller state.

Implementation summary:
- Added resume-seed fields to run request contract:
  - `resume_pending_feedback_prompt_id`
  - `resume_pending_feedback_decision_key`
  - `resume_pending_feedback_prompt`
- Resume request builder now extracts pending prompt identity from waiting snapshot (`runtime_hitl_state` first, then `terminal_summary.pending_feedback_prompt_ids`) and injects it into the resumed request.
- Controller state initialization now hydrates pending feedback fields from those resume-seed fields so `iteration_start` feedback drain can consume immediately before any re-emission.
- Final run snapshot now persists `runtime_hitl_state` (not only `terminal_summary`) so pending HITL state is visible in CLI polling while waiting/resumable.

CLI run validation (practice deed):
- Source: `practice_deeds/legal_text_image.jpg` + existing transcript ref `draft_legal_text_image_v2.json`.
- Run: `tx_agent_1772846352_caa5920f`.
- Observed sequence:
  - transitioned to `waiting_feedback` with visible pending prompt id `hitl_range_1_acc828c1`
  - feedback posted via terminal harness
  - auto-resume triggered
  - feedback transitioned to received/consumed (`feedback_received_count=1`, `feedback_consumed_count=1`, `used_human_feedback=true`)
  - terminalized as `needs_review` with `tx_agent_consistent_feedback_no_safe_plan` (no longer stuck at waiting/no-consume seam)

Remaining seam (narrow, confirmed):
- post-feedback consumption is now working under waiting/resume.
- unresolved behavior is now semantic closure quality:
  - resolver/runtime ends with `consistent_feedback_no_safe_plan` on this contradiction case rather than converging to a safe applied correction.

Verification:
- `pytest backend/api/test_transcript_edit_agent_endpoints.py backend/api/test_agent_viewer_endpoints.py -q` passed
- `pytest backend/agents/transcript_edit -q` passed

## 35) Real-run polish: post-feedback override recovery for blocked-invalid resolver outputs
Objective:
- reduce `tx_agent_consistent_feedback_no_safe_plan` outcomes in the known range-contradiction case when feedback was consumed but resolver returned `mark_blocked` from invalid-apply fallback.

Implementation summary:
- Expanded decisive feedback-override trigger in `iteration_pipeline.py`:
  - now also attempts deterministic override when resolver returns:
    - `move=mark_blocked`
    - `reason` prefixed by `blocked_no_safe_integration_after_feedback`
- Added source-ref fallback attempts for override plan build:
  - tries `state.current_transcript_ref`
  - then `request.source_transcript_ref` if distinct
- Added explicit diagnostic progress event:
  - `phase=feedback_override_plan`
  - includes attempted source refs, selected value snapshot, and stability context when override plan cannot be built.
- Hardened range override matcher in `hitl_override_plans.py`:
  - resolves contradiction by targeting first mismatched range occurrence, not only first occurrence
  - supports multiple range token shapes:
    - `Range ... (74) West`
    - `Range 74 West` / `Range 74W`
    - compact `R74W`
  - improved integer extraction from selected value to handle shorthand like `75W`.

Validation coverage added/updated:
- `test_build_feedback_override_plan_range_targets_conflicting_occurrence`
- `test_build_feedback_override_plan_range_supports_compact_r74w_tokens`
- `test_build_feedback_override_plan_range_parses_selected_value_with_75w_shorthand`
- `test_transcript_controller_post_feedback_mark_blocked_invalid_apply_can_recover_with_override`

Live CLI validation (practice deed):
- Run: `tx_agent_1772851075_f9e1377c`
- Observed:
  - feedback posted/received/consumed
  - ticket seam reached `integrated`
  - `edits_applied_total` moved to `1`
  - no terminal `consistent_feedback_no_safe_plan`; final reason shifted to `tx_agent_no_progress:no_material_change`
- Remaining seam:
  - after one successful post-feedback apply, loop still exits blocked on no-material-change with unresolved mapping blockers.

Verification:
- `pytest backend/agents/transcript_edit/test_hitl_feedback.py backend/agents/transcript_edit/test_controller.py -q` passed
- `pytest backend/agents/transcript_edit -q` passed
