# agents.md

## Scope
- Folder: `backend/agent_kernel/orientation/`
- Purpose: mission-agnostic orientation **containers** and JSON-safe startup document coercion.

## Contracts & invariants
- `coerce_generic_orientation_payload` validates **generic** fields only; it does not accept transcript-edit checklist rows as a substitute for startup signal.
- `coerce_startup_understanding` merges work items with **`impact_tier`** (`high` \| `medium` \| `low` \| `unknown`) only — never infers transcript/mapping-specific posture. Domain tokens in `mission_impact` yield **`unknown`** unless explicitly mapped elsewhere.
- Do not add `mapping_blocking`, `transcript_quality_only`, or ledger layer enums here (Phase 28).

## Allowed changes
- Extend generic container coercion with bounded list sizes and new optional fields that remain mission-agnostic.
- Do not add transcript-edit checklist keys, deed ontology, or domain-specific validators here.

## Commands
- Test: `pytest backend/agent_kernel/test_orient_contract_generic.py backend/agent_kernel/orientation/test_phase28_generic_posture.py`

## Gotchas
- Transcript-edit checklist compatibility lives in `agents/transcript_edit/orient_checklist_adapter.py`, not in this package.

## Links
- Docs: `docs/architecture/harness/harness-constitution.md`
- Domain adapter: `backend/agents/transcript_edit/orient_tool.py` (kernel wires it lazily via `session.py` — Phase 30)
