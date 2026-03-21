# Harness Constitution

This document defines the non-negotiable architectural constitution for Plattera's generic harnesses, mission runtimes, and agent loops.

It exists to prevent a specific class of architectural regression:

- deterministic runtime logic quietly reclaiming authorship over the agent's work
- scripted issue taxonomies becoming the real source of work content
- harness layers deciding what matters in the case before the agent has understood the case

The harness exists to provide rails, persistence, execution, observability, and safety.
It does not exist to secretly become the investigator.

---

## 1. Core Rule

The harness may be deterministic in its mechanics.
It may not be deterministic in its semantic authorship.

That means:

- deterministic rails are allowed
- deterministic work authorship is forbidden

The LLM is the engine that understands the case, forms the work, chooses the focus, and decides what unresolved items mean.

The harness is the structure around that engine.

---

## 2. What The Harness Is Allowed To Do

The harness may:

- persist artifacts, traces, and run state
- dispatch tools and actions
- validate schemas and payload structure
- enforce budgets, retries, and safety limits
- maintain session/run continuity
- store and project decision-ledger state
- shape bounded prompts and focus packets
- expose tool results and evidence to the agent
- enforce execution invariants that are mechanical rather than semantic

These are rails.
They support the run without deciding the case.

---

## 3. What The Harness Must Never Do

The harness must not:

- create the practical work universe through deterministic issue detection
- define the initial problem inventory through validator findings
- create, rank, or resolve decision-ledger items from hard-coded domain logic
- assign blocker meaning through deterministic domain taxonomies
- decide what is mapping-critical through scripted finding types
- generate correction plans from deterministic domain heuristics
- declare semantic closure because a validator says the transcript is clean

If a deterministic component is deciding what work exists or what that work means, the architecture is out of bounds.

---

## 4. Agent Authorship Rule

The following must be agent-authored:

- case orientation
- initial case inventory
- investigation brief content
- decision-ledger items
- blocker formation
- focus selection
- closure posture
- next-step planning
- interpretation of evidence

Valid semantic origins are:

- LLM reasoning
- explicit human feedback
- direct source material interpreted by the LLM

Tools may provide evidence.
They may not provide runtime truth about what the work means.

---

## 5. Evidence Rule

Deterministic tools are allowed to produce evidence-shaped outputs.

Good examples:

- transcript spans
- image crops
- extracted text regions
- draft-to-draft comparisons
- artifact lineage
- hashes, refs, and provenance
- structural parsing output

Bad examples:

- pre-authored issue classes as the main runtime truth
- deterministic findings like "this is the blocker"
- scripted domain labels that directly become ledger work
- deterministic closure or contradiction verdicts

The distinction is:

- evidence may be deterministic
- semantic authorship may not

---

## 6. Decision Ledger Rule

The decision ledger is the agent's organized-work surface.

It must be populated from:

- agent orientation
- agent discovery
- agent interpretation of evidence
- human feedback when present

It must not be populated from:

- deterministic validator findings as the primary source of work
- pre-authored default ontologies hidden behind startup logic
- scripted category mappers that turn findings into durable work items

The ledger may store evidence refs from tools.
The meaning of the item must still come from the agent.

---

## 7. Focus And Blocker Rule

Focus and blocker semantics must emerge from the agent's understanding of the case.

The harness may:

- ask the agent to choose a focus
- supply bounded context
- store blocker state
- require explicit structured output

The harness must not:

- hard-code which issue type outranks another
- infer blocker truth from deterministic finding categories
- use scripted priority ladders as the practical source of focus

Priority policy may exist as a prompt doctrine.
It must not exist as hidden deterministic authorship.

---

## 8. Closure Rule

Closure is not a validator verdict.

Closure is the agent's final judgment, grounded in:

- the current transcript state
- the decision ledger state
- available evidence
- remaining contradictions
- remaining dependencies
- mapping relevance
- human feedback if present

Deterministic checks may support confidence.
They may not define semantic closure.

---

## 9. Prompt And Packet Rule

Focus packets, support state, and prompt rails are allowed.

But the content carried in those structures should be agent-authored wherever it expresses:

- what the case is
- what matters
- what remains unresolved
- what the next move should be

Prompt scaffolding may shape the container.
It must not smuggle in the work content through deterministic doctrine.

---

## 10. Anti-Regression Rule

Any new harness feature, helper, or refactor must be rejected if it causes any of the following:

- the harness begins defining work content through deterministic domain logic
- a validator becomes the practical author of the run's issue inventory
- ledger items originate from scripted category mappers instead of agent reasoning
- focus or closure meaning depends on hard-coded semantic taxonomies

If a change adds semantic convenience by scripting what the case means, that change violates the constitution.

---

## 11. Review Questions

Every substantial harness or loop change should be reviewed with these questions:

1. Is the harness still only rails and infrastructure?
2. Did any deterministic component start authoring the work universe?
3. Are ledger items still agent-authored?
4. Is focus still agent-chosen rather than script-ranked?
5. Is closure still agent-judged rather than validator-declared?
6. Are tool outputs evidence-shaped instead of issue-authorship-shaped?

If any answer is "no", the design is drifting out of bounds.

---

## 12. Summary

The harness must remain:

- deterministic in mechanics
- agentic in semantic authorship

The model decides what the case means.
The harness makes that process durable, bounded, observable, and safe.

That boundary is not optional.
