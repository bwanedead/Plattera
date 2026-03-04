# agents.md

## Scope
- Folder: `frontend/src/components/agent-viewer/`
- Purpose: Agent Viewer UI composition, event timeline rendering, canvas presentation, and feedback actions.

## Contracts & invariants
- Keep `AgentViewerPanel.tsx` as orchestration/composition only: state wiring, mode switching, and top-level layout.
- Canvas rendering belongs in dedicated canvas components; sidebar rendering belongs in sidebar components.
- Stream/event transport and feedback API behavior should stay in hooks under `hooks/`, not in presentational components.
- Additive payload compatibility is required for agent-viewer events (`phase/detail/stream_kind` fields).

## Allowed changes
- Safe: extract render-heavy sections into focused components with stable props.
- Safe: add utility helpers in `agentViewerUtils.ts` for shared formatting/extraction logic.
- Avoid: reintroducing multi-concern logic into `AgentViewerPanel.tsx`.
- Avoid: coupling presentational components directly to API calls when hooks already own that behavior.

## Commands
- Build: `.venv\scripts\activate.ps1; npm --prefix frontend run build`
- Test: `.venv\scripts\activate.ps1; pytest backend/api/test_agent_viewer_endpoints.py -q`

## Gotchas
- `next build` currently skips type-checking/lint; compile success does not guarantee TypeScript safety.
- Keep fallback behavior intact for missing artifacts (live draft and transcript fallback path).

## Links
- Docs: `docs/ethos/architecture-ethos.md`
- Related code: `frontend/src/components/agent-viewer/hooks/`
