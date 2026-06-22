# Agent Viewer Implementation Worklist

Status: living plan for `cursor/universal-agent-viewer-ui-848b`.

## Completed

- [x] Native-only viewer (legacy prototype deleted)
- [x] Replay transport + normalization seam
- [x] Live transport via `useAgentViewerRun`
- [x] Universal shell (activity, canvas, resolution/inventory)
- [x] Canvas renderer registry + domain adapter registration
- [x] Generic HITL interaction tray (snapshot-first)
- [x] Attention strip, outcome panel, raw inspection
- [x] Work item inspector (generic resolution projection)
- [x] Transcript-edit domain canvas renderer (registered, not shell-branched)
- [x] Action registry + `useAgentViewerActions`
- [x] Session reset on `sessionKey` change in `AgentViewerPanel`
- [x] `useAgentViewerShellState` (selection, raw, observability drawer)
- [x] Observability drawer (timing, tokens, delegate counts)
- [x] Chapter rail / handoff markers
- [x] Delegate activity lane badge in timeline
- [x] Keyboard Escape to close overlay
- [x] **Temporal replay projection** (`loading | available | unavailable`) — no final/prior-state leak
- [x] **HITL lifecycle** — submitted ≠ consumed; pending acknowledgment UI
- [x] **Replay interaction lane** — feedback.json + turn HITL exchanges projected chronologically
- [x] **Ref-counted log bridge** for concurrent viewers
- [x] **Strict action handler resolution** — unsupported kinds fail visibly
- [x] Contract tests + `npm run test:agent-viewer`
- [x] Split `agentViewerShell.css` into focused modules

## Next

### Architecture hardening
- [ ] Mission-thread navigator (viewer-owned run list; needs transport contract)
- [ ] Multi-run instance switcher (needs live run inventory API)

### Domain renderers (registered only)
- [ ] Image locator / crop renderer
- [ ] Diff renderer
- [ ] GeoJSON / map artifact renderer
- [ ] Deed-to-IR artifact presenters

### Quality
- [ ] Keyboard focus trap inside overlay dialog
- [ ] Wire `test:agent-viewer` into CI/check flow

## Non-goals (this branch)

- Editing harness or domain packs
- Refactoring host workspaces
- Embedding mapping/schema workflows inside the viewer
