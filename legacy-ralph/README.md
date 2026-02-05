# Ralph System (Repo-local)

## What this is
This repo uses a “Ralph run” workflow: define a feature precisely, break it into tiny stories, convert to `prd.json`, then run a loop (Claude Code + ralph-loop) to implement stories iteratively.

A Ralph run is fully captured in `ralph/runs/<run-id>/`:
- PRD (human spec)
- prd.json (atomic stories + acceptance criteria)
- PROMPT.md (run instructions for the coding agent)
- progress log(s) (iteration notes)
- SUMMARY.md (human-readable debrief, one entry per story; recommended)

## Why we do per-run directories
- Durable history of intent -> implementation
- Reproducible: rerun the same run later if needed
- Easy review: PRD and story list match resulting commits

## Canonical flow
1) Create a new run directory: `ralph/runs/<run-id>/`
2) Draft PRD.md using `templates/PRD_TEMPLATE.md`
3) Convert PRD.md into `prd.json` using `templates/PRD_JSON_TEMPLATE.json`
4) Create PROMPT.md using `templates/PROMPT_TEMPLATE.md`
5) Execute Ralph loop using the prompt in PROMPT.md
6) Append progress notes per iteration into `progress.md` (and/or the tool’s output)
7) Append a human-readable per-story debrief into `SUMMARY.md` (recommended)

## Run naming convention
Use a stable run-id:
`YYYY-MM-DD__short-slug`
Example: `2026-01-11__vector-index-preview`

## Where instructions live
- Repo-wide operating rules: `CLAUDE.md`
- Ralph-specific run instructions: `ralph/templates/*` + `ralph/runs/<run-id>/PROMPT.md`
- Folder-level constraints: `agents.md` files near code

If anything conflicts: follow `CLAUDE.md`.


