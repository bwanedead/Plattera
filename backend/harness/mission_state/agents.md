# agents.md

## Scope
- Folder: `backend/harness/mission_state/`
- Purpose: canonical shared `mission_state` / `resolution_state` contracts for harness continuity.

## Contracts & invariants
- `mission_state` is the top-level continuity object; `resolution_state` is the active organized-work surface inside it.
- Keep the contract generic. Domain-specific meaning belongs in `domain_payload` or in compatibility projections.
- `active_item_id` lives on `resolution_state`, not as a chooser or ranking surface.

## Allowed changes
- Safe: add bounded fields that improve continuity transport or serialization clarity.
- Safe: add compatibility projection helpers for legacy surfaces.
- Avoid: graph-engine logic, ranking/chooser semantics, or domain ontology in shared fields.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/harness/test_run_state.py backend/harness/test_mission_state_contracts.py -q`
- Build/Run: none

## Gotchas
- This folder defines the canonical contract, not the old `work_board` / `decision_ledger` vocabulary.
- Keep legacy compatibility projections thin and explicit.

## Links
- Docs: `docs/architecture/harness/mission-state-and-resolution-state-architecture.md`
- Docs: `docs/architecture/harness/minimal-shared-run-state-envelope.md`
