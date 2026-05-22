# Delegate Subtask Architecture

This document preserves the intended architecture for generic harness-owned subagent delegation.

The motivating use case is a transcript-edit source-reading failure: the main agent can have a good localized crop, but still misread a small handwritten mark after carrying a large prompt, prior peer candidates, graph state, doctrine, and closure obligations. A human often solves that kind of problem by briefly narrowing attention: ignore the whole case, look only at the mark, decide what the mark appears to say, then return that observation to the larger task.

The harness should support that same pattern without turning deterministic code into the semantic author of the case.

Implementation should follow the companion rollout plan in [`delegate-subtask-implementation-plan.md`](delegate-subtask-implementation-plan.md).

---

## Core Idea

`delegate_subtask` is generic harness infrastructure for agent-authored subagent work.

The parent agent may ask the harness to run a small, isolated subtask through a registered subagent profile. The harness executes the subtask with bounded context, receives a structured result, and returns that result to the parent as a tool result.

The parent agent remains responsible for mission meaning:

- whether to accept the subtask result
- whether to reject it
- whether to treat it as ambiguous
- how to update the resolution graph
- how to update artifacts
- whether HITL is needed
- whether the run is handoffable

The subagent returns observations. It does not close work.

---

## Constitutional Boundary

The harness may provide subagent rails:

- profile registration
- input validation
- prompt assembly
- model-call execution
- batching/concurrency limits
- output validation
- audit records
- bounded projection back to the parent

The harness must not use subagent results to deterministically author semantic state.

Forbidden:

- automatic graph patches from subagent results
- automatic closure of resolution items
- automatic artifact rewrites
- automatic handoff decisions
- deterministic "truth" selection from a subagent reading
- hidden promotion of subtask output into domain-specific blocker or success meaning

Valid semantic flow:

1. parent agent authors the subtask
2. subagent returns an observation
3. parent agent interprets that observation in mission context
4. parent agent authors any durable state/artifact changes

This preserves the Harness Constitution: tools may produce evidence-shaped outputs, but the agent authors what that evidence means.

---

## Why This Exists

Long-running agent loops accumulate useful context, but that context can also become cognitive noise for tiny perceptual or local judgment tasks.

`delegate_subtask` exists to reduce:

- candidate imprinting from earlier drafts or graph values
- attention spread across unrelated doctrine and state
- repeated full-prompt turns for isolated tasks
- expensive serial evaluation of multiple small artifacts
- main-loop bloat when a small task needs only a small prompt

It should make each main turn more productive without scripting the mission.

The parent agent should use delegation when an isolated subtask is likely to benefit from fresh, narrow attention. It should not delegate merely because delegation exists.

---

## Generic Architecture

### 1. Parent Action Contract

The parent agent emits a normal action:

```json
{
  "alias": "p1_bearing_subtask",
  "action_type": "delegate_subtask",
  "action_inputs": {
    "profile": "transcript_edit.visual_source_observation",
    "task": "Determine the exact bearing text visible in the provided crop. Use only the image.",
    "context_refs": ["image:derived:..."],
    "isolation": {
      "omit_parent_graph": true,
      "omit_peer_candidates": true
    },
    "output_contract": {
      "kind": "source_observation"
    }
  }
}
```

The parent-authored fields are the semantic core:

- `profile`: what kind of subagent should be used
- `task`: the parent agent's specific mini-mission
- `context_refs`: artifacts/images/text refs to provide
- `isolation`: requested context exclusions
- `output_contract`: the bounded result shape the parent needs

The exact wire shape can evolve, but the ownership should not: the parent agent authors intent; the harness realizes it.

### 2. Harness Subtask Runner

The generic runner owns:

- resolving `context_refs`
- checking profile availability
- enforcing profile limits
- building the child prompt
- attaching allowed media/artifacts
- invoking the configured model
- validating the child result
- returning a bounded result row to the parent
- recording audit-safe traces

The runner should be deterministic, but not semantic.

### 3. Subagent Profile Registry

A profile is a registered subagent class. It defines mechanics and prompt framing for one kind of subtask.

