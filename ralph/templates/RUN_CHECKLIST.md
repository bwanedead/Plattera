# Ralph Run Checklist

## Familiarize yourself with the Ralph process, purpose and the full documentation

Read and understand:

- `ralph/templates/README.md`
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

## Populate required files
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
- [ ] Repo guardrails in `CLAUDE.md` are in place
- [ ] `transcripts/` exists and `iter-0001.md` will be written after iteration 1
- [ ] If `loop_state.json` exists, worker does not edit it
- [ ] Review only sets `steering_requested` with `STEERING_NEEDED: yes` in `review.md`
- [ ] Steering clears `steering_requested` and logs actions in `steering.md`

## Run
- [ ] Start ralph-loop using PROMPT.md
- [ ] Monitor early iterations for tool permission prompts and obvious drift


