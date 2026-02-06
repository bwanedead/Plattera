# Ralph Run Checklist

## Familiarize yourself with the Ralph process, purpose and the full documentation

Read and understand:

- `ralph/README.md`
- `ralph/templates/HOW_RALPH_WORKS.md`
- `ralph/templates/STORY_GUIDELINES.md`
- `ralph/templates/PROMPT_TEMPLATE.md`
- `ralph/templates/SUMMARY_TEMPLATE.md`
- `ralph/templates/PRD_TEMPLATE.md`
- `ralph/templates/PRD_JSON_SCHEMA.md`
- `ralph/templates/PRD_JSON_TEMPLATE.json`
- `ralph/templates/RUN_SKELETON.md`
- `ralph/templates/RUN_SKELETON_CONTRACT.md`
- `ralph/templates/COMPATIBILITY_NOTES.md`
- Additionally any other relevant documentation file that provides detail on how to design and prep the ralph run.

## Create run folder

- [ ] `ralph/runs/<run_id>/` created

## Ensure project-level config exists

- [ ] `ralph/config.json` created (from `ralph/templates/CONFIG_JSON_TEMPLATE.json`)
- [ ] For harness drivers, `driver.worker_cmd` and `driver.reviewer_cmd` include `{task_file}`
- [ ] If PATH resolution fails, point to a concrete executable (use `.cmd` on Windows)

## Populate required files

- [ ] `run.json` created (engine-required; pending status)
- [ ] `control.json` created (engine-required; all false)
- [ ] `events.ndjson` created (engine-required; empty ok)
- [ ] `orchestration.json` created (engine-required; from ORCHESTRATION_JSON_TEMPLATE.json)
- [ ] `PRD.md` created (from PRD_TEMPLATE.md)
- [ ] `prd.json` created (from PRD_JSON_TEMPLATE.json)
- [ ] `PROMPT.md` created (from PROMPT_TEMPLATE.md)
- [ ] `progress.md` created (empty header ok)
- [ ] `SUMMARY.md` created (recommended; from SUMMARY_TEMPLATE.md)
- [ ] `transcripts/` created (recommended; per-iteration logs)
- [ ] `review.md` created (optional; review cadence output)
- [ ] `steering.md` created (optional; steering notes)
- [ ] `loop_state.json` created (optional; from LOOP_STATE_TEMPLATE.json)
- [ ] `VISION.md` created (optional; from VISION_TEMPLATE.md)

## Quality gates before running

- [ ] Stories are XS/S and each is one-iteration doable
- [ ] Acceptance criteria are objective & verifiable
- [ ] Story order respects dependencies
- [ ] run.json has status "pending" and UTC ISO 8601 timestamps
- [ ] Repo guardrails in `CLAUDE.md` (or equivalent) are in place
- [ ] `transcripts/` exists and `iter-0001.md` will be written after iteration 1
- [ ] If `loop_state.json` exists, worker does not edit it
- [ ] Review only sets `steering_requested` with `STEERING_NEEDED: yes` in `review.md`
- [ ] Steering clears `steering_requested` and logs actions in `steering.md`

## Run

- [ ] Start ralph-loop using PROMPT.md
- [ ] Monitor early iterations for tool permission prompts and obvious drift
