# Mapping Family Pipeline Vision

This document preserves the longer-range mapping-family architecture. It is a planning reference, not a promise that every layer exists today.

The family goal is to move from deed source material to a trustworthy mapped artifact through agent-authored semantic work and deterministic mechanical rails.

---

## 1. Pipeline Shape

The intended mapping stream is layered:

1. **Source intake and retrieval**
   - collect deed images, T0 drafts, existing artifacts, and later dependency documents
   - preserve source identity and retrieval provenance

2. **Transcript-edit**
   - recover a mapping-ready transcript from source imagery and T0 drafts
   - atomize, verify, and publish source-grounded transcript output
   - preserve forwardable vs blocked parcel scope

3. **Deed-to-IR**
   - consume transcript-edit handoff
   - author feature-graph IR for forwardable scope
   - compile, judge, inspect, repair, and publish IR artifacts

4. **Map rendering and visual sanity**
   - render compiled geometry or schematic map previews
   - inspect whether the map reflects the IR and deed meaning
   - expose mismatches for repair instead of hiding them

5. **Dependency orchestration**
   - detect missing external deed references, station chains, frames, or referenced features
   - shelf blocked work until dependencies are available
   - resume pending work when the right dependency appears

6. **Portfolio or folder-level completion**
   - process a folder of deeds as an interdependent set
   - maintain queues of ready, blocked, and resumed work
   - produce coherent downstream mapping outputs across related documents

---

## 2. Ownership Boundaries

The mapping family should stay layered.

- Transcript-edit owns source-grounded transcript recovery.
- Deed-to-IR owns feature-graph IR authoring from a transcript handoff.
- Feature graph owns representable IR, compile, judge, gaps, artifacts, and bundles.
- Retrieval owns finding external source material.
- Higher orchestration owns queues, dependency scheduling, and cross-deed resumption.

Do not make deed-to-IR responsible for the whole folder-level dependency manager. Deed-to-IR should identify dependency needs and preserve them in artifacts or state. A higher layer should decide when and how to retrieve or resume across many deeds.

---

## 3. External Dependencies

Many deeds are not self-contained.

A deed may refer to:

- an external deed
- a station chain
- a plat or map artifact
- a frame, section, right-of-way centerline, or prior parcel
- a named feature whose geometry is defined elsewhere

When a dependency is missing, the system should not fake it. It should record what is missing, why it matters, and what kind of source would resolve it.

Later orchestration should support:

- pending dependency records
- retrieval hints
- dependency-to-deed matching
- shelved work queues
- resumption when a dependency appears

This lets a folder of deeds become a working set instead of isolated one-off attempts.

---

## 4. Agent/Tool Contract

The LLM agent performs semantic work:

- decides what the deed means
- authors transcript edits
- authors IR
- explains blockers and repair rationale
- chooses when a dependency is actually needed

Deterministic code performs mechanical work:

- stores artifacts
- validates schema
- compiles IR
- judges structural gaps
- renders maps
- tracks refs, lineage, and queues

This boundary matters. A deterministic compiler can say an operand is missing. It cannot decide that a deed reference is semantically satisfied by a different document unless the agent or an explicit retrieval/matching layer authors that conclusion with evidence.

---

## 5. Raptor 3 Direction

The long-term system should become one native pipeline, not a pile of legacy adapters.

Good direction:

- one canonical transcript handoff shape
- one canonical IR artifact shape
- one canonical compile/judge/render loop
- one canonical way to record dependencies
- one higher-level scheduler for cross-deed work

Bad direction:

- deed-to-IR secretly reopening transcript-edit as the normal path
- deterministic loaders parsing deed meaning into IR
- every domain inventing its own dependency queue
- map rendering treating visual output as proof without judge/IR lineage
- old kernel action names living forever as compatibility ballast

The visible shape should match the real shape: transcript -> IR -> compile/judge/render -> repair or handoff, with dependency orchestration above the domain agents.

