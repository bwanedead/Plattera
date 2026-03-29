# Domain Pack Constitution

This document defines the non-negotiable architectural rules for domain packs in Plattera's generic harness.

It is subordinate to:

- `docs/architecture/harness/harness-constitution.md`

If this document ever conflicts with the harness constitution, the harness constitution wins.

---

## 1. Purpose

This constitution exists to prevent one specific regression:

- domain packs quietly becoming semi-scripted runtime species

That regression usually appears through:

- deterministic focus authorship
- deterministic sequencing of semantic work
- domain packs absorbing machinery that belongs to the harness
- product/tool wiring getting confused with domain meaning

The goal is:

**the harness remains the machine; the domain pack remains the semantic specialization bundle on top of it.**

---

## 2. Core Rule

The domain pack may own semantics.

It must not own generic machine law.

Short form:

- harness owns machinery
- domain owns semantics
- agent owns authored motion

This triangle is the primary rule for the domain-pack layer.

---

## 3. Ownership Triangle

## 3.1 Harness owns machinery

The harness may own:

- mission runtime shell
- orchestration mechanics
- execution kernel mechanics
- HITL transport lifecycle
- continuity transport
- generic prompt trunk
- observability and trace collection
- prompt-event capture
- generic state containers
- generic focus continuity carriage
- generic terminal taxonomy
- budgets, retries, idempotency, and safety rails

The harness must not own:

- domain ontology
- domain evidence meaning
- domain closure meaning
- domain feedback meaning
- domain-specific work inventory truth
- domain sequencing truth

## 3.2 Domain pack owns semantics

The domain pack may own:

- domain doctrine
- domain prompt branch
- domain state authority
- domain read models and projections
- domain evidence interpretation
- domain closure semantics
- domain feedback semantics
- capability requirements
- execution translation from semantic move to concrete action
- handoff posture and recommendations
- focus-context hydration for an already-chosen focus

The domain pack must not own:

- generic loop law
- generic runtime law
- generic HITL transport law
- generic prompt trunk
- generic observability law
- shared terminal taxonomy
- semantic focus authorship through deterministic code
- semantic next-move authorship through deterministic code

## 3.3 Agent owns authored motion

The following must remain agent-authored or human-authored:

- discovering what unresolved items exist
- deciding what matters
- choosing the next meaningful move
- interpreting evidence
- determining whether ambiguity is material
- deciding whether closure is warranted

Deterministic code may carry, validate, and transport those outputs.

It must not silently replace them.

---

## 4. What A Domain Pack Is

A domain pack is not:

- a class with 9 hooks
- a hidden controller loop
- a domain-specific runtime species
- a script that decides what the agent should do

A domain pack is:

- a semantic specialization bundle
- a bounded owner of domain doctrine and meaning
- a translator between domain-authored semantics and shared harness rails

The 9-hook `DomainPack` protocol is only the hosting seam.

It is not the whole architecture.

---

## 5. Focus Rule

Focus is the most dangerous domain-pack seam.

It must be split into four distinct concerns.

## 5.1 Focus discovery

What unresolved items exist.

Allowed owners:

- agent-authored state
- human-authored input
- LLM-authored orientation or iteration understanding

Forbidden owners:

- deterministic harness truth
- deterministic domain-pack truth

## 5.2 Focus selection

Which item is active now.

The harness may carry:

- active focus continuity
- last selected focus key
- bounded focus continuity mechanics

The harness must not become the semantic authority for what matters next.

The domain pack must not deterministically script "first x, then y, then z" as hidden focus truth.

## 5.3 Focus context hydration

Given an already-chosen focus item, the domain pack may assemble bounded relevant context for that focus.

This may include:

- relevant domain item state
- relevant evidence refs
- relevant recent attempts
- relevant human feedback
- relevant artifacts
- relevant domain summaries
- relevant capability affordances

This is legitimate domain ownership because the generic harness cannot know what "relevant context" means across radically different domains.

## 5.4 Focus move resolution

What to do next about that focus.

This remains agent-authored.

The domain pack may:

