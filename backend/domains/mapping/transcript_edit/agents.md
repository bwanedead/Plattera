# agents.md

## Scope
- Folder: `backend/domains/mapping/transcript_edit/`
- Purpose: Native transcript-edit domain-pack semantics on top of the shared harness.

## Contracts & invariants
- Domain-pack code here owns semantics only: doctrine, domain state authority, projection/read models, focus hydration, move resolution, execution translation, closure, feedback meaning, and handoff posture.
- Deterministic transcript-edit capability code belongs in `backend/tooling/mapping/transcription_edit/`.
- Workflow/application support belongs in `backend/services/workflows/mapping/transcription_edit/`.
- Agent Kernel action ids (`TX_*`) remain the only execution path; do not add controller-style direct execution here.
- Preserve `domain_pack.py` as a thin host seam; keep state authority split across dedicated modules such as `decision_ledger*.py`, `blocker_registry*.py`, and `state_projection.py`.
- Prompt doctrine belongs in `prompt_sources.py`, `prompting.py`, and `orient_prompts.py`, not in workflow services or shared harness code.
- `decision_ledger_focus.py` is legacy-named compatibility logic inside the pack only; do not let it regrow as deterministic focus truth.
- `work_board_*` and emergent-board helpers are still migration-risk surfaces; prefer shrinking or deleting them over expanding them.

## Allowed changes
- Safe: tighten semantic boundaries, simplify pack surfaces, improve read models, and delete compatibility residue.
- Safe: move non-semantic helpers out to tooling or workflow services when responsibility is clear.
- Do not add controller/runtime species, compatibility wrappers, or product/provider composition directly into this pack.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/api/test_transcript_edit_agent_endpoints.py backend/services/test_run_inspection_service.py -q`
- Other: `.venv\scripts\activate.ps1; python -m api.mission_runtime_cli --help`

## Gotchas
- `edit_plan` is optional; terminalization must stay honest when unresolved closure items remain.
- Keep feedback transport assumptions out of the pack; only feedback meaning belongs here.
- If changing event payloads or run-feed persistence, update `backend/services/workflows/mapping/transcription_edit/`, not this folder.
- If changing deterministic edit/apply validation, update `backend/tooling/mapping/transcription_edit/`, not this folder.

## Links
- Related code: `backend/domains/common/`
- Related code: `backend/services/workflows/mapping/transcription_edit/`
- Related code: `backend/tooling/mapping/transcription_edit/`

