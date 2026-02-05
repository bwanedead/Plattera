# Prep Agent Checklist — Create a Ralph-Ready Run Folder

## Your job
Given a brainstorm/feature idea, create a fully compatible Ralph run directory at:
`ralph/runs/<run_id>/`

A run is “Ralph-ready” only if it matches the run skeleton contract and is compatible with the loop mechanics described in the Ralph docs.

---

## Step 0 — Understand the system (read these first)
Before writing any run artifacts, read:
1) `CLAUDE.md` (repo safety + workflow rules)
2) Repo ethos/vision docs relevant to scope (start at `docs/ethos/*` if unsure)
3) `ralph/README.md` (repo’s Ralph workflow)
4) `ralph/templates/HOW_RALPH_WORKS.md` (ground-truth loop mechanics)
5) `ralph/templates/STORY_GUIDELINES.md` (what “tiny stories” means)
6) `ralph/templates/PRD_TEMPLATE.md` (PRD format)
7) `ralph/templates/PRD_JSON_SCHEMA.md` + `ralph/templates/PRD_JSON_TEMPLATE.json` (story list format)
8) `ralph/templates/PROMPT_TEMPLATE.md` (what the loop will repeatedly receive)
9) `ralph/templates/SUMMARY_TEMPLATE.md` (human-readable per-story run debrief)

---

## Step 1 — Choose run-id and create the folder
- Pick a run id: `YYYY-MM-DD__short-slug`
- Create:
  `ralph/runs/<run_id>/`

---

## Step 2 — Create required files (Run Skeleton Contract)
A valid run folder MUST contain:
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

## Step 3 — Write PRD.md (use the template)
- Use `ralph/templates/PRD_TEMPLATE.md`
- Fill:
  - Context, Goal, Non-goals
  - Constraints & invariants
  - Success criteria (objective, testable)
  - Edge cases
- Keep it crisp. Avoid vague “make it better” statements.

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

Avoid criteria requiring human taste judgment (“looks good”).

Order stories by dependency (foundation first).

---

## Step 5 — Create PROMPT.md (run prompt)
- Use `ralph/templates/PROMPT_TEMPLATE.md`
- Replace `<run_id>` placeholders with the actual run id.
- Ensure PROMPT explicitly instructs:
  - read `CLAUDE.md` + ethos docs
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

# Progress — <run_id>

(append entries per iteration)

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
- Run folder contains required files (PRD.md, prd.json, PROMPT.md, progress.md)
- `SUMMARY.md` exists (recommended) so the loop can append per-story debrief entries
- `transcripts/` exists (recommended) for per-iteration logs
- If `loop_state.json` exists, it is valid JSON and follows `CONTROL_PLANE.md`
- All stories in prd.json start with `"passes": false`
- Acceptance criteria are objective and testable
- Stories are XS/S and ordered
- PROMPT references the correct run folder paths and includes the completion promise tag

If any check fails, fix before the run starts.


