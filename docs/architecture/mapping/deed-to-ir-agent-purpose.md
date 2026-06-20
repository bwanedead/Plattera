# Deed-to-IR Agent Purpose

This document preserves the architectural intent for the `mapping / deed_to_ir` domain. Live behavioral doctrine remains in `backend/domains/mapping/deed_to_ir/prompting/branch.py`.

## Core Mission

Deed-to-IR converts available deed meaning into source-traceable feature-graph IR and an honestly mapped result. It is not a prose summarizer and it is not a freehand drawing agent. Its IR is the executable geometric model consumed by the downstream mapping system.

The governing chain is:

```text
source evidence
-> transcript-edit resolution units
-> feature-graph IR
-> computed geometry
-> mapped artifact
```

Each layer has a different job. Transcript-edit establishes source-grounded values and scope. Deed-to-IR expresses those values as geometric entities, relationships, constraints, frames, and dependencies. Deterministic mapping infrastructure validates, computes, renders, and reports mechanical facts. The agent interprets those facts, repairs the correct semantic layer, and authors closure posture.

## Upstream Substrate

The transcript-edit handoff provides normalized and verbatim transcript lanes, parcel scope metadata, issues, HITL decisions, evidence refs, and a final resolution-state work graph. It is high-value upstream work rather than raw OCR, but it is not infallible.

Deed-to-IR should normally build from that handoff instead of reopening source interpretation. If geometry or map sanity exposes a real upstream defect, the agent may inspect supporting resolution units and evidence, then repair the correct layer with explicit rationale.

## Provenance

Feature-graph nodes and edges can carry exact source-entity links to transcript-edit resolution units. Those links preserve the route from mapped geometry back to determined values, evidence locators, crops, and source material. Deterministic code stores and validates these associations; it does not invent them.

This lineage supports audit and future UI interactions without copying every source artifact into every IR entity.

## Deterministic Mapping Boundary

The eventual public mapping action should accept an authored IR artifact and coordinate the deterministic mapping stages internally. Compiler and judge remain feature-graph implementation vocabulary, not separate semantic closure layers and not necessarily separate normal agent actions.

Deterministic feedback can establish schema validity, computed geometry, typed gaps, and render output. It cannot establish that the IR faithfully represents the deed. Likewise, successful rendering proves only that something rendered.

## Closure Obligations

1. **Deed meaning to IR fidelity:** mappable deed meaning is represented faithfully and traceably in IR.
2. **IR and geometry integrity:** resulting geometry follows the authored IR and makes sense against the deed description.
3. **External dependency and representability completeness:** missing sources, references, frames, and unsupported primitives remain explicit.
4. **Map handoffability and scoped completion:** mapped, blocked, and dependency-pending scopes and their durable artifacts are clearly identified.

Partial success is valid. A complete parcel may be handed forward while another parcel remains blocked by incomplete source material. What is forbidden is silent fake completeness.

## Ownership Boundary

The agent owns:

- deed interpretation expressed in IR
- source-entity provenance associations
- diagnosis and repair decisions
- dependency and blocker meaning
- scoped closure and handoff posture

Deterministic tools own:

- schema validation
- artifact persistence and hydration
- geometric computation
- mechanical diagnostics
- rendering and artifact references

Tools must not parse deed prose into semantic IR, infer atom-to-feature links, invent geometry, or declare semantic closure.

## Larger Pipeline

External retrieval, dependency queues, folder-level deed scheduling, and cross-deed resumption belong to mapping-family orchestration. Deed-to-IR should emit dependency needs cleanly but should not become the scheduler for the entire document collection.
