# agents.md

## Scope
- Folder: `backend/tooling/mapping/deed_to_ir/`
- Purpose: Mechanical I/O for deed-to-IR startup (transcript-edit output loading only in Brief A).

## Contracts & invariants
- Copy transcript-edit output fields without semantic inference or mutation.
- Do not parse deed text into IR, rank parcels, or invent blockers.

## Commands
- Test: `pytest backend/domains/mapping/deed_to_ir/ -q` (loader covered via domain tests)

## Links
- Domain: `backend/domains/mapping/deed_to_ir/`
