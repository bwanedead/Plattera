# Agent-Engine Constitution

This document defines the architectural law for the contract seam between the
agent and the harness.

It complements, and does not replace:

- `docs/architecture/harness/harness-constitution.md`
- `docs/ethos/agent-engine-ergonomics-theory.md`

Its purpose is to prevent a specific class of recurring failure:

- making the agent redescribe stable state every turn
- spending model tokens on host-derivable ceremony
- teaching a bloated contract surface that costs both output tokens and model
  cognition
- forcing the agent to speak an awkward engine dialect when the runtime could
  safely own that burden instead

The core idea is simple:

- the harness is a stateful decoder with durable context
- the agent is a delta encoder of new intent

The contract should be built around that reality.

---

## 1. Core Rule

The agent should emit only the information the harness cannot already:

- preserve,
- default,
- normalize,
- or infer safely from local context.

That means:

- agent emits high-entropy novelty
- harness owns low-entropy persistence and ceremony

The goal is not maximal brevity for its own sake.
The goal is:

**maximal semantic compression without loss of operational distinction**

If the harness can reconstruct the intended meaning exactly, the agent should
not have to spend tokens restating it.

If the harness cannot reconstruct it exactly, the distinction must remain
explicit.

This constitution governs the **accepted external seam** the agent is asked to
speak through.

It does not require the runtime's internal execution form to be identical to the
external surface.

Internal normalization into a different canonical form is healthy.
What this constitution tries to minimize is unnecessary **external** ceremony
and burden on the agent.

---

## 2. Ownership Map

### 2.1 Agent-owned novelty

The agent should spend tokens on things that are genuinely new, changed, or
selected.

Examples:

- what kind of move is being made
- which tool or action to run
- action inputs
- which existing state rows are changing
- what fields on those rows are changing
- which new rows are being introduced
- what human question is being asked
- what new continuity fact is worth preserving
- terminal or closure judgment that is genuinely new this turn

### 2.2 Host-owned persistence

The harness should own information that is stable, defaultable, or already
durable.

Examples:

- omitted falsey flags
- empty arrays or empty objects
- transport-only ids and idempotency tokens
- unchanged fields on existing rows
- unchanged titles, kinds, summaries, and active ids
- unchanged state structure
- normalization into canonical internal execution shape

### 2.3 Host-owned local inference

The harness may infer meaning from local shape only when that inference is
strictly unambiguous.

That is valid only when:

- the shape family is intentionally defined
- mutual exclusivity is mechanically validated
- fallback ambiguity is rejected rather than guessed

Examples:

- if a turn contains only a tool dispatch, the host can infer it is not a
  complete or human-wait turn
- if a turn contains only state deltas, the host can treat it as a state-only
  move
- if an existing row is identified and only one field is present, omitted fields
  can remain unchanged

The host must not guess where multiple interpretations are possible.

---

## 3. State Inertia Rule

State has inertia unless explicitly perturbed.

That means:

- durable state persists across turns
- omission on an existing keyed row means unchanged, not absent
- stable fields should not need to be re-emitted for completeness
- the contract should prefer sparse deltas over full redrafts

This is the correct default geometry for long-running loops.

Sparse delta semantics are valid only where the runtime owns deterministic keyed
merge, stable identity semantics, or an equivalent exact reconstruction rule.

The agent should not be asked to redescribe the current world.
It should only describe the delta to the world.

---

## 4. Sparse Delta Rule

For existing rows:

- send the stable identity key
- send only the fields that are actually changing
- omit everything else

For unchanged structures:

- do not emit `null` just to satisfy a schema recital
- do not resend stable fields merely because they exist
- do not rewrite large containers when one narrow delta will do

If the harness already supports keyed merge, the prompt and parser should teach
and reward keyed sparse updates rather than accidental full replacement.

---

## 5. Create vs Update Rule

The contract must preserve a clear distinction between:

- creating a new row
- updating an existing row

New rows require enough information to be semantically legible and mechanically
valid.

Existing rows should require only:

- identity
- changed fields

The agent should not have to remember an implicit prose rule like:

> "sometimes resend the whole thing, sometimes only send the delta"

That distinction should be structurally obvious in the contract surface or
unambiguous in runtime merge semantics.

If the runtime cannot tell whether something is a create or an update without
guessing, the seam is underspecified.

---

## 6. Turn Shape Rule

When multiple turn encodings are valid, prefer the smallest unambiguous shape
the runtime can support safely.

Preferred bias:

- one explicit discriminator, or
- one mutually exclusive shape family the host can interpret without guesswork

Disfavored pattern:

- a mutually exclusive turn choice expressed through repeated low-information
  truth-table fields when one smaller surface would preserve the same
  distinction

If a legacy surface still uses multiple booleans, omission should default to the
lowest-information safe value wherever backward-compatible.

The model should not be paying recurring cognitive cost to restate:

- "not complete"
- "not waiting"
- "not skipping"

when the move shape already implies those facts.

---

## 7. Transport And Ceremony Rule

Transport ceremony belongs to the harness, not the agent.

Examples:

- idempotency tokens
- purely mechanical envelopes
- canonical empty containers
- normalization fields the runtime can derive

If a field exists only to satisfy transport or runtime bookkeeping, it should be
host-generated or host-filled whenever possible.

The agent should express intent.
The harness should realize that intent deterministically.

---

## 8. Prose Restraint Rule

Free-text fields are auxiliary, not first-class, unless they carry genuinely new
durable meaning that cannot be captured structurally.

Use prose only when it adds information that would otherwise be lost.

Disfavored behavior:

