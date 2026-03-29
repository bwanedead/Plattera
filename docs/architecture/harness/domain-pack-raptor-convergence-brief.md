# Domain-Pack Raptor Convergence Brief

Date: 2026-03-28  
Status: Open-ended execution brief  
Scope: Agent-level domain-pack layer only

Related:

- `docs/architecture/harness/harness-constitution.md`
- `docs/architecture/harness/domain-pack-constitution.md`
- `docs/architecture/harness/domain-pack-architecture.md`
- `docs/architecture/harness/native-harness-core-and-domain-pack-architecture-v1.md`
- `docs/architecture/agent-kernel/domain-pack-interface-v1.md`
- `docs/architecture/harness/prompt-system-architecture.md`
- `docs/architecture/harness/transcript-edit-domain-pack-target.md`
- `docs/architecture/harness/deed-to-ir-domain-pack-target.md`
- `docs/ethos/architecture-ethos.md`
- `docs/ethos/structure-ethos.md`
- `.codex/agents/domain-pack-raptor-reviewer.toml`

---

## 1. Purpose

This brief is for the next open-ended convergence phase:

- turning the domain layer into a clean native domain-pack ecosystem on top of the finished harness core

This is not:

- a request to preserve old domains
- a request to keep compatibility stacks comfortable
- a request to let legacy tooling or wrappers survive because they are familiar
- a request to redesign lower-level infrastructure that is outside the domain-pack layer

The goal is a **Raptor 3 domain-pack layer**:

- one clean harness core underneath
- one clean domain-pack root above it
- one clear shared support surface for domain-pack contracts and prompt doctrine
- one separate tooling root for deterministic capability tooling
- one separate workflow-service root for runtime/application support
- no hidden controller species
- no compatibility museums
- no wrapper packages surviving without a seat in the final architecture

The harness is already the planet core.
This phase is about rebuilding the outer semantic crust so it matches that core.

---

## 2. North Star

The end state is:

- the harness remains the finished generic machine
- domain packs are thin bounded semantic bundles that plug into it directly
- every real domain lives under one coherent domain-pack root
- shared domain-pack support lives in one coherent common support area
- deterministic tooling is separate from domain-pack semantics
- tooling may be universal, family-scoped, or domain-scoped, but it is not harness machinery
- product composition wires capabilities/providers without being mistaken for domain meaning
- no old runtime species, controller loops, compatibility wrappers, or adapter chains remain alive as the actual domain layer

Short form:

- harness owns machinery
- domain pack owns semantics
- tooling owns deterministic capability implementation
- workflow services own runtime/application support
- product composition owns concrete provider wiring
- agent owns authored motion

If any layer starts owning another layer's job, the design is drifting.

---

## 3. Ultimate Outcome Expression

Do not call this phase complete until the repo can honestly be described like this:

> Plattera has one native harness core and a native domain-pack ecosystem on top of it.  
> Domain packs are bounded semantic skins, not hidden runtimes.  
> Shared domain-pack support is explicit and centralized.  
> Deterministic tooling is explicit and separate.  
> Old domain/controller species and compatibility shells are gone.  
> Adding a new domain means adding a new clean pack, not copying a legacy stack.

That is the Raptor domain-pack target.

---

## 4. Read-First Guidance

Before each substantial cut, re-anchor on:

1. `docs/architecture/harness/harness-constitution.md`
2. `docs/architecture/harness/domain-pack-constitution.md`
3. `docs/architecture/harness/domain-pack-architecture.md`
4. `docs/architecture/harness/native-harness-core-and-domain-pack-architecture-v1.md`
5. `docs/architecture/agent-kernel/domain-pack-interface-v1.md`
6. `docs/architecture/harness/prompt-system-architecture.md`
7. `docs/ethos/architecture-ethos.md`
8. `docs/ethos/structure-ethos.md`

Use the constitutions as law.

Use `.codex/agents/domain-pack-raptor-reviewer.toml` as the standing thematic reviewer.

---

## 5. Scope Boundary

This phase is about the **agent-level domain-pack layer**.

### 5.1 In scope

- current domain packs and their agent/runtime shells
- shared domain-pack support surfaces
- domain-owned API and CLI entrypoints
- domain-owned tracing/run-state bridges outside `backend/harness`
- domain-owned prompt doctrine sources and prompt assembly surfaces
- top-level wrapper packages that only exist to keep legacy domain shapes alive
- deterministic transcript/deed tooling **only to classify it as keep/extract/delete**

