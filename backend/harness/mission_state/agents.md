# agents.md

## Scope
- Folder: `backend/harness/mission_state/`
- Purpose: canonical shared `mission_state` / `resolution_state` contracts for harness continuity.

## Contracts & invariants
- `mission_state` is the top-level continuity object; `resolution_state` is the active organized-work surface inside it.
- Keep the contract generic. Domain-specific meaning belongs in `domain_payload`, not in harness-owned translation layers.
- `active_item_id` lives on `resolution_state`, not as a chooser or ranking surface.
- Top-level `harness.mission_state` exports are contract-only: versions, models, constructors, and recent-activity shaping.
- Resolution lifecycle helpers and update normalizers must be imported from their explicit submodules.

## Allowed changes
- Safe: add bounded fields that improve continuity transport or serialization clarity.
- Avoid: graph-engine logic, ranking/chooser semantics, domain ontology, or new retired-shape teaching in shared fields.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/harness/test_run_state.py backend/harness/test_mission_state_contracts.py -q`
- Build/Run: none

## Gotchas
- This folder defines the canonical contract; keep older organized-work dialects out of shared naming and APIs.
- Do not reintroduce deleted projection layers as native expectations.

## Links
- Docs: `docs/architecture/harness/mission-state-and-resolution-state-architecture.md`
- Docs: `docs/architecture/harness/minimal-shared-run-state-envelope.md`
