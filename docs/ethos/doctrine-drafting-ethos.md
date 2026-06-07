# Doctrine Drafting Ethos

Doctrine is behavioral steering for long-running agents under pressure. It is not just instruction text, and it is not only a contract reference. Good doctrine helps the agent choose sane motion when the exact situation was not anticipated.

This document is soft guidance, not a validator. Use it when writing or refactoring prompt doctrine, domain guidance, action-contract teaching, tool-use guidance, and run-method docs.

## Core Aim

Doctrine should communicate the operating sensibility behind the behavior, not only the behavior itself.

When relevant, a doctrine paragraph can be strengthened by explaining:

- what behavior is expected
- why it matters
- what failure mode it prevents
- what downstream value it creates
- how it relates to the action vocabulary or state vocabulary the agent can actually use

Not every paragraph needs all of those. Some doctrine exists mostly for correctness, some for efficiency, some for user experience, some for downstream economics, and some for keeping the agent from repeating a known failure mode. Include the context that makes the behavior easier to generalize.

The goal is not polished legal prose. The goal is useful behavioral force.

## Explain The Why

Flat commands are weak when the agent has to generalize. Prefer guidance that gives the agent a practical reason to care.

Weak:

> Build inventory before resolution.

Better:

> Build the work universe early because later turns inherit its shape. Missing atoms discovered late cannot be batched with nearby work, cause backtracking, increase prompt cost, and make the run feel less trustworthy to the user.

The why is not decoration. It helps the agent choose well when the next situation is not exactly like the example.

## Preserve Behavioral Force

Doctrine should not be timid when the behavior is important. Use emphasis when the issue is a real recurring failure mode or a high-value run habit.

Do not make everything sound equally mild. Important behaviors need priority information.

Useful emphasis can look like:

- This is not optional bookkeeping.
- Do not disregard this.
- This is a common failure mode.
- If the packet does not contain the target, it is not evidence for that target.

Avoid fake certainty, but do not sand off useful emphasis just to sound official.

### Sharp Language Is Sometimes Correct

Do not flatten all doctrine into neutral legal speech. Some failures are catastrophic enough, common enough, or expensive enough that the doctrine should sound like a demand.

Blunt language is not a manners failure when it carries meaning. Doctrine is written for capable agents operating under pressure, not for institutional politeness theater. If a direct, hard, non-polite sentence carries the priority, consequence, or nuance better than a softened version, use the direct sentence.

If a behavior is genuinely load-bearing, it is acceptable for doctrine to use blunt or abrasive language such as:

- Do not betray this rule.
- This is not optional housekeeping.
- If this is missing, the run is not ready.
- This failure poisons the rest of the run.

The point is not to be mean, theatrical, or hostile. The point is priority information and nuance preservation. Harsh phrasing can be the mechanism that tells the agent "this is different from the surrounding polite guidance." Do not sacrifice meaning, urgency, or delicate behavioral distinction just to make a sentence sound more official.

Abrasive can mean direct, blunt, impatient with a known failure mode, or deliberately unsmoothed. It does not need to mean insulting. The standard is whether the wording makes the behavioral weight clearer. If polite phrasing would make the rule easier to ignore, blur the consequence, or wash out the lived failure mode, the polite phrasing is worse doctrine.

Do not use abrasive language everywhere. If every paragraph yells, nothing stands out. Use it where the failure mode has repeatedly degraded correctness, economics, auditability, or user trust.

## Keep Related Details Together

When several details share one behavioral purpose, teach them together instead of scattering them as separate reminders.

Good doctrine often binds:

- the command
- the reason it matters
- the failure mode it prevents
- the relevant action/state vocabulary
- the downstream economics or UX value

For example, if a pinned artifact matters because it preserves memory, prevents hydrate-only turns, and supports later adjustment, those details belong near the `pin_refs` instruction. Splitting them across distant sections makes the rule easier to forget and weaker to generalize.

This is a Raptor 3 pressure: integrate the idea into one native method paragraph rather than leaving a pile of local warnings. Compression is good only when it preserves or increases behavioral force. Do not shorten doctrine by deleting the why, the economics, or the nuance that makes the rule usable.