### 5.2 Out of scope unless a piece is explicitly being extracted or relocated

- `backend/harness/`
- `backend/agent_kernel/`
- `backend/feature_graph/`
- lower-level domain infrastructure that is not part of the agent/domain-pack layer
- generic product/service infrastructure unrelated to current domain-pack teardown

Important distinction:

- this phase may decide that a lower-level deterministic helper is worth preserving
- it does **not** redesign the foundational infrastructure itself

---

## 6. Operating Posture

Work from these assumptions:

- the current transcript-edit agent domain is disposable
- the current deed-to-IR agent domain is disposable
- the current controller agent domain is disposable
- wrapper packages that only preserve old domain structure are disposable
- tests or fixtures that exist only to preserve the old domain shape are disposable
- prompt doctrine may be worth preserving
- deterministic capability tooling may be worth extracting
- if something does not clearly belong to the final architecture, delete it first and justify keeping it second

Optimize for:

- deletion over adaptation
- smaller architecture over comfortable migration
- one clean boundary between harness, domain packs, tooling, and product composition
- future scale across many domains, not survival of today's legacy packs

Do not optimize for:

- preserving old controller logic because it already exists
- preserving wrapper packages because they are convenient
- preserving file count
- preserving old domain-specific tests as a memory of prior behavior

---

## 7. What A Native Domain-Pack Ecosystem Must Look Like

### 7.1 Harness core

The harness is the finished machine.
It should not be modified to preserve old packs.

### 7.2 Domain-pack root

The final repo should converge on a single obvious root for domain packs.

Recommended direction:

```text
backend/domains/
  common/
  <family>/
    <domain_a>/
    <domain_b>/
```

Exact path names may still change, but the architectural rule should not:

- all domain packs live under one coherent root
- shared domain-pack support is beside them, not scattered through unrelated trees

### 7.3 Tooling root

Deterministic tooling should not live inside the pack unless it is truly pack-specific and semantic.

It should also not live under `backend/harness/`.

Reason:

- the harness owns generic machine law
- tooling owns deterministic capability implementation
- putting tooling under `harness` would blur machine law with capability realization and risk re-coupling the core to specific families

Recommended direction:

```text
backend/tooling/
  shared/
  <family>/
    <domain>/
```

Where:

- `shared/` holds universal deterministic tooling usable across many domains
- `<family>/` holds family-scoped tooling when it is not universal
- `<family>/<domain>/` holds truly domain-scoped deterministic tooling when it does not deserve to be shared across the family

Examples of things that belong here:

- deterministic text-apply logic
- validators
- deterministic section/normalization helpers
- capability-local schemas/models shared by deterministic helpers
- lower-level capability wrappers that multiple domains can use

What does **not** belong here by default:

- run registries
- endpoint-facing run orchestration shells
- artifact/state persistence services
- application lifecycle or viewer/session support

Those are runtime/application support concerns, not callable capability tooling.
They should usually live under workflow-service roots, not under `backend/tooling/`.

Important clarification:

- not every file inside `backend/tooling/` is itself a callable tool surface
- schema/model modules such as `contracts.py` or `schemas.py` are normal and often necessary there when they define the typed contract for the deterministic capability package
- what matters is responsibility, not whether every file looks like a command

### 7.4 Workflow-service root

Runtime/application support for agent workflows should have its own coherent root under `backend/services/`.

Recommended direction:

```text
backend/services/workflows/
  shared/
  <family>/
    <domain>/
```

Where:

- `shared/` holds workflow-support services that are genuinely reusable across families/domains
- `<family>/` holds family-scoped workflow support when it is not universal
- `<family>/<domain>/` holds domain-scoped workflow support when it is tied to one workflow family/domain

Examples of things that belong here:

- artifact/state persistence services
- run registries
- endpoint-facing workflow bookkeeping
- viewer/session or application-lifecycle support for workflow runs

What does **not** belong here by default:

- harness runtime law
- semantic domain-pack logic
- deterministic apply/validator/normalization tooling

### 7.5 Product composition

Concrete provider and product wiring belongs in product composition surfaces, not in the semantic pack itself.

### 7.6 Shared support

The final shared domain support surface should contain only things like:

- domain-pack contracts
- manifest/handoff/capability contracts
- shared prompt-source block helpers
- prompt observability helpers

It should not become a hidden second harness or a new generic controller layer.

---

## 8. Canonical Domain-Pack Shape

