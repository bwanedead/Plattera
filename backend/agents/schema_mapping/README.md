# `backend/agents/schema_mapping/`

v0 “schema mapping” agent loop.

This loop will:

1. Start from a finalized dossier (canonical input)
2. Produce a schema attempt
3. Run deterministic judge steps (schema → polygon → georef → validator)
4. Convert failures into typed gaps
5. Retrieve grounded evidence from the corpus
6. Apply minimal patches and retry until success or a clear “needs user input” outcome


