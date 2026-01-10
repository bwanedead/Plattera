# Retrieval System Specification

This document describes the current retrieval system architecture as implemented in the Plattera codebase.

---

## Overview

The retrieval system provides a unified interface for accessing, searching, and citing content from the corpus. It is built around three core abstractions:

1. **CorpusEntryRef** - Stable references to corpus entries (no raw paths)
2. **EvidenceSpan** - Citeable spans of text with provenance
3. **Corpus Views** - Pluggable filters that enumerate different subsets of entries

---

## Corpus Structure

### Directory Layout

```
backend/corpus/
├── types.py              # Core type definitions (CorpusEntryRef, CorpusEntryKind, CorpusView)
├── interfaces.py         # CorpusProvider protocol
├── hydrate.py            # Hydration logic (ref → full content)
├── virtual_provider.py   # Main provider implementation
├── adapters/
│   ├── dossiers_fs.py    # Dossier filesystem path resolution
│   └── artifacts_fs.py   # Artifact (schema/georef) path resolution
└── views/
    ├── finalized.py      # FINALIZED view
    ├── everything.py     # EVERYTHING view
    ├── artifacts.py      # ARTIFACTS view
    └── final_segments.py # FINAL_SEGMENTS view
```

### Data Layout (Filesystem)

```
dossiers_data/
├── views/transcriptions/
│   └── <dossier_id>/
│       ├── <transcription_id>/raw/<transcription_id>.json
│       └── final/dossier_final.json
├── artifacts/
│   ├── schemas/<dossier_id>/latest.json
│   └── georefs/<dossier_id>/latest.json
└── state/
    ├── <dossier_id>/final_registry.json
    ├── finalized_index.json
    ├── schemas_index.json
    └── georefs_index.json
```

---

## CorpusEntryRef

**Definition**: `backend/corpus/types.py` (lines 35-54)

A `CorpusEntryRef` is a stable, immutable identifier for a corpus entry. It abstracts away filesystem paths so that retrieval code never handles raw paths directly.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `view` | `CorpusView` | Which corpus view (FINALIZED, EVERYTHING, ARTIFACTS, FINAL_SEGMENTS) |
| `entry_id` | `str` | Unique stable identifier (e.g., `final:dossier123`) |
| `kind` | `CorpusEntryKind` | Entry type (see below) |
| `dossier_id` | `Optional[str]` | Parent dossier identifier |
| `transcription_id` | `Optional[str]` | For transcription-based entries |
| `segment_id` | `Optional[str]` | For segment-final entries |
| `draft_id` | `Optional[str]` | For segment-final entries (which draft) |
| `artifact_type` | `Optional[str]` | e.g., "schema", "georef" |
| `artifact_id` | `Optional[str]` | Artifact identifier |
| `metadata` | `Dict[str, Any]` | Arbitrary key-value data |

### CorpusEntryKind Enum

Defined in `backend/corpus/types.py` (lines 19-32):

| Kind | Description |
|------|-------------|
| `FINALIZED_DOSSIER_TEXT` | Complete finalized dossier content |
| `TRANSCRIPT` | Raw transcription data |
| `SCHEMA_JSON` | Schema artifact |
| `GEOREF_JSON` | Georeferencing artifact |
| `IMAGE_OCR_TEXT` | OCR text from images |
| `SEGMENT_FINAL_TEXT` | User-finalized segment draft |

### entry_id Conventions

- Finalized dossiers: `final:{dossier_id}`
- Transcripts: `transcript:{dossier_id}:{transcription_id}`
- Schemas: `schema_latest:{dossier_id}`
- Georefs: `georef_latest:{dossier_id}`
- Segment finals: `segment_final:{dossier_id}:{segment_id}:{draft_id}`

---

## EvidenceSpan

**Definition**: `backend/retrieval/evidence/models.py` (lines 23-37)

