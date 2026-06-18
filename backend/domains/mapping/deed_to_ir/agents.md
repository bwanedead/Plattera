# agents.md

## Scope
- Folder: `backend/domains/mapping/deed_to_ir/`
- Purpose: Semantic doctrine, startup handoff payloads, tool declarations, and projection for deed-to-IR work — no dossier filesystem access.

## Contracts & invariants
- **Domain vs tooling:** Transcript-edit output loading lives in `backend/tooling/mapping/deed_to_ir/` only.
- **Brief A skeleton:** No IR save/compile/judge tools yet; `execution/tool_specs.py` may declare zero tools intentionally.
- **Pack is the semantic surface owner:** `domain_pack.py` declares mapping-family branch, deed-to-IR branch, procedural guidance, startup context, and closure/handoff semantics.
- **Startup handoff is injected, not inferred:** Loader copies transcript-edit output fields mechanically; it does not decide forwardability, blockers, or IR meaning.
- **`runtime_adapter/`** is the only harness-facing seam; it must not author mission state, closure, inventory, blockers, or IR.

## Allowed changes
- Prompt/tool-spec updates that keep closure layers and mapping purpose intact.
- New semantic payload dataclasses under `payloads/` when they stay non-orchestrating.
- Adding real tool specs once save/compile/judge implementations exist.

## Commands
- Test: from repo root, venv active: `pytest backend/domains/mapping/deed_to_ir/ -q`

## Gotchas
- Launch context for Brief A accepts explicit `transcript_edit_output_path`; ref-based resolution is follow-up.
- `transcript_edit_output_path` is loader input only — never project raw filesystem paths to startup prompt or handoff payload; use `loaded_source_label`, `source_revision_ref`, and `published_at`.
- Empty tool surface is valid for Brief A — tests assert intentional zero-tool binding.

## Links
- Tooling: `backend/tooling/mapping/deed_to_ir/`
- Upstream: `backend/domains/mapping/transcript_edit/`
- Feature graph: `backend/feature_graph/`
