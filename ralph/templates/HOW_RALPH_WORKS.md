# How Ralph Works

Ralph uses a **repeated loop** where an agent receives the **same prompt** each iteration.

## Core Mechanic

Ralph is NOT "one long conversation." It is a loop:

```
while :; do
  cat PROMPT.md | claude-code --continue
done
```

What changes between iterations is not the prompt — it's the **repo state**:
- Files the agent edited last iteration
- Git commits it created
- Run artifacts (prd.json/progress.md) it updated

The agent "sees its past work" because it can read the repo and git history.

## What the ralph-loop Plugin Does

- Start with: `/ralph-loop "<PROMPT>" [options]`
- Each iteration (one phase: worker OR reviewer):
  1. Agent receives the SAME prompt
  2. Agent edits files / runs commands / commits as instructed
  3. Agent tries to exit
  4. The plugin intercepts stop and starts the next iteration with the SAME prompt
- The loop ends when either:
  - Agent outputs the exact completion tag: `<promise>YOUR_PROMISE_TEXT</promise>`
  - OR the loop hits `--max-iterations N`
  - Engine scheduling is driven by `orchestration.json`, and a reviewer can stop the run via control signals.

## Why Per-Run Directories

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

## Orchestration (Workers + Reviewers)

Each run has `orchestration.json` that controls worker/reviewer scheduling.
Default scheme is `W5R` (5 workers, then 1 reviewer, repeat).
Reviewers can also be injected ad hoc (see `control.json` review flags).
Workers can request a final review by writing `output/worker_result.json` with `{ "complete": true, "reason": "worker_done" }`.

## Review & Steering Cadence

Every N iterations, a review pass may run and must fill out `STEERING_NEEDED: yes/no`.
Steering runs only when `STEERING_NEEDED: yes` (unless forced by `loop_settings`).
Steering updates PRD/story structure while preserving tiny-story discipline.

Review tasks include a `review_mode` in their task envelope:
- `periodic` (cadence)
- `adhoc` (queued via control signals)
- `final` (after worker signals completion)

## Loop State Control Plane (Optional)

`loop_state.json` is an optional control plane at `ralph/runs/<run_id>/loop_state.json`.
Review may set `steering_requested`; worker must not edit `loop_state.json`.
Permissions are defined in `ralph/templates/CONTROL_PLANE.md`.

## Required Compatibility for a "Ralph-Ready" Run

A run is considered "Ralph-ready" if:
1. There exists a run folder: `ralph/runs/<run_id>/`
2. It contains:
   - `PRD.md`
   - `prd.json` (valid format, passes fields included)
   - `PROMPT.md` (references the above files)
   - `progress.md` (exists; entries appended each iteration)
3. `PROMPT.md` includes:
   - read-first instructions
   - "pick next story where passes=false"
   - "implement + test + commit"
   - "set passes=true only when criteria met"
   - "append progress entry"
   - completion promise tag usage

## How Stories Map to Iterations

- We aim for **one story per iteration**.
- Sometimes a story takes multiple iterations; in that case:
  - it stays `passes=false` until truly complete
  - the agent continues working it next iteration (same prompt, same story selection rule)

This is why stories should be XS/S and acceptance criteria must be objective.

## How the Loop "Knows" What to Do Next

The prompt directs the agent to:
- open `prd.json`
- select the next story with `"passes": false` (usually the earliest by order)
- complete it
- commit
- mark it true
- log progress

Then repeat. This is effectively a kanban board encoded as JSON.

## What the Prep Agent Must Design For

The prep agent's job is to generate artifacts that are:
- unambiguous (objective criteria)
- bite-sized (iteration-safe)
- ordered (dependencies respected)
- testable (agent can self-verify without asking a human)
- safe (consistent with repo guardrails)

If any of these are missing, Ralph can still run, but it will drift or thrash.
