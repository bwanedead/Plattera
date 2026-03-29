# agents.md

## Scope
- Folder: `backend/agent_kernel/`
- Purpose:
  - Step-driven kernel runtime plus concrete tool implementations.
  - Stable facade imports in `tooling.py` for generic/kernel-owned tooling only.

## Contracts & invariants
- Keep `backend/agent_kernel/tooling.py` as the stable import facade for callers/tests **for tools it actually exports**.
- Preserve tool class names, action reason codes, payload keys, and artifact-ref behavior.
- Keep helper ownership clear: generic/kernel-owned tooling only. Deleted domain-specific tooling should not be reintroduced here casually.
- Keep source modules below monolith thresholds; split again before crossing 900-1000 lines.

## Allowed changes
- Safe: internal refactors inside `tooling_*` modules that preserve public behavior.
- Safe: additive helper extraction into dedicated sibling modules (for size/boundary hygiene).
- Do not change casually: `actions.py` wiring contracts or public symbols imported from `tooling.py`.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/agent_kernel/test_tooling.py -q`
- Lint: `N/A`
- Build/Run: `N/A`
- Other: `.venv\scripts\activate.ps1; pytest backend/agent_kernel -q`

## Gotchas
- `tooling.py` is intentionally a thin re-export layer; implementation logic belongs in `tooling_*` modules.
- If extracting helpers, preserve decorator lines and constructor signatures (`@dataclass`) when moving classes.

## Links
- Docs: `docs/ethos/architecture-ethos.md`
- Related code: `backend/agent_kernel/tooling.py`
- Related code: `backend/agent_kernel/tooling_feature_graph.py`
