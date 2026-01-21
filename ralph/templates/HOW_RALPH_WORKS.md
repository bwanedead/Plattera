# How Ralph Works (In This Repo)

This repo uses the **Ralph Wiggum loop** via the Claude Code **ralph-loop plugin**.

## Core mechanic (what actually happens)
Ralph is NOT “one long conversation.” It is a **repeated loop** where Claude receives the **same prompt** each iteration.

Conceptually:

while :; do
  cat PROMPT.md | claude-code --continue
done

What changes between iterations is not the prompt — it’s the **repo state**:
- files Claude edited last iteration
- git commits it created
- run artifacts (prd.json/progress.md) it updated

Claude “sees its past work” because it can read the repo and git history.

## What the ralph-loop plugin does
- You start it with: `/ralph-loop "<PROMPT>" [options]`
- Each iteration:
  1) Claude receives the SAME prompt
  2) Claude edits files / runs commands / commits as instructed
  3) Claude tries to exit
  4) The plugin intercepts stop and starts the next iteration with the SAME prompt
- The loop ends when either:
  - Claude outputs the exact completion tag:
    `<promise>YOUR_PROMISE_TEXT</promise>`
  - OR the loop hits `--max-iterations N`

## Why we use per-run directories
We keep durable, replayable state in the repo so iterations remain coherent:
- `PRD.md`: human-readable spec
- `prd.json`: ordered atomic stories (each should fit in one iteration)
- `PROMPT.md`: the single prompt repeatedly fed to Ralph
- `progress.md`: short-term memory across iterations
- `SUMMARY.md`: per-story human debrief (recommended)
- `transcripts/`: per-iteration durable logs (recommended)
- `review.md`: review cadence output (optional)
- `steering.md`: steering notes if review indicates drift (optional)

This makes the loop deterministic and inspectable.

## Review & steering cadence
Every N iterations, a review pass may run and must fill out `STEERING_NEEDED: yes/no`.
Steering runs only when `STEERING_NEEDED: yes` (unless forced by `loop_settings`).
Steering updates PRD/story structure while preserving tiny-story discipline.

## Loop state control plane (optional)
`loop_state.json` is an optional control plane at `ralph/runs/<run_id>/loop_state.json`.
Review may set `steering_requested`; worker must not edit `loop_state.json`.
Permissions are defined in `ralph/templates/CONTROL_PLANE.md`.

## Required compatibility requirements for a “Ralph-ready” run
A run is considered “Ralph-ready” if:
1) There exists a run folder: `ralph/runs/<run_id>/`
2) It contains:
   - `PRD.md`
   - `prd.json` (valid format, passes fields included)
   - `PROMPT.md` (references the above files)
   - `progress.md` (exists; entries appended each iteration)
3) `PROMPT.md` includes:
   - read-first instructions
   - “pick next story where passes=false”
   - “implement + test + commit”
   - “set passes=true only when criteria met”
   - “append progress entry”
   - completion promise tag usage

## How stories map to iterations
- We aim for **one story per iteration**.
- Sometimes a story takes multiple iterations; in that case:
  - it stays `passes=false` until truly complete
  - the agent continues working it next iteration (same prompt, same story selection rule)

This is why stories should be XS/S and acceptance criteria must be objective.

## How the loop “knows” what to do next
The prompt directs the agent to:
- open `prd.json`
- select the next story with `"passes": false` (usually the earliest by order)
- complete it
- commit
- mark it true
- log progress
Then repeat.

This is effectively a kanban board encoded as JSON.

## What the prep agent must design for
The prep agent’s job is to generate artifacts that are:
- unambiguous (objective criteria)
- bite-sized (iteration-safe)
- ordered (dependencies respected)
- testable (agent can self-verify without asking a human)
- safe (consistent with CLAUDE.md guardrails)

If any of these are missing, Ralph can still run, but it will drift or thrash.


