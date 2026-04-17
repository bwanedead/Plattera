# Harness Polish Backlog

This document is the working backlog for current harness-polish items that were identified from:

- external harness review notes
- local code validation
- local live-regression fixtures
- targeted harness test reads

It is intentionally narrower than the long-range convergence and agent-kernel roadmap docs.
Use it as the "what should we clean up next?" queue for current harness reality.

## Scope

- Track bounded harness cleanup and polish items that have real merit.
- Separate immediate fixes from evidence-gated hypotheses.
- Preserve the conclusions from the April 17, 2026 review pass so future sessions do not need to rediscover them.

## Status Legend

- `[ready]` bounded change with enough evidence to execute now
- `[investigate]` good candidate, but should be shaped by emitted-run evidence first
- `[later]` valid cleanup, but lower leverage than the items above it
- `[done]` completed

## Review Snapshot

- Confirmed: shared harness code still hard-codes transcript-edit publish/save action ids.
- Confirmed: `loop_health_summary` includes editorial prose that drifts past pure mechanical facts.
- Confirmed: prompt assembly currently uses `json.dumps(..., sort_keys=True)`, which defeats stable-prefix ordering.
- Confirmed: the prompt doctrine surface is large and repetitive.
- Confirmed: prompt-visible tool cards are intentionally slimmed down before prompt assembly.
- Confirmed: existing audit plumbing already captures raw prompt text, raw response text, parse outcomes, parsed action plans, and repair records.
- Confirmed: local live-regression fixtures show meaningful `state_patch` rejection rates, which makes state-shape ergonomics a more credible seam concern than tool-card richness.

## Non-Priorities Right Now

- Do not expand prompt-visible tool cards unless emitted-run evidence shows meaningful tool-input-shape failures.
- Do not refactor `ActionPlan` into a discriminated union based on cleanliness alone.
- Do not replace the JSON prompt packet format casually; preserve current architectural guardrails unless there is a deliberate architecture decision to change them.

## Priority Queue

### 1. [done] Remove publish/save action-id leakage from shared harness

- Why it matters: shared harness code should not know transcript-edit tool names.
- Implementation brief:
  - `docs/architecture/harness/closure-policy-action-ownership-brief.md`
- Current anchors:
  - `backend/harness/runtime/orchestration/orchestrator.py`
  - `backend/harness/runtime/orchestration/orchestrator_policy.py`
  - `backend/domains/mapping/transcript_edit/domain_pack.py`
- Desired direction:
  - move publish/save action-id knowledge into domain-owned policy or domain-owned context
  - keep shared harness gating generic
- Done when:
  - shared harness no longer hard-codes `publish_workspace_artifact` or `save_workspace_artifact`
  - policy tests pass with the ids coming from run/domain context rather than harness constants

### 2. [done] Make loop-health flags factual instead of advisory

- Why it matters: shared deterministic code should expose mechanical facts, not editorial guidance.
- Current anchors:
  - `backend/harness/runtime/orchestration/loop_health_summary.py`
  - `backend/harness/runtime/orchestration/test_loop_health_summary.py`
- Desired direction:
  - keep counts, streaks, blockers, and thresholds
  - replace prose nudges with compact fact strings
  - example direction: prefer `success_conditions_empty_with_resolution_items:3` over advisory wording
- Done when:
  - `mechanical_flags` remains useful to the model and operators
  - no flag text tells the model what semantic conclusion it should draw
  - loop-health tests still pass after updating expected strings as needed

### 3. [done] Preserve stable prompt-body key order and remove `sort_keys=True`

- Why it matters: prompt assembly already builds a sensible stable-to-volatile order, then discards it by alphabetically sorting keys.
- Current anchors:
  - `backend/harness/runtime/orchestration/prompt_packet_builder.py`
  - `backend/harness/test_architecture_guardrails.py`
- Desired direction:
  - keep the JSON packet format
  - preserve insertion order for `prompt_body`
  - keep stable content first and volatile content later
- Done when:
  - prompt assembly still uses `json.dumps(prompt_body, ...)`
  - prompt key ordering is explicit and stable
  - no architecture guardrail is violated

### 4. [ready] Deduplicate and compress doctrine without weakening rigor