An `EvidenceSpan` represents a citeable portion of a corpus entry. It carries both the text and the provenance needed to trace the span back to its source.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `entry` | `CorpusEntryRef` | Source entry reference |
| `text` | `str` | Actual text content of the span |
| `chunk` | `Optional[CorpusChunkRef]` | Chunk reference if applicable |
| `start` | `Optional[int]` | Byte offset in canonical/raw text |
| `end` | `Optional[int]` | End byte offset |
| `content_hash` | `Optional[str]` | SHA256 hash of entry's full text |
| `preview` | `Optional[str]` | Short excerpt for UI display |
| `trace` | `Optional[MatchTrace]` | Mapping info for normalized matches |
| `metadata` | `Dict[str, Any]` | Additional provenance data |

### MatchTrace

When retrieval operates in normalized mode, the `MatchTrace` (lines 9-20) documents how a match in normalized space maps back to raw text:

- `space`: Which space the match occurred in (normalized vs raw)
- `normalized_start/end`: Positions in normalized text
- `normalized_preview`: Match preview in normalized space
- `mapping_kind`: How the mapping works
- `normalizer_version`: Version of normalization algorithm

### Related Types

- **EvidenceCard** (lines 40-51): Wrapper containing one or more `EvidenceSpan` objects with score, lane name, and provenance
- **RetrievalResult** (lines 54-62): Final output container with query, cards list, and debug info

---

## Hydration Flow

**Definition**: `backend/corpus/hydrate.py`

Hydration converts a `CorpusEntryRef` into a `CorpusEntry` containing the full text and metadata. The `CorpusHydrator` class dispatches based on entry kind.

### Dispatch Logic (`hydrate()` method, lines 49-87)

```
CorpusEntryRef → kind dispatch → read file → extract text → CorpusEntry
```

### Kind-Specific Hydration

| Kind | Method | Source Path | Text Extraction |
|------|--------|-------------|-----------------|
| `FINALIZED_DOSSIER_TEXT` | `_hydrate_finalized()` | `<dossier>/final/dossier_final.json` | `stitched_text` field |
| `TRANSCRIPT` | `_hydrate_transcript()` | `<dossier>/<tid>/raw/<tid>.json` | `text` field or joined `sections[].body` |
| `SCHEMA_JSON` | `_hydrate_schema()` | `artifacts/schemas/<dossier>/latest.json` | Full JSON as text |
| `GEOREF_JSON` | `_hydrate_georef()` | `artifacts/georefs/<dossier>/latest.json` | Full JSON as text |
| `SEGMENT_FINAL_TEXT` | `_hydrate_segment_final()` | Draft path via adapter | `sections` → `text` → `mainText` → empty |

### Error Handling

Hydration never throws. On error, it returns a `CorpusEntry` with:
- Empty text
- `provenance["error"]` set to the error message

### Supporting Methods

- `_read_text_file()` - UTF-8 file reading
- `_read_json()` - JSON parsing
- `_compute_content_hash()` - SHA256 hashing
- `_mtime_iso()` - File mtime to ISO-8601

---

## View Production

**Location**: `backend/corpus/views/`

Corpus views are pluggable filters that enumerate subsets of entries. Each view implements entry enumeration and is registered in `VirtualCorpusProvider`.

### CorpusView Enum

Defined in `backend/corpus/types.py`:

| View | Purpose |
|------|---------|
| `FINALIZED` | High-signal finalized dossier content |
| `EVERYTHING` | All transcriptions (raw, variants, consensus) |
| `ARTIFACTS` | Schema and georef artifacts |
| `FINAL_SEGMENTS` | User-finalized drafts per segment |

### View Implementations

#### FINALIZED (`views/finalized.py`)

- Iterates finalized dossier IDs from `finalized_index.json` or filesystem scan
- Yields one entry per finalized dossier
- Entry kind: `FINALIZED_DOSSIER_TEXT`

#### EVERYTHING (`views/everything.py`)

- Enumerates all transcription HEAD files
- One entry per (dossier_id, transcription_id) pair
- Entry kind: `TRANSCRIPT`

