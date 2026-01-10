"""
Final Segments Corpus View
==========================

Surfaces segment-final selections from final_registry.json as corpus entries.

This is the canonical "final pool" for semantic retrieval — the user-finalized
draft for each segment of each dossier.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from config.paths import dossiers_state_root

from ..adapters.dossiers_fs import DossiersFSAdapter
from ..types import CorpusEntryKind, CorpusEntryRef, CorpusView

logger = logging.getLogger(__name__)


@dataclass
class FinalSegmentsCorpusView:
    """
    "Final segments" view.

    Enumerates segment-final selections from final_registry.json for each dossier.
    Each entry represents a single segment's user-selected draft.

    Indexing Cleanup Semantics
    --------------------------
    When re-indexing this view for embedding/vector storage:

    - **Replace-all per dossier**: When a dossier's final_registry.json changes,
      the indexer should delete ALL existing entries for that dossier_id and
      re-insert the current set. This is simpler and safer than incremental
      upserts because:

      1. draft_id changes are frequent when users re-finalize segments
      2. entry_id includes draft_id, so old entries become orphaned
      3. segment deletions from final_registry need explicit cleanup

    - **Entry stability**: entry_id = `segment_final:{dossier_id}:{segment_id}:{draft_id}`
      This means the entry_id changes whenever the user selects a different draft
      for a segment. The stable key for deduplication is (dossier_id, segment_id).

    - **Atomic replacement**: Indexers should wrap per-dossier re-indexing in a
      transaction or use delete-then-insert to avoid partial states.

    This view is the canonical "final pool" for semantic retrieval over
    user-finalized transcription segments.
    """

    adapter: DossiersFSAdapter = field(default_factory=DossiersFSAdapter)

    def _final_registry_path(self, dossier_id: str) -> Path:
        """Path to final_registry.json for a dossier."""
        return dossiers_state_root() / str(dossier_id) / "final_registry.json"

    def _read_final_registry(self, dossier_id: str) -> Dict[str, Any]:
        """
        Read final_registry.json for a dossier.

        Returns empty segments dict if file missing or corrupt (never throws).
        """
        path = self._final_registry_path(dossier_id)
        if not path.exists():
            return {"segments": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"segments": {}}
                data.setdefault("segments", {})
                return data
        except Exception as exc:
            logger.warning(
                f"Failed to read final_registry.json for dossier {dossier_id}: {exc}"
            )
            return {"segments": {}}

    def iter_entries(self, dossier_id: Optional[str] = None) -> Iterable[CorpusEntryRef]:
        """
        Enumerate segment-final entries.

        For each dossier, reads final_registry.json and yields one CorpusEntryRef
        per segment with a finalized selection.

        Entry ID format: segment_final:{dossier_id}:{segment_id}:{draft_id}
        This makes the entry_id stable across re-finalizations only if draft_id
        changes (which it typically does if a different draft is selected).
        """
        if dossier_id:
            dossier_ids = [dossier_id]
        else:
            # Use iter_dossier_ids to enumerate all dossiers in the workspace
            dossier_ids = list(self.adapter.iter_dossier_ids())

        for did in dossier_ids:
            registry = self._read_final_registry(did)
            segments = registry.get("segments", {})

            for seg_id, seg_entry in segments.items():
                if not isinstance(seg_entry, dict):
                    continue

                transcription_id = seg_entry.get("transcription_id")
                draft_id = seg_entry.get("draft_id")

                if not transcription_id or not draft_id:
                    # Incomplete entry — skip
                    continue

                # Entry ID includes draft_id for uniqueness when draft changes
                entry_id = f"segment_final:{did}:{seg_id}:{draft_id}"

                yield CorpusEntryRef(
                    view=CorpusView.FINAL_SEGMENTS,
                    entry_id=entry_id,
                    kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
                    dossier_id=did,
                    transcription_id=transcription_id,
                    segment_id=seg_id,
                    draft_id=draft_id,
                    metadata={
                        "set_at": seg_entry.get("set_at"),
                        "set_by": seg_entry.get("set_by"),
                    },
                )
