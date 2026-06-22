# Universal Agent Viewer Product Vision

## Status And Audience

Status: active product guidance.

This is the product and experience north star for Plattera's universal Agent
Viewer. It is written primarily for UI engineers and autonomous coding agents
building the viewer while the harness and domain pipelines continue to evolve.

This document answers:

- what experience we are trying to create
- what should be universal across every agent domain
- how polished presentation and raw structural inspection coexist
- how users watch, inspect, communicate with, and steer an agent run
- how cloud development proceeds without committing real source binaries

It does not replace the engineering contracts or harness constitutions.

## Source Hierarchy

Use these sources together, in this order:

1. This document defines the product experience and success standard.
2. `docs/architecture/agent-viewer-v1.md` defines ownership boundaries,
   generic read-model primitives, transport expectations, and anti-monolith
   rules.
3. `docs/ui-agent-resources/platform-viewer-contract.md` defines the stable
   generic lanes represented by replay data.
4. `docs/ui-agent-resources/README.md` explains how to use the checked-in,
   git-safe run replay during cloud development.
5. `docs/architecture/harness/harness-constitution.md` and neighboring harness
   constitutions remain authoritative for agent authorship, runtime rails,
   domain ownership, and HITL meaning.

If a product idea conflicts with a harness constitutional boundary, the
constitution wins. The UI displays and transports authored meaning; it does
not invent semantic truth.

## Hard Scope Boundary For Cloud UI Development

The harness is forbidden territory for this UI effort.

The cloud UI agent must not edit:

- `backend/harness/`
- harness runtime, orchestration, audit, trace, continuity, or HITL mechanics
- active domain packs, domain semantics, or domain runtime adapters
- domain tooling and output production to make the viewer easier to build
- live run artifacts or producer behavior

The harness and active domains are sensitive, concurrently evolving systems.
The viewer must consume them without reshaping them from the UI branch.

If the UI would benefit from a different intake shape, work is limited to the
viewer-owned seam:

- frontend wire types and normalizers
- replay transport and fixture adapters
- viewer-owned renderer/domain adapters
- viewer-owned API/projection contracts outside the harness, when explicitly
  in scope
- a documented upstream contract request when the producer lacks required
  information

Do not solve an intake mismatch by patching the harness or domain implementation.
Preserve the native payload, adapt it at the viewer boundary when the mapping is
mechanical and lossless, and record any genuinely missing producer contract for
separate upstream work.

Current domains are read-only compatibility evidence for the viewer. Inspect
transcript-edit, deed-to-IR, mapping, and their replay/output shapes to ensure
the universal model serves real work cleanly. Do not promote their vocabulary
into the generic shell, and do not edit those domains from the UI effort.

## Why This Exists

The harness is becoming a durable, generic mission machine with pluggable
domain packs. Its UI must be equally universal. Building a new viewer for each
pipeline would recreate domain coupling at the product layer and make every
future agent expensive to ship.

The Agent Viewer should instead be one reusable window into any Plattera agent
process. Transcript edit, deed-to-IR, mapping, validation, document analysis,
and future unrelated domains should all enter the same foundational
experience. Domain adapters may improve presentation, but an unknown domain
must remain usable through generic fallbacks.

The goal is not a prettier log viewer. The goal is a legible, trustworthy,
interactive view into the agent's work.

## North Star

**The user should be able to watch an agent run like a movie, pause to inspect
any meaningful object, reveal the underlying structures when desired, and
communicate or steer without leaving the run context.**

The default experience is clean and human-readable. The full underlying truth
remains available through progressive disclosure.

## Product Principles

### 1. A Live Work Narrative, Not A Log Tail

The primary surface should communicate purposeful motion:

- what the agent is trying to accomplish
- what it is inspecting now
- what action or tool it requested
- what result came back
- what changed in mission or resolution state
- what evidence or artifact was created
- what remains open, blocked, or waiting
- what the agent plans to do next

Raw trace events remain inspectable, but raw event volume must not define the
default experience. The movie should be authored from meaningful run events,
turns, actions, state changes, artifacts, delegation, and interaction posture.

### 2. Clean By Default, Raw On Demand

Most users will want a concise, curated presentation. Expert users, reviewers,
and developers will sometimes need the actual payload.

Every important presented object should therefore support two layers:

- a polished view optimized for comprehension and action
- a raw or structural view that preserves the source data and provenance

Raw access is not a separate debugging product. It is a consistent inspection
capability available from turns, actions, tool results, state, resolution
items, artifacts, evidence, delegation, HITL, and outcomes.