Each mature domain pack should be able to map cleanly onto a bounded shape like:

```text
backend/domains/<domain>/
  manifest.py
  prompting/
    branch.py
  domain_pack.py
  state.py
  projection.py
  focus_hydration.py
  execution_translation.py
  closure.py
  capabilities.py
  handoff.py
```

Not every pack must use these exact filenames.
Not every pack needs every file as a separate module.
The important part is the responsibility split:

- semantic doctrine is explicit
- state authority is explicit
- projection is explicit
- hydration is explicit
- execution translation is explicit
- closure/handoff are explicit
- `domain_pack.py` is thin

The prompting rule is:

- every domain gets a `prompting/` folder
- it may begin with only `branch.py`
- it should grow only when real prompt surface size justifies it
- do not create extra prompt modules preemptively

The deeper rule is:

- the pack is mostly a semantic bundle, not a machinery bundle
- the pack gives the agent domain doctrine, domain vocabulary, domain state surfaces, and semantic translation seams
- the pack does **not** get to re-own runtime law, HITL mechanics, or semantic authorship through deterministic helpers
- the pack does **not** get to invent rich semantic phase grammar or scripted choreography

For transcript-edit specifically, the pack should feel like:

- mission and doctrine
- state authority
- projections / read models
- focus-context hydration for an already-chosen focus
- execution translation from semantic move to concrete action
- closure posture and handoff posture

And the operational stance should be:

- here is the mission
- here is the source content and evidence
- here are the capabilities
- here are the closure layers
- here is the broader family objective
- now pursue closure sensibly

Not like:

- a controller
- a runtime
- a loop script
- a domain-owned HITL subsystem

Important clarification on feedback:

- harness owns HITL / feedback transport lifecycle
- agent owns semantic interpretation of the answer
- the pack may only provide the domain vocabulary and state surfaces that interpretation lands into

That means:

- no deterministic pack helper should be pretending to decide that a feedback answer "closed" the case
- no pack helper should be acting like feedback transport is domain-owned machinery
- if a feedback answer changes domain truth, that change should be agent-authored or explicitly confirmed, then reflected in ordinary pack-owned state or closure surfaces

For transcript-edit, the most important domain vocabulary should stay narrow and honest:

- mapping-relevant truth posture
- the four closure layers
- bounded unresolved-item / blocker / dependency posture
- handoff readiness or blockage

Do not inflate the pack with fake ontology just because files want something to talk about.

Do not inflate the pack with semantic phase grammar either.

Keep only:

- minimal mechanical grammar in the harness for bounded execution, waiting, resume, persistence, and observability

Do not keep:

- domain-specific orient/runtime/plan/apply phase ladders as first-class architecture
- hook-shaped runtime vocabulary inside the domain pack

What the pack must not become:

- a controller loop
- a second runtime
- a workflow script
- a compatibility museum
- a bag of unrelated helpers wrapped in a host protocol

---

## 9. Current Repo Reality

Current audited package reality:

- `backend/domains/mapping/transcript_edit/`
  - is now the main blocker
  - root placement is correct, but the internal pack shape is still too transitional
  - `domain_pack.py` still behaves like a runtime species host instead of a thin semantic adapter shell
- `backend/domains/mapping/deed_to_ir/`
  - is now in the correct root
  - currently looks like a small seed pack rather than a major blocker
- `backend/domains/common/`
  - now holds shared domain-pack support in the correct root direction
  - should stay narrow and not become a second harness or junk drawer
- `backend/tooling/mapping/transcription_edit/`
  - now holds the preserved deterministic transcript-edit capability code
- `backend/services/workflows/mapping/transcription_edit/`
  - now holds workflow/application support such as persistence and run registry

Already removed:

- `backend/agents/controller/`
- `backend/transcript_edit/`
- `backend/transcription_edit_loop/` as a live code root

Main remaining architectural blocker:

- `backend/domains/mapping/transcript_edit/domain_pack.py`
  - still too large
  - still too phase/runtime-shaped internally
  - still too close to a host runtime species instead of a semantic shell

Secondary watchpoints:

- `backend/pipelines/image_to_text/pipeline.py`
  - still directly coupled to transcript-edit runtime-era seams
- `backend/feature_graph/kernel_executor_composition.py`
  - still directly composes transcript-edit-specific provider/menu surfaces
- local pack notes and stale residue
  - should teach the final native boundary, not controller-era lineage

