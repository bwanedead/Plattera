from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..models import CorpusDocRef, CorpusView


@dataclass
class ArtifactsCorpusView:
    """
    Artifacts-only view.

    Intended to expose schema/georef artifacts as retrievable documents.
    """

    def iter_docs(self, dossier_id: Optional[str] = None) -> Iterable[CorpusDocRef]:
        # v0 placeholder: later enumerate artifacts/schemas + artifacts/georefs.
        if dossier_id:
            yield CorpusDocRef(view=CorpusView.ARTIFACTS, doc_id=f"artifacts:{dossier_id}", dossier_id=dossier_id)