Profile metadata should be explicit:

- `profile_id`
- owner (`harness` or domain pack)
- description
- allowed input ref kinds
- prompt preamble/source
- output schema
- maximum context refs
- maximum prompt size
- maximum result size
- model preference or model policy
- batch/concurrency cap
- whether parent graph/state is omitted by default
- whether candidate values are allowed
- maximum turns, initially `1`

Profiles should be pluggable. Generic profiles can live in shared harness code. Domain profiles live in domain packs.

### 4. Domain Profiles

Transcript-edit can register the first domain profile:

`transcript_edit.visual_source_observation`

Purpose:

- inspect one or more provided source-image crops
- answer the parent-authored mini task
- preserve source-visible text/marks
- avoid normalizing unless asked
- explain local ambiguity without making mission decisions

This profile should not be treated as the generic primitive. It is only the first profile using the generic delegation infrastructure.

---

## Result Shape

Do not include `confidence`.

Confidence fields tend to create false precision and distract from the evidence. Prefer direct fields describing status, reading, ambiguity, observations, and limits.

Example completed result:

```json
{
  "subtask_id": "p1_bearing_subtask",
  "profile": "transcript_edit.visual_source_observation",
  "status": "completed",
  "input_refs": ["image:derived:..."],
  "result": {
    "reading": "N. 4° 00' W., 1638 feet distant",
    "ambiguity": "The degree numeral is handwritten; the visible mark appears more consistent with 4 than 2.",
    "observations": [
      "Only the supplied crop was used.",
      "The following text reads 00' W., 1638 feet distant."
    ],
    "limits": []
  }
}
```

Example unresolved result:

```json
{
  "subtask_id": "p1_bearing_subtask",
  "profile": "transcript_edit.visual_source_observation",
  "status": "ambiguous",
  "input_refs": ["image:derived:..."],
  "result": {
    "reading": null,
    "ambiguity": "The crop does not make the numeral reliably distinguishable.",
    "observations": [
      "The surrounding text reads N. [digit]° 00' W.",
      "The degree numeral is the only uncertain mark."
    ],
    "limits": [
      "Need a wider crop, different scale, or operator review."
    ]
  }
}
```

Suggested generic statuses:

- `completed`
- `ambiguous`
- `insufficient_input`
- `failed`

Domain profiles may narrow the result payload, but should avoid pretending uncertainty is precision.

---

## Prompt Isolation

Subtask prompts should be much smaller than parent prompts.

Default isolation for focused subtasks:

- omit parent resolution graph
- omit parent closure ledger
- omit peer draft candidates unless explicitly requested
- omit broad doctrine
- include only the task, profile rules, output contract, and requested refs

The child prompt should clearly say:

- perform only this isolated task
- use only supplied inputs
- do not infer from broader mission context
- report ambiguity directly
- return the structured result only

Isolation is the point. A delegated subtask should not receive a miniature copy of the whole main loop prompt.

---

## Candidate Values

Candidate values are useful in the parent loop, but they can bias narrow perceptual tasks.

Default policy for visual/source reading profiles:

- blind read first
- do not include candidate values unless the parent explicitly requests a discriminative comparison

If the parent needs a comparison task, it should author that task explicitly:

> Decide whether the visible mark is more consistent with `2` or `4`, and describe the visible shape. Use only the supplied crop.

This keeps blind observation and candidate comparison distinct.

---

## Batching And Concurrency

`delegate_subtask` should be batchable.

The main efficiency gain comes when the parent agent can create several crops, then ask for several isolated subtasks without spending a full parent turn on each one.

Initial cap suggestion:

- max 4 delegated subtasks per parent turn
- run synchronously first for implementation simplicity
- allow internal parallel execution later if the model/provider layer supports it safely

Batching must remain bounded and visible in audit:

- one parent turn may delegate several subtasks
- each subtask has its own alias/id
- each subtask has its own input refs
- each subtask has its own result
- failures are isolated to the subtask row where possible

Do not batch unrelated subtasks just to increase action count. Delegation should support sensible motion density, not chaotic attention splitting.

---