This means the current problem is not just "refactor a few modules."

The current problem is:

- the root shape now exists, but transcript-edit still carries too much old-world internal shape
- `domain_pack.py` is still oversized and runtime-shaped
- product/API/pipeline surfaces still treat transcript-edit as a special built-in species
- the prompt/doctrine split must be preserved while the old runtime-era pack internals are removed

That is why this phase should be deletion-biased.

---

## 10. Preserve / Extract / Delete Map

### 10.1 Preserve as foundational infrastructure

These are outside the domain-pack teardown unless a specific extraction path requires touching them:

- `backend/harness/`
- `backend/agent_kernel/`
- `backend/feature_graph/`

### 10.2 Preserve, but classify as shared domain support

These are likely real final-architecture candidates, though they may later move under a cleaner root:

- `backend/agents/common/domain_pack_contracts.py`
- `backend/agents/common/prompt_sources.py`
- `backend/agents/common/prompt_observability.py`
- other genuinely shared domain-pack support helpers in `backend/agents/common/`

Rule:

- keep only what is truly shared support
- do not let `backend/agents/common/` become a junk drawer

### 10.3 Preserve as doctrine archive or native prompt seed

These are worth preserving for authored wording and domain doctrine, even if the current packages are deleted:

- `backend/agents/transcript_edit/prompt_sources.py`
- `backend/agents/deed_to_ir/prompt_sources.py`
- selected doctrine/prompt contract material from `backend/agents/controller/prompting.py`

Rule:

- preserve the words if they are good
- do not preserve the old package shape just to keep the words

Preferred direction:

- archive or extract them into a clean prompt/doctrine seed area before deleting the old packs

### 10.4 Extract then relocate if genuinely valuable

These are the already-preserved support surfaces that earned a seat:

- `backend/tooling/mapping/transcription_edit/`
- `backend/services/workflows/mapping/transcription_edit/`

Rule:

- keep only the pieces that clearly belong to deterministic tooling or workflow/application support
- do not let these roots regrow old domain runtime species under softer names
- if a piece does not clearly belong there, delete it rather than preserving it by inertia

### 10.5 Delete outright

These should not survive as part of the final domain-pack architecture:

- `backend/agents/transcript_edit/`
- runtime-era residue still living under `backend/agents/`

And likely also the old domain-owned outer shells tied directly to them once the rebuilt packs exist:

- `backend/api/endpoints/transcript_edit_agent.py`
- transcript-edit-specific viewer/runtime shells
- old pipeline or handoff glue that exists only for the retiring domain-pack species

Audit targets here include:

- `backend/pipelines/image_to_text/pipeline.py`
- `backend/agents/schema_mapping/handoff_bridge.py`

If they only preserve the old transcript/deed/controller flow, delete them with the packs.

---

## 11. Hard Rules For Preservation

Do not preserve a surface just because it already exists.

A surface only earns preservation if it clearly belongs to one of these four categories:

1. harness core
2. foundational infrastructure
3. shared domain-pack support
4. deterministic tooling that is worth relocating

Everything else is either:

- doctrine worth archiving
- or legacy runtime residue worth deleting

If uncertain:

- delete
- then re-add later only if the rebuilt architecture proves the need

---

## 12. Prompt Doctrine Rule

Prompt doctrine is one of the few things that is often worth preserving.

But preserve it correctly:

- keep authored wording
- discard old runtime/package scaffolding around it

Prompt doctrine should end up as:

- shared trunk doctrine in shared support
- one domain branch source per new pack
- surface-local task framing near the relevant pack surface

The prompt layering rule is fixed:

- harness trunk = generic machine law
- domain branch = domain doctrine and manifestation of that law in one mission family
- run context = current mission-instance state
- surface packet = immediate task + schema
- structured state = descriptive payloads only

Do not let this drift into:

- domain runtime helpers secretly becoming doctrine owners
- run-context payloads becoming strategy prose
- structured state becoming hidden steering
- surface packets re-teaching trunk or branch law

It should not stay embedded in:

- dead controller loops
- dead wrapper packages
- dead domain runtime stacks

---

## 13. What Must Be Swept Away

The following should not survive this phase:

- hidden controller species
- domain-specific runtime stacks pretending to be packs
- wrapper packages that re-export old tooling
- compatibility-only handoff bridges
- action-ID compatibility layers used as domain identity
- no-op protocol parity seams preserved only because the old design expected them
- domain-private tracing/run-state/reporting bridges that belong to the retired pack stack
- domain-specific API/CLI entrypoints that exist only for the retiring pack species

