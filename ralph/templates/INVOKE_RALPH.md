# How to invoke Ralph (Claude Code ralph-loop plugin)

1. Create run folder: `ralph/runs/<run-id>/`
2. Ensure `PROMPT.md` exists in that run folder.
3. Start the loop:

`/ralph-loop "<paste PROMPT.md content>" --completion-promise "TASK COMPLETE" --max-iterations 20`

Notes:
- The prompt is re-run identically each iteration.
- One iteration is one phase (worker or reviewer), not a worker+reviewer pair.
- The loop stops when Claude outputs: `<promise>TASK COMPLETE</promise>`
- `max_iterations` means N more phase iterations from now (per run invocation).
- You can extend a live run by setting `control.json.add_iterations`.
