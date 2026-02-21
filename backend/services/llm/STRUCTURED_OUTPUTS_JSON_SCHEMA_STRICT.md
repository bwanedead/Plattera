# Structured Outputs (JSON Schema, `strict: true`) — Local Rules & Gotchas

## Scope
- This repo uses OpenAI Chat Completions structured outputs via `response_format.type = "json_schema"` with `"strict": true`.
- This document captures the **hard requirements** and **known footguns** so we don’t rediscover them via `400 Bad Request` during agent-loop runs.

## Why this exists
When OpenAI structured outputs are enabled with `strict: true`, OpenAI **validates your JSON Schema server-side**. If the schema violates their supported subset / strict rules, the API call fails with a `400` and an error like:

- `Invalid schema for response_format ... 'additionalProperties' is required to be supplied and to be false.`

That class of failure is **preventable** with deterministic schema shaping + local tests.

## Canonical request shape (what we do)
We send something structurally equivalent to:

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "some_name",
      "schema": { "... JSON Schema ..." },
      "strict": true
    }
  }
}
```

Code location in this repo:
- `backend/agents/controller/openai_client.py` (controller step proposals)

## Hard requirements (treat as invariants)
These are the rules that routinely trigger OpenAI `400 invalid_request_error` when violated.

### 1) `additionalProperties: false` is required for **every object schema**
- You must set `"additionalProperties": false` at the **root object** and for **all nested objects** that can appear in output.
- Do **not** assume that setting it once at the root is enough.

### 1.5) `required` must exist and include every property key for object schemas
- For each object schema node:
  - `"required"` must be present,
  - and it must include every key in `"properties"`.
- `"required"` must not include keys that are not in `"properties"` (OpenAI will reject with `Extra required key '...' supplied`).
- Optional fields should be represented as **required-but-nullable** (for example `type: ["string", "null"]` or `anyOf` with `null`), not by omitting the field from `required`.

Example:
```json
{
  "type": "object",
  "properties": {
    "ir_ref": { "type": ["string", "null"] }
  },
  "required": ["ir_ref"],
  "additionalProperties": false
}
```

### 2) Root schema must be an object schema (no `$ref` wrapper as the “root”)
Pydantic v2 sometimes emits a top-level schema shaped like:

```json
{ "$ref": "#/$defs/NextStepProposal", "$defs": { ... } }
```

If you only mutate the wrapper dict, OpenAI may still validate the dereferenced schema and reject it (because the actual object schema is under `$defs`).

**Rule:** The schema you pass to OpenAI should have a root with:
- `"type": "object"`
- `"properties": { ... }`
- `"required": [ ... ]`
- `"additionalProperties": false`

If your generator produces `$ref` at the root, **deref or inline** the referenced `$defs` node into the root before sending.

### 3) Avoid free-form dictionaries in strict mode
Fields like `dict[str, object]`, “map of arbitrary keys”, or “JSON blob” designs are fundamentally in tension with strict-mode schemas, because:
- strict-mode wants closed-world objects (`additionalProperties: false`)
- unbounded dicts imply open-world objects (`additionalProperties: true` or absent)
- in practice this can surface as `required/properties` mismatches (for example `Extra required key ...`) when OpenAI rejects/normalizes unsupported property shapes.

If you need action-specific inputs, prefer a **discriminated union** (one input model per action type) rather than `dict[str, object]`.

### 4) Required-vs-null must be explicit
If you want “always include the key, even when not applicable”:
- make the property **required**
- allow `null` explicitly (e.g., `anyOf: [{ "type": "string" }, { "type": "null" }]`)

If you want “key may be omitted”, don’t require it.

## Recommended repo pattern (mechanically reliable)
### A) Make Pydantic generate “closed” object schemas
In Pydantic v2, set `extra="forbid"` (or equivalent config) on models used for structured outputs. This typically yields `additionalProperties: false` for those objects.

### B) Normalize schema before sending to OpenAI
Perform a deterministic normalization step that:
- dereferences root `$ref` into an object root (if present)
- recursively sets `additionalProperties: false` on every schema node with `"type": "object"`
- recursively ensures object schemas define `required`, and when `properties` exists, `required` equals `list(properties.keys())`
- (optionally) asserts the schema contains no unsupported constructs for your use case

### C) Add a “schema compliance” unit test
For each schema used with `strict: true`, add a unit test that:
- builds the schema dict
- validates the invariant properties (root object + recursive `additionalProperties: false`)

This makes schema breakage a **local test failure** rather than a runtime paid API failure.

## Implementation notes for this repo
Current controller proposal schema generator:
- `backend/agents/controller/contracts.py` (`next_step_json_schema()`)

If you hit a 400 schema error:
- capture the `openai_next_step_error {...}` log line (it includes the exact OpenAI message and request id)
- update the local schema normalization + tests to prevent recurrence

## External references (source of truth)
- OpenAI Structured Outputs guide: `https://platform.openai.com/docs/guides/structured-outputs#supported-schemas`
- OpenAI cookbook intro: `https://cookbook.openai.com/examples/structured_outputs_intro`
- Community thread (exact error class): `https://community.openai.com/t/schema-additionalproperties-must-be-false-when-strict-is-true/929996`