## Single-Turn First, Persistent Later

Version 1 should be single-turn.

No child memory. No child tools beyond supplied refs. No child resume state. No autonomous child loop.

The v1 goal is to test whether isolated attention improves:

- local visual/source reads
- small artifact comparisons
- narrow consistency checks
- parent-loop efficiency

The architecture should still leave room for future persistent subagents:

- `max_turns`
- child task id
- parent run id
- child trace id
- resumability posture
- profile-owned tool permissions

But those should not be implemented until the single-turn design proves useful.

---

## Relationship To Existing Actions

`delegate_subtask` is not a replacement for:

- `transform_artifact`
- `hydrate_artifact_refs`
- HITL
- state patches
- publish/output actions

It complements them.

Typical transcript-edit rhythm:

1. parent uses `transform_artifact` to create local crops
2. parent delegates isolated source observations over those crops
3. parent receives compact subtask results
4. parent patches graph/artifact/HITL posture if warranted

Delegation is not the evidence artifact itself. It is an agentic observation over evidence.

---

## Audit And Observability

Every delegated subtask should be traceable without dumping large payloads.

Audit-safe records should include:

- parent turn index
- parent action alias
- profile id
- task excerpt
- input refs
- isolation flags
- status
- result summary
- bounded errors
- child model metadata if safe and useful

Audit records must not include:

- raw base64
- secrets
- oversized prompt bodies
- full parent prompt
- unbounded child responses

Prompt budget reporting should distinguish parent prompt cost from delegated subtask prompt cost. Otherwise delegation can hide cost instead of reducing it.

---

## Safety And Policy

Subagent profiles should enforce:

- maximum task text length
- maximum context refs
- allowed ref kinds
- maximum output size
- timeout / retry budget
- model/provider policy
- no raw secret projection
- no direct state mutation

If a subtask fails, the parent receives a normal failed subtask result. The harness should not silently retry into a different semantic task.

If a subtask result is malformed, the runner may request structured repair inside the child call budget, but it still must return only an observation-shaped result to the parent.

---

## Teaching The Parent Agent

Parent doctrine should be light.

Teach the agent:

- use delegation when a narrow task benefits from isolated attention
- write the child task plainly and specifically
- give only the refs and context the child needs
- keep blind reads blind when candidate imprinting could matter
- treat subtask results as observations, not automatic truth
- integrate results through normal graph/artifact/HITL channels

Do not teach delegation as mandatory. It is a tool for attention management and cost control.

---

## Tests For First Implementation

Minimum acceptance tests:

- parser accepts `delegate_subtask` as a normal action
- profile registry resolves generic and domain profiles
- invalid profile is rejected repairably
- task text and ref lists are bounded
- child prompt excludes parent graph/large doctrine by default
- image refs are attached to the child call when profile allows images
- result validation accepts completed/ambiguous/insufficient/failed statuses
- result projection back to parent is bounded
- no raw `b64` appears in prompt/audit projections
- batched `delegate_subtask` rows execute independently
- subtask results do not mutate mission state directly
- transcript-edit visual profile can read an existing image crop through the generic runner

Behavior test:

- use a real crop where the main loop previously misread a handwritten mark
- compare main-loop direct reading vs delegated isolated observation
- inspect whether candidate-free isolation changes the reading

---

## Anti-Patterns

Avoid:

- naming the generic action around the first use case (`focused_read`)
- hard-coding transcript-edit semantics into shared harness code
- letting subtask result fields become deterministic state patches
- making child prompts as large as parent prompts
- using `confidence` as a substitute for concrete ambiguity/limits
- giving candidates to a blind reading task by default
- creating persistent child-agent machinery before single-turn value is proven
- hiding subtask cost from prompt/budget observability
- letting profile-specific implementation leak into the generic action parser

---

## Design Bias

Build `delegate_subtask` as infrastructure first.

The first practical profile may be transcript-edit visual source observation, but the architecture should support future subagents for many domains and task types.

The parent agent owns why the subtask matters.
The subagent owns a narrow observation.
The harness owns safe execution.

That is the boundary to preserve.
