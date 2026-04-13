# Harness Convergence Canonical Owners

This note locks the canonical owner for each convergence track so each phase removes split truth instead of adding parallel systems.

## Domain Contract Owner

- Canonical owner: `backend/domains/<family>/<domain>/domain_pack.py`
- Supporting semantic declarations stay in domain-owned `manifest.py`, `prompting/`, `execution/tool_specs.py`, and `semantics/`.
- Runtime adapters may only compile the pack declaration with startup inventory and scoped handlers.
- Phase 1 concrete owner: `backend/domains/mapping/transcript_edit/domain_pack.py`

## Prompt Layer Owner

- Stable harness doctrine owner: `backend/harness/runtime/prompting/surface.py`
- Stable family/domain doctrine owner: domain-owned `backend/domains/<family>/<domain>/prompting/`
- Mode-specific instruction owner: harness-owned `backend/harness/runtime/orchestration/*_instruction.py`
- Dynamic turn-packet owner: `backend/harness/runtime/orchestration/llm_prompt_builder.py`
- Final stitch ownership stays in the harness; domain code may not smuggle extra doctrine into the assembly layer.

## Extension Lifecycle Owner

- Canonical owner target: `backend/harness/runtime/orchestration/contracts.py` plus explicit typed lifecycle surfaces under the orchestration runtime.
- Mechanical observers/contributors may enrich mechanics, not semantic truth.
- The orchestration loop owns the active lifecycle bundle and injects adapter-visible observer refs through `OrchestratorContext`; semantic adapters must not retain their own lifecycle authority.

## Event Identity Owner

- Canonical owner target: orchestration trace emission under `backend/harness/runtime/orchestration/trace_collector.py`
- Audit and summary layers must carry that lineage rather than mint competing identities.
- Required identity surfaces for later phases: `run_id`, `session_id`, `request_id`, turn/iteration lineage, prompt-event lineage, and step-event lineage.

## Phase Rules

- One concern ends with one canonical owner.
- Compile from declared surfaces; do not silently inject extra runtime truth.
- Startup and run-context payloads are mechanical inputs, not alternate semantic declarations.
- Final prompts must remain reconstructable from owned layers.
- Short migration shims are allowed only when necessary and should be removed quickly.

## Phase 1 Removal

- Removed owner: transcript-edit runtime prompt/tool payload declaration inside `runtime_adapter/`.
- Canonical owner now: `backend/domains/mapping/transcript_edit/domain_pack.py`.

## Phase 3 Removal

- Removed owner: duck-typed lifecycle seams via `wire_*`, `run_continuity_pre_choose_action`, and `on_turn_completed`.
- Canonical owner now: `backend/harness/runtime/orchestration/lifecycle.py` plus `backend/harness/runtime/orchestration/llm_turn_lifecycle.py`.
- Removed residual split owner: adapter-held `lifecycle` state inside `LlmTurnOrchestrationAdapter`; the loop/context path is the only remaining lifecycle authority.