## Prefer Sensibility Over Over-Scripting

Do not turn every doctrine point into a checklist or rigid flow unless the contract truly requires it.

Prefer language that preserves judgment:

- when sensible
- when the work pocket supports it
- when the evidence is ready
- if the next move can plausibly change the answer
- from the current vantage point

Be careful with accidental hard rules:

- always
- never, unless the behavior is genuinely forbidden
- first do X, then always do Y
- over-specific sequences that will sabotage a different task

Doctrine should teach judgment, not trap the agent in a brittle script.

## Avoid Overfitting

Generic doctrine must not be secretly shaped around one domain or one practice run.

Domain doctrine may use domain vocabulary, but it should still avoid overfitting to one document, one run failure, or one observed example. Use incidents to discover general failure modes. Do not paste the incident into doctrine unless the incident itself is a stable domain pattern.

Bad:

> List parcel cutoff, Range 75/74 conflict, and 2 vs 4 degree issue before moving.

Better:

> List all map-critical values, references, contradictions, source limits, dependencies, and downstream-governing choices before resolution motion.

The doctrine should survive the next run, not only explain the last one.

## Use Action Vocabulary Where It Helps

When a behavior maps to a tool or state mechanism, name the mechanism naturally.

Examples:

- `batch` when teaching multiple related actions in one turn
- `hydrate_next` when teaching next-turn setup
- `pin_refs` when teaching durable attention
- `delegate_subtask` when teaching isolated observations
- `state_patch` when teaching durable integration
- `covered_units` when teaching atomized group coverage

This matters because action vocabulary connects doctrine to what the agent can actually do.

Do not mention tool names gratuitously. Mention them where the behavior and tool are semantically linked.

## Raptor 3 Doctrine

Avoid doctrine piles.

When a new failure mode appears, do not automatically add a new paragraph. First ask:

- Is this already taught somewhere else?
- Is the existing teaching too weak, misplaced, or stale?
- Can this be merged into the canonical method paragraph?
- Does this belong in generic doctrine, domain doctrine, action contract, tool spec, or startup context?
- Can older wording be deleted after the better version lands?

Good doctrine integrates related ideas. For example, inventory enables batching, batching improves efficiency, localized packets improve proof, delegation improves attention, and state patches preserve truth. Those ideas should be explained together when they are part of one motion pattern.

Bad doctrine stacks those as unrelated reminders.

## Ownership

Put doctrine where it naturally belongs.

Generic harness surface:

- mission method
- work universe
- atoms and groups
- evidence standard
- delegation principle
- HITL and blocker posture
- closure and handoff posture

Action instruction:

- valid action JSON
- field mechanics
- action sequencing
- `hydrate_next`, pins, HITL transport, repair mechanics
- brief behavior reminders only when they directly affect action authoring

Domain branch:

- stable domain law
- domain authority model
- closure model
- output contract
- definition of done

Domain procedural guidance:

- domain working rhythm
- current tool workflow
- domain-specific movement patterns

Tool specs:

- request shape
- result shape
- limits
- mechanical examples
- not broad behavioral philosophy

## User Experience And Economics Matter

Doctrine should sometimes name the practical cost of bad motion and the practical gain of good motion.

Relevant gains include:

- fewer turns
- lower prompt growth
- less wall-clock time
- less user fatigue
- clearer evidence packets
- easier audit
- better downstream handoff
- fewer late backtracks
- fewer false earned values

Efficiency is not just speed. It expands what missions are practically possible.

## Drafting Review Questions

Before landing doctrine, ask:

1. Is this the canonical home for this idea?
2. Is this duplicating another surface?
3. Does it explain why the behavior matters when that context would help?
4. Does it name the relevant action or state vocabulary when useful?
5. Is it broad enough to survive a different domain or run?
6. Is it too hard-scripted?
7. Did it preserve important emphasis?
8. Did it delete or retire stale wording?
9. Does it read like a coherent method or a patch note?
10. Would it help the agent choose well in an unanticipated situation?
