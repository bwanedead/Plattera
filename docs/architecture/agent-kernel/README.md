# Agent Kernel Architecture

This folder is the seed area for the next convergence stage after the shared harness and unified mission runtime work.

Purpose:
- define the holistic `agent kernel` target shape
- separate `execution kernel` concerns from `orchestration kernel` concerns
- define how domain-specific loop behavior should plug into one shared loop law

Current status:
- this is an active seed area, not yet a replacement for the existing `docs/architecture/harness/` spine
- current implemented shared-harness and mission-runtime reality remains primarily documented under:
  - `docs/architecture/harness/`
  - `docs/architecture/migration/`

## Interpretation rule

- `docs/architecture/harness/` and `docs/architecture/migration/` are authoritative for currently implemented runtime boundaries.
- This `agent-kernel/` area is the forward-looking seed for the next deeper convergence stage.
- Do not use seed vocabulary to override active harness doc authority.

## Docs in this folder

- `target-agent-kernel-v1.md` — seed architecture contract defining the execution kernel / orchestration kernel / domain-pack / mission-shell layer split
- `current-to-next-vocabulary-crosswalk.md` — explicit mapping from current harness vocabulary to next-stage seed vocabulary; read before planning next-stage work; includes `mode pack` → `domain pack` reconciliation
- `loop-family-orchestration-delta-matrix.md` — concrete code-grounded delta between `deed_to_ir` and `transcript_edit` orchestration; primary input to orchestration kernel design
- `orchestration-kernel-contracts-v1.md` — Phase 2 contract freeze: shared phase grammar, and minimum contract surfaces (`FocusPacket`, `MoveDecision`, `MoveExecutionPlan`, `ProgressDelta`, `HitlState`, `TerminalDecision`)
- `shared-loop-memory-v1.md` — Phase 3 contract freeze: six loop-memory category contract (continuity, work-state, evidence, feedback, progress, domain-state); persistence and resume expectations; field-mapping appendix for both loop families
- `domain-pack-interface-v1.md` — Phase 4 contract freeze: domain-pack callable protocol (9 hooks), ownership table, projection rules, and worked examples for transcript-edit and deed-to-IR

## Related migration docs

- `docs/architecture/migration/agent-kernel-convergence-roadmap.md` — phased roadmap for the next convergence stage
- `docs/architecture/migration/transcript-extraction-plan.md` — Phase 5 extraction plan: six transcript-edit mechanics with kernel-vs-pack boundary calls, code anchors, and sequencing/verification plan
