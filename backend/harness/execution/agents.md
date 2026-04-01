# agents.md

## Scope
- Folder: `backend/harness/execution/`
- Purpose: Generic harness-native step execution substrate.
- Purpose: Action dispatch, one-step session execution, durable execution records, and persistence only.

## Contracts & invariants
- Keep this layer generic: no domain, family, mapping, transcript, dossier, or product semantics.
- Do not add orchestration, prompt authoring, mission-state meaning, closure logic, or startup phase scripting here.
- Action ids are opaque strings. This layer may normalize and dispatch them, but must not interpret their semantic meaning.
- `run_artifact.py` is execution history only. Do not add domain-specific artifact slots.

## Allowed changes
- Generic request/result contracts, idempotency, dispatch, persistence, and latest-ref helpers.
- Thin compatibility work that points harness runtime at this package while avoiding semantic bleed.

## Commands
- Test: `. .venv\scripts\activate.ps1; pytest backend/harness/execution/test_execution_layer.py backend/harness/runtime/orchestration/test_orchestrator.py backend/harness/runtime/orchestration/test_progress.py -q`
- Guardrails: `. .venv\scripts\activate.ps1; pytest backend/harness/test_architecture_guardrails.py -q`
- Syntax: `. .venv\scripts\activate.ps1; Get-ChildItem backend/harness/execution/*.py | ForEach-Object { python -m py_compile $_.FullName }`

## Gotchas
- Do not recreate `agent_kernel` protocol contamination here (compile/judge/bundle/georeference-style interfaces).
- Do not add an `orientation/` subsystem unless there is a future explicit architectural decision for it.

## Links
- Docs: `docs/architecture/harness/harness-constitution.md`
- Related code: `backend/harness/runtime/orchestration/`
