# agents.md

## Scope
- Folder: `backend/agent_kernel/`
- Purpose:
  - Step-driven kernel runtime plus concrete tool implementations.
  - Stable facade imports in `tooling.py` with implementation split by domain modules.

## Contracts & invariants
- Keep `backend/agent_kernel/tooling.py` as the stable import facade for callers/tests **for tools it actually exports**.
- **Transcript orient (Phase 30):** `TranscriptOrientBaselineTool` is defined in `agents/transcript_edit/orient_tool.py` only. It is **not** imported from `tooling.py` (avoids cycles). `KernelSessionManager` wires it via a lazy import in `session.py`. Optional lazy re-export: `tooling_transcript_orient` (`__getattr__`).
- Preserve tool class names, action reason codes, payload keys, and artifact-ref behavior.
- Keep helper ownership by domain: corpus/text spans/transcript core/orient/image/feature graph/retrieval/artifacts.
- Keep source modules below monolith thresholds; split again before crossing 900-1000 lines.

## Allowed changes
- Safe: internal refactors inside `tooling_*` modules that preserve public behavior.
- Safe: additive helper extraction into dedicated sibling modules (for size/boundary hygiene).
- Do not change casually: `actions.py` wiring contracts or public symbols imported from `tooling.py`.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/agent_kernel/test_tooling.py backend/agent_kernel/test_transcript_tooling.py backend/agent_kernel/test_import_phase30.py -q`
- Lint: `N/A`
- Build/Run: `N/A`
- Other: `.venv\scripts\activate.ps1; pytest backend/agent_kernel -q`

## Gotchas
- `tooling.py` is intentionally a thin re-export layer; implementation logic belongs in `tooling_*` modules.
- If extracting helpers, preserve decorator lines and constructor signatures (`@dataclass`) when moving classes.

## Links
- Docs: `docs/ethos/architecture-ethos.md`
- Related code: `backend/agent_kernel/tooling.py`
- Related code: `backend/agent_kernel/tooling_feature_graph.py`
- Related code: `backend/agent_kernel/tooling_transcript_image.py`
