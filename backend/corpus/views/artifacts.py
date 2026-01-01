from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Set, Tuple

from ..adapters.artifacts_fs import ArtifactsFSAdapter
from ..types import CorpusEntryKind, CorpusEntryRef, CorpusView


@dataclass
class ArtifactsCorpusView:
    """
    Artifacts-only view.

    Intended to expose schema/georef artifacts as retrievable documents.
    """

    adapter: ArtifactsFSAdapter = field(default_factory=ArtifactsFSAdapter)

    def iter_entries(self, dossier_id: Optional[str] = None) -> Iterable[CorpusEntryRef]:
        """
        Enumerate artifact-backed entries (schemas, georefs, etc.).

        v0: expose only the latest schema and latest georef per dossier, using
        index files when available with a scan fallback.
        """

        # Schemas
        for did, _path in self.adapter.iter_schema_latest():
            if dossier_id and did != str(dossier_id):
                continue
            yield CorpusEntryRef(
                view=CorpusView.ARTIFACTS,
                entry_id=f"schema_latest:{did}",
                kind=CorpusEntryKind.SCHEMA_JSON,
                dossier_id=did,
                artifact_type="schema",
            )

        # Georefs
        for did, _path in self.adapter.iter_georef_latest():
            if dossier_id and did != str(dossier_id):
                continue
            yield CorpusEntryRef(
                view=CorpusView.ARTIFACTS,
                entry_id=f"georef_latest:{did}",
                kind=CorpusEntryKind.GEOREF_JSON,
                dossier_id=did,
                artifact_type="georef",
            )


