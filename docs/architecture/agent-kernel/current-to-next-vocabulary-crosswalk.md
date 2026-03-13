# Current-to-Next Vocabulary Crosswalk

Date: 2026-03-13
Status: Active reference for next-stage planning
Related docs:
- `docs/architecture/agent-kernel/target-agent-kernel-v1.md`
- `docs/architecture/harness/mission-runtime-contracts-v1.md`
- `docs/architecture/harness/target-harness-v1.md`

## Purpose

This document reconciles current implemented harness vocabulary with the next-stage agent-kernel seed vocabulary.

It is short and practical.
Its job is to prevent terminology drift during next-stage planning and implementation.

---

## Term Crosswalk

| Current term | Current meaning | Next-stage interpretation | Change type |
| --- | --- | --- | --- |
| `MissionRuntime` | Top-level mission lifecycle orchestrator, owns mode lifecycle, continuity, and terminal handling | Narrows to mission shell: owns mission identity, mode selection, cross-mode continuity envelope, CLI/API entry. Delegates deeper loop law to `orchestration kernel` | Boundary narrowing |
| `ModePolicy` | Domain-local interpretation, completion, and transition recommendation. Today wraps entire family controller | Narrows to domain pack: owns domain-specific context, projection, move menu, closure rules, move compilation. Should not wrap a top-level controller loop | Boundary narrowing — today's `ModePolicy` implementations are too large |
| `RuntimeCapability` | Reusable cross-mode orchestration mechanics, currently conceptually named but underspecified in code | Becomes the explicit home for shared orchestration mechanics: orient, blocker handling, evidence, progress evaluation, HITL lifecycle, loop-brake | Crystallization — concept exists; contents must be defined |
| `MissionLedger` | Mission-level continuity record: mode, transitions, artifact refs, posture summaries | Unchanged. Remains mission-shell scope. Must not absorb mode-local loop-memory (ledger, registry, progress state) | No change |
| `ModeTransition` | Ordered record of a mode switch, owned and validated by `MissionRuntime` | Unchanged | No change |
| `backend/agent_kernel/` | The execution kernel: step execution, budgets, idempotency, tool dispatch, artifact persistence | Unchanged. Remains the execution kernel | No change |
| `execution kernel` | Shorthand for `backend/agent_kernel/` | Unchanged — preserved in next-stage seed vocabulary | No change |
| `orchestration kernel` | Does not yet exist as implemented code | New: the shared loop-law substrate that goes between the mission shell and domain packs. Owns phase grammar, loop-memory structure, focus selection flow, progress evaluation, HITL lifecycle, and closure/continue/terminal decisions | New concept to be built |
| `agent kernel architecture` | Not currently used in active harness docs | Next-stage umbrella term for the full holistic stack: execution kernel + orchestration kernel + domain packs + mission shell. Deliberately broader than `backend/agent_kernel/` | New umbrella term |
| `domain pack` | Not currently used in active harness docs | Next-stage term for what a `ModePolicy` should shrink toward: a bounded policy surface that injects domain-specific content into the shared loop law | Replaces "mode policy" at smaller scope |
| `deed_to_ir controller` | `backend/agents/controller/` family with family-sized orchestration loop | Migrates toward a `deed_to_ir` domain pack: a smaller content-and-policy surface plugged into the orchestration kernel | Scope reduction |
| `transcript_edit controller` | `backend/agents/transcript_edit/` family with rich orchestration loop | Migrates toward a `transcript_edit` domain pack. Reusable orchestration patterns (orient, blocker lifecycle, focus/move, progress evaluation, HITL) migrate to shared orchestration kernel; domain-specific closure, ledger semantics, and move menu stay in the pack | Scope reduction + extraction |
| `TranscriptEditLoopState` | Domain-local loop memory for transcript-edit loop | A specific instance of domain-owned loop memory. Generic categories (continuity, work-state, evidence, feedback, progress) should be shared loop-memory contract fields; domain-specific cached state stays domain-local | Partially shared, partially retained |

---

## Interpretation Rule

These terms describe the **same evolving system** at two stages, not competing architectures:

- The **current** harness vocabulary documents what is built and enforced today.
- The **next-stage** agent-kernel vocabulary describes what the same system should grow toward after the current harness converges.

Never use the next-stage seed vocabulary to override current harness doc authority.
Use next-stage vocabulary only when discussing architecture planning for the next convergence stage.

---

## Collision Warnings

These name collisions are the most likely sources of confusion:

| Collision | Risk | How to avoid |
| --- | --- | --- |
| `agent kernel` vs `backend/agent_kernel/` | "agent kernel" may be read as referring narrowly to the execution kernel package | Use `agent kernel architecture` for the full stack; use `execution kernel` or `backend/agent_kernel/` for the execution substrate only |
| `domain pack` vs `ModePolicy` | "domain pack" may be confused with current `ModePolicy` implementations | `ModePolicy` implementations today are too large to be domain packs; reserve "domain pack" for the smaller target surface |
| `orchestration kernel` vs `MissionRuntime` | "orchestration kernel" may be confused with `MissionRuntime` | `MissionRuntime` is the outer mission shell; `orchestration kernel` is the inner loop-law substrate that `MissionRuntime` will delegate to |
