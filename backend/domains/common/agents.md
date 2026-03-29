# agents.md

## Scope
- Folder: `backend/domains/common/`
- Purpose: Shared domain-pack contracts and prompt-doctrine support.

## Contracts & invariants
- Keep only genuinely shared domain-pack support here: manifests/capabilities/handoff contracts, prompt source blocks, prompt-event observability, and identity composition.
- Do not place harness machinery, workflow services, or domain-specific semantics in this folder.
- Shared prompt doctrine here must stay domain-agnostic; branch doctrine lives in the owning pack.

## Allowed changes
- Safe: extend shared contracts, improve prompt observability, and simplify shared composition helpers.
- Do not add controller/runtime helpers or family-specific logic.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/domains/common/test_domain_pack_contracts.py -q`

## Links
- Related code: `backend/domains/mapping/`
- Related code: `backend/harness/`
