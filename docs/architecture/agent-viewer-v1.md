# Agent Viewer V1 Engineering Brief

## Status

Active architecture brief. The transport, snapshot, model-normalization, and
registry foundation is partially implemented, while the universal shell and
domain renderer system remain in progress. This document defines the target
boundaries for continued implementation.

Product and UX intent is defined in the companion document:

- `docs/architecture/agent-viewer-product-vision.md`

Read the product vision first when implementing the viewer. Use this brief for
module boundaries, contracts, and implementation sequencing.

Cloud UI scope is narrower than this architecture brief: the harness, active
domain packs, and domain tooling are read-only. Backend sections below describe
the intended system boundary; they do not authorize the cloud UI agent to edit
those systems. Any intake mismatch must stop at a viewer-owned adapter/contract
seam or become a documented upstream request.

## Why This Exists

Plattera is moving from hidden backend agent loops toward visible, user-facing
agent workflows. The harness is now close enough that the UI needs to become a
first-class control plane: a live window into what the agent is doing, what it
has produced, what evidence supports its claims, where it is blocked, and when a
human answer or handoff approval is needed.

There is already an early Agent Viewer shell in the frontend, but it should be
treated as a prototype/reference rather than a binding architecture. It carries
useful ideas: a live overlay, event feed, artifact canvas, feedback composer, and
some transcript-edit-specific rendering. It also reflects the churn of prior
harness refactors: transport appears partially severed, and several UI paths are
too transcript-edit-shaped for the long-term goal.

The next pass should therefore build a durable Agent Viewer substrate, not just
repair the old panel. The viewer needs to serve transcript-edit, deed-to-IR,
mapping/georeference, validation/render, and future domains without becoming a
monolith or another hidden decision engine.

## Constitutional Boundary

The Agent Viewer is a control plane and read model over harness/domain truth.

It may:

- display run progress, artifacts, evidence, work items, blockers, and handoff
  posture
- collect human feedback and route it through the generic HITL transport
- expose user commands such as review again, approve handoff, open map, or open
  an artifact in a related workspace
- render domain-specific artifacts through registered domain renderers

It must not:

- decide what work exists
- rank or resolve work items
- infer semantic closure
- decide that human feedback has been incorporated
- encode transcript-edit, deed, PLSS, or mapping ontology in the generic shell
- turn UI convenience into harness runtime law

