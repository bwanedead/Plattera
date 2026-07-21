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
- **Preview publish idempotency:** Under the output publish lock, if latest pointer
  `final_package_preview_ref` matches the request, replay the stored revision
  (`idempotent_replay=true`) or refuse with `published_preview_replay_state_invalid`
  (missing/invalid revision or mapping/IR selection conflict). Never allocate a
  duplicate revision for that matching preview. Direct/legacy publish omits the
  pointer field. Idempotency is latest-pointer-scoped (a newer published preview
  supersedes prior matching). Replay validates mapping/IR selection only.
- **Preview lineage in artifact_refs:** Preview-backed publication places the same
  immutable `final_package_preview_ref` in top-level `artifact_refs` (exactly once)
  so harness `latest_refs` can satisfy completion-anchor preview lineage.

## Commands
- Test: `pytest backend/tooling/mapping/deed_to_ir/ -q`
- Live launch: see `docs/architecture/harness/deed-to-ir-live-loop-testing.md`

## Gotchas
- `resolution_state_snapshot_path` loads JSON mechanically and pairs with `resolution_state_ref`; mutually exclusive with inline `resolution_state_snapshot`.
- Scope helpers live in `resolution_scope.py`: operands use first-match `infer_scope_id_from_identifiers`; dependency candidates use conflict-aware `resolve_unambiguous_scope_id` (conflict → omit candidate + diagnostic only).
- Dependency include/decline mechanics live in `dependency_decisions.py`, not `intent_first_prepare.py`.
- Unified missing-lane detection lives in `intent_first_preflight.py`; prepare expands rows only after all required lanes are present.
- Retry continuity: `missing_finalization_decisions` refusals emit the decision
  card and `retry_request_template` (and finalizer `outputs.missing` /
  `active_finalization_session` when applicable). Read those from
  `latest_action_results` — do not invent IDs or hydrate just to recover them.
- Live prompt seam: `manifest.prompt_runtime_projection_module_ref` →
  `domains.mapping.deed_to_ir.state.prompt_runtime_projection` projects active + historical
  lineage into `run_context.domain_runtime_projection` each choose_action turn. Emits
  `hot_artifact_refs` / `cold_artifact_refs` for mechanical exact-ref windowing. Historical
  classification uses only work-item `evidence_refs` mapping/IR refs; no status mutation.
- Finalization session: workspace sidecar `finalization_session.json` (same identity as
  `current_mapping_lineage.json`). Model `finalization_session.py`, scope inventory
  `finalization_scope_inventory.py`, lifecycle `finalization_session_persistence.py`.
  Successful `submit_ir_for_mapping` replaces the session; newer IR write marks it stale.
  Prompt projects compact `active_finalization_session` for pending_decisions,
  preview_ready, and published (stale excluded). Decisions never migrate across
  lineages; empty scope inventory persists `scope_inventory_unavailable`.
  Sole live finalization action: `finalize_current_deed_to_ir_output`
  (`finalization_decisions.py` + `finalize_current_output.py`). Lower-level
  prepare/publish functions are internal compatibility primitives only.
  Compact decisions include agent-authored `closure_statuses` for the four
  fixed closure dimension IDs (`closed|partial|blocked`); partial/blocked
  require a matching rationale. Session schema is
  `deed_to_ir.finalization_session.v2` — prior sessions refuse with
  `finalization_session_invalid` (remap); no closed backfill.
  Partial finalizer calls are not generic pre-dispatch publish attempts;
  successful finalizer publication is the completion-anchor event and may
  complete the run in the same turn when the domain anchor is satisfied.
  Finalizer agent-visible results are normalized by `finalizer_result_boundary.py`:
  reason-aware next-action routing (finalize vs submit_ir_for_mapping vs HITL/none);
  never invent a next tool for unknown refusals; preserve reason-specific repair
  prerequisites while scrubbing retired prepare/publish IDs/prose.
  Canonically recoverable publisher refusals (`publication_in_progress`,
  `final_pointer_write_failed`, unusable-preview codes) are reclassified to
  retryable at this boundary even when internal publish emitted invariant refusals.
  Agent-facing preview hydration omits `working_preview_ref`,
  `recommended_publish_request`, and `preview_ready_summary` (internal prepare
  outputs may still emit them).
- `projection_module_ref` remains the normal state-projection module slot (unused for deed-to-IR).
- Without usable current lineage, work items are left unclassified (never forced historical).


## Links
- Domain pack: `backend/domains/mapping/deed_to_ir/`
- Feature graph: `backend/feature_graph/`
