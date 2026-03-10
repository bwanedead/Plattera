# Transcript-Edit Agent Ergonomics Progress Report

Date: 2026-03-10
Owner: coding-agent live validation pass

## Scope
- Goal: controlled live validation of resolver/engine ergonomics seams on the practice legal deed range-contradiction case.
- Scenario:
  - source transcript ref: `dossiers_data/views/transcriptions/6a3a833c-e055-493d-8dd4-06b0f615a151/draft_legal_text_image/raw/draft_legal_text_image_v2.json`
  - image ref: `../practice_deeds/legal_text_image.jpg`
  - dossier: `live-validation-practice-legaltext`

## Run 1 (initial)
- Run ID: `tx_agent_1773139317_3b0f2100`
- Raw capture: `test_results/live_validation_20260310_agent_ergonomics_run1.txt`

### Observed move sequence
1. resolver focus selected `range` (fallback focus source still in use)
2. resolver outcome valid
3. resolver move gate accepted `gather_more_evidence` with `kind=image_evidence`
4. image evidence executed with `mode=select_region`
5. next iteration resolver outcome valid
6. resolver move gate accepted `request_human_feedback`
7. run paused `waiting_feedback`

### Key validation outcomes
- Resolver-first behavior confirmed:
  - no automatic pre-resolver spans/image waterfall was observed.
- Agent-invoked image evidence confirmed:
  - evidence executed only after resolver gather-more-evidence move.
- Focused artifact creation confirmed:
  - `tx_image_evidence_region_ref` produced.
- Selector telemetry confirmed:
  - selector type surfaced as `normalized_box`.
- No evidence-request normalization rejection seen in this run.

### Finding A
- Type: runtime contract/payload propagation bug
- Classification: ergonomics/observability behavior gap (not model reasoning)
- Symptom:
  - `human_feedback_needed` event context did not include `focused_image_evidence` in live output even though region artifact existed.
- Evidence:
  - parsed `critical_events` showed context keys only `decision_key`.

## Run 1 Resume (feedback posted)
- Feedback capture: `test_results/live_validation_20260310_agent_ergonomics_run1_resume.txt`
- Post-resume snapshot: `test_results/live_validation_20260310_agent_ergonomics_run1_post_resume_snapshot.txt`

### Resume observations
- Feedback posted: `prompt_id=hitl_range_2_resolver`, choice `r75w`
- Auto-resume triggered successfully.
- Resolver integrated ticket and applied edit:
  - apply operation observed replacing `74` -> `75`.
- Evidence of transcript-version progression present:
  - `tx_edited_transcript_ref` advanced in live status.

### Finding B
- Type: runtime/infrastructure stability issue
- Classification: runtime (not resolver reasoning, not request-shape ergonomics)
- Symptom:
  - run remained `running` with stale `updated_at` and stale `live_status` (`resolver_attempt`, iteration 5) for extended period.
- Notes:
  - this blocked terminal outcome collection in this pass.

## Code changes applied in this pass
1. Hardened HITL prompt assembly fallback in iteration pipeline so focused image refs are attached when available even if upstream prompt builder omitted them.
   - File: `backend/agents/transcript_edit/iteration_pipeline.py`
   - Change: `_build_feedback_prompt_with_optional_image()` now injects `context.focused_image_evidence` from `visual_evidence`/`latest_refs` when refs exist and context lacks them.

2. Added regression test for this exact live seam.
   - File: `backend/agents/transcript_edit/test_controller.py`
   - New test: `test_human_feedback_needed_includes_focused_image_evidence_after_select_region`
   - Assertion: `human_feedback_needed` event includes focused region/context artifact refs after `select_region`.

## Tests run
- `pytest backend/agents/transcript_edit/test_controller.py -k "focused_image_evidence_after_select_region or resolver_can_chain_image_evidence_locate_then_verify" -q`
- Result: `2 passed`

## Remaining open item for next cycle
- Investigate stuck-running resume path for `tx_agent_1773139317_3b0f2100` (runtime stability/timeouts/thread progression), separately from agent-engine request ergonomics.

## Additional post-fix live attempts

### Run 2 (post-fix quick check)
- Run ID: `tx_agent_1773141304_847e30e6`
- Raw capture: `test_results/live_validation_20260310_agent_ergonomics_run2_postfix.txt`
- Outcome: `needs_review` (`tx_agent_no_progress:no_material_change`)
- Observed sequence:
  - resolver repeatedly requested `image_evidence:select_region`
  - no `request_human_feedback` emitted before no-progress guard