This follows:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/hitl-constitution.md`
- `docs/architecture/harness/domain-pack-constitution.md`
- `docs/architecture/harness/cli-constitution.md`
- `docs/ethos/architecture-ethos.md`
- `docs/ethos/structure-ethos.md`

The viewer can make the agent's authored state legible. It cannot author that
state.

## Core Product Intent

The user should be able to watch the agent work without reading raw logs,
terminal output, or JSON audit files.

For image/document workflows, if the agent creates a crop, locator, highlight,
rendered evidence packet, or transformed artifact, the user should see it. For
text/data workflows, if the agent cites a span, table cell, JSON path, diff,
query result, or trace, the user should see a compact human-readable view. For
work graph items, the user should see what is open, determined, blocked,
evidence-backed, disputed, or ready for handoff.

The experience should feel like an operational cockpit: dense, clean, polished,
and minimal. It should not feel like a marketing page, raw debugger, or
backend-log wrapper.

## Generic Viewer Primitives

The base viewer should understand only domain-agnostic primitives.

### `ViewerScope`

A UI-owned grouping key for product navigation. In the current mapping product,
this commonly points to a dossier. Other products may bind it to a project,
case, repository, or document set. This is viewer/product composition metadata,
not new harness ontology.

### `MissionThread`

A UI continuity container that groups related runs, chapters, participants,
handoffs, and outputs around one user goal. It allows a cross-domain handoff to
feel continuous while preserving the distinct identities of each underlying
run.

`MissionThread` must be derived from existing launch/handoff metadata or
viewer-owned association data. The cloud UI effort must not modify the harness
to create it.

### `ViewerInstance`

The local presentation state for one open viewer bound to a mission thread,
run/job, or participant. Closing an instance detaches the UI only. Process
control remains an explicit action and must never be coupled to component
unmount or window close.

### `AgentRun`

The active logical run or mission. Carries identity, status, active chapter,
terminal posture, timestamps, and high-signal refs.

### `RunChapter`

A visible segment in the run story. Examples: T0 draft generation,
transcript-edit, deed-to-IR, mapping/georeference, validation/render, handoff.
Chapters are not hardcoded phases in the shell. They are projected from
harness/domain state.

A chapter may also denote an explicit agent/domain handoff inside a continuous
mission thread.

### `ParticipantDescriptor`

Identifies the primary agent, downstream agent, or delegate responsible for a
visible portion of work. Participant identity supports navigation and
attribution; it does not imply a new runtime lifecycle.

### `ActivityEvent`

A short human-facing progress item. This is the "movie" of the run: inspecting
source image, creating evidence, resolving blocker, saving artifact, waiting for
feedback. It is not a raw log line.

### `ArtifactDescriptor`

A durable object produced or consumed by the run. Examples: image, crop,
transcript draft, edit plan, GeoJSON, map render, validation report, JSON data,
diff, table, prompt packet, trace excerpt.

Artifacts should carry a generic `kind`, `ref`, title, summary, created time,
domain hints, and optional preview metadata. The viewer shell should not parse
domain semantics directly from arbitrary artifact JSON.

### `EvidencePacket`

A curated proof bundle connected to one or more work items or prompts. Evidence
can include image locators, crops, text spans, table cells, diffs, JSON paths,
trace snippets, query results, map overlays, or rendered validation outputs.

Evidence is displayable. Its meaning remains agent/domain-authored.

### `WorkItem`

A user-facing claim, task, blocker, decision, dependency, or readiness item.
This is the viewer's claim inventory surface.

Minimum shape:

- title
- generic status
- candidate values
- determined value
- confidence/posture
- blocker/waiting state
- evidence refs
- relation refs
- domain payload for domain renderers

The generic viewer should not know mission-specific key families.

### `HITLPrompt`

A human feedback request projected from generic HITL transport and
agent-authored prompt content.

Minimum shape:

- prompt id
- blocking vs async posture
- short question
- choices
- optional note field
- relevant evidence refs
- affected work item refs
- downstream consequence/context

The UI captures the answer. The agent remains responsible for interpreting it
on a later turn.

### `ViewerAction`

A user command exposed by the run projection. Examples:

- open map
- open artifact
- approve handoff
- pause/resume where supported
- ask agent to review again
- submit feedback
- start next chapter

Actions are generic command descriptors. Domain/product adapters own what the
target means.

### `HandoffState`

The visible posture for passing an output to the next workflow: not ready,
partial, blocked, review-ready, publish-ready, handed off, or failed. The
generic status is transport/display posture; domain packs own handoff meaning.

## Ownership Boundaries

### Backend API Transport

Owns HTTP/SSE mechanics only.

Candidate home:

- `backend/api/endpoints/agent_viewer.py`

Responsibilities:

- serve run snapshots
- serve SSE event streams
- serve artifact reads through a safe gateway
- accept feedback/action posts

Non-responsibilities:

- domain semantic projection logic
- artifact interpretation
- work item authorship
- HITL answer interpretation

### Backend Projection Service

Owns the generic viewer read model assembly.

Candidate home:

- `backend/services/agent_viewer/projection.py`

Responsibilities:

- merge generic harness state, domain adapter projections, latest refs, and
  event history into `AgentViewerSnapshot`
- preserve unknown domain payloads without interpretation
- expose generic status and structural refs

Non-responsibilities:

- deciding semantic closure
- inventing work items from validators
- deciding human answers are incorporated

### Backend Artifact Gateway

Owns safe artifact opening for the viewer.

Candidate home:

- `backend/services/agent_viewer/artifact_gateway.py`

Responsibilities:

- resolve allowed artifact refs
- return JSON/text/image/blob metadata
- enforce path safety and content-type decisions
- avoid exposing secrets

### Backend Event Bus

Owns live delivery and short replay only.

Existing home:

- `backend/services/agent_viewer/event_bus.py`

The event bus is not the source of truth. The snapshot is. SSE exists for
immediacy, while snapshots support refresh, reconnect, replay, and opening the
viewer after the run already started.

### Backend Feedback Store

Owns generic feedback persistence.

Existing home:

- `backend/services/agent_viewer/feedback_store.py`

It stores prompt answers and notes. It must not interpret the answer.

### Domain Viewer Adapters

Own domain-specific projection into generic viewer primitives.

Potential homes:

- `backend/domains/<family>/<domain>/viewer_projection.py`
- or a bounded adapter under the domain's harness-facing seam

Responsibilities:

- map domain state/artifacts into generic `WorkItem`, `EvidencePacket`,
  `ArtifactDescriptor`, `RunChapter`, and `ViewerAction` objects
- attach domain payloads for domain renderers
- define domain artifact/evidence kinds

Non-responsibilities:

- frontend rendering code
- API transport
- concrete artifact I/O
- harness runtime law

### Frontend Transport Hooks

Own fetching, reconnect, SSE subscription, and feedback/action POSTs.

Candidate homes:

- `frontend/src/components/agent-viewer/hooks/useAgentViewerRun.ts`
- `frontend/src/services/agentViewerApi.ts`

React presentational components should not call API endpoints directly.

### Frontend Model Normalization

Own conversion from backend wire/snapshot into stable UI view models.

Candidate home:

- `frontend/src/components/agent-viewer/model/`

Responsibilities:

- normalize missing/additive fields
- sort chapters/events/work items
- create fallback view models for unknown kinds
- keep rendering code away from raw backend payload scanning

### Frontend Renderer Registry

Own lookup of renderers by artifact/evidence/action kind.

Candidate home:

- `frontend/src/components/agent-viewer/registry/`

The shell should call the registry. It should not contain `if transcript`,
`if deed`, or `if map` branches.

### Frontend Shell

Owns layout composition only.

Candidate home:

- `frontend/src/components/agent-viewer/shell/AgentViewerShell.tsx`

Responsibilities:

- chapter rail
- activity feed placement
- artifact/evidence canvas placement
- work item inspector placement
- HITL tray placement
- command/action bar placement

Non-responsibilities:

- transport
- raw event parsing
- domain-specific artifact interpretation
- feedback persistence

## Suggested Frontend File Shape

```text
frontend/src/components/agent-viewer/
  agents.md
  shell/
    AgentViewerShell.tsx
    AgentViewerLayout.tsx
    AgentViewerHeader.tsx
  hooks/
    useAgentViewerRun.ts
    useAgentViewerActions.ts
  model/
    types.ts
    wireTypes.ts
    normalizeSnapshot.ts
    normalizeEvents.ts
  registry/
    rendererRegistry.ts
    actionRegistry.ts
  renderers/
    generic/
      GenericArtifactRenderer.tsx
      GenericEvidenceRenderer.tsx
      JsonArtifactRenderer.tsx
      TextArtifactRenderer.tsx
      ImageArtifactRenderer.tsx
      UnknownKindRenderer.tsx
    transcriptEdit/
      TranscriptDraftRenderer.tsx
      TranscriptDiffRenderer.tsx
      ImageLocatorRenderer.tsx
    mapping/
      MapArtifactRenderer.tsx
      GeoJsonOverlayRenderer.tsx
  panels/
    ActivityFeed.tsx
    WorkGraphPanel.tsx
    EvidenceInspector.tsx
    HitlPromptTray.tsx
    ArtifactCanvas.tsx
