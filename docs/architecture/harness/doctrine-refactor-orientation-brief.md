# Doctrine Refactor — Orientation Brief

You are taking on a staged refactor of the harness trunk doctrine. This brief gives you the goal, the why, the system context, and your required reading order. Your governing contract is `doctrine-refactor-constitution.md` (already added to the codebase). Read this brief first, then the constitution, then the reading list. Do not touch any doctrine text until you have finished all of it.

---

## 1. The goal

The doctrine system — the trunk (`backend/harness/runtime/prompting/surface.py`, currently ~v33) **and** the domain surfaces (`backend/domains/mapping/prompting/family_branch.py`, `backend/domains/mapping/transcript_edit/prompting/branch.py`, and `.../surfaces/procedural_guidance.py`) — is being refactored from an accreted rule pile into a consolidated, named-law structure:

- Each behavioral law gets **one canonical, named articulation** at full strength — repetition collapsed, not averaged.
- An **emphasis budget** is applied: a few hard markers reserved for the highest-stakes failure modes, everything else carried by strong wording.
- A **world-model cohesion narrative** is added: how the machine's pieces interlock (atoms, evidence, point crops, window constraints, delegates, state patches, closure) told once as one causal story — and every rule it makes derivable gets tagged and deleted.
- Every clause is **routed twice**: by kind — task truth (trunk) vs driver correction (model-specific) vs world-model (cohesion narrative) — and by layer, the layer-routing audit: trunk content that is really domain mechanics gets evicted down; domain content restating trunk law gets collapsed up. Misplacement is a form of repetition.
- **Layer character is enforced** (constitution §7.2): the trunk carries only universal agentic sensibilities — broad-strokes principles of sane problem-solving that any domain would be wise to follow — and **no doctrine anywhere hard-scripts sequences**. Doctrine teaches judgment; enforced sequences are mechanics and belong in code. The domain surfaces are more directed but still principle-shaped, and each major domain element carries its **downstream clause** (constitution §7.1): what it is, why it matters in itself, and what it feeds next — atomization → landable crops → verifiable delegates → honest closure — so the consequence chain is the tie-breaker when the agent is uncertain which way to tip.
- A **provenance changelog** is established so every future doctrine edit records what behavior motivated it.

Token reduction will happen but is not the goal. The goal is one tunable knob per law, higher information density, and doctrine an agent can actually bind to instead of skim.

## 2. Why we are doing this

The doctrine was not written; it accreted. Roughly fifteen observe-and-sharpen cycles, each responding to observed failures, appended corrections wherever the incident suggested. The result:

- The evidence/localization law is taught in **five-plus separate sections**, each worded slightly differently. The duplicates are accidental, not intentional emphasis. This splits our most sensitive behavioral lever into five coupled knobs that cannot be tuned independently, and trains the driving model to skim doctrine as boilerplate (semantic satiation).
- Field-semantics rules are restated three times. Self-audit asks roughly a dozen silent questions per turn. Emphasis markers (IMPORTANT/PLEASE) have inflated to the point of devaluing each other.
- The per-turn doctrine load is roughly 26K tokens: ~14.6K trunk plus ~11.3K domain surfaces (transcript_edit branch ~5.3K, procedural_guidance ~4.5K, family_branch ~1.5K). Both layers are cumbersome; this is a doctrine-system refactor, not a trunk cleanup.
- The most recent run showed **behavioral degradation we cannot yet explain**. We are past the point where appending another rule helps; the structure itself is the suspect.

Two facts make this dangerous, and they are why the constitution exists. First: **the wording is the weights.** The exact phrasing encodes calibration from expensive observation cycles, with no record of which phrase fixes which behavior. Second: **LLM rewriters sanitize by default.** Your own prior pulls toward neutral professional prose, and in this task that pull is a bug. The constitution's Nuance Ledger, verbatim bias, and register-preservation law are the protections. They are not bureaucracy; they are what makes this refactor survivable.

A further motivation is portability. The doctrine is currently overfit to one model's failure surface. Routing clauses into trunk vs driver-correction is what lets the trunk carry over when the model changes, while driver patches become hypotheses to retest.

## 3. What the harness is (context)

The harness is a generic mission-execution kernel: the driving model authors an ActionPlan each turn (actions, rationale, state patches, continuity journal entries), the harness executes mechanics deterministically and never authors meaning. Durable semantic state lives in mission_state / resolution_state with explicit postures (work universe, motion, success conditions) and earned-vs-provisional closure discipline. The constitution of the whole system is **mechanics vs semantics**: the harness records and carries; the agent decides and means.

The doctrine you are refactoring is the prompting surface that teaches the driving model its method: evidence discipline, inventory-before-resolution, investigation economics, state hygiene, HITL behavior. The current domain riding on the harness is legal-deed → parcel-map resolution: transcripts are decomposed into atomic claim units ("atoms"), evidence is localized via point crops against imagery within window constraints, subtasks go to delegates with restricted views. The domain surfaces are in scope as the final stage — and they are the most sensitive text in the system, because procedural_guidance encodes the operator's economy-of-motion and sensibility calibration from many observation cycles. They are touched last, only after the method has proven itself on the trunk stages. You must understand the domain machinery from the start regardless, because the world-model narrative (constitution §7.1) teaches exactly how those pieces interlock, and it anchors in the domain stage.

## 4. Required reading, in order

