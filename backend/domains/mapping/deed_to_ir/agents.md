# agents.md

## Scope
- Folder: `backend/domains/mapping/deed_to_ir/`
- Purpose: Semantic doctrine, startup handoff payloads, tool declarations, and projection for deed-to-IR work — no dossier filesystem access.

## Contracts & invariants
- **Domain vs tooling:** Transcript-edit output loading, input hydration, and IR persistence live in `backend/tooling/mapping/deed_to_ir/` only.
- **Eight foundation tools:** `hydrate_deed_to_ir_input`, `describe_feature_graph_capabilities`, `save_ir_artifact`, `patch_ir_draft`, `submit_ir_for_mapping`, `finalize_current_deed_to_ir_output`, `hydrate_artifact_refs`, `list_feature_graph_artifacts`.
- **Semantic-head result views:** The four state-advancing deed-to-IR tools share a provider-owned `deed_to_ir.current_working_head:<sha256(scope)>` continuity key; artifact refs remain historical identities, not continuity keys.
- **Sole live finalization action:** `finalize_current_deed_to_ir_output`. Lower-level prepare/publish functions are internal compatibility primitives only — not agent-facing tools.
- **Completion ownership:** Outer `DomainClosurePolicy.publish_action_ids` is empty so partial finalizer calls are not generic pre-dispatch publish attempts. Nested `CompletionAnchorPolicy.publish_action_ids` recognizes successful finalizer publication.
- **Mapping submission is one action:** `submit_ir_for_mapping` internally compiles, judges, and renders; those are not separate agent workflow actions.
- **Pack is the semantic surface owner:** `domain_pack.py` declares mapping-family branch, deed-to-IR branch, procedural guidance, startup context, and closure/handoff semantics.
- **Startup handoff is injected, not inferred:** Loader copies transcript-edit output fields mechanically; resolution state arrives via explicit launch-context snapshot.
- **`runtime_adapter/`** is the only harness-facing seam; it must not author mission state, closure, inventory, blockers, or IR.

## Allowed changes
- Prompt/tool-spec updates that keep closure layers and mapping purpose intact.
- New semantic payload dataclasses under `payloads/` when they stay non-orchestrating.
- Provenance link shapes on feature-graph nodes/edges via `ProvenanceAttachment.source_entity_links`.

## Commands
- Test: from repo root, venv active: `pytest backend/domains/mapping/deed_to_ir/ -q`
- Tooling tests: `pytest backend/tooling/mapping/deed_to_ir/ -q`

## Gotchas
- Launch context accepts explicit `transcript_edit_output_path` and optional paired `resolution_state_ref` with either inline `resolution_state_snapshot` or `resolution_state_snapshot_path` (mutually exclusive).
- `resolution_state_ref` must pair with exactly one snapshot source; ref must use `transcript_edit:resolution_state:*`.
- `transcript_edit_output_path` and `resolution_state_snapshot_path` are loader input only — never project raw filesystem paths to startup prompt or handoff payload.
- Startup prompt shows resolution counts/summary; full graph is via `hydrate_deed_to_ir_input`.
- Agent authors all `source_entity_links`; deterministic code must not infer atom-to-feature associations.

## Links
- Tooling: `backend/tooling/mapping/deed_to_ir/`
- Upstream: `backend/domains/mapping/transcript_edit/`
- Feature graph: `backend/feature_graph/`
