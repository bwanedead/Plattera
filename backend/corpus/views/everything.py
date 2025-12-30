from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..models import CorpusDocRef, CorpusView


@dataclass
class EverythingCorpusView:
    """
    "Everything" view.

    Intended to include:
    - all transcriptions (raw, redundancy variants, consensus, edits)
    - unfinalized dossiers
    - job outputs/history (optional)
    """

    def iter_docs(self, dossier_id: Optional[str] = None) -> Iterable[CorpusDocRef]:
        # v0 placeholder
        if dossier_id:
            yield CorpusDocRef(view=CorpusView.EVERYTHING, doc_id=f"dossier:{dossier_id}", dossier_id=dossier_id)


