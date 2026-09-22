# agents.md

## Scope

- Folder: `backend/domains/mapping/transcript_edit/`
- Purpose: Semantic doctrine, payload contracts, tool *declarations*, and projection—no dossier filesystem access.

## Contracts & invariants

- **Domain vs tooling:** Dossier I/O and ref resolution live in `backend/tooling/mapping/transcript_edit/` only.
- **Shared-capability tool surface:** `execution/tool_specs.py` declares tools matching shared `tooling/artifact_capability/` IDs plus domain-owned `initialize_working_transcript`, `copy_forward_save_workspace_artifact`, and `apply_transcript_edits`: `hydrate_artifact_refs`, `transform_artifact`, `initialize_working_transcript`, `save_workspace_artifact`, `copy_forward_save_workspace_artifact`, `apply_transcript_edits`, `publish_workspace_artifact`. `execution/dossier_tool_specs.py` changes only their dossier-mode transport contracts; no fake or spec-only tools.
- **Artifact-progress roles:** Generic harness observability reads this pack's `save_action_ids` and `publish_action_ids`. Do not expect harness code to hard-code transcript-edit write tools. Publication stays a distinct output-tier role. A missing role lane inherits generic defaults; a present empty list or tuple stays empty. This pack declares its ids, so it does not use that fallback.
- **Working-transcript initialization:** `initialize_working_transcript` copies one exact agent-selected T0 draft into working `rev:0001` as an unverified candidate. It does not select among peers, verify text, or earn readings. Empty schema-v2 `transcript_edit_decisions` plus `initialization_provenance` are required; further lane edits use `apply_transcript_edits`. Doctrine (procedural v49 / branch v37 / dossier v3 / startup v6) teaches initialize as the normal economical bootstrap when an exact T0 offers a useful source-shaped baseline; full-save remains available even when a copyable T0 exists. Copy-source selection is not truth ranking. Tool specs keep the mechanical contract.
- **Pack is the semantic surface owner:** `domain_pack.py` declares the mapping-family branch, transcript-edit branch, procedural guidance, semantic tool menu, and closure policy. `runtime_adapter/` may only materialize that declaration with startup inventory and scoped handlers.
- **Startup context is injected, not callable:** `build_startup_context_block` (from `prompting/surfaces/startup_context.py`) formats the startup inventory into a prompt block—there is no `load_transcript_edit_startup_inventory` callable tool.
- **Handlers close over scope:** `build_transcript_edit_tool_bindings(dossier_id, transcription_id, workspace_key)` must be called with explicit scope. LLM requests carry only capability-level inputs.
- **Dossier launch mode:** Dossier machinery is production-reachable only through explicit `transcript_edit_scope_mode="dossier"` selection; the absent selector remains single-transcription mode. `runtime_adapter/adapter.py` selects mode, builds the dossier startup inventory, and packages dossier bindings via `dossier_composition.py` / `dossier_tool_bindings.py` behind the same action IDs.
- **Dossier-mode delegate context refs:** Dossier-mode delegate context refs retain their qualified `dossier_segment` identity; the active dossier hydrator owns validation and leaf resolution. Profile `transcript_edit.visual_source_observation` allows `image`, `artifact`, and `dossier_segment` so generic allowlist checks accept the outer kind while keeping `image` for child image-evidence transport.
- **Dossier prompt delta:** common transcript-edit doctrine remains canonical. Dossier mode adds one driver block plus the ordered dossier startup context; it treats segments as save/evidence lineages inside one instrument and requires explicit per-segment exact revisions for publication.
- **Result views:** `execution/result_views.py` owns hydrate/transform `AgentResultView` payloads. Save/copy/publish stay exact-output only. Point-crop projection lives in `tooling/mapping/transcript_edit/point_crop_set_projection.py` (not harness memory).
- **Refusal retryability:** `runtime_adapter/tool_refusal_boundary.py` is the sole owner of agent-correctable refusal classification for transcript-edit tool bindings (leaf and dossier).
- **Revision-bound edits:** `apply_transcript_edits` owns evidence-linked exact transcript lane edits and `payload.transcript_edit_decisions` provenance (schema_version **2**). Each decision requires `uncertainty_reasons` (canonical vocab; provisional ≥1, earned `[]`). Constants live in `payloads/transcript_edit_decisions.py` (`MAX_DECISIONS_PER_REQUEST` vs larger `MAX_PERSISTED_TRANSCRIPT_EDIT_DECISIONS`). Tooling owns matching/persistence; compact handoff projection is mechanical only. Prompt-visible request grammar is the shared `APPLY_TRANSCRIPT_EDITS_*_REQUEST_SHAPE` in `execution/tool_specs.py` (dossier adds qualification only via `dossier_tool_specs.py`); do not replace it with “same leaf contract” shorthand. Wrong-nesting refusals (`unknown_decision_fields` when `lane`/`expected_text`/`replacement_text` sit on the decision) carry a stable nesting `repair_hint` without leaking source text. Hints are transport-only — `tool_refusal_boundary.py` alone classifies retryability; tooling must not derive `retryable` from hint presence.
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
- All tool handlers extract inputs via `request.inputs` (not `dict(request)`) to support both `ExecutionStepRequest` and direct dict calls.
- Leaf `surface.blocks` has 4 entries. Dossier mode adds `transcript_edit_dossier_guidance` before its startup context.

## Links

- Tooling: `backend/tooling/mapping/transcript_edit/`
- Spec: `docs/transcription-dossier-system-spec.md`