If a surface exists only to keep the old world legible, it should cease to exist.

---

## 14. Recommended Working Order

1. Freeze the north star and boundary.
2. Inventory the current domain-side packages and classify each surface as:
   - preserve
   - extract then relocate
   - archive as doctrine
   - delete
3. Preserve prompt doctrine and any truly reusable deterministic tooling first.
4. Delete the old domain-pack/runtime packages and their outer entrypoints.
5. Keep the extracted deterministic tooling and workflow-support roots clean.
6. Stand up the new domain-pack root and shared domain support root.
7. Rebuild fresh native packs directly against the harness/domain-pack constitutions.
8. Move API/product composition to the rebuilt packs instead of legacy `backend/agents/*` species.
9. Delete the legacy `backend/agents/*` domain runtime packages once cut over is complete.
10. Add only generic/scalable tests for the new pack ecosystem, not nostalgia tests for the deleted one.

The important part is sequence:

- preserve the rare good pieces
- then remove the old stack decisively
- then rebuild from first principles

---

## 15. Checkpoint Review Cadence

After each self-assessed checkpoint:

1. review against:
   - `docs/architecture/harness/harness-constitution.md`
   - `docs/architecture/harness/domain-pack-constitution.md`
   - `docs/architecture/harness/domain-pack-architecture.md`
2. run the reviewer at:
   - `.codex/agents/domain-pack-raptor-reviewer.toml`
3. ask it to review the touched surfaces only
4. summarize:
   - converging / mixed / patchwork
   - what became deletable
   - what actually got deleted
   - what was preserved and why
   - what still looks like a hidden second runtime or compatibility museum

Do not move on from a touched area if it still keeps the old stack alive underneath a nicer label.

---

## 16. Definition Of Success

This phase succeeds when:

- the harness remains untouched as the native generic core
- the repo has one clean domain-pack root
- the repo has one clean tooling root for deterministic capability tooling
- the repo has one clean workflow-service root for runtime/application support
- the old transcript-edit, deed-to-IR, and controller runtime species are gone
- wrapper packages like `backend/transcript_edit/` are gone
- only shared domain support and real deterministic tooling survive, and only in clean locations
- new domain packs are thin semantic bundles that read like native first-generation packs, not cleaned-up migrations
- future domains can be added without copying legacy controller stacks

The result should feel like:

- a finished planet core
- a clean outer crust
- a scalable ecosystem for many future domains

Not:

- a cleaned-up ruin of the old world

---

## 17. Review Standard

"Did this checkpoint actually reduce the domain layer to a clean native domain-pack ecosystem with separate tooling, or did it preserve old domain/runtime species under softer names?"

---

## 18. Checkpoint Notes (2026-03-28)

Current checkpoint read:

- `backend/domains/` exists and is now the canonical domain root.
- `backend/domains/common/` exists and is now the canonical shared domain-support root.
- `backend/domains/mapping/transcript_edit/` and `backend/domains/mapping/deed_to_ir/` exist.
- `backend/agents/controller/` is removed.
- `backend/transcript_edit/` is removed.
- `backend/transcription_edit_loop/` is removed as a code root.
- Canonical CLI remains `backend/api/mission_runtime_cli.py`.
- Deterministic transcript-edit capability code now lives under:
  - `backend/tooling/mapping/transcription_edit/`
- Workflow/application support now lives under:
  - `backend/services/workflows/mapping/transcription_edit/`
- The main remaining architectural blocker is:
  - `backend/domains/mapping/transcript_edit/domain_pack.py`
  - which still carries too much runtime-era shape inside the new domain root

Immediate next rebuild order:

1. Thin `backend/domains/mapping/transcript_edit/domain_pack.py` into a semantic adapter shell.
2. Split transcript-edit by semantic responsibility, not by hook/runtime naming.
3. Preserve the prompt trunk / domain branch architecture while removing runtime-era internal shape.
4. Reduce transcript-edit special-casing in pipeline/product composition.
5. Delete stale residue, empty dirs, and cache artifacts after each cut.

Guardrail reminder:

- Do not preserve controller/runtime species as concepts.
- Do not reintroduce family-specific CLI surfaces.
- Do not let a temporary extraction island become permanent by inertia.
- Do not create `domain_pack_runtime.py`-style files or other hook-shaped runtime surrogates inside the pack.
