# `backend/corpus/`

This package defines **what exists in the user’s corpus** and how to read it consistently.

It is **not** a vector database. It is the layer that standardizes:

- What a “document” is (finalized dossier snapshot, draft transcription, schema artifact, etc.)
- What a “view/channel” is (finalized-only vs everything, artifacts-only, etc.)
- How to hydrate a reference into bytes/text + provenance (without callers knowing filesystem details)

## Design constraints

- **Import-safe**: avoid heavy deps here.
- **No hardcoded paths**: filesystem adapters must read through `backend/config/paths.py`.
- **Stable IDs**: downstream systems should depend on `CorpusDocRef` and `CorpusChunkRef`, not raw file paths.


