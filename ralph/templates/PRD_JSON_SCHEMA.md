# prd.json Schema (Human-readable)

`prd.json` is an ordered list of atomic stories.

Top-level:
- `run_id`: string
- `title`: string
- `repo_context`: short string (optional)
- `global_verification`: array of strings (optional; commands to run when relevant)
- `loop_settings`: object (optional; loop cadence settings)
- `stories`: array of story objects (ordered)

Story object:
- `id`: string (stable, e.g. "S1", "S2"...)
- `title`: string
- `size`: "XS" | "S" | "M"   (prefer XS/S)
- `passes`: boolean (start false)
- `acceptance_criteria`: array of strings (objective checks)
- `verification_commands`: array of strings (optional; per-story commands to run)
- `depends_on`: array of story IDs (optional)
- `files_expected`: array of strings (optional; helps keep scope tight)
- `notes`: string (optional)

Loop settings object (all optional):
- `global_verify_every_n_stories`: integer (run `global_verification` every N completed stories)
- `review_every_n_iterations`: integer (run review cadence every N iterations)
- `steer_every_n_iterations`: integer (run steering cadence every N iterations)

Rules:
- Each story MUST be completable in one iteration.
- `acceptance_criteria` must be objectively verifiable.
- Stories are ordered by dependency (foundation first).
- If `loop_settings` is absent:
  - run `global_verification` only at the end (if defined)
  - no review/steering cadence is required
