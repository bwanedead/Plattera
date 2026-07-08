# agents.md

## Scope
- Folder: `backend/tooling/mapping/deed_to_ir/`
- Purpose: Mechanical I/O for deed-to-IR — transcript handoff loading, upstream input hydration, IR persistence, artifact listing/hydration.

## Contracts & invariants
- **Mechanical only:** Copy/hydrate/project fields; no semantic inference, blocker authoring, or atom-to-feature conversion.
- **Path-free model output:** Never return filesystem paths in tool results or startup projections.
- **Persistence:** Wrap `FeatureGraphPersistenceService`; do not duplicate artifact storage logic.
- **Ref scheme:** `feature_graph:ir:{artifact_id}` (+ compile/judge/bundle prefixes for future types).
- **Capability contract:** Derive compact field inventories from Pydantic models and operation details from `OPERATION_REGISTRY`; keep authored examples in `feature_graph_examples.py` schema-valid and compiler-tested.
- **Course repair:** `patch_ir_draft.course_updates` surgically edits one CourseTraverse row (1-based `course_index`); agent authors `value` — never infer corrected deed values.
- **Draft patch targets:** `draft_patch_targets` / `patch_update_shells` are mechanical bridges from course-leg facts to patch locations; placeholders only, no corrected values.

## Commands
- Test: `pytest backend/tooling/mapping/deed_to_ir/ -q`
- Live launch: see `docs/architecture/harness/deed-to-ir-live-loop-testing.md`

## Gotchas
- `resolution_state_snapshot_path` loads JSON mechanically and pairs with `resolution_state_ref`; mutually exclusive with inline `resolution_state_snapshot`.

## Links
- Domain pack: `backend/domains/mapping/deed_to_ir/`
- Feature graph: `backend/feature_graph/`
