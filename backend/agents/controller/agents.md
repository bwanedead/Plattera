# agents.md

## Scope
- Folder: `backend/agents/controller/`
- Purpose:
  - Controller loop that proposes `KernelStepRequest` actions via an LLM.
  - OpenAI tool-calling (`kernel_step`) with local validation and kernel refusal feedback.

## Contracts & invariants
- **No strict JSON-schema unions for step proposals**: controller proposals use tool calling or `json_object` fallback.
- **One proposal per iteration**: exactly one `kernel_step` call (or one JSON object in fallback mode).
- **Local validation is authoritative at controller boundary**: minimal contract parse, tool-menu gating, bounded args, per-action required fields.
- **Kernel remains source of truth**: controller never substitutes actions; kernel refusal payloads pass through unchanged.
- **Preserve observability**: keep `openai_next_step_error {...}` and `controller_parse_failed` payloads stable and bounded.

## Allowed changes
- Safe:
  - Improve prompt quality and refusal handling.
  - Expand per-action validators and deterministic repair behavior.
- Do not change casually:
  - `kernel_step` function name/shape without updating controller tests/docs.
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
