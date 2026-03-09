# Transcript-Edit Live Validation Path (Phase 1/2)

Date: March 8, 2026

## Purpose
- Provide one controlled operator path to validate blocker-registry lifecycle behavior end-to-end.
- Avoid broad soak tests that get dominated by unrelated runtime noise.

## Validation mode
- Use `validation_mode=live_hitl` only when validating lifecycle plumbing.
- Default runtime behavior remains `validation_mode=off`.

## Scenario
- Source deed image: `practice_deeds/legal_text_image.jpg`
- Known transcript seed: `draft_legal_text_image_v2.json`
- Expected blocker class: `range` contradiction (`74` vs `75`).

## Expected lifecycle
1. Run starts and opens blocker for `range`.
2. HITL prompt is issued and linked to blocker row (`waiting_feedback`).
3. Human feedback is posted to active prompt.
4. Blocker row transitions to `answered_unintegrated`.
5. Resume path prioritizes returned feedback integration before fresh ambiguity work.
6. Terminal summary reports blocker counts/owners and post-feedback state clearly.

## Operator checkpoints
- Checkpoint A: waiting owner
  - `status=waiting_feedback`
  - `terminal_summary.waiting_feedback_owner.decision_key == "range"`
  - `pending_feedback_prompt_ids` includes active prompt
- Checkpoint B: feedback accepted
  - `runtime_hitl_state.feedback_received_count` increments
  - blocker row for `range` shows `state=answered_unintegrated` before integration
- Checkpoint C: post-resume integration
  - run resumes from waiting state
  - blocker deltas/history show integration attempt outcome
- Checkpoint D: terminal explainability
  - `terminal_summary.terminal_classification` matches stop reason
  - `final_decision_rationale` and blocker ownership fields are present

## Non-goals for this path
- Not a dependency-retrieval test.
- Not a model-comparison test.
- Not a throughput benchmark.
