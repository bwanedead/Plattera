# Prep Agent Checklist — Create a Ralph-Ready Run Folder

## Your job

Given a brainstorm/feature idea, create a fully compatible Ralph run directory at:
`ralph/runs/<run_id>/`

A run is "Ralph-ready" only if it matches the run skeleton contract and is compatible with the loop mechanics described in the Ralph docs.

---

## Step 0 — Understand the system (read these first)

Before writing any run artifacts, read:
1. Repo guidelines (e.g., `CLAUDE.md`) for safety + workflow rules
2. Any repo-wide ethos/vision docs relevant to scope
3. `ralph/README.md` (repo's Ralph workflow)
4. `ralph/templates/HOW_RALPH_WORKS.md` (ground-truth loop mechanics)
5. `ralph/templates/STORY_GUIDELINES.md` (what "tiny stories" means)
6. `ralph/templates/PRD_TEMPLATE.md` (PRD format)
7. `ralph/templates/PRD_JSON_SCHEMA.md` + `ralph/templates/PRD_JSON_TEMPLATE.json` (story list format)
8. `ralph/templates/PROMPT_TEMPLATE.md` (what the loop will repeatedly receive)
9. `ralph/templates/SUMMARY_TEMPLATE.md` (human-readable per-story run debrief)
10. `ralph/templates/RUN_JSON_TEMPLATE.json` + `ralph/templates/CONTROL_JSON_TEMPLATE.json` (engine-required files)
11. `ralph/templates/ORCHESTRATION_JSON_TEMPLATE.json` (engine-required orchestration state)
12. `ralph/templates/CONFIG_JSON_TEMPLATE.json` (project-level driver config)

---

## Step 0a — Ensure project-level config exists

The engine reads driver settings from `ralph/config.json` (project-level).
Create it once per project using:
- `ralph/templates/CONFIG_JSON_TEMPLATE.json`

For harness drivers (claude_code, codex_cli, shell), ensure:
- `driver.worker_cmd` includes `{task_file}`
- `driver.reviewer_cmd` includes `{task_file}`
The engine writes `worker_summary.md` from worker stdout and `review_result.json` from reviewer stdout when the CLI doesn't write those files itself.
If your CLI command is not on PATH for the engine process, update `ralph/config.json` to point to a concrete executable (e.g., `C:\Users\<user>\AppData\Roaming\npm\claude.cmd` on Windows; use the extensionless command on macOS/Linux).

---

## Step 1 — Choose run-id and create the folder

- Pick a run id: `YYYY-MM-DD__short-slug`
- Run ids must not contain `/` or `\`
- Create:
  `ralph/runs/<run_id>/`

---

## Step 2 — Create required files (Run Skeleton Contract)

A valid run folder MUST contain:
- `run.json` (engine-required; see schema below)
- `control.json` (engine-required; see schema below)
- `events.ndjson` (engine-required; empty file ok)
- `orchestration.json` (engine-required; scheduling state)
- `PRD.md` (human-readable spec)
- `prd.json` (atomic stories; includes `passes` fields)
- `PROMPT.md` (the single prompt repeatedly fed to Ralph)
- `progress.md` (short-term memory log; starts empty)

Optional (only if useful):
- `SUMMARY.md` (human-readable debrief, one entry per story)
- `notes.md` (raw brainstorm dump)
- `artifacts/` (screenshots/log snippets)
- `transcripts/` (per-iteration durable logs; recommended)
- `review.md` (review cadence output; optional)
- `steering.md` (steering notes if review triggers; optional)
- `loop_state.json` (control plane for advanced loops; optional)
- `VISION.md` (high-level intent for review/steering; optional)

---

## Step 2a — Write engine-required files first

Create these before any prep files so the run is immediately engine-usable.
Use atomic write for JSON outputs.

`run.json` (from `ralph/templates/RUN_JSON_TEMPLATE.json`):
- Set `run_id` to the run folder name.
- Set `created_at` and `updated_at` to UTC ISO 8601 (e.g., `2026-01-29T21:04:33Z`).
- Set `max_iterations` to an actual integer for the run (do not leave placeholders).

Minimum schema:
```
{
  "run_id": "<run_id>",
  "status": "pending",
  "iteration": 0,
  "max_iterations": <int>,
  "created_at": "<ISO8601 UTC>",
  "updated_at": "<ISO8601 UTC>",
  "error": null
}
```

`control.json` (from `ralph/templates/CONTROL_JSON_TEMPLATE.json`, minimum schema):
```
{
  "pause": false,
  "stop_soft": false,
  "stop_hard": false,
  "skip_iteration": false,
  "review_now": false,
  "review_next": false
}
```

`events.ndjson`:
- Copy from `ralph/templates/EVENTS_NDJSON_TEMPLATE.ndjson` (empty file ok). Engine will append.

`orchestration.json` (from `ralph/templates/ORCHESTRATION_JSON_TEMPLATE.json`):
- Default scheme is `W5R` (5 workers then 1 reviewer, repeat).
- Leave `cursor`, `queue`, and `final_review_pending` at defaults for new runs.

---

## Step 3 — Write PRD.md (use the template)

- Use `ralph/templates/PRD_TEMPLATE.md`
- Fill:
  - Context, Goal, Non-goals
  - Constraints & invariants
  - Success criteria (objective, testable)
  - Edge cases
- Keep it crisp. Avoid vague "make it better" statements.

---

## Step 4 — Convert PRD → prd.json (atomic stories)

- Use `ralph/templates/PRD_JSON_TEMPLATE.json` and follow schema rules.
- Produce 5–25 stories typically.
- Each story must be completable in (roughly) one iteration.
- Each story MUST include objective acceptance criteria.

Acceptance criteria must be verifiable by:
- `pytest`/`python -m pytest` for backend (preferred),
- deterministic CLI output,
- or other objective commands.

Avoid criteria requiring human taste judgment ("looks good").

Order stories by dependency (foundation first).

---

## Step 5 — Create PROMPT.md (run prompt)

- Use `ralph/templates/PROMPT_TEMPLATE.md`
- Replace `<run_id>` placeholders with the actual run id.
- Ensure PROMPT explicitly instructs:
  - read repo guidelines + ethos docs
  - read PRD.md + prd.json
  - pick next story where passes=false
  - implement + test + commit
  - set passes=true only when criteria met
  - append progress
  - append SUMMARY.md
  - emit `<promise>TASK COMPLETE</promise>` only when done

---

## Step 6 — Create progress.md

Create:
`ralph/runs/<run_id>/progress.md`

Start with:

```
# Progress — <run_id>

(append entries per iteration)
```

---

## Step 7 — Create SUMMARY.md (recommended)

Create:
`ralph/runs/<run_id>/SUMMARY.md`

Start from:
`ralph/templates/SUMMARY_TEMPLATE.md`

---

## Step 8 — Create transcripts/ (recommended)

Create:
`ralph/runs/<run_id>/transcripts/`

(Ralph will write `iter-XXXX.md` files each iteration.)

---

## Step 9 — Create loop_state.json (optional for advanced loops)

Create:
`ralph/runs/<run_id>/loop_state.json`

Start from:
`ralph/templates/LOOP_STATE_TEMPLATE.json`

---

## Step 10 — Create VISION.md (optional)

Create:
`ralph/runs/<run_id>/VISION.md`

Start from:
`ralph/templates/VISION_TEMPLATE.md`

---

## Step 11 — Final validation (before handing to Ralph)

Confirm:
- Run folder contains required files (run.json, control.json, events.ndjson, orchestration.json, PRD.md, prd.json, PROMPT.md, progress.md)
- `ralph/config.json` exists and includes worker_cmd + reviewer_cmd with `{task_file}` for harness drivers
- If PATH resolution fails, `ralph/config.json` points to a concrete executable (use `.cmd` on Windows)
- run.json has status "pending" and UTC ISO 8601 timestamps
- `SUMMARY.md` exists (recommended) so the loop can append per-story debrief entries
- `transcripts/` exists (recommended) for per-iteration logs
- If `loop_state.json` exists, it is valid JSON and follows `CONTROL_PLANE.md`
- All stories in prd.json start with `"passes": false`
- Acceptance criteria are objective and testable
- Stories are XS/S and ordered
- PROMPT references the correct run folder paths and includes the completion promise tag

If any check fails, fix before the run starts.

Optional validation:
- `ralph-engine list <project_path>` shows the new run with status pending
