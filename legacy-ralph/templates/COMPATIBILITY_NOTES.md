# Compatibility Notes (Prep Agent Must Follow)

A run must be compatible with:
- Claude Code ralph-loop plugin
- Completion promise tag: `<promise>...</promise>`
- Max iterations may stop early: design stories so each is small and ordered.

Therefore:
- `PROMPT.md` must instruct selection by `"passes": false`.
- `prd.json` must contain `passes` booleans.
- Acceptance criteria must be testable without human judgment.
- `progress.md` must exist for short-term memory.
- Run folder must be fully self-contained and referenced by prompt.


