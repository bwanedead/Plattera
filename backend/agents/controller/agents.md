# agents.md

## Scope
- Folder: `backend/agents/controller/`
- Purpose:
  - Controller loop that proposes `KernelStepRequest` actions via an LLM.
  - Stable facade (`controller.py`) over split runtime/context/proposal/summary/transcript/guardrail modules.

## Contracts & invariants
- **No strict JSON-schema unions for step proposals**: controller proposals use tool calling or `json_object` fallback.
- **One proposal per iteration**: exactly one tool call from the provided tool list (or one JSON object in fallback mode).
- **Local validation is authoritative at controller boundary**: minimal contract parse, tool-menu gating, bounded args, per-action required fields.
- **Kernel remains source of truth**: controller never substitutes actions; kernel refusal payloads pass through unchanged.
- **Preserve observability**: keep `openai_next_step_error {...}` and `controller_parse_failed` payloads stable and bounded.

## Module boundaries
- `controller.py`: stable public exports only (`run_controller_loop`, `ControllerLoopError`, `ControllerRunResult`, transcript hook set/restore, client protocols).
- `controller_runtime.py`: runtime public surface/types; delegates loop body.
- `controller_runtime_loop.py`: main loop sequencing and terminal branching.
- `controller_runtime_step_prep.py`: proposal normalization, guard checks, and step request preparation.
- `controller_bootstrap.py`: bootstrap context and deed/span-seed bootstrap wiring.
- `controller_context.py`: context packet assembly, recent trace, inline artifact hint shaping.
- `controller_proposals.py`: next-step/refusal-repair proposal calls, coercion, autofill, validation.
- `controller_summary.py`: digest/run-summary/docket normalization and no-progress stop result shaping.
- `controller_transcript.py`: transcript event append/bounding, display delta shaping, persistence/log payload helpers.
- `controller_guardrails.py`: idempotency/refusal streak helpers, thrash/quality gates, parse-resync proposal.

## Allowed changes
- Safe:
  - Improve prompt quality and refusal handling.
  - Expand per-action validators and deterministic repair behavior.
- Do not change casually:
  - Controller proposal mapping (tool-name + top-level params -> local `KernelStepProposal`) without updating tests/docs.
  - Error payload fields used by logs/transcripts.

## Commands
- Test (controller): `pytest backend/agents/controller -q`
- Test (agent kernel): `pytest backend/agent_kernel -q`

## Gotchas
- If OpenAI returns `400` for strict schema keywords, verify strict mode was not reintroduced for controller proposals.
- If tool calls are missing, inspect `tool_choice`, `tools`, and model compatibility first.
- Keep `args` refs-not-blobs; large geometry or deep payloads are refused before kernel step.

## Links
- Controller spec: `docs/agent-kernel-controller-spec.md`
- OpenAI config notes: `backend/services/llm/openai_config.md`