- Classification:
  - reasoning/policy path variation (not a request-shape rejection)

### Run 3 (post-fix retry)
- Run ID: `tx_agent_1773141534_84de7d90`
- Raw capture: `test_results/live_validation_20260310_agent_ergonomics_run3_postfix.txt`
- Outcome: `needs_review`
- Observed sequence:
  - no `human_feedback_needed` event emitted
  - run did not exercise HITL payload contract in this attempt
- Classification:
  - reasoning/policy path variation (not a contract-ergonomics failure)

## Cycle 2 (controlled live refinement pass)

### Run 4 (pre-patch reproduction in this cycle)
- Run ID: `tx_agent_1773142231_b809488a`
- Raw capture: `test_results/live_validation_20260310_agent_ergonomics_cycle2_run1.txt`
- Outcome: `needs_review` (`tx_agent_no_progress:no_material_change`)

### Observed move sequence
1. resolver focus selected `range` (fallback focus source still present)
2. resolver chose `gather_more_evidence` `image_evidence:select_region`
3. resolver then chose a refine-style follow-up (normalized to select-region style execution)
4. image evidence ran again as `select_region`
5. loop hit `no_progress_guard` and terminated `needs_review`

### Finding C
- Type: rails/policy issue
- Classification: gate/policy (not contract-shape rejection, not runtime stall)
- Symptom:
  - repeated image evidence on same blocker terminated via no-progress instead of escalating to HITL
- Evidence:
  - continuity showed repeated `gather_more_evidence:image_evidence` on `range`
  - terminal reason was no-progress, with no pending feedback ticket

## Patch applied (Cycle 2)
1. Added bounded no-progress fallback escalation in repair iteration.
   - File: `backend/agents/transcript_edit/iteration_pipeline.py`
   - Behavior:
     - when no-progress threshold is reached,
     - and hitl is enabled,
     - and there are repeated image-evidence attempts on the same unresolved mapping blocker,
     - runtime now emits fallback HITL prompt and returns `waiting_feedback` instead of immediate `needs_review`.
   - Added helper:
     - `_recent_image_evidence_attempt_count(...)` for bounded continuity-log detection.

2. Added focused regression test for this exact path.
   - File: `backend/agents/transcript_edit/test_controller.py`
   - New test:
     - `test_no_progress_with_repeated_image_evidence_falls_back_to_waiting_feedback`
   - Assertions:
     - result status becomes `waiting_feedback`
     - fallback reason `no_progress_repeated_image_evidence` is emitted
     - `human_feedback_needed` event is present

## Tests run (Cycle 2 patch)
- `pytest backend/agents/transcript_edit/test_controller.py -k "no_progress_with_repeated_image_evidence_falls_back_to_waiting_feedback or human_feedback_needed_includes_focused_image_evidence_after_select_region" -q`
- Result: `2 passed`

### Run 5 (post-patch live rerun)
- Run ID: `tx_agent_1773142690_37c6c2f9`
- Raw capture: `test_results/live_validation_20260310_agent_ergonomics_cycle2_run2_postfix.txt`
- Outcome: `waiting_feedback` (`tx_agent_waiting_feedback`)

### Key observed behavior
- Resolver-first path maintained.
- No automatic pre-resolver evidence waterfall observed.
- Explicit evidence requests observed (`open_spans`, `image_evidence:select_region`).
- After repeated no-progress with image evidence, fallback HITL fired as intended:
  - phase message: fallback HITL after repeated image evidence
  - blocker recap: `action=fallback_request_hitl, result=waiting_feedback`
- `human_feedback_needed` context included focused region artifact refs.

### Run 5 resume check (post-feedback integration)
- Raw capture: `test_results/live_validation_20260310_agent_ergonomics_cycle2_run2_resume.txt`
- Feedback submitted: `Range 75 West` on prompt `hitl_range_4_f2d06d58`
- Auto-resume: `resumed=true`
- Observed:
  - feedback received/consumed/reused events emitted
  - ticket advanced to integrated
  - apply phase executed
  - run reached clean terminal state (`needs_review`) without stale-running hang

### Finding D
- Type: runtime stability follow-up
- Classification: runtime verification
- Result:
  - prior stuck-running symptom was not reproduced in this cycle’s resumed run
  - post-resume/apply path now terminated cleanly in observed run
- Remaining issue class:
  - resolver strategy/policy still can burn iterations on open-span gathering after integration, ending in `needs_review`
  - this is reasoning/policy quality, not a run-lifecycle stall