- repeating rationale already evident from the chosen action or state delta
- emitting operator progress text when no meaningful user-facing status changed
- writing continuity memory that merely paraphrases durable state

The main action grammar should stay centered on:

- chosen move
- changed state
- human escalation when needed
- genuinely new memory when needed

Everything else is secondary.

---

## 9. Prompt Teaching Rule

Prompting should teach invariant laws, not ceremony-heavy recitals.

Preferred teaching pattern:

- lead with "emit the smallest valid object"
- say explicitly that omission means unchanged where the runtime supports it
- state that existing rows use identity plus changed fields only
- discourage redundant prose
- show tiny examples of correct minimal output

Disfavored teaching pattern:

- large schema blobs presented as if all fields are equally expected
- giant canonical examples that teach the model that "good answers are big"
- examples that normalize fully-populated restatements of stable state

The prompt surface should reduce both:

- expression cost
- decision cost

for the model.

---

## 10. Compression Safety Rule

Compression is only good when the decoder can reconstruct the intended meaning
exactly.

Do not compress away:

- create vs update distinctions
- pause vs async human escalation
- action choice distinctions
- row identity
- any semantic difference the runtime needs in order to act deterministically

Do not rely on hidden state when that hidden state is not safely recoverable.

Do not replace explicit meaning with fuzzy shorthand if the host would have to
guess.

This constitution is pro-compression.
It is not pro-ambiguity.

---

## 11. Evidence-Led Evolution Rule

Action seams should evolve from observed emitted behavior, not from contract
guesswork.

That means:

- record raw emitted shapes
- observe recurring sane near-miss forms
- observe repeated redundant fields the model keeps producing
- measure where output bloat and truncation actually happen
- adapt the accepted contract toward the recurring sane shapes where safe

This follows the ergonomics law:

- do not force the agent to keep speaking with an accent
- do not pave a path you have not actually observed

The accepted contract should become more natural only where real runs show that
the natural form is recurring, unambiguous, and safe to normalize.

---

## 12. Observability Rule

If the contract is under active evolution, the seam must be instrumented well
enough to judge whether it is improving.

Useful measurements include:

- prompt size
- prompt token count
- completion token count
- reasoning token count when available
- finish reason
- truncation frequency
- partial response tail on truncation
- recurring invalid or near-miss action shapes

Without seam observability, contract evolution becomes taste-driven rather than
evidence-driven.

---

## 13. Migration Rule

Legacy surfaces may temporarily remain more ceremonial than this constitution's
preferred end state.

Migration should usually proceed in this order:

- first remove agent burden the host can safely own already
- then teach sparse defaults and minimality clearly
- then use observability to judge whether deeper grammar redesign is justified

Preferred bias:

- additive ergonomic narrowing before disruptive protocol replacement
- measured refinement before speculative redesign
- observability-led decisions about whether to stop at sparse defaults or move
  to a deeper contract rewrite

This constitution does not require every legacy wire shape to be replaced at
once.
It requires movement toward a better seam when evidence shows the current one is
needlessly burdensome.

---

## 14. Design Bias And Direction Of Travel

The constitution does not freeze one exact wire shape forever.

It does define a strong design bias:

- smaller intent-first contracts
- sparse keyed deltas
- host-owned transport ceremony
- optional prose instead of routine prose
- explicit or unambiguous turn typing
- fewer top-level knobs
- lower branching burden on the model

In practice, that usually means moving toward a message algebra shaped more
like:

- intent or turn kind
- action selection when needed
- sparse changes when needed
- human escalation when needed
- memory delta when needed

The exact field names may change.
The law does not:

- the agent should transmit novelty
- the harness should carry inertia

---

## 15. Anti-Patterns

The following are architectural failures at the seam:

- making the agent author transport-only ids
- requiring repeated low-information turn ceremony when a smaller exact signal
  would preserve the same distinction
- requiring full redrafts of large structured state to express tiny changes
- teaching examples that normalize overfilled payloads
- treating schema completeness as more important than information efficiency
- making the model restate unchanged titles, summaries, or row metadata
- allowing prompt ceremony to consume the budget needed for actual decisions
- compressing so aggressively that the runtime must guess

If the model is spending more effort on speaking the contract than on deciding
the work, the seam is wrong.

---

## 16. Review Questions

Every substantial agent-engine contract change should be reviewed with these
questions:

1. Is the agent emitting only information the host cannot safely preserve,
   default, or infer?
2. Are unchanged rows and unchanged fields allowed to remain implicit?
3. Does omission mean unchanged only where that meaning is unambiguous?
4. Is create vs update explicit enough to avoid runtime guesswork?
5. Is turn typing encoded with less ceremony than a repeated truth table?
6. Did any transport-only field remain model-authored without good reason?
7. Are prose fields truly carrying new durable information, or just narrating
   what structured state already says?
8. Do the prompt examples teach minimality, or do they teach overfilling?
9. Is the seam instrumented well enough to measure actual bloat and truncation?
10. Did any compression collapse an operational distinction the runtime still
    needs?

If those questions are not answered cleanly, the contract is not yet in its
higher form.

---

## 17. Summary

The agent-engine seam should behave like this:

- the harness is the persistent decoder
- the agent is the minimal perturbation encoder
- stable state has inertia
- novelty is transmitted
- ceremony is host-owned
- ambiguity is rejected rather than guessed
- contract evolution is driven by observed sane emitted behavior

The aim is not merely to make the payload shorter.

The aim is to make the contract:

- lighter,
- clearer,
- more natural for the agent,
- more deterministic for the runtime,
- and more faithful to the information actually changing in the run.
