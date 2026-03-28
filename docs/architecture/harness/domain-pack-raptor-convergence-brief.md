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
- one separate tooling/support root for deterministic domain tooling
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
- product composition wires capabilities/providers without being mistaken for domain meaning
- no old runtime species, controller loops, compatibility wrappers, or adapter chains remain alive as the actual domain layer

Short form:

- harness owns machinery
- domain pack owns semantics
- tooling owns deterministic capability implementation
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
  <domain_a>/
  <domain_b>/
```

Exact path names may still change, but the architectural rule should not:

- all domain packs live under one coherent root
- shared domain-pack support is beside them, not scattered through unrelated trees

### 7.3 Tooling root

Deterministic domain tooling should not live inside the pack unless it is truly pack-specific and semantic.

Recommended direction:

```text
backend/domain_tooling/
  <capability_or_family>/
```

Examples of things that belong here:

- deterministic text-apply logic
- validators
- deterministic section/normalization helpers
- lower-level capability wrappers that multiple domains can use

### 7.4 Product composition

Concrete provider and product wiring belongs in product composition surfaces, not in the semantic pack itself.

### 7.5 Shared support

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
  prompt_sources.py
  domain_pack.py
  state.py
  projection.py
  focus_hydration.py
  execution_translation.py
  closure.py
  feedback.py
  capabilities.py
  handoff.py
```

Not every pack must use these exact filenames.
The important part is the responsibility split:

- semantic doctrine is explicit
- state authority is explicit
- projection is explicit
- hydration is explicit
- execution translation is explicit
- closure/feedback/handoff are explicit
- `domain_pack.py` is thin

What the pack must not become:

- a controller loop
- a second runtime
- a workflow script
- a compatibility museum
- a bag of unrelated helpers wrapped in a host protocol

---

## 9. Current Repo Reality

Current audited package reality:

- `backend/agents/transcript_edit/`
  - about 142 Python files
  - clearly multi-era and compatibility-heavy
- `backend/agents/deed_to_ir/`
  - small on its own, but still part of the old agent estate
- `backend/agents/controller/`
  - much larger than a thin domain pack and still carries controller/compatibility history
- `backend/transcript_edit/`
  - wrapper package around older transcript-edit tooling
- `backend/transcription_edit_loop/`
  - lower-level deterministic tooling/runtime package, not a clean final domain-pack surface

This means the current problem is not just "refactor a few modules."

The current problem is:

- the domain layer is scattered
- some packages are semantic
- some are wrappers
- some are deterministic tooling
- some are old runtime species
- the boundaries are not clean enough for a scalable domain ecosystem

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

These are candidates to survive only as separated deterministic tooling, not as scattered top-level legacy packages:

- `backend/transcription_edit_loop/`

Likely extract-worthy pieces:

- deterministic apply semantics
- validators
- section normalization/adaptation
- minimal typed contracts if still useful

Likely non-final pieces inside that package:

- old mini-runtime shells
- persistence/run registry wrappers that only existed for the old domain runtime

Rule:

- if a piece is good tooling, extract and relocate it
- if not, delete it
- do not keep the package in place just because some parts are useful

### 10.5 Delete outright

These should not survive as part of the final domain-pack architecture:

- `backend/agents/transcript_edit/`
- `backend/agents/deed_to_ir/`
- `backend/agents/controller/`
- `backend/transcript_edit/`

And likely also the old domain-owned outer shells tied directly to them:

- `backend/api/endpoints/transcript_edit_agent.py`
- `backend/api/transcript_edit_agent_cli.py`
- `backend/api/mission_runtime_cli_support.py`
- `backend/api/endpoints/agent_loop.py`
- old pipeline or handoff glue that exists only for the retiring domain packs

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
5. Relocate any extracted deterministic tooling into the clean tooling root.
6. Stand up the new domain-pack root and shared domain support root.
7. Rebuild fresh native packs directly against the harness/domain-pack constitutions.
8. Add only generic/scalable tests for the new pack ecosystem, not nostalgia tests for the deleted one.

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
- the repo has one clean tooling/support root for deterministic domain tooling
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
