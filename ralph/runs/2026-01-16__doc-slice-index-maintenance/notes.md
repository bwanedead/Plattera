# Notes — 2026-01-16__doc-slice-index-maintenance

Source brief (condensed):
- Doc-level slices are the unit of rebuild: (pool_identifier, dossier_id, entry_id)
- Pools:
  - FINAL_SEGMENTS: segment-final drafts per segment (authoritative citations)
  - EVERYTHING: broader workspace, but v0 indexes one canonical doc per run (head-only), with draft-aware identity
- Desired signature per slice: prefer `content_hash` of hydrated entry content
- “Stale” can mean: content changed OR model/policy identity changed
- New persistence needed:
  - list_labels_for_entry + delete_entry_slice (doc-slice replace-all)
  - indexed_entry_state table storing indexed_signature + identity per slice
- Maintenance controller surface:
  - diagnose (cheap) -> status + plan (dry-run)
  - execute (heavy) -> rebuild slice(s), explicit and observable


