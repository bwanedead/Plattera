# PROMPT.md — Ralph Run: 2026-01-11__golden-example

You are an autonomous coding agent working in this repository under a Ralph Wiggum loop.

IMPORTANT: This exact prompt will be re-run repeatedly each iteration. You must use repo state (files + git + run logs) as memory.

## Read-first (every iteration)
1) Read `CLAUDE.md` and obey it.
2) Read `ralph/templates/HOW_RALPH_WORKS.md` (understand the loop).
3) Read `ralph/runs/2026-01-11__golden-example/PRD.md`
4) Read `ralph/runs/2026-01-11__golden-example/prd.json`
5) Read any `agents.md` files in directories you touch.

## Mission (loop behavior)
Each iteration:
- Select the next story in `prd.json` where `"passes": false` (prefer lowest ordered unmet story).
- Implement it with minimal scope.
- Make it self-verifying (tests or deterministic commands).
- Commit the change.
- Update run state (`prd.json`, `progress.md`).
- Continue next iteration until all stories pass.

## Per-iteration procedure (do this in order)
For the selected story:
1) Implement the change with minimal scope.
2) Sanity + ethos check (before verification and before marking the story done):
   - Benchmark the change against repo ethos docs (at minimum):
     - `docs/ethos/architecture-ethos.md`
     - `docs/ethos/structure-ethos.md`
     - `docs/ethos/testing-ethos.md`
     - `docs/ethos/agents-md-ethos.md`
   - Confirm scope stayed within this story (no “and also”).
   - Confirm you preserved stated constraints/invariants (PRD, agents.md, existing contracts).
   - Confirm the change is structurally sound: clear module boundaries, no dumping grounds, no tight coupling.
   - Confirm anything that must be durable is persisted (not left only in ephemeral state).
   - If you discovered a durable local constraint or footgun, note it for `agents.md`.
3) Add/update tests and/or verification commands so acceptance criteria are objectively verifiable.
4) Run relevant checks (tests/lint/build) when feasible.
5) Commit with: `Ralph 2026-01-11__golden-example: <story id> <story title>`
6) Update `ralph/runs/2026-01-11__golden-example/prd.json`:
   - set that story `"passes": true` ONLY if acceptance criteria are satisfied
7) Append to `ralph/runs/2026-01-11__golden-example/progress.md` (format below)
8) If you learn a durable local rule, create/update a folder-level `agents.md` using the repo’s standard template (keep it short).

## Progress log format (append)
Append exactly this shape:

- Iteration: <n or unknown>
- Story: <S#> <title>
- Result: PASS|FAIL
- Files changed: <list>
- Commands run: <list>
- Notes:
  - <bullets>

## Completion promise (required)
When ALL stories in `prd.json` are `"passes": true`, output exactly:

<promise>TASK COMPLETE</promise>

Do not output the promise unless the run is genuinely complete.


