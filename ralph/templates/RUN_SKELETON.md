# Run Skeleton Contract

A valid run folder MUST contain:
- `run.json` (engine-required)
- `control.json` (engine-required)
- `events.ndjson` (engine-required; can start empty)
- `PRD.md`
- `prd.json`
- `PROMPT.md`
- `progress.md`

Project-level requirement for harness drivers (claude_code, codex_cli, shell):
- `ralph/config.json` must exist and include `driver.name`, `driver.worker_cmd`, and `driver.reviewer_cmd` (see `ralph/templates/CONFIG_JSON_TEMPLATE.json`).

Recommended:
- `SUMMARY.md` (human-readable debrief, one entry per story)
- `notes.md` (brainstorm dump)
- `transcripts/` (per-iteration durable logs; recommended for diffability)

Optional:
- `artifacts/` (screenshots, logs)
- `review.md` (review/steering cadence output)
- `steering.md` (review-triggered steering notes)
- `loop_state.json` (optional control plane for role gating)
- `VISION.md` (optional high-level intent for review/steering)
- Local `agents.md` files (in directories that were edited, only if gotchas/invariants/workflows were discovered that are worth capturing)
