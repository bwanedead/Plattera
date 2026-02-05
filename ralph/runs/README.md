# Ralph Runs

Create one folder per run under this directory:

`ralph/runs/<run-id>/`

Recommended run-id format:

`YYYY-MM-DD__short-slug`

Each run folder should contain:
- `run.json` (engine-required)
- `control.json` (engine-required)
- `events.ndjson` (engine-required; can start empty)
- `PRD.md`
- `prd.json`
- `PROMPT.md`
- `progress.md`

Templates live in `ralph/templates/`.
