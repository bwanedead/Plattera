# Docs Index

This `docs/` tree is organized to keep active architecture work easy to find without forcing a full docs reorganization.

## Active Architecture and Migration Spine

Primary program sequence is tracked in:
- `docs/architecture/migration/harness-convergence-roadmap.md`

Current active harness convergence docs:
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`
- `docs/architecture/harness/canonical-trace-schema.md`
- `docs/architecture/harness/shared-terminal-taxonomy.md`
- `docs/architecture/harness/shared-blocker-escalation-envelope.md`
- `docs/architecture/harness/minimal-shared-run-state-envelope.md`
- `docs/architecture/harness/transcript-edit-state-authority.md`
- `docs/architecture/harness/trace-normalization-and-adapter-design.md`
- `docs/architecture/migration/harness-delta-ledger.md`
- `docs/architecture/migration/harness-decisions.md`
- `docs/architecture/migration/unified-mission-runtime-plan-2026-03-12.md`
- `docs/architecture/migration/transcript-edit-authority-migration-notes.md`
- `docs/architecture/migration/trace-implementation-plan.md`
- `docs/architecture/migration/harness-review-operating-routine.md`

Use these as the source of truth for destination architecture, migration gaps, and major decisions.
For unified mission runtime layer boundaries, `docs/architecture/harness/mission-runtime-contracts-v1.md` takes precedence; `target-harness-v1.md` remains broader harness-direction context.

## Next-Stage Agent Kernel Seed

This next-stage seed captures the direction after the current shared harness / mission-runtime convergence work.

Start here for next-stage planning orientation:
- `docs/architecture/agent-kernel/README.md` — index and interpretation rules for the seed area
- `docs/architecture/agent-kernel/target-agent-kernel-v1.md` — seed architecture contract: execution kernel / orchestration kernel / domain-pack / mission-shell layering
- `docs/architecture/agent-kernel/current-to-next-vocabulary-crosswalk.md` — explicit mapping from current harness terms to next-stage seed terms; read before planning next-stage work
- `docs/architecture/agent-kernel/loop-family-orchestration-delta-matrix.md` — concrete code-grounded delta between `deed_to_ir` and `transcript_edit` orchestration; primary input to orchestration kernel design
- `docs/architecture/agent-kernel/orchestration-kernel-contracts-v1.md` — Phase 2 contract freeze: shared phase grammar (orient → refresh → project → select-focus → resolve-move → execute → evaluate-progress → decide → terminalize) and minimum shared contract surfaces
- `docs/architecture/agent-kernel/shared-loop-memory-v1.md` — Phase 3 contract freeze: six loop-memory categories (continuity, work-state, evidence, feedback, progress, domain-state); persistence/resume expectations; field-mapping appendix for both loop families
- `docs/architecture/agent-kernel/domain-pack-interface-v1.md` — Phase 4 contract freeze: domain-pack callable protocol (9 hooks), ownership table, projection rules, worked examples for transcript-edit and deed-to-IR
- `docs/architecture/migration/agent-kernel-convergence-roadmap.md` — phased roadmap for next convergence stage (7 phases: architecture clarification → orchestration kernel → loop memory → domain packs → transcript extraction → deed migration → blended missions)
- `docs/architecture/migration/transcript-extraction-plan.md` — Phase 5 extraction plan: six transcript-edit mechanics (orient, refresh, focus-selection, move layer, progress evaluator, HITL substrate) with kernel-vs-pack boundary calls, code anchors, sequencing, and verification

Use this seed when planning the next convergence stage:
- one shared orchestration kernel above both loop families
- one shared loop-memory law (six memory categories)
- domain packs that differ in content and policy, not in fundamental loop shape

Current implemented harness and mission-runtime reality is still primarily documented under:
- `docs/architecture/harness/`
- `docs/architecture/migration/`

Interpretation rule:
- `docs/architecture/harness/` and `docs/architecture/migration/` remain authoritative for the currently implemented runtime boundaries
- `docs/architecture/agent-kernel/` is the forward-looking seed area for the next deeper convergence stage
- do not use next-stage seed vocabulary to override current harness doc authority

## Active Reference Architecture Docs

These remain active references for current-state architecture and loop behavior:
- `docs/agent-ecosystem-architecture-top-down.md`
- `docs/architecture/agent-viewer-v1.md` — Agent Viewer v1 engineering brief: generic control-plane/read-model architecture, renderer registry boundaries, HITL/display responsibilities, and anti-monolith rules
- `docs/agent-loop-system-overview.md`
- `docs/agent-testing/transcript-edit-loop-holistic-intent.md`
- `docs/transcript-edit-loop-orchestration.md`
- `docs/agent-kernel-controller-spec.md`
- `docs/agent-kernel-action-tool-menu.md`
- `docs/harness-engineering-ambition-gap-map-2026-03-11.md`

## Ethos and Working Rules

Repo-wide engineering ethos and operating principles:
- `docs/ethos/`
- repository `AGENTS.md`

## Historical and Legacy Material

Older docs remain in place during this program. Treat them as reference or historical context unless they are explicitly linked from the active architecture/migration spine above.

The objective of this index is clarity of current direction, not exhaustive cataloging.
