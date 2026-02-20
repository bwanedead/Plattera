# agents.md

## Scope
- Folder: `backend/agents/controller/`
- Purpose:
  - Controller loop that proposes `KernelStepRequest` actions via an LLM.
  - OpenAI-backed strict structured output (`response_format: json_schema`) for step proposals.

## Contracts & invariants
- **Structured outputs are strict**: the controller’s step proposal schema must be accepted by OpenAI with `strict: true`.
- **`additionalProperties: false` everywhere**: root and nested object schemas must explicitly forbid extras, or OpenAI may reject the request with `400 invalid_request_error`.
- **Root schema must be an object schema**: avoid `$ref`-wrapped roots; normalize/deref before sending.
- **Avoid free-form dict inputs in strict schemas**: prefer per-action typed inputs (discriminated union) over `dict[str, object]` when using `strict: true`.
- **Preserve observability**: keep the `openai_next_step_error {...}` structured log payload intact so failures are diagnosable via logs/transcripts.

## Allowed changes
- Safe:
  - Improve schema normalization, add schema compliance tests, tighten proposal contracts.
  - Improve prompt quality and controller-side validation (tool menu membership, bounded payloads, etc.).
- Don’t change casually:
  - The strict-schema request shape (`response_format.type="json_schema"`, `strict: true`) without updating docs + tests.
  - Logging fields in `openai_next_step_error` and transcript parse-failure payloads.

## Commands
- Test (controller): `pytest backend/agents/controller -q`
- Test (agent kernel): `pytest backend/agent_kernel -q`

## Gotchas
- If you see `400 Bad Request` mentioning `"additionalProperties" is required ... false`, the JSON Schema is not compliant with strict structured outputs.
- Pydantic v2 can emit `$ref` at the schema root; mutating the wrapper dict is insufficient unless you dereference or inline the `$defs` target.

## Links
- Local strict-mode rules: `backend/services/llm/STRUCTURED_OUTPUTS_JSON_SCHEMA_STRICT.md`
- OpenAI structured outputs guide: `https://platform.openai.com/docs/guides/structured-outputs#supported-schemas`
- Cookbook intro: `https://cookbook.openai.com/examples/structured_outputs_intro`

