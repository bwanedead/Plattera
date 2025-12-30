from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..models import CorpusDocRef, CorpusView


@dataclass
class FinalizedCorpusView:
    """
    "Finalized high-signal" view.

    Intended to surface canonical finalized dossier artifacts first:
    - stitched dossier_final.json (or latest snapshot)
    - per-segment final selections (registry) indirectly via dossier services
    - latest schema/georef artifacts (optional, via artifacts view)
    """

    def iter_docs(self, dossier_id: Optional[str] = None) -> Iterable[CorpusDocRef]:
        # v0 placeholder: actual enumeration will be implemented via adapters over dossiers_data.
        # The returned refs must be resolvable by `corpus/hydrate.py`.
        if dossier_id:
            yield CorpusDocRef(view=CorpusView.FINALIZED, doc_id=f"final:{dossier_id}", dossier_id=dossier_id)