1. **`doctrine-refactor-constitution.md`** — your governing contract. Every rule in it binds you. Sections 1 (Multi-Channel Law), 2 (Nuance Ledger), and 4 (one native articulation, echoes default zero) are the ones you will be most tempted to violate. Don't.
2. **`docs/ethos/doctrine-drafting-ethos.md`** — the house drafting law: explain the why, sharp language is sometimes correct, doctrine should read as operating philosophy not a changelog of incidents.
3. **`docs/ethos/raptor-3-ethos.md`** — the refactor philosophy. Subtractive-integrative: success is fewer live shapes to reason about, not shorter files. Internalize the "what it is not" section.
4. **`backend/harness/agents.md`** — harness orientation: vocabulary, layer map, guardrails, deleted paths. Note the banned-vocabulary list; retired terms must not reappear in anything you write.
5. **`docs/architecture/harness/harness-constitution.md`** — the mechanics/semantics law and ownership map.
6. **`docs/architecture/harness/agent-engine-constitution.md`** — the seam law. The delta-encoder principle (transmit novelty, don't restate) applies to the doctrine you write: teach each law once, natively.
7. **`backend/harness/runtime/prompting/surface.py`** — the target. Read it fully, twice. First pass: comprehension. Second pass: build your inventory of repeated laws, emphasis artifacts, examples, register breaks, and candidate `derivable` rules. This file is calibrated text — you will not edit a word of it until the Nuance Ledger for the stage in scope is complete.
8. **The domain prompting surfaces** — `family_branch.py`, the transcript_edit `branch.py`, `procedural_guidance.py`, and `startup_context.py` — read fully. They are Stage 4's target, the layer-routing audit's other half, and the raw material for the cohesion narrative. Build their repetition/misplacement inventory just as for the trunk.
9. **`doctrine-backups/`** — note the prior raptor prepass snapshot; you will add the v33 snapshot here before any edit (constitution §9).
10. **Mechanical flag definitions** — grep the codebase for the flag names referenced in doctrine (`same_ref_bundle_reread_no_gain`, `coarse_work_graph_under_active_investigation`, `hitl_evidence_readiness_debt`, `artifact_excerpt_boundary_risk`) and locate their canonical definitions. You need them for the verification phase, and constitution Finding routing applies: flag-response protocols may belong beside the flags, not in method philosophy.
11. **The audit/observability surfaces** — locate `human_timeline` and `loop_health_summary` under `backend/harness/runtime/`, plus the regression fixtures (`harness_regression_pack`). These are your verification instruments.
12. **`test_architecture_guardrails.py`** — the executable doctrine for code. Nothing you do may regress it.

## 5. Known findings inventory (verify, then use)

A prior review identified these; confirm each against the current text before acting on it:

- Evidence/localization law taught in 5+ sections: mission-critical exactness, decisive-detail localization, defensible evidence, orientation vs claim-local evidence, evidence-local earned claims — plus restatements in investigation-discipline bullets and evidence refs vs locators.
- Field semantics (determined_value compactness, field roles, work-graph projection) restated ~3 times.
- ~9 IMPORTANT/PLEASE markers in the trunk; emphasis budget target is ~3.
- Mechanical-flag response protocols taught inside method philosophy (ownership question).
- Self-audit load: ~12 silent self-interrogations per turn; cut to the ~5 that do the work.
- Inventory-before-resolution taught in four places.

Domain-surface repetition and misplacement have not been inventoried yet — building that inventory is part of your reading pass, and your Stage 4 plan derives from it.

Out of scope for this effort (do not touch, but flag if encountered): point_crop domain contamination in the generic harness code (`point_crop_set_projection.py`, `point_crop_set_timeline.py`), reviewer-agent rot (`raptor-3-native-reviewer.md` frontmatter collision, dead doc references, retired vocabulary), and any tool-ergonomics issue (boxes, overlay parameters). Tool problems get mechanical fixes, not doctrine — constitution §7.1 boundary.

## 6. Process and stop conditions

- **Before any edit:** snapshot v33 to doctrine-backups; capture baseline run audits including the recently degraded run; **diff current doctrine against the last-known-good version in both layers** — the degraded behaviors (placement, atomization, recrops) are governed mostly domain-side, so recent edits to procedural_guidance and the transcript_edit branch are the prime suspects. The degradation may already be a doctrine regression, and finding it is cheaper than the refactor and tells us which wording is load-bearing.
- **Stages run in constitution §8 order:** (1) field-semantics merge (trunk), (2) emphasis budget pass (trunk), (3) the Evidence Law (trunk), (4) domain doctrine pass — the most calibrated text, touched only after the method is proven. One stage per session. Each stage produces: completed Nuance Ledger (committed), merged text, changelog entries, and passes the §10 verification before the next stage opens. Stage 3 does not begin because 1 and 2 felt easy.
- The world-model cohesion narrative (§7.1) is drafted alongside Stage 3, since the Evidence Law is its anchor — but rule deletions funded by it require `derivable` tags in the ledger and explicit sign-off.
- **Stop and surface, don't improvise, when:** a source clause's intent is ambiguous; two source articulations genuinely conflict; you believe a nuance must be dropped; or you find yourself rewriting for quality rather than consolidating for strength. Ambiguity goes to the operator; it does not get resolved by smoothing.

## 7. Definition of done

The trunk teaches each law once, natively, by name, at full or greater register strength; every ledger row is dispositioned; the changelog explains every change by observed behavior; emphasis markers are scarce and load-bearing; the cohesion narrative exists and has paid for deletions; regression runs show flags and qualitative sanity at or better than baseline; and the original author, reading it cold, says it hits harder than v33.
