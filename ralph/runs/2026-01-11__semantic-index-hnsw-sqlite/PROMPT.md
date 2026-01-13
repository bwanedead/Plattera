# PROMPT.md — Ralph Run: 2026-01-11__semantic-index-hnsw-sqlite

You are an autonomous coding agent working in this repository under a Ralph Wiggum loop.

IMPORTANT: This exact prompt will be re-run repeatedly each iteration. You must use repo state (files + git + run logs) as memory.

## Read-first (every iteration; do not skip)
1) Read `CLAUDE.md` and obey it.
2) Read the repo ethos/vision docs relevant to this change scope (even if referenced elsewhere). If unsure, start with `docs/ethos/*` and any vision/spec docs linked from there.
3) Read `ralph/templates/HOW_RALPH_WORKS.md` (understand the loop mechanics).
4) Read `ralph/runs/2026-01-11__semantic-index-hnsw-sqlite/PRD.md`
5) Read `ralph/runs/2026-01-11__semantic-index-hnsw-sqlite/prd.json`
6) Read any `agents.md` files in directories you touch.

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
     - any other ethos at `docs/ethos/` or if any submodule ethos files are relevant to edits made.
   - Confirm scope stayed within this story (no “and also”).
   - Confirm you preserved stated constraints/invariants (PRD, agents.md, existing contracts).
   - Confirm the change is structurally sound: clear module boundaries, no dumping grounds, no tight coupling.
   - Confirm anything that must be durable is persisted (not left only in ephemeral state).
3) Add/update tests and/or verification commands so acceptance criteria are objectively verifiable.
4) Run relevant checks when feasible:
   - Backend: `pytest` (or `python -m pytest`) for Python code.
5) Commit with: `Ralph 2026-01-11__semantic-index-hnsw-sqlite: <story id> <story title>`
6) Update `ralph/runs/2026-01-11__semantic-index-hnsw-sqlite/prd.json`:
   - set that story `"passes": true` ONLY if acceptance criteria are satisfied
7) Append to `ralph/runs/2026-01-11__semantic-index-hnsw-sqlite/progress.md` (format below)
8) Append to `ralph/runs/2026-01-11__semantic-index-hnsw-sqlite/SUMMARY.md` (format below)
9) (Optional) Consider local `agents.md` enrichment:
   - For each directory you edited, check if a local `agents.md` exists
   - If you discovered a gotcha, invariant, required workflow, or sharp edge that would help future agents working in that area, create/update the folder-level `agents.md` using the repo’s standard template (see root `AGENTS.md` section 4)
   - Only do this if there's genuinely useful information to capture (don't spam empty files)
   - Keep it short (~30-50 lines) and factual

## Progress log format (append)
Append exactly this shape to `progress.md`:

- Iteration: <n or unknown>
- Story: <S#> <title>
- Result: PASS|FAIL
- Files changed: <list>
- Commands run: <list>
- Notes:
  - <bullets>

---

## Summary format (append)
Append exactly this shape to `SUMMARY.md`:

---

## Story S<#>: <title>
**Status:** PASS|FAIL
**Iteration:** <n>

### What was built
- <bullet: concrete deliverable>
- <bullet: concrete deliverable>

### Files changed
- `<path>` - <what changed>
- `<path>` - <what changed>

### Key decisions
- <bullet: architectural choice or tradeoff>

### Tests added
- <count> new tests in `<path>`

### Notes
- <bullet: anything notable for future maintainers>

## Completion promise (required)
When ALL stories in `prd.json` are `"passes": true`, output exactly:

<promise>TASK COMPLETE</promise>

Do not output the promise unless the run is genuinely complete.