```

This is a target shape, not a mandate to create every file at once. Add modules
only when the responsibility is needed.

## Suggested Backend File Shape

```text
backend/api/endpoints/
  agent_viewer.py

backend/services/agent_viewer/
  event_bus.py
  feedback_store.py
  artifact_gateway.py
  projection.py
  models.py

backend/domains/<family>/<domain>/
  viewer_projection.py
```

Again, this is a target shape. Start thin.

## Wire Contract Sketch

The initial read model can be intentionally small and additive.

```json
{
  "protocol": "agent_viewer_snapshot_v1",
  "run": {
    "run_id": "run_123",
    "loop_kind": "transcript_edit",
    "status": "running",
    "active_chapter_id": "tx"
  },
  "chapters": [
    {
      "id": "tx",
      "title": "Transcript edit",
      "status": "running",
      "artifact_refs": ["artifact://..."]
    }
  ],
  "activity": [
    {
      "id": "evt_1",
      "chapter_id": "tx",
      "timestamp_epoch_seconds": 0,
      "title": "Inspecting source evidence",
      "detail": "Checking candidate values against the source image.",
      "status": "running"
    }
  ],
  "artifacts": [
    {
      "ref": "artifact://...",
      "kind": "transcript.draft",
      "title": "Working transcript",
      "summary": "Agent-authored working draft"
    }
  ],
  "evidence": [
    {
      "id": "ev_1",
      "kind": "image.locator",
      "title": "Source crop",
      "artifact_refs": ["artifact://crop"]
    }
  ],
  "work_items": [
    {
      "id": "wi_1",
      "title": "Resolve governing value",
      "status": "blocked",
      "candidate_values": ["A", "B"],
      "determined_value": null,
      "evidence_refs": ["ev_1"],
      "domain_payload": {}
    }
  ],
  "hitl_prompts": [
    {
      "prompt_id": "p_1",
      "blocking": true,
      "question": "Which candidate is correct?",
      "choices": ["A", "B", "Unable to determine"],
      "evidence_refs": ["ev_1"],
      "affected_work_item_refs": ["wi_1"]
    }
  ],
  "actions": [
    {
      "id": "open_map",
      "label": "Open map",
      "kind": "open_workspace",
      "target": {
        "workspace": "mapping",
        "artifact_ref": "artifact://geojson"
      }
    }
  ]
}
```

Field names can evolve, but the architectural contract should stay:

- generic shell fields
- typed domain kinds
- opaque domain payload
- artifact refs instead of embedded large objects
- additive compatibility

## Renderer Registry Rule

Renderers should be registered by kind.

Examples:

```ts
registry.registerArtifactRenderer('text.plain', TextArtifactRenderer)
registry.registerArtifactRenderer('json.generic', JsonArtifactRenderer)
registry.registerArtifactRenderer('image.source', ImageArtifactRenderer)
registry.registerArtifactRenderer('transcript.draft', TranscriptDraftRenderer)
registry.registerArtifactRenderer('geojson.map_overlay', GeoJsonOverlayRenderer)

