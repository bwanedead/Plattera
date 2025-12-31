from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..types import CorpusEntryKind, CorpusEntryRef, CorpusView


@dataclass
class ArtifactsCorpusView:
    """
    Artifacts-only view.

    Intended to expose schema/georef artifacts as retrievable documents.
    """

    def iter_entries(self, dossier_id: Optional[str] = None) -> Iterable[CorpusEntryRef]:
        """
        Enumerate artifact-backed entries (schemas, georefs, etc.).

        v0: placeholder that yields a single reference per dossier. Later this
        should enumerate concrete schema/georef artifacts via filesystem
        adapters.
        """

        if dossier_id:
            yield CorpusEntryRef(
                view=CorpusView.ARTIFACTS,
                entry_id=f"artifacts:{dossier_id}",
                kind=CorpusEntryKind.SCHEMA_JSON,
                dossier_id=dossier_id,
            )


