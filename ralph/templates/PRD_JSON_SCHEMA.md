# prd.json Schema (Human-readable)

`prd.json` is an ordered list of atomic stories.

Top-level:
- `run_id`: string
- `title`: string
- `repo_context`: short string (optional)
- `global_verification`: array of strings (optional; commands to run when relevant)
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

Rules:
- Each story MUST be completable in one iteration.
- `acceptance_criteria` must be objectively verifiable.
- Stories are ordered by dependency (foundation first).