The UI must never simplify by silently discarding unknown fields.

### 3. One Core Viewer, Optional Domain Intelligence

The core viewer owns universal concepts only:

- run lifecycle
- turns and activity
- actions and results
- mission and resolution state
- continuity and refs
- artifacts and evidence
- delegation
- observability
- interaction and HITL
- outcomes and handoffs

Domain adapters may register specialized renderers and commands. They must not
fork the run shell, chronology, state model, persistence behavior, or
interaction system.

The generic viewer must remain useful when it has never seen the domain ID,
tool ID, artifact kind, event kind, or payload shape before.

### 4. Artifact-Native And Ref-Aware

Artifacts are first-class parts of the run story, not attachments at the end.
The viewer should expose:

- source artifacts
- working artifacts and revisions
- derived artifacts such as crops, locators, diffs, and transformed data
- evidence artifacts
- published outputs
- lineage and relationships
- latest, pinned, hydrated, superseded, and final posture where available

The viewer should understand references generically and resolve them through a
bounded artifact gateway. It must not require every artifact to be embedded in
events or React state.

### 5. Interaction Preserves Causality

The user should be able to:

- answer a blocking or asynchronous HITL request
- send information or clarification
- request another review or correction
- steer attention toward an item or artifact
- invoke explicitly exposed viewer actions
- approve or reject a handoff when the product flow supports it

The UI must show what happened to that input. Useful generic postures include:

- drafted
- submitted
- received by transport
- surfaced to the agent
- acknowledged by the agent
- superseded or no longer applicable

Submission is not semantic incorporation. Only an agent-authored or explicitly
human-authored state transition may claim that the meaning was incorporated.

### 6. The Viewer Is Trustworthy Across Time

A user may open the viewer before, during, or after a run. Refreshing,
reconnecting, replaying, or resuming must not erase the understandable run
story.

Durable snapshots, persisted state, artifacts, and replay data are the source
of truth. Streaming improves immediacy. It must not become the only way the UI
knows what happened.

### 7. Existing Human Workspaces Remain Valuable

The Agent Viewer is a second agent-facing layer over Plattera's existing
human-centered workspaces. It should deep-link or hand off to specialized map,
document, schema, and other workspaces when that is the better tool.

It should not absorb every product workspace into one enormous modal.

## Experience Model

The viewer should support four progressively deeper modes without feeling like
four separate applications.

### Watch

The default mode. The user sees the live run narrative, current focus, major
state changes, produced artifacts, blockers, and requests for attention.

The experience should be calm enough to leave open while the agent works and
dense enough that the user can understand progress at a glance.

### Inspect

The user selects a turn, action, resolution item, artifact, evidence packet,
delegate result, or outcome and sees its relationships and curated details.

Selection should preserve context: inspecting an artifact should not make the
user lose where it appeared in the run or which work item it supports.

### Raw

The user reveals source structures such as:

- JSON trees and JSON paths
- native event payloads
- action request and result envelopes
- mission state and resolution state snapshots
- artifact descriptors, refs, and lineage
- continuity and pin/hydration state
- delegate request and observation payloads
- timing, token, retry, and model metadata
- final output and terminal envelopes

Raw views should provide readable formatting and stable identity. Unknown data
must be shown, not omitted because no purpose-built component exists.

### Intervene

The user answers, messages, supplies information, or invokes an available
action. Intervention should be focused around the object that caused it, with
relevant evidence and downstream consequence visible.

Intervention is part of the run timeline and must remain auditable.

## Core Surface Anatomy

The exact layout may evolve, but the conceptual surfaces should remain stable.

### Run Header And Chapter Context

Shows run identity, domain, lifecycle posture, active chapter/mode, elapsed
time, connection posture, terminal state, and high-signal controls.

The header should be compact. It is orientation, not a dashboard by itself.

### Live Activity And Turn Timeline

Shows the movie of the run:

- turn boundaries
- agent-authored rationale or progress
- requested actions and batches
- tool results, refusals, and repairs
- state changes
- delegate activity
- HITL and user messages
- artifact creation and publication
- terminal outcome

The timeline should distinguish narrative from high-frequency ticker or
diagnostic updates. Users should be able to scrub or step through a replay
without changing the underlying model.

### Universal Canvas

The central display area renders the selected object. It is artifact-type
agnostic at the shell level and chooses a renderer through a registry.

Baseline generic renderers should cover:

- structured JSON and unknown payloads
- plain or rich text
- images and media placeholders
- tables and lists
- diffs and revisions
- ref and lineage summaries
- generic state/resolution structures
- action/result envelopes

Domain renderers may add maps, geometry, deed-specific source comparisons,
transcript lanes, evidence locators, or other specialized presentations.

The canvas must always have a safe fallback. An unknown artifact is still an
inspectable artifact.

### Mission And Resolution Inspector

Presents the agent-authored work universe in a scannable form:

- mission posture
- active focus
- resolution items
- candidate and determined values
- blockers and waiting posture
- dependencies and relationships
- linked evidence and artifacts
- closure and handoff posture

A graph visualization is useful when relationships matter, but it is one view
of resolution state rather than a second source of truth. Users should also be
able to inspect the same state as a list/table and as raw structured data.

Do not create new architecture around the retired `work_board` vocabulary.
Use current generic mission-state and resolution-state concepts.

### Artifact And Evidence Inventory

Provides a complete, filterable inventory of source, working, derived,
evidence, and output objects. It should support relationship-driven navigation:

- show where an artifact came from
- show which turn or action created it
- show which resolution item or HITL prompt references it
- show newer or older revisions
- show the final output that incorporates it when known

### Interaction Tray

Holds active HITL requests and user communication. A prompt should arrive with
the relevant evidence, choices, free-form input where appropriate, and enough
context to understand what is blocked or affected.

General steering should be available without pretending every message is a
blocking HITL answer.

### Observability And Delegation

Advanced inspection should expose model calls, timing, token usage, retries,
streaming posture, delegate requests, delegate observations, and integration
into the parent run.

These are important for trust and engineering review but should not overwhelm
the default watch experience.

### Outcome And Handoff

The end state should explain:

- what was produced
- what is complete, partial, blocked, or unresolved
- what output package is canonical
- what important decisions or human inputs affected it
- what dependencies remain
- whether a downstream handoff is available, pending approval, automatic, or
  complete

The user should not need to read the full timeline to understand the final
posture.

## Renderer And Domain Extension Model

The shell must never branch on concrete domain IDs. Renderer resolution should
be registry-driven using generic metadata such as:

- primitive lane
- domain ID
- artifact or evidence kind
- tool/action ID
- declared media/content type
- renderer hints supplied by a bounded domain adapter

A domain plugin may provide:

- artifact and evidence renderers
- state/resolution presentations
- action/result presenters
- domain-specific viewer actions
- links into an existing product workspace

A domain plugin may not own:

- run chronology
- snapshot or replay persistence
- generic selection/navigation state
- generic HITL transport
- generic raw inspection
- generic connection/reconnect behavior

Fallback behavior is a release requirement, not an error state reserved for
development.

## Raw Inspection Standard

Raw inspection should be consistent across the product. Every raw panel should
make the following available when present:

- stable object identity
- schema/protocol version
- source lane and event/turn identity
- refs and resolved artifact path tokens
- structured payload with unknown fields preserved
- related objects and lineage
- timestamps and sequence numbers
- provenance or adapter/renderer identity

Raw views must remain read-only unless an explicit viewer action represents a
supported mutation. Editing JSON in the inspector must not become an implicit
runtime control channel.

Sensitive values, raw prompts, credentials, absolute local paths, and omitted
binary data remain subject to sanitization and access policy.

## Replay And Cloud Development Model

Cloud UI development must not depend on live harness runs or committed source
deed imagery.

The checked-in replay under `docs/ui-agent-resources/fixtures/` is the primary
development resource. It preserves realistic run structure while keeping git
lightweight and safe.

The cloud implementation should:

1. Read `replay_manifest.json` first.
2. Treat `replay/events.jsonl` and `replay/turn_index.json` as the replay clock
   and chronology.
3. Load per-turn snapshots only when inspecting a turn.
4. Use the artifact and media catalogs to resolve refs.
5. Render `media/placeholder.svg` through the same image renderer used for real
   media; do not special-case placeholder UI.
6. Exercise HITL, user messages, delegate results, action batches, timing,
   continuity, artifacts, final state, and terminal outcome from the fixture.
7. Preserve unknown fields and tolerate absent optional fields.
8. Keep replay transport separate from normalization and rendering so the same
   UI model can consume live production snapshots and streams later.

Transcript-edit data is a representative stress case, not the universal
schema. Do not derive foundational UI concepts from transcript-specific keys.

## Required Generic States

The UI should be intentionally designed and tested for:

- no run selected
- run starting with little data
- live run with active streaming
- disconnected stream with durable snapshot available
- reconnect and replay catch-up
- unknown domain and unknown artifact types
- artifact loading, unavailable, sanitized, or unresolved
- active blocking HITL
- asynchronous user message pending agent attention
- delegate running, completed, refused, or failed
- partial/blocked terminal outcome
- completed outcome with published artifacts
- historical replay with scrub/step controls
- large inventories and long runs

Empty and failure states should explain posture without exposing implementation
noise or implying semantic conclusions the harness did not author.

## Visual And Interaction Direction

The viewer is an operational cockpit, not a marketing page.

It should feel:

- sleek, restrained, and high-trust
- dense but organized
- quiet during normal progress
- explicit when the user is needed
- fast to scan repeatedly
- capable of presenting visual artifacts at useful size

Prefer strong hierarchy, stable geometry, compact controls, restrained status
color, readable typography, and predictable navigation. Avoid decorative
dashboard cards, giant headings, explanatory feature copy, and novelty visuals
that compete with the actual work.

The agent's artifacts and evidence are the visual content.

## Architectural Guardrails

- Cloud UI work does not modify the harness, active domain packs, or domain
  tooling. Intake mismatches are handled at the viewer-owned seam or documented
  as separate upstream contract needs.
- Transport, replay, normalization, registry, selection state, rendering,
  interaction, and shell layout remain separate responsibilities.
- The shell does not scan native payloads for domain-specific fields.
- Renderers do not fetch run state or own transport.
- Domain adapters translate and register; they do not become mini runtimes.
- Raw inspectors preserve unknown fields and do not author state.
- Streaming enriches durable state rather than replacing it.
- User feedback transport does not claim semantic incorporation.
- The existing human workspaces remain separate destinations.
- Large or high-churn files must be decomposed before they become new
  monoliths.

## Non-Goals

The first universal viewer is not required to:

- perfectly visualize every future artifact type
- replace every existing Plattera workspace
- expose unrestricted filesystem access
- allow arbitrary mutation of raw state
- mirror every backend diagnostic in the default timeline
- hardcode one workflow's phases as universal product navigation
- infer domain meaning when an adapter or payload does not supply it

## Cloud Agent Working Agreement

A cloud agent implementing this vision should:

1. Read the source hierarchy at the top of this document.
2. Treat `backend/harness/`, active domains, and domain tooling as read-only.
3. Inspect existing viewer code before deciding whether to migrate or replace
   a component.
4. Build the actual operational viewer, not a landing page or visual mockup.
5. Use the replay bundle as the working backend and keep a transport boundary
   compatible with live snapshots/streams.
6. Implement generic fallback behavior before specialized transcript-edit
   polish.
7. Keep domain-specific behavior in registered adapters/renderers.
8. Preserve raw inspection access for every new polished presentation.
9. Add focused tests around normalization, unknown-kind fallback, replay
   ordering, selection continuity, and interaction lifecycle.
10. Verify desktop and constrained/mobile layouts for overflow and overlap.
11. Leave the branch in reviewable slices with explicit architecture notes for
    unresolved decisions.

If a required producer field or behavior is missing, stop at a viewer-side
adapter or a written seam proposal. Do not cross into harness/domain code to
make the demo work.

The agent may make normal product and design judgments inside these boundaries.
It should not wait for human approval on every spacing, component, or visual
choice. It should escalate decisions that would change the generic contract,
harness authority, persistence model, or domain-extension law.

## Product Acceptance Standard

The viewer is on the right path when a user can:

1. Open any recorded or live run and understand its posture quickly.
2. Watch meaningful work progress without reading raw logs.
3. Select any important turn, action, state item, artifact, evidence packet,
   delegate result, or outcome and inspect it in context.
4. Reveal the underlying structured data without leaving the viewer.
5. Answer HITL or send steering information with visible lifecycle and
   causality.
6. Navigate source, working, derived, evidence, and final artifacts through a
   universal canvas and inventory.
7. Understand final output and unresolved work without replaying the entire
   run.
8. Load an unknown domain replay and still receive a coherent generic
   experience.
9. Add a new domain renderer or action without editing the generic shell.
10. Switch from replay transport to live harness transport without rewriting
    normalization or presentation.

## One-Line Product Rule

Build one universal, artifact-native Agent Viewer that makes agent work legible
by default, inspectable down to raw truth, and steerable without stealing
semantic authorship from the agent or requiring a new UI for every domain.