#### ARTIFACTS (`views/artifacts.py`)

- Enumerates latest schema and georef per dossier
- Uses index files when available, falls back to filesystem scan
- Entry kinds: `SCHEMA_JSON`, `GEOREF_JSON`

#### FINAL_SEGMENTS (`views/final_segments.py`)

- Reads `final_registry.json` for each dossier
- Registry format: `{"segments": {"seg_id": {"transcription_id": "...", "draft_id": "...", "set_at": "...", "set_by": "..."}}}`
- Yields one entry per segment with finalized selection
- Entry kind: `SEGMENT_FINAL_TEXT`
- Indexing semantics: Replace-all per dossier (not incremental)

### Provider Flow

1. `VirtualCorpusProvider.list_entry_refs(view, filters)` dispatches to appropriate view
2. View yields `CorpusEntryRef` objects matching filters
3. `VirtualCorpusProvider.hydrate_entry(ref)` calls `CorpusHydrator.hydrate()`

---

## Retrieval Lanes

**Location**: `backend/retrieval/lanes/`

Retrieval happens through pluggable "lanes" that search the corpus and produce `EvidenceCard` objects.

### Lexical Lane (`lanes/lexical/grep_backend.py`)

- **Modes**: `raw` (direct substring) or `normalized` (with mapping back to raw)
- **Flow**:
  1. List entry refs from corpus provider
  2. Hydrate each entry
  3. Search for query matches
  4. Convert matches to `EvidenceSpan` objects
  5. Wrap in `EvidenceCard` with ID: `lex:{mode}:{entry_id}:{start}:{end}`

### Provenance Lane (`lanes/provenance/lane.py`)

- Deterministic assembly of canonical dossier artifacts
- Input: dossier_id + ProvenanceRecipe
- Recipes: `CANONICAL_STACK`, `FINAL_ONLY`, `ARTIFACTS_ONLY`
- Output: One `EvidenceCard` per artifact type

### Semantic Lane (`lanes/semantic/lane.py`)

- Vector similarity retrieval using embeddings
- Infrastructure exists; implementation in progress

### Retrieval Engine (`engine/retrieval_engine.py`)

Orchestrates multiple lanes:
- Accepts list of lane names: `lexical`, `hybrid`, `lexical.raw`, `lexical.normalized`, `semantic`, `provenance`
- `hybrid` mode: Lexical → extract dossier anchors → Provenance on anchors
- Deduplicates, sorts by score, truncates to limit

---

## Filtering

**Definition**: `backend/retrieval/filters/models.py`

`RetrievalFilters` scopes retrieval:

| Field | Type | Description |
|-------|------|-------------|
| `view` | `Optional[CorpusView]` | Corpus view to search |
| `dossier_id` | `Optional[str]` | Limit to specific dossier |
| `transcription_id` | `Optional[str]` | Limit to specific transcription |
| `artifact_type` | `Optional[str]` | schema/georef/... |
| `since_iso` | `Optional[str]` | Time-based lower bound |
| `until_iso` | `Optional[str]` | Time-based upper bound |
| `extra` | `Dict[str, Any]` | Lane-specific options |

---

## Draft Path Resolution

**Location**: `backend/corpus/adapters/dossiers_fs.py` (lines 164-313)

The `DossiersFSAdapter.resolve_draft_path()` method handles complex draft ID formats:

| Format | Example | Resolution |
|--------|---------|------------|
| Consensus LLM | `abc123_consensus_llm` | `abc123/consensus/llm_abc123.json` |
| Consensus alignment | `abc123_consensus_alignment` | `abc123/consensus/alignment_abc123.json` |
| Alignment per-draft | `abc123_draft_1` | `abc123/alignment/draft_1.json` |
| Raw versioned | `abc123_v3` | `abc123/raw/abc123_v3.json` |
| Non-versioned | `abc123` | `abc123/raw/abc123.json` |

Includes caching and rglob fallback for robustness.
