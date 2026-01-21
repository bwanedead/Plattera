# Ralph loop updates summary

## Scope
This summary covers the Ralph template updates that add transcript logging, global verification cadence, and review/steering scaffolding while remaining backward compatible.

## Files changed (details)

### `ralph/templates/RUN_SKELETON.md`
- Added `transcripts/` to the recommended run artifacts list so per-iteration logs are a first-class, encouraged practice.
- Added `review.md` and `steering.md` as optional files that can exist in a run.

### `ralph/templates/RUN_SKELETON_CONTRACT.md`
- Added `transcripts/` to the recommended artifacts, aligned with `RUN_SKELETON.md`.
- Added optional `review.md` and `steering.md` to reflect the new review/steering cadence scaffold.

### `ralph/templates/PREP_AGENT_CHECKLIST.md`
- Expanded optional artifacts to include `transcripts/`, `review.md`, and `steering.md`.
- Added a dedicated step to create the `transcripts/` folder.
- Added a final validation check to confirm `transcripts/` exists.

### `ralph/templates/RUN_CHECKLIST.md`
- Added checklist items to create `transcripts/`, `review.md`, and `steering.md`.
- Added a quality gate ensuring the transcript folder exists and `iter-0001.md` will be written after iteration 1.

### `ralph/templates/PRD_JSON_SCHEMA.md`
- Introduced optional `loop_settings` top-level object.
- Documented cadence fields:
  - `global_verify_every_n_stories`
  - `review_every_n_iterations`
  - `steer_every_n_iterations`
- Clarified default behavior when `loop_settings` is absent (global verification only at end; no review/steering cadence).

### `ralph/templates/PRD_JSON_TEMPLATE.json`
- Added a `loop_settings` object with example cadence values to demonstrate the new optional configuration.

### `ralph/templates/PROMPT_TEMPLATE.md`
- Added deterministic iteration number rules (derive from `progress.md` count).
- Preferred deterministic iteration number source is transcript count; `progress.md` count is now fallback.
- Required `transcripts/` creation and per-iteration transcript file writing.
- Added explicit global verification cadence rules tied to `loop_settings` and end-of-run verification.
- Defined story completion count semantics for cadence (increment only on `passes: true`).
- Added cadence collision priority ordering to remove ambiguity.
- Required explicit reporting of global verification commands, pass/fail, and transcript reference.
- Added review/steering cadence scaffold with guidance to write to `review.md` and `steering.md` using the new templates.
- Updated progress log format to require a real iteration number (not “unknown”).
- Added a loop-state control plane section that defers permissions to `CONTROL_PLANE.md`.

### `ralph/templates/HOW_RALPH_WORKS.md`
- Expanded the durable run state list to include `SUMMARY.md`, `transcripts/`, `review.md`, and `steering.md`.
- Added explicit review/steering cadence semantics and the `STEERING_NEEDED` gating rule.
- Documented optional `loop_state.json` and pointer to `CONTROL_PLANE.md`.

### `ralph/templates/RUN_SKELETON.md`
- Added optional `loop_state.json` control plane and optional `VISION.md` guidance.

### `ralph/templates/RUN_SKELETON_CONTRACT.md`
- Added optional `loop_state.json` control plane and optional `VISION.md` guidance.
- Clarified required vs optional artifacts for Ralph-ready runs.

### `ralph/templates/PREP_AGENT_CHECKLIST.md`
- Added optional `loop_state.json` and `VISION.md` artifacts.
- Added steps to create `loop_state.json` and `VISION.md`.
- Added validation to ensure `loop_state.json` follows `CONTROL_PLANE.md`.

### `ralph/templates/RUN_CHECKLIST.md`
- Added optional `loop_state.json` and `VISION.md` items.
- Added quality gates for role-based edits and steering flag handling.

## New templates added

### `ralph/templates/TRANSCRIPT_TEMPLATE.md`
- Rigid per-iteration log structure: story, plan, commands + outputs, failures/fixes, files touched, reviewer notes.

### `ralph/templates/REVIEW_TEMPLATE.md`
- Short review scaffold focused on PRD alignment, drift, tech debt, and test/verification trend.
- Includes a concise “actions recommended” section.
- Added a steering flag section (`STEERING_NEEDED`, reason, and suggested actions) to gate steering on review outcome.
- Added a reminder to sync `STEERING_NEEDED` with `loop_state.json.steering_requested`.

### `ralph/templates/STEERING_TEMPLATE.md`
 - Steering scaffold to keep the run aligned if review indicates drift.
 - Emphasizes tiny-story discipline and constrained PRD/story adjustments.

### `ralph/templates/LOOP_STATE_TEMPLATE.json`
- Added a minimal control-plane JSON template with role and cadence fields.

### `ralph/templates/CONTROL_PLANE.md`
- Documented loop_state semantics and a permissions matrix by mode.
- Added cadence source-of-truth guidance (`prd.json` as authoritative).
- Added a short invariant to keep `STEERING_NEEDED` and `steering_requested` consistent.

### `ralph/templates/VISION_TEMPLATE.md`
- Added a minimal vision template for review/steering context.

## Compatibility notes
- No required files were added to the “must have” contract.
- All additions are optional/recommended and preserve existing Ralph-ready runs.
