# Ralph Run Checklist

## Familiarize yourself with the Ralph process, purpose and the full documentation

Read and understand:

- `ralph/templates/README.md`
- `ralph/templates/HOW_RALPH_WORKS.md`
- `ralph/templates/STORY_GUIDELINES.md`
- `ralph/templates/PROMPT_TEMPLATE.md`
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

## Quality gates before running
- [ ] Stories are XS/S and each is one-iteration doable
- [ ] Acceptance criteria are objective & verifiable
- [ ] Story order respects dependencies
- [ ] Repo guardrails in `CLAUDE.md` are in place

## Run
- [ ] Start ralph-loop using PROMPT.md
- [ ] Monitor early iterations for tool permission prompts and obvious drift


