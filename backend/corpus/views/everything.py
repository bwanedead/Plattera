from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..types import CorpusEntryKind, CorpusEntryRef, CorpusView


@dataclass
class EverythingCorpusView:
    """
    "Everything" view.

    Intended to include:
    - all transcriptions (raw, redundancy variants, consensus, edits)
    - unfinalized dossiers
    - job outputs/history (optional)
    """

    def iter_entries(self, dossier_id: Optional[str] = None) -> Iterable[CorpusEntryRef]:
        """
        Enumerate "everything" entries for a dossier.

        v0: placeholder that yields a single reference standing in for the
        dossier-wide text surface. Later, this should expose individual
        transcripts, drafts, and other text-bearing items.
        """

        if dossier_id:
            yield CorpusEntryRef(
                view=CorpusView.EVERYTHING,
                entry_id=f"dossier:{dossier_id}",
                kind=CorpusEntryKind.TRANSCRIPT,
                dossier_id=dossier_id,
            )


