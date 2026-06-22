# Universal Agent Viewer Cloud Initiation Brief

## Assignment

Build Plattera's universal Agent Viewer into an elite, durable product surface
for current and future agentic workflows.

This is a long-running UI development assignment, not a one-shot mockup. The
goal is to leave behind a foundation that can continue absorbing new agent
domains, artifact types, run shapes, and interaction patterns without repeated
rewrites or shell-level domain branching.

The implementation approach is intentionally open. Read the existing system,
form a sound architectural view, and make normal engineering and product
judgments autonomously inside the boundaries below.

## Branch Instructions

- Base branch: `moving-into-deed-to-IR`
- Create a dedicated working branch before making UI changes.
- Follow the active Cursor/cloud harness branch-naming convention rather than
  forcing a specific prefix. Choose a descriptive name centered on
  `universal-agent-viewer-ui`.
- Branch from the latest committed `moving-into-deed-to-IR` that contains this
  brief and the Agent Viewer vision documentation.
- Do not commit UI implementation work directly to `moving-into-deed-to-IR`.
- Keep commits small, coherent, and reviewable throughout the long-running
  effort.

The base branch may contain unrelated active backend work in other developers'
working trees. Do not absorb, recreate, or modify that work from the UI branch.

## Highest Virtue

**Elite architectural foundation is more important than short-term feature
volume.**

Prefer:

- clear ownership boundaries
- focused modules with one responsibility
- stable generic contracts
- explicit state and data flow
- renderer/adapter registration instead of shell branching
- durable replay/live transport separation
- safe unknown-kind fallbacks
- progressive disclosure without data loss
- components that remain understandable under substantial future growth

Avoid:

- monolithic panels, hooks, services, or utility files
- domain behavior embedded in the universal shell
- duplicated run models for replay and live transport
- presentation code scanning arbitrary native payloads
- large rewrites that erase working behavior without a migration seam
- convenience abstractions that obscure ownership or data provenance
- visual polish built on unstable state architecture

When speed and structural soundness conflict, choose structural soundness.

## Hard Scope Boundary

The harness is forbidden to edit for this assignment.

Treat the following as read-only:

- `backend/harness/`
- harness runtime, orchestration, trace, audit, continuity, and HITL mechanics
- active domain packs and domain semantics
- domain runtime adapters
- domain tooling and output producers
- live run artifacts

Current domains should be inspected to understand real payloads, artifacts,
state, and workflow needs. They are compatibility evidence for the viewer, not
implementation surfaces for the UI agent.

If the viewer wants a different intake shape:

1. preserve the native source payload
2. adapt mechanically at the viewer-owned transport/normalization seam when
   that mapping is lossless
3. document a proposed upstream contract when required information is absent
4. do not patch the harness or domain producer to make the UI work

Viewer-owned API/projection seam work outside the harness may be proposed or
implemented only when clearly necessary and cleanly isolated. Default to
frontend/replay-side adaptation during cloud development.

## Required Reading

Read these before substantial implementation.

### Repository Law And Engineering Ethos

1. [`AGENTS.md`](../../AGENTS.md)
2. [`docs/ethos/architecture-ethos.md`](../ethos/architecture-ethos.md)
3. [`docs/ethos/structure-ethos.md`](../ethos/structure-ethos.md)
4. [`docs/ethos/testing-ethos.md`](../ethos/testing-ethos.md)
5. [`docs/ethos/agent-engine-ergonomics-theory.md`](../ethos/agent-engine-ergonomics-theory.md)

### Agent Viewer Product And Architecture

1. [`docs/architecture/agent-viewer-product-vision.md`](../architecture/agent-viewer-product-vision.md)
2. [`docs/architecture/agent-viewer-v1.md`](../architecture/agent-viewer-v1.md)
3. [`frontend/src/components/agent-viewer/agents.md`](../../frontend/src/components/agent-viewer/agents.md)

The product vision defines the desired experience. The engineering brief
defines boundaries and target structure. The local `agents.md` defines
implementation invariants near the current code.

### Replay And Universal Viewer Contract

1. [`docs/ui-agent-resources/README.md`](./README.md)
2. [`docs/ui-agent-resources/platform-viewer-contract.md`](./platform-viewer-contract.md)
3. [`docs/ui-agent-resources/agents.md`](./agents.md)
4. [`replay_manifest.json`](./fixtures/practice-row-live-20260619-76/replay_manifest.json)

Use the replay bundle as the cloud development backend. It contains a realistic
multi-turn agent run, artifacts, state, delegation, HITL, timing, continuity,
and final outcome without committing real deed imagery.

### Read-Only Harness Context

These explain what the UI is observing and the authority boundaries it must
respect:

1. [`harness-constitution.md`](../architecture/harness/harness-constitution.md)
2. [`domain-pack-constitution.md`](../architecture/harness/domain-pack-constitution.md)
3. [`hitl-constitution.md`](../architecture/harness/hitl-constitution.md)
4. [`domain-runtime-adapter-architecture.md`](../architecture/harness/domain-runtime-adapter-architecture.md)
5. [`delegate-subtask-architecture.md`](../architecture/harness/delegate-subtask-architecture.md)

