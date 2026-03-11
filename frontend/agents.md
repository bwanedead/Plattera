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
- Safe: extend lint/static-governance rules when they are cheap, deterministic, and clearly protect architecture.
- Avoid piling new behavior into already large files when the concern can be isolated cleanly.

## Commands
- Lint: `.venv\scripts\activate.ps1; npm --prefix frontend run lint`
- Typecheck: `.venv\scripts\activate.ps1; npm --prefix frontend run typecheck`
- Governance: `.venv\scripts\activate.ps1; npm --prefix frontend run governance`
- Build: `.venv\scripts\activate.ps1; npm --prefix frontend run build`
- Run: `.venv\scripts\activate.ps1; npm --prefix frontend run dev`

## Gotchas
- "Works now" is not sufficient if structure degrades; prefer modular changes that keep future edits and pivots cheap.
- Use `npm --prefix frontend run governance` before shipping frontend-heavy changes; it guards page-boundary violations, test placement drift, and growth in known monolith hotspots.
- Read `docs/linting/static-governance.md` before changing the governance rules or relaxing an allowlist; exceptions should stay explicit and justified.
- Design for rewind/pivot: isolate responsibilities so features can be changed or removed without destabilizing adjacent behavior.
- Avoid massive spaghetti piles. If a change spans unrelated concerns, split it before shipping.

## Links
- Docs: `docs/ethos/architecture-ethos.md`
- Docs: `docs/ethos/structure-ethos.md`
- Docs: `docs/linting/static-governance.md`
- Related code: `frontend/src/components/`
