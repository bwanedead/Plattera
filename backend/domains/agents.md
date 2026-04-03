# agents.md

## Scope

- Folder: `backend/domains/`
- Purpose: Bounded **semantic** domain packs (doctrine, state meaning, projection lens, semantic tool declarations, closure/handoff meaning) on top of the generic harness—never a second runtime.

## Contracts & invariants

- **Harness** (`backend/harness/`) owns loop/run mechanics, continuity, tool execution rails, tracing, run summary, review.
- **Domains** (`backend/domains/`) own mission doctrine, semantic state meaning, projections, semantic tool **menus** (declarations only), closure/handoff/feedback **meaning**, and a thin harness-facing adapter **only if needed**.
- **Tooling** (`backend/tooling/`) owns concrete tool handlers, service integration, persistence, image/compare/mutate/refresh logic.
- `manifest.py` = identity and declaration only (no meaningful logic). `domain_pack.py` = thin index/bundle, not a controller. `prompting/branch.py` = canonical doctrine source for prompt text; extra domain-local guidance surfaces live under `prompting/surfaces/` only when earned.
- Semantic mission **facets** (e.g. orient / investigate / repair / verify / handoff) are vocabulary for doctrine and semantics—not a scripted domain pipeline or state machine.
- Prefer **deletion over compatibility** for dead domain residue; do not preserve parallel “museum” packs.
- Add optional modules (`state/hydration.py`, `execution/translator.py`, `semantics/feedback.py`, `prompting/surfaces/`, `runtime_adapter/`) only when earned.

## Allowed changes

- Add or refine domain doctrine, earned prompt guidance under `prompting/surfaces/`, `state/contracts.py`, `state/projection.py`, `state/projection_coerce.py`, `execution/tool_specs.py`, `semantics/*`.
- New domains follow the default first-cut tree in `docs/architecture/harness/domain-pack-architecture.md` §2.1.

## Commands

- Test (harness smoke): `.venv\scripts\activate.ps1; cd backend; pytest harness/test_architecture_guardrails.py -q`
- Test (transcript_edit pack): `.venv\scripts\activate.ps1; cd backend; pytest domains/mapping/transcript_edit/test_transcript_edit_pack.py -q`
- Docs: `docs/architecture/harness/domain-pack-constitution.md`, `domain-pack-architecture.md`, `transcript-edit-domain.md`

## Gotchas

- If code looks like orchestration, polling, HTTP, or file I/O, it belongs in **tooling** or API layers—not here.
- Do not import dossier services, LLM clients, or FastAPI routers from domain packs.

## Patterns

- Standard tree: `manifest.py`, `domain_pack.py`, `prompting/branch.py`, `state/contracts.py`, `state/projection.py`, `execution/tool_specs.py`, `semantics/closure.py`, `semantics/handoff.py`.
- Earned prompt helpers: use `prompting/surfaces/` for additional domain-local guidance that should be included every iteration, but keep it suggestive and never turn it into a deterministic domain pipeline.
- Projection split: keep `state/projection.py` as the public lens (scope merge + assembly); put coercion helpers in `state/projection_coerce.py` so the lens file does not become a junk drawer.
- Avoid `Mapping[str, Any]` escape hatches on domain state contracts—extend `state/contracts.py` with real fields instead.

## Links

- Docs: `docs/architecture/harness/domain-pack-constitution.md`
- Docs: `docs/architecture/harness/domain-pack-architecture.md`
- Docs: `docs/architecture/harness/domain-runtime-adapter-architecture.md`
- Docs: `docs/architecture/harness/domain-authoring-shape.md`
- Docs: `docs/architecture/harness/transcript-edit-domain.md`
- Related code: `backend/domains/mapping/transcript_edit/`
- Tooling home: `backend/tooling/`
