# Run Skeleton Contract

A Ralph run folder MUST be located at:
`ralph/runs/<run_id>/`

It MUST contain:
- `PRD.md`
- `prd.json`
- `PROMPT.md`
- `progress.md`

Only the items under “It MUST contain” are required for a Ralph-ready run.

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

Everything in these files must be compatible with:
- `ralph/templates/HOW_RALPH_WORKS.md`
- the repo safety rules in `CLAUDE.md`

Note:
- The more detailed version of this contract lives in `ralph/templates/RUN_SKELETON.md`. Keep these two aligned.


