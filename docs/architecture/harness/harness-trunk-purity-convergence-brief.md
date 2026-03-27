# Harness Trunk Purity Convergence Brief

Date: 2026-03-27  
Status: Open-ended execution brief  
Scope: Shared harness trunk only

Related:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/domain-pack-constitution.md`
- `docs/architecture/harness/generic-harness-native-core-guardrails.md`
- `docs/architecture/harness/generic-harness-native-core-target.md`
- `docs/architecture/harness/generic-harness-native-core-roadmap.md`
- `docs/architecture/harness/generic-harness-native-core-layer-1-inventory.md`
- `docs/architecture/harness/mission-state-and-resolution-state-architecture.md`
- `docs/ethos/architecture-ethos.md`
- `docs/ethos/structure-ethos.md`
- `.codex/agents/raptor-3-native-reviewer.toml`

---

## 1. Purpose

This brief is for open-ended execution toward one outcome:

- the harness becomes a clean, end-to-end native system

It is not a request for local cleanup.
It is not a request to preserve old domains.
It is not a request to build another adapter layer.

The goal is a **Raptor 3 harness**:

- one trunk
- one canonical state model
- one canonical runtime model
- one canonical tracing/reporting model
- one clean domain seam
- no hidden legacy substrate
- no adapter-chain patchwork

Domains may be rebuilt later.
The harness trunk should not be shaped around preserving them.

---

## 2. North Star

The target end state is:

- `mission_state` is the canonical top-level shared continuity object
- `resolution_state` is the canonical organized-work surface
- the orchestration kernel runs natively on that model
- mission runtime speaks only generic runtime/mode/transition language
- tracing and run-state reporting speak only native harness language
- domain packs plug in through one direct native seam
- the harness does not reconstruct meaning from domain-private legacy payloads

The harness should be:

- more native
- more mechanical
- more constitutional
- more direct
- more subtractive

If a patch keeps the old system alive underneath a nicer surface, it is not the target.

---

## 3. Read-First Guidance

Before each substantial cut, re-anchor on:

1. `docs/architecture/harness/harness-constitution.md`
2. `docs/architecture/harness/generic-harness-native-core-guardrails.md`
3. `docs/architecture/harness/generic-harness-native-core-target.md`
4. `docs/architecture/harness/generic-harness-native-core-roadmap.md`
5. `docs/architecture/harness/generic-harness-native-core-layer-1-inventory.md`
6. `docs/ethos/architecture-ethos.md`
7. `docs/ethos/structure-ethos.md`

Use the constitutions and guardrails as the law.

Use the roadmap and inventory as the implementation map.

Use `.codex/agents/raptor-3-native-reviewer.toml` as the thematic review lens.

---

## 4. Operating Posture

Work from these assumptions:

- transcript-edit is disposable
- deed/controller compatibility is disposable
- domain preservation is not the trunk goal
- if the harness still knows domain-private legacy shapes, the harness is not pure yet
- compatibility is only acceptable as a bounded temporary seam with a deletion plan

Do not optimize for:

- keeping old domains comfortable
- keeping old tests alive if they only preserve retired architecture
- minimizing churn inside legacy domain adapters

Optimize for:

- a smaller canonical harness
- fewer layers
- fewer metaphors
- fewer compatibility surfaces
- fewer domain-specific assumptions inside `backend/harness`

---

## 5. What Must Be True When This Is Done

The harness should contain only:

- canonical shared contracts
- canonical kernel rails
- canonical mission runtime law
- canonical run-state/reporting law
- canonical tracing law
- one clean domain protocol

The harness should not contain:

- `work_board` as a living concept
- `decision_ledger` as a living concept
- transcript-edit-specific reconstruction in shared runtime paths
- domain-private payload archaeology in the shared trunk
- domain-specific mode glue embedded as if it were harness law
- domain-specific trace normalization embedded as if it were harness law
- stale docs teaching old kernel/state grammar

---

## 6. Known Remaining Purity Targets

The following are already identified as the main remaining trunk impurities.

### 6.1 Canonical state layer still exports migration surfaces

Primary targets:

- `backend/harness/mission_state/__init__.py`
- `backend/harness/mission_state/contracts.py`
- `backend/harness/mission_state/compat.py`
- `backend/harness/mission_state/resolution_envelope.py`
- `backend/harness/mission_state/recent_activity.py`

Issues already identified:

- canonical exports still include legacy conversion helpers
- native helpers still know old wire ids
- native recent-activity helpers still carry legacy naming residue

Target outcome:

- the canonical `mission_state` surface exports only native concepts
- old-shape readers, if temporarily required, are buried and visibly secondary

### 6.2 `run_state.py` still performs domain-era reconstruction

Primary target:

- `backend/harness/run_state.py`

Issues already identified:

- transcript-edit snapshot archaeology
- direct reading of `decision_ledger`
- compat fallback item synthesis
- blocker-registry compatibility shaping
- active-item compatibility synthesis

Target outcome:

- `run_state.py` should consume native shared payloads only
- or one generic domain seam only
- not domain-private legacy internals

### 6.3 Mission runtime still hosts domain-specific mode glue inside the harness

Primary targets:

- `backend/harness/mission_runtime/modes/__init__.py`
- `backend/harness/mission_runtime/modes/deed_to_ir.py`
- `backend/harness/mission_runtime/modes/transcript_edit.py`
- `backend/harness/mission_runtime/cli_support.py`
- `backend/harness/mission_runtime/agents.md`

Issues already identified:

- domain-specific adapters live inside the harness package
- controller/transcript-edit runtime glue still shapes the mission-runtime layer

Target outcome:

- mission runtime becomes purely generic mode/runtime law
- domain-specific mode implementations are no longer treated as trunk architecture

### 6.4 Tracing still contains domain-specific adapter centers

Primary targets:

- `backend/harness/tracing/adapters/__init__.py`
- `backend/harness/tracing/adapters/controller_kernel.py`
- `backend/harness/tracing/adapters/transcript_edit.py`
- `backend/harness/tracing/adapters/transcript_edit_helpers.py`
- `backend/harness/tracing/adapters/kernel_direct.py`

Issues already identified:

- transcript-edit closure truth still shaped around `decision_ledger`
- controller transcript normalization still lives in the harness tracing layer

Target outcome:

- tracing centers on canonical kernel/runtime events
- domain-specific normalization no longer defines the trunk

### 6.5 Stale harness-local teaching surfaces still preserve old grammar

Primary targets:

- `backend/harness/orchestration_kernel/agents.md`
- `backend/harness/mission_state/agents.md`
- stale tests/docs inside `backend/harness/`

Issues already identified:

- old kernel vocabulary is still taught as if live
- migration language still appears in canonical-facing notes

Target outcome:

- docs/notes teach the actual trunk, not historical grammar

### 6.6 Empty or residual legacy shells should be removed

Primary targets:

- `backend/harness/work_board/`
- `backend/harness/decision_ledger/`

Target outcome:

- if they have no active role, delete them
- do not leave them behind as visual ballast

---

## 7. Recommended Working Order

Use this order unless a stronger dependency is discovered:

1. Purify `mission_state` canonical exports and native helpers.
2. Purify `run_state.py` so the harness stops doing domain archaeology.
3. Remove domain-specific mode glue from `mission_runtime`.
4. Remove domain-specific adapter centers from `tracing`.
5. Delete dead legacy shells and stale harness-local teaching surfaces.
6. Add or maintain one minimal native validation surface proving the trunk works directly.

The main principle is:

- remove harness knowledge of old domain internals before worrying about rebuilt domains

---

## 8. Working Rules During Execution

### 8.1 Be subtractive

Each checkpoint should answer:

1. What is now canonical?
2. What old surface stopped being canonical?
3. What can now be deleted?
4. What actually got deleted?
5. What temporary seam remains, and when does it die?

If a checkpoint adds structure but nothing becomes deletable, scrutinize it.

### 8.2 Do not preserve adapter stacks

Do not leave:

- new native surface
- old compatibility surface
- translation bridge
- domain-specific fallback

all alive at once unless there is a very short, explicit retirement path.

### 8.3 Protect constitutional boundaries

Never allow cleanup work to reintroduce:

- deterministic focus authorship
- deterministic blocker authorship
- deterministic closure authorship
- deterministic next-step authorship
- shared helpers interpreting domain meaning

The harness owns mechanics.
The domain owns semantics.
The agent authors motion.

### 8.4 Ignore domain comfort

If a legacy domain cannot survive the cleaned seam, that is acceptable.
The harness should not be distorted to preserve it.

---

## 9. Checkpoint Review Cadence

After each self-assessed checkpoint:

1. do a self-review against:
   - `docs/architecture/harness/harness-constitution.md`
   - `docs/architecture/harness/generic-harness-native-core-guardrails.md`
2. run the Raptor 3 reviewer defined at:
   - `.codex/agents/raptor-3-native-reviewer.toml`
3. ask it to review only the checkpoint delta and the currently affected trunk surfaces
4. summarize:
   - whether the checkpoint is converging / mixed / patchwork
   - what became deletable
   - what ballast still remains
5. do not move to the next checkpoint if the checkpoint is still preserving hidden old substrate in the touched area

Use the Raptor 3 reviewer as a standing thematic reviewer throughout execution, not only at the end.

---

## 10. Definition Of Success

This effort succeeds when:

- the harness package itself reads as one coherent native system
- canonical state, kernel, runtime, run-state, and tracing layers all speak the same native model
- the harness no longer contains domain-era archaeology as part of normal operation
- compatibility residue is gone or strictly quarantined outside canonical APIs
- old `work_board` / `decision_ledger` substrate is not merely hidden, but gone
- the trunk is smaller, cleaner, and more direct than before

The result should feel like a single designed machine, not a stack of migration layers.