- Why it matters: the model re-reads a large amount of stable doctrine every turn, and there is visible repetition across layers.
- Current anchors:
  - `backend/harness/runtime/prompting/surface.py`
  - `backend/domains/mapping/prompting/family_branch.py`
  - `backend/domains/mapping/transcript_edit/prompting/branch.py`
  - `backend/domains/mapping/transcript_edit/prompting/surfaces/procedural_guidance.py`
  - `backend/domains/mapping/transcript_edit/prompting/surfaces/startup_context.py`
  - `backend/harness/runtime/orchestration/choose_action_instruction.py`
- Desired direction:
  - say each rule once whenever possible
  - let lower layers assume higher-layer doctrine rather than restating it
  - keep the rigor-bearing concepts intact: work-universe posture, audit sweep, earned vs provisional, closure discipline
- Done when:
  - prompt doctrine is materially smaller
  - important rules are clearer rather than blurrier
  - tests and live behavior show no regression in rigor

### 5. [ready] Surface emitted-shape evidence from the existing audit pipeline

- Why it matters: the repo already records rich seam data, but the evidence is not yet summarized into a convenient ergonomics view.
- Current anchors:
  - `backend/harness/runtime/orchestration/llm_turn_adapter.py`
  - `backend/harness/audit/run_audit_writer.py`
  - `backend/harness/review/tool.py`
  - `backend/harness/test_fixtures/transcript_edit_live_regression/`
- Desired direction:
  - add an easy way to summarize parse failures, repair reasons, rejected `state_patch` reason codes, and recurring emitted-shape patterns
  - make ergonomics decisions from recorded evidence rather than hunches
- Done when:
  - a reviewer can answer "what shapes is the model naturally trying to emit?" from audit artifacts
  - future seam changes can cite evidence instead of guesswork

### 6. [investigate] Revisit `state_patch` ergonomics using emitted-run evidence

- Why it matters: the live-regression fixtures suggest state-shape friction is more real than tool-shape friction.
- Current anchors:
  - `backend/harness/runtime/orchestration/choose_action_instruction.py`
  - `backend/harness/runtime/orchestration/state_patch_apply.py`
  - `backend/harness/runtime/orchestration/test_state_patch_apply.py`
  - `backend/harness/test_fixtures/transcript_edit_live_regression/practice_row_live_20260409_3_summary.json`
  - `backend/harness/test_fixtures/transcript_edit_live_regression/phase1_pack_sanity_20260412_1_summary.json`
- Current evidence:
  - one live fixture records `16 applied / 4 rejected` patches over 20 turns
  - one live fixture records `7 applied / 1 rejected` patches over 8 turns
  - one notable rejection is `closure_state_unknown_keys`
- Questions to answer before changing the seam:
  - which rejected shapes recur most often?
  - are there sane recurring alias forms worth accepting?
  - are the examples and repair hints aligned with the shapes the model actually emits?
- Done when:
  - any accepted seam change is justified by emitted-shape evidence
  - rejection rates go down for the targeted failure class

### 7. [later] Close remaining silent-skip paths so the model always sees what happened

- Why it matters: warning-and-continue paths can consume an iteration without giving the model equivalent structured feedback next turn.
- Current anchors:
  - `backend/harness/runtime/orchestration/orchestrator.py`
  - `backend/harness/runtime/orchestration/action_plan_parser.py`
- Desired direction:
  - move invariant failures into parse/repair where practical
  - otherwise emit explicit feedback into the next prompt
- Done when:
  - no meaningful plan failure vanishes into a silent skip from the model's perspective

### 8. [later] Move `turn_snapshot` and similar turn-local data out of durable state payloads

- Why it matters: current flow launders ephemeral turn context through durable `opaque_payload`, then strips it back out before prompting.
- Current anchors:
  - `backend/harness/runtime/orchestration/llm_turn_adapter.py`
  - `backend/harness/runtime/orchestration/prompt_sanitization.py`
- Desired direction:
  - keep turn-local context on a turn-local surface instead of mission/resolution durable payload
- Done when:
  - prompt sanitization no longer needs to strip `turn_snapshot` and `launch_context` duplicates from projected durable state

## Working Order

When choosing the next cleanup batch, prefer this sequence:

1. item 4
2. item 5
3. item 6

Items 7 and 8 are valid follow-up cleanup, but they should not displace the higher-leverage work above.

## Related Docs

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/harness-sanity-refactor-brief.md`
- `docs/ethos/agent-engine-ergonomics-theory.md`
