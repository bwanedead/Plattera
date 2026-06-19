# agents.md

## Scope
- Folder: `backend/tooling/mapping/deed_to_ir/`
- Purpose: Mechanical I/O for deed-to-IR — transcript handoff loading, upstream input hydration, IR persistence, artifact listing/hydration.

## Contracts & invariants
- **Mechanical only:** Copy/hydrate/project fields; no semantic inference, blocker authoring, or atom-to-feature conversion.
- **Path-free model output:** Never return filesystem paths in tool results or startup projections.
- **Persistence:** Wrap `FeatureGraphPersistenceService`; do not duplicate artifact storage logic.
- **Ref scheme:** `feature_graph:ir:{artifact_id}` (+ compile/judge/bundle prefixes for future types).

## Commands
- Test: `pytest backend/tooling/mapping/deed_to_ir/ -q`

## Links
- Domain pack: `backend/domains/mapping/deed_to_ir/`
- Feature graph: `backend/feature_graph/`
