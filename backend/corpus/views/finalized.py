from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..adapters.dossiers_fs import DossiersFSAdapter
from ..types import CorpusEntryKind, CorpusEntryRef, CorpusView


@dataclass
class FinalizedCorpusView:
    """
    "Finalized high-signal" view.

    Intended to surface canonical finalized dossier artifacts first:
    - stitched dossier_final.json (or latest snapshot)
    - per-segment final selections (registry) indirectly via dossier services
    - latest schema/georef artifacts (optional, via artifacts view)
    """

    adapter: DossiersFSAdapter = DossiersFSAdapter()

    def iter_entries(self, dossier_id: Optional[str] = None) -> Iterable[CorpusEntryRef]:
        """
        Enumerate finalized, high-signal entries.

        Uses finalized_index.json when present, falling back to a scan of the
        views/transcriptions tree.
        """

        if dossier_id:
            ids = [dossier_id]
        else:
            ids = list(self.adapter.iter_finalized_dossier_ids())

        for did in ids:
            yield CorpusEntryRef(
                view=CorpusView.FINALIZED,
                entry_id=f"final:{did}",
                kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
                dossier_id=did,
            )


