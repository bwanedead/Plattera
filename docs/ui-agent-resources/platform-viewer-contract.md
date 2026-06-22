# Universal Agent Viewer Contract

## Core Rule

The viewer consumes the harness's generic execution envelope. It does not make
transcript-edit, mapping, or any current tool vocabulary foundational.

Unknown domains, tools, state fields, artifact kinds, and event types must
degrade to readable structured views rather than disappearing or breaking the
interface.

## Stable Viewer Lanes

1. **Run** - identity, lifecycle state, elapsed time, terminal decision.
2. **Turn** - chronology, current phase/posture, authored rationale and progress.
3. **Action** - tool/action identity, alias, inputs, outputs, refusal, batching.
4. **State** - mission, resolution/work graph, stable context, closure dimensions.
5. **Continuity** - pinned refs, latest refs, hydration, resume-visible memory.
6. **Observability** - model/provider timing, tokens, retries, streaming, warnings.
7. **Delegation** - target entity, context refs, prompt, observation, integration.
8. **Interaction** - user messages, HITL requests, deferrals, consumed decisions.
9. **Artifacts** - refs, kinds, lineage, previews, media, working/final posture.
10. **Outcome** - final output package, unresolved work, dependencies, handoff.

## Extension Model

- Core renderers understand generic JSON, text, refs, images, state, and events.
- Domain renderers are optional plugins selected by `domain_id`, artifact kind,
  state lane, or tool ID.
- A domain renderer may improve presentation but cannot own navigation,
  chronology, persistence, or the generic run model.
- Tool results and state are inspectable in raw structured form even when no
  specialized renderer exists.

## Replay Bundle v1

The checked-in bundle provides:

- a manifest describing source, sanitization, and file topology
- one compact sanitized turn snapshot per completed turn
- a generic chronological event stream and turn index
- final mission/resolution/stable-context state
- persisted domain artifacts and source-draft JSON
- ref and media catalogs
- one placeholder visual for every omitted binary image
- the human timeline and audit review as reference presentations

The replay is representative data, not the canonical UI schema. Production UI
adapters should tolerate additional fields and missing optional fields.

## Media Policy

Large binaries are not committed. `media_catalog.json` preserves each media
artifact's ref, role, dimensions when known, descriptor relationship, and
original byte size. Every media row points to `media/placeholder.svg` so image
states can be designed without shipping deed imagery.

