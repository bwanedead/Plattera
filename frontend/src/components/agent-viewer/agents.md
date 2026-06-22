# agents.md

## Scope
- Folder: `frontend/src/components/agent-viewer/`
- Purpose: Native universal Agent Viewer only — run shell, transport, normalization, registry, panels, and renderers.

## Contracts & invariants
- UI work in this folder must not edit `backend/harness/`, active domain packs, or domain tooling.
- Do not touch host workspaces (image processing, text-to-schema, mapping, etc.); they import `AgentViewerPanel` only.
- **Native-only:** delete legacy viewer code instead of keeping parallel or adapter-wrapped old paths.
- Closing/unmounting a viewer detaches presentation only; it must never stop, pause, or cancel the underlying run.
- Shell is composition only. Transport in hooks/services. Normalization in `model/`. Rendering via registries.
- Unknown kinds must fall back safely with raw/provenance access.

## Allowed changes
- Add focused modules under `shell/`, `model/`, `registry/`, `renderers/`, `panels/`, `hooks/`, `transport/`, `selection/`.
- Extend `AgentViewerPanel` only as the stable workspace import; implementation stays native shell + `useAgentViewerRun`.

## Commands
- Replay dev page: `npm --prefix frontend run dev` → `/agent-viewer/`
- Live overlay: opened from host workspaces via `AgentViewerPanel`
- Build: `npm --prefix frontend run build`
- Contract tests: `cd frontend && npx tsx --test src/components/agent-viewer/model/eventIdentity.test.mjs`

## Gotchas
- `AgentViewerPanelProps` includes workspace-owned fields (`transcriptionDrafts`, `isTranscribing`) that the viewer intentionally ignores.
- Replay fixture symlink: `frontend/public/agent-viewer-replay` → `docs/ui-agent-resources/fixtures/`

## Links
- Docs: `docs/architecture/agent-viewer-product-vision.md`
- Docs: `docs/architecture/agent-viewer-v1.md`
- Docs: `docs/ui-agent-resources/platform-viewer-contract.md`
