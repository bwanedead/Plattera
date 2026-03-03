# agents.md

## Scope
- Folder: `frontend/`
- Purpose: UI composition, viewer/workspace behavior, and client-side orchestration.

## Contracts & invariants
- Separation of concerns is mandatory: avoid mixing stream transport, domain state, render composition, and interaction workflows in one file.
- Before extending a feature, ask: "Should these edits be separated into dedicated modules of responsibility?"
- If yes, define the target architecture first (state hooks, presentation components, utilities, API adapters) and then implement.

## Allowed changes
- Safe: split large components into focused hooks/components/utilities with stable props/contracts.
- Safe: add lightweight local `agents.md` files in high-churn subfolders (for example `src/components/agent-viewer/`) when they prevent repeat monolith growth.
- Avoid piling new behavior into already large files when the concern can be isolated cleanly.

## Commands
- Build: `.venv\scripts\activate.ps1; npm --prefix frontend run build`
- Run: `.venv\scripts\activate.ps1; npm --prefix frontend run dev`

## Gotchas
- "Works now" is not sufficient if structure degrades; prefer modular changes that keep future edits and pivots cheap.
- Design for rewind/pivot: isolate responsibilities so features can be changed or removed without destabilizing adjacent behavior.
- Avoid massive spaghetti piles. If a change spans unrelated concerns, split it before shipping.

## Links
- Docs: `docs/ethos/architecture-ethos.md`
- Docs: `docs/ethos/structure-ethos.md`
- Related code: `frontend/src/components/`