registry.registerEvidenceRenderer('image.locator', ImageLocatorEvidenceRenderer)
registry.registerEvidenceRenderer('text.span', TextSpanEvidenceRenderer)
registry.registerEvidenceRenderer('table.cell', TableCellEvidenceRenderer)
registry.registerEvidenceRenderer('json.path', JsonPathEvidenceRenderer)
```

Unknown kinds must render safely through a generic fallback rather than breaking
the shell.

## Initial Implementation Sequence

### 1. Documentation and local guardrails

- Add this brief.
- Tighten `frontend/src/components/agent-viewer/agents.md`.
- Do not start visual redesign yet.

### 2. Backend transport and snapshot skeleton

- Add `backend/api/endpoints/agent_viewer.py`.
- Register it in `backend/api/router.py`.
- Add or restore:
  - snapshot endpoint
  - SSE endpoint
  - artifact JSON/image endpoint
  - feedback GET/POST endpoint
- Keep endpoints thin.

### 3. Backend projection and artifact gateway

- Add `projection.py`, `models.py`, and `artifact_gateway.py`.
- Build generic snapshots from existing run state where available.
- Preserve current event bus/feedback store.

### 4. Frontend contracts and registry

- Define generic TypeScript read model types.
- Add normalizers.
- Add renderer registry with generic fallback renderers.
- Keep the current viewer shell usable until replacement is ready.

### 5. New shell slice

- Build a minimal `AgentViewerShell` around the generic model:
  - chapter rail
  - activity feed
  - artifact canvas
  - work item panel
  - HITL tray
- Avoid domain polish in this slice.

### 6. Transcript-edit adapter/renderers

- Port useful existing transcript-edit display behaviors into registered
  renderers.
- Keep transcript-specific code out of the generic shell.

### 7. Mapping/deed-to-IR adapter/renderers

- Add map/GeoJSON artifacts and `open_map` viewer action.
- Bridge actions into the existing map workspace rather than embedding all map
  workflow inside the viewer.

## Anti-Monolith Rules

- No component should own transport, normalization, domain interpretation, and
  rendering at the same time.
- No API endpoint should own projection logic.
- No renderer should fetch its own run state.
- No shell component should scan raw event payloads for domain-specific fields.
- No shared viewer type should contain deed-, transcript-, PLSS-, or
  mapping-specific first-class fields.
- No domain adapter should become a runtime/controller.
- No generic fallback should silently erase unknown payloads.
- No HITL UI should mark a prompt semantically resolved merely because an answer
  was submitted.

If a file starts growing because it mixes concerns, split by responsibility
before adding more behavior.

## Acceptance Criteria For The First Real Slice

A first implementation slice is successful when:

- a run can be opened from a stable snapshot endpoint
- refresh/reconnect does not lose the visible run story
- live SSE updates enrich the same model rather than replacing the source of
  truth
- unknown artifact/evidence kinds render safely
- HITL answers persist through the generic feedback channel
- at least one generic artifact renderer and one domain renderer coexist through
  the registry
- the shell contains no transcript/deed/mapping-specific branches
- existing human-centered workspaces remain intact

## Open Questions

- Should the old `AgentViewerPanel` be migrated incrementally or replaced behind
  a new shell entrypoint?
- What should the canonical artifact-ref format be for all viewer-facing
  domains?
- Should viewer actions be submitted to one generic action endpoint first, or
  should some actions deep-link directly into existing workspace routes?
- How should automatic handoff approval be represented: user preference,
  per-run action, or mission-mode policy?
- Which domain owns the first map-specific renderer: deed-to-IR, mapping, or a
  shared geospatial renderer package?

These questions should be resolved in small planning/implementation slices, not
by expanding the shell to handle every case up front.
