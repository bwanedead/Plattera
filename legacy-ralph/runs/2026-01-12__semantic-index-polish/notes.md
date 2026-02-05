# Notes — Semantic index polish (yellow-zone cloud)

This file exists so the Ralph loop has durable context without relying on chat memory.

## Cloud (verbatim-ish)

What we have now is the right overall shape: we can chunk deterministically, embed locally, and persist a vector index with metadata so semantic search can return stable pointers back into the corpus. The remaining work is mostly about turning “it works” into “it’s trustworthy and ergonomic under real use.”

Yellow-zone buckets:
- Semantic hits must be usable: provide a small excerpt/preview that explains why it matched (triage/debug).
- Retrieval-time vs read-time separable: two-phase flow (locate candidates cheaply → hydrate full context on demand).
- Index state truthfulness: manifest must actually reflect the built index; mismatch detection must be real.
- Model identity clarity: stored model identifier must be unambiguous (model id + immutable revision/fingerprint).
- Operational failure modes explicit: distinguish missing vs failed-to-load vs incompatible/stale.
- Test/CI reliability: persistence coverage without unstable test runner behavior.
- Update semantics safe: avoid relying on undefined ANN behaviors (label reuse / in-place replacement).
- Tombstones understood: accumulation acknowledged; compaction deferred but future remedy should be clear.
- Debuggability: “why this matched” trace includes score/distance, policy id, pool id, model identity.

## Structured plan (hand-off summary)

Goals:
- Make semantic results evaluable (preview + trace).
- Make locate→read deterministic (especially FINAL_SEGMENTS hydration).
- Make manifest/model identity truthful and compared correctly.
- Make operational signals explicit (missing vs corrupt vs stale).
- Make tests reliable without losing persistence coverage.
- Make update semantics provably safe for hnswlib.
- Improve “why this matched” provenance for tuning later.

Stories are captured in `prd.json` for this run.


