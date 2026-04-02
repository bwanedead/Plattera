# agents.md

## Scope

- Folder: `backend/domains/mapping/transcript_edit/`
- Purpose: Semantic doctrine, payload contracts, tool *declarations*, and projection—no dossier filesystem access.

## Contracts & invariants

- **Domain vs tooling:** Dossier I/O and ref resolution live in `backend/tooling/mapping/transcript_edit/` only.
- **Startup payloads** (`payloads/startup_inventory.py`) are ref-first inventories for model-facing assembly—not persistence services, no “next action” scripting, no draft ranking.
- **FinalSelectionPosture** uses `authored_transcript_edit_ref` (not legacy head pointers) for the agent-authored draft; `selected_final_ref` remains for pinned segment finals when applicable.

## Allowed changes

- Prompt/tool-spec updates that keep closure layers and mapping purpose intact.
- New semantic payload dataclasses under `payloads/` when they stay non-orchestrating.

## Commands

- Test: from `backend/`, venv active: `pytest domains/mapping/transcript_edit/test_transcript_edit_pack.py -q`

## Gotchas

- Tool specs describe intent only; runtime wiring may lag—mark deferred tools honestly in `execution/tool_specs.py`.

## Links

- Tooling: `backend/tooling/mapping/transcript_edit/`
- Spec: `docs/transcription-dossier-system-spec.md`
