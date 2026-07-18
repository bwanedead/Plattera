# agents.md

## Scope

- Folder: `backend/domains/mapping/transcript_edit/`
- Purpose: Semantic doctrine, payload contracts, tool *declarations*, and projection—no dossier filesystem access.

## Contracts & invariants

- **Domain vs tooling:** Dossier I/O and ref resolution live in `backend/tooling/mapping/transcript_edit/` only.
- **Shared-capability tool surface:** `execution/tool_specs.py` declares exactly 5 tools matching `tooling/artifact_capability/` IDs: `hydrate_artifact_refs`, `transform_artifact`, `save_workspace_artifact`, `copy_forward_save_workspace_artifact`, `publish_workspace_artifact`. No fake or spec-only tools.
- **Pack is the semantic surface owner:** `domain_pack.py` declares the mapping-family branch, transcript-edit branch, procedural guidance, semantic tool menu, and closure policy. `runtime_adapter/` may only materialize that declaration with startup inventory and scoped handlers.
- **Startup context is injected, not callable:** `build_startup_context_block` (from `prompting/surfaces/startup_context.py`) formats the startup inventory into a prompt block—there is no `load_transcript_edit_startup_inventory` callable tool.
- **Handlers close over scope:** `build_transcript_edit_tool_bindings(dossier_id, transcription_id, workspace_key)` must be called with explicit scope. LLM requests carry only capability-level inputs.
- **Result views:** `execution/result_views.py` owns hydrate/transform `AgentResultView` payloads. Save/copy/publish stay exact-output only. Point-crop projection lives in `tooling/mapping/transcript_edit/point_crop_set_projection.py` (not harness memory).
- **TranscriptEditAuthoredDraftPosture** (`working_draft_ref` / `output_draft_ref`) models the agent-authored draft only. `selected_final_ref` is not part of the domain shape.
- `runtime_adapter/` is the only harness-facing seam; it must not author mission-state, closure, ranking, or undeclared prompt/tool truth.

## Allowed changes

- Prompt/tool-spec updates that keep closure layers and mapping purpose intact.
- New semantic payload dataclasses under `payloads/` when they stay non-orchestrating.
- Adding new sub-actions to `transform_artifact` (implemented in `tooling/mapping/transcript_edit/artifact_transform.py`).

## Commands

- Test: from `backend/`, venv active: `pytest domains/mapping/transcript_edit/ -q`

## Gotchas

- `build_transcript_edit_tool_bindings()` now requires `dossier_id`, `transcription_id`, `workspace_key` kwargs — no positional args.
- All 4 tool handlers extract inputs via `request.inputs` (not `dict(request)`) to support both `ExecutionStepRequest` and direct dict calls.
- `surface.blocks` has 4 entries: mapping family, domain branch, procedural guidance, startup context. Tests that hardcode block count must use `== 4`.

## Links

- Tooling: `backend/tooling/mapping/transcript_edit/`
- Spec: `docs/transcription-dossier-system-spec.md`
