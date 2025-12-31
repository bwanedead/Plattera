from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

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

    def iter_entries(self, dossier_id: Optional[str] = None) -> Iterable[CorpusEntryRef]:
        """
        Enumerate finalized, high-signal entries.

        v0: requires an explicit dossier_id and yields a single reference to the
        finalized stitched dossier text. Later this can expand to enumerate all
        dossiers and additional artifact kinds.
        """

        if dossier_id:
            yield CorpusEntryRef(
                view=CorpusView.FINALIZED,
                entry_id=f"final:{dossier_id}",
                kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
                dossier_id=dossier_id,
            )


