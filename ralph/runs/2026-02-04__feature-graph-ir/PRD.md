# PRD: Universal Feature Graph IR (deed meaning substrate) - first leg

## Context
We need a universal, deterministic substrate that can represent any deed meaning, compile as far as possible, surface typed gaps, and persist artifacts with provenance. This must run in parallel with existing PLSS-focused pipelines and reuse deterministic oracles where applicable.

## Goal
Introduce a universal Feature Graph IR with persistence, compilation, deterministic judges, and bundling, so any deed can be represented and partially compiled without mystery failure.

## Non-goals
- Full LLM extraction from deed text (parsing/interpretation can be added later).
- Full georeferencing for all jurisdictions (only minimal anchoring representation in this leg).
- UI integration or frontend changes.
- Replacing or refactoring existing PLSS or text-to-schema pipelines.

## Users / Use cases
- As an engineer, I can persist an IR artifact for any deed, even with unsupported operations.
- As a compiler, I can produce a local geometry output for a subset of traverses and return typed gaps for the rest.
- As a validator, I can run deterministic judges and get gap records tied to evidence/provenance.
- As an operator, I can bundle IR + dependencies into a portable artifact.

## Scope
- Backend-only: new `feature_graph` domain module(s), persistence, compiler/judge scaffolding.
- New API endpoints dedicated to feature graph IR, running in parallel with legacy endpoints.
- Artifact storage with lineage and provenance, following existing persistence patterns.

## Constraints / invariants
- Representability is total: any deed assertion must be representable in IR.
- No confidence scores; record facts, provenance, deterministic outcomes.
- Best-effort compilation: partial results + typed gaps, never silent failure.
- Separate local geometry from global anchoring (frame refs + transforms).
- No PLSS hard-coding in the IR model; PLSS is a frame plugin.
- Persistence is truth: IR/compile/judge/bundle artifacts must be durable.
- New feature graph endpoints/artifacts must not disturb legacy pipelines.

## Success criteria
- Any deed can be encoded as a Feature Graph IR artifact (even with unsupported ops).
- Local compilation works for a subset of traverses (LineStep + Close), returning deterministic gaps for unsupported steps.
- Deterministic judge report returns typed gaps with citations and evidence links.
- IR, compile, and judge artifacts persist with lineage and can be rehydrated.
- Bundle/freeze operation produces a standalone artifact with minimal dependency subgraph.

## Edge cases
- Open curves that must not be auto-closed.
- Missing or ambiguous external references (FeatureRef bindings).
- Missing parameters (distance, curve params, widths) mid-compile.
- Unsupported operations stored in IR but not compilable.
- Anchoring missing: local geometry compiled without global placement.

## Implementation notes (optional)
- Follow existing artifact persistence patterns in `backend/services/text_to_schema`.
- Keep module boundaries tight; avoid dumping all logic into a single file.
- Use deterministic tests and avoid external dependencies in this leg.