These files are context, not authorization to edit harness/domain code.

## Product Goal

Create one universal, canvas-first agent monitoring and interaction workspace
that lets a user:

- watch meaningful agent work unfold like a movie
- see what material the agent is currently using or producing
- inspect turns, actions, results, state, artifacts, evidence, delegation, and
  outcomes
- navigate growing mission/resolution inventory cleanly
- reveal raw structures and provenance whenever desired
- answer HITL and send context-addressed guidance
- monitor multiple concurrent runs or agents
- close a viewer without affecting the underlying process
- return to agent work through product-scope navigation, currently often by
  dossier
- follow one continuous mission across explicit agent and domain handoffs

The primary metaphor is not chat. The primary experience is a visual agent
workstation with a live canvas, state/inventory, and a supporting communication
feed.

## Universal Product Model

Keep these identities distinct:

- product scope, currently often a dossier
- mission thread spanning a continuous user goal
- run or job execution
- chapter or domain handoff segment
- primary agent, downstream agent, or delegate participant
- turn, action, result, and artifact identities

The viewer may open one instance per mission, run, job, or participant. Several
instances may coexist. Closing/unmounting a viewer is presentation-only and
must never stop, pause, or cancel a run.

Current transcript-edit, deed-to-IR, and mapping domains must be serviced
cleanly, but none of their vocabulary should become required universal shell
state. A future unrelated agent domain should still receive a coherent generic
experience through fallback renderers and raw inspection.

## Experience Standard

The default experience should be sleek, minimal, dense, and user-oriented.
Users should see only the information useful for understanding progress,
evidence, blockers, decisions, and outputs. Deeper detail stays one interaction
away.

The viewer should support:

- a persistent run/agent navigator grouped through a generic product-scope
  adapter
- a compact run header with truthful working/waiting/interaction posture
- a live activity/turn feed
- a central universal artifact and evidence canvas
- follow-live attention showing hydrated, pinned, active, and newly created
  material
- stable mission/resolution groups and items that grow with authored state
- candidates, determinations, blockers, dependencies, evidence, and raw data
- a complete source/working/derived/evidence/output artifact inventory
- contextual HITL and communication anchored to selected objects
- observability and delegation detail through progressive disclosure
- clear outcomes and cross-domain handoff chapters

Operational transparency means agent-authored focus, intent, progress, plans,
actions, results, and state changes. Do not expose hidden chain-of-thought or
fabricate reasoning narration.

## Replay Development Rule

Replay and live operation must converge on the same normalized UI model.

Keep separate:

- replay file loading and clock control
- live snapshot/SSE transport
- wire normalization
- selection and viewer state
- renderer lookup
- presentation components
- interaction submission

Do not build a transcript-edit replay player that later needs to be replaced by
the real Agent Viewer. Build the Agent Viewer with a replay transport.

Placeholder media must flow through normal artifact/media rendering. Unknown
fields and unknown artifact/tool/event kinds must remain inspectable.

## Autonomy And Working Style

You are expected to work with substantial autonomy.

- Inspect the existing code before deciding whether to migrate or replace a
  component.
- Make ordinary layout, interaction, component, state, and styling decisions
  without repeatedly asking for approval.
- Build the operational product, not a landing page or static concept mockup.
- Work in coherent vertical or architectural slices based on your judgment.
- Keep useful existing behavior when it fits the target architecture.
- Decompose legacy monoliths deliberately rather than adding more behavior to
  them.
- Add focused tests for durable contracts and important interaction behavior.
- Use replay screenshots and responsive verification to evaluate the actual
  experience.
- Record meaningful architectural decisions or unresolved contract needs in
  docs rather than leaving them implicit.
- Commit and push reviewable progress regularly on the dedicated UI branch.

Do not wait for detailed human sequencing. Choose the next structurally useful
slice and keep moving.

Escalate only when a decision would:

- require editing the forbidden harness/domain surfaces
- change the generic viewer contract materially
- create a new persistence or runtime authority
- remove or replace a major existing product workflow
- require unavailable product information that cannot be represented honestly
  through fixtures or generic fallbacks

## Long-Running Definition Of Success

The effort is succeeding when:

- architecture remains clear as functionality grows
- the shell contains no current-domain branches
- replay and live data share one model
- every polished view has raw/provenance access
- unknown data degrades into useful generic presentation
- several concurrent runs remain navigable and distinct
- handoffs remain continuous but explicitly denoted
- user inspection does not fight live-follow behavior
- contextual feedback has an honest pending/surfaced lifecycle
- a new domain can register renderers/actions without rewriting the shell
- the experience feels like an elite agent command center rather than a log
  tail or chat clone

The assignment is not complete merely because the replay renders. The durable
goal is a universal foundation that future Plattera agentic workflows can adopt
without structural compromise.

## One-Line Mandate

Build the universal Agent Viewer as a clean, canvas-first, deeply inspectable,
contextually steerable agent workspace whose architecture is strong enough to
serve every future Plattera agent domain without touching the harness or
rebuilding the UI per pipeline.
