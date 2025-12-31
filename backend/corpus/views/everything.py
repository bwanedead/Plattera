from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..adapters.dossiers_fs import DossiersFSAdapter
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

    adapter: DossiersFSAdapter = DossiersFSAdapter()

    def iter_entries(self, dossier_id: Optional[str] = None) -> Iterable[CorpusEntryRef]:
        """
        Enumerate "everything" entries for a dossier.

        Conservative v0 behavior: one HEAD transcript per (dossier_id,
        transcription_id) pair based on the raw JSON file under
        dossiers_data/views/transcriptions/.
        """

        for did, tid, _path in self.adapter.iter_transcription_heads(dossier_id=dossier_id):
            yield CorpusEntryRef(
                view=CorpusView.EVERYTHING,
                entry_id=f"transcript:{did}:{tid}",
                kind=CorpusEntryKind.TRANSCRIPT,
                dossier_id=did,
                transcription_id=tid,
            )


