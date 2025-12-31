from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Set

from .hydrate import CorpusHydrator
from .interfaces import CorpusProvider
from .types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView
from .views.artifacts import ArtifactsCorpusView
from .views.everything import EverythingCorpusView
from .views.finalized import FinalizedCorpusView


@dataclass
class VirtualCorpusProvider(CorpusProvider):
    """
    Virtual corpus provider backed by the filesystem layout.

    This is the main surface retrieval + agents should depend on in v0.
    """

    finalized_view: FinalizedCorpusView = field(default_factory=FinalizedCorpusView)
    everything_view: EverythingCorpusView = field(default_factory=EverythingCorpusView)
    artifacts_view: ArtifactsCorpusView = field(default_factory=ArtifactsCorpusView)
    hydrator: CorpusHydrator = field(default_factory=CorpusHydrator)

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
        kinds: Optional[Set[CorpusEntryKind]] = None,
    ) -> Iterable[CorpusEntryRef]:
        if view == CorpusView.FINALIZED:
            it = self.finalized_view.iter_entries(dossier_id=dossier_id)
        elif view == CorpusView.EVERYTHING:
            it = self.everything_view.iter_entries(dossier_id=dossier_id)
        elif view == CorpusView.ARTIFACTS:
            it = self.artifacts_view.iter_entries(dossier_id=dossier_id)
        else:
            it = []

        if kinds is None:
            return it
        return (ref for ref in it if ref.kind in kinds)

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        return self.hydrator.hydrate(ref)