- define move vocabulary and contracts
- translate accepted semantic moves into execution-ready actions

The domain pack must not:

- deterministically choose the semantic move on the agent's behalf

---

## 6. Capability Rule

Domain packs should declare capability requirements, not confuse raw tool wiring with domain identity.

A capability requirement expresses:

- what classes of resources or actions the domain needs

It does not itself express:

- how those tools are implemented
- which provider is used
- which concrete product wiring realizes them

Product composition owns concrete tool/provider wiring.

The domain pack owns capability needs and semantics.

---

## 7. Execution Translation Rule

The domain pack may translate semantic moves into concrete executable actions.

This is allowed because it is a semantic-to-mechanical boundary.

But execution translation must remain:

- bounded
- explicit
- auditable

It must not become:

- a hidden planner
- a sequencing engine
- a workaround layer that authors semantic work because the prompt or move contract is weak

---

## 8. Closure Rule

The domain pack owns domain closure meaning.

The harness may provide:

- generic terminal scaffold
- generic waiting/completed/blocked categories
- mechanical progress and observability rails

The harness must not define what closure means for the domain.

The domain pack may define:

- what unresolved work is material
- what evidence is sufficient
- what risks are acceptable
- when handoff readiness exists

---

## 9. Feedback Rule

The harness owns feedback transport lifecycle.

The agent owns what the feedback means.

The domain pack may provide domain state and closure surfaces that the agent updates.

The harness may track:

- prompt issued
- waiting on answer
- answer received
- answer surfaced back to the agent

Neither shared harness nor deterministic domain helpers may pretend feedback has been semantically integrated unless that meaning has actually been authored or explicitly confirmed.

---

## 10. Handoff Rule

The domain pack may express handoff posture and recommendations.

It must not directly become the mission runtime.

Allowed:

- "ready for downstream domain"
- "blocked on dependency"
- "waiting on human"
- "closure reached but not promotable"

Forbidden:

- hidden direct pack-to-pack control flow as domain truth
- a domain pack redefining mission runtime transition mechanics

Mission runtime owns actual transition mechanics.

---

## 11. Banned Leakage

The following are architectural violations:

- a domain pack defining alternate generic runtime law
- a domain pack quietly owning loop mechanics
- deterministic domain code deciding what unresolved items exist
- deterministic domain code deciding the semantic active focus
- deterministic domain code deciding the next meaningful move
- domain-specific tool/provider wiring treated as if it were shared-harness law
- domain prompts or doctrine leaking back into shared trunk layers
- generic containers being forced to carry one mission family's ontology as canonical truth

---

## 12. Anti-Regression Rule

Reject any domain-pack feature or refactor if it causes any of the following:

- the pack becomes a hidden workflow script
- the pack becomes a second runtime species
- focus discovery or selection quietly becomes deterministic domain truth
- execution translation becomes semantic authorship
- product composition details become confused with domain semantics

If a change makes the pack more convenient by making it more scripted, that change is out of bounds.

---

## 13. Review Questions

Every substantial domain-pack change should be reviewed with these questions:

1. Is the domain pack still owning semantics rather than machinery?
2. Did any deterministic pack logic start authoring unresolved work truth?
3. Did any deterministic pack logic start choosing semantic focus truth?
4. Is focus-context hydration still hydration rather than hidden planning?
5. Is move resolution still agent-authored rather than deterministic pack-authored?
6. Is execution translation still just semantic-to-mechanical compilation?
7. Are capability requirements still declarations of need rather than hardcoded workflow doctrine?
8. Is closure meaning still domain-owned and not leaked into shared generic rails?
9. Is feedback meaning still domain-owned while transport stays harness-owned?
10. Are handoff recommendations still bounded posture signals rather than hidden runtime mechanics?

If any answer is "no", the design is drifting out of bounds.

---

## 14. Summary

The domain pack must remain:

- semantic
- bounded
- replaceable
- subordinate to the harness machine

The harness remains the machine.

The pack gives that machine a domain-specific world to operate in.

It must never quietly become the thing that decides the work on the agent's behalf.
