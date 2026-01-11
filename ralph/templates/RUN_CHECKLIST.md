# Ralph Run Checklist

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


