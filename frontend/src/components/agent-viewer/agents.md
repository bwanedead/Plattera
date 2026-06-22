# agents.md

## Scope
- Folder: `frontend/src/components/agent-viewer/`
- Purpose: Generic Agent Viewer UI substrate: run shell, renderer registry, event/activity display, artifact/evidence presentation, work graph inspection, HITL capture, and viewer actions.

## Contracts & invariants
- UI work in this folder must not edit `backend/harness/`, active domain packs, or domain tooling. Treat those systems as read-only and keep compatibility work at the viewer-owned intake/normalization seam.
- Closing/unmounting a viewer detaches presentation only; it must never stop, pause, or cancel the underlying run.
- Keep product scope (currently often dossier), mission thread, run/job, chapter/handoff, participant, and turn identities distinct. Product adapters supply dossier navigation; the generic shell does not make dossier harness ontology.
- Contextual feedback may anchor to resolution items, artifacts, evidence, actions, or canvas selections, but submission must remain pending until transport/agent lifecycle confirms later posture.
- Treat the existing panel as prototype/reference unless a future implementation deliberately keeps it. Do not preserve old structure just because it exists.
- The viewer shell is composition only: layout, selected view, and child wiring. No transport, raw event scanning, or domain interpretation in shell components.
- Transport and feedback API behavior stay in hooks/services; presentational components receive typed view models and callbacks.
- Normalization from raw backend payloads into UI models belongs under a model/adapter layer, not inside renderers or panels.
- Domain-specific artifact/evidence/work-item views must be registered renderers or adapters, not hardcoded branches in the generic shell.
- HITL UI captures and submits answers only; it must not imply semantic incorporation or resolution after submit.
- Unknown artifact/evidence/action kinds must fall back safely without hiding payloads.

## Allowed changes
- Safe: add focused `shell/`, `model/`, `registry/`, `renderers/`, `panels/`, `hooks/`, `transport/`, and `selection/` modules when the responsibility is real.
- Safe: port useful prototype behavior into the new structure when it fits the generic model.
- Avoid: growing `AgentViewerPanel.tsx`, `agentViewerUtils.ts`, or one large renderer as a catch-all.
- Avoid: adding deed/transcript/PLSS/mapping fields to shared viewer types; use generic fields plus opaque domain payload.

## Commands
- Replay dev page: `npm --prefix frontend run dev` then open `/agent-viewer/`
- Build: `.venv\scripts\activate.ps1; npm --prefix frontend run build`
- Typecheck: `.venv\scripts\activate.ps1; npm --prefix frontend run typecheck`
- Governance: `.venv\scripts\activate.ps1; npm --prefix frontend run governance`

## Gotchas
- `next build` currently skips type-checking/lint; compile success does not guarantee TypeScript safety.
- The viewer is a control plane/read model, not a harness semantic authority.
- SSE is for immediacy; a durable snapshot should be the source of truth for reconnect/replay.
- Keep existing human-centered workspaces intact; viewer actions should bridge to them rather than absorbing them.

## Links
- Docs: `docs/architecture/agent-viewer-product-vision.md`
- Docs: `docs/architecture/agent-viewer-v1.md`
- Docs: `docs/architecture/harness/harness-constitution.md`
- Docs: `docs/architecture/harness/hitl-constitution.md`
- Related code: `frontend/src/components/agent-viewer/hooks/`
