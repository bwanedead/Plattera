# agents.md

## Scope
- Folder: `backend/domains/`
- Purpose: Domain packs as bounded semantic skins on top of the harness, with consistent package layout and strict separation from product/tool realization.

## Contracts & invariants
- Domain packs own semantics only: doctrine, state meaning, projection, execution translation, closure, feedback, and handoff.
- Domain packs must not own loop machinery, persistence machinery, trace machinery, or provider/client wiring.
- `manifest.py` is identity/capabilities only; `domain_pack.py` is a thin host shell; `prompting/branch.py` is the canonical doctrine source.
- Tool menus declared under a domain are semantic declarations only. Concrete endpoint/service/provider realization belongs outside `backend/domains/`.
- Start minimal. Add `state/`, `execution/`, `semantics/`, or `prompting/surfaces/` only when the domain has genuinely earned them.

## Allowed changes
- Add or refine domain doctrine, state/projection, semantic tool specs, and closure/feedback/handoff logic.
- Create new domain-pack files when they establish one clear responsibility.
- Delete older domain scaffolding rather than preserving parallel systems.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/harness -q`
- Other: `Get-Content docs/architecture/harness/domain-pack-constitution.md`
- Other: `Get-Content docs/architecture/harness/domain-pack-architecture.md`
- Other: `Get-Content docs/architecture/harness/transcript-edit-domain-brief.md`

## Gotchas
- Do not let `backend/domains/` become a second harness. If code looks like runtime/control flow, it is probably in the wrong layer.
- Do not mix product IDs, endpoint wiring, or provider setup into semantic pack code.
- Pycache residue and older transcript-edit names are not architecture. Treat them as noise unless live source still depends on them.

## Patterns
- Structure: `manifest.py`, `domain_pack.py`, `prompting/branch.py` are the default seed for every new domain.
- Structure: When a domain grows, prefer `state/`, `execution/`, and `semantics/` subpackages over growing one large file.

## Links
- Docs: `docs/architecture/harness/domain-pack-constitution.md`
- Docs: `docs/architecture/harness/domain-pack-architecture.md`
- Docs: `docs/architecture/harness/transcript-edit-domain-brief.md`
- Docs: `docs/architecture/harness/prompt-system-architecture.md`
- Related code: `backend/domains/mapping/transcript_edit/`
