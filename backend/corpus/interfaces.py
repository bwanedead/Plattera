from __future__ import annotations

from typing import Iterable, Optional, Protocol

from .types import CorpusEntry, CorpusEntryRef, CorpusView


class CorpusProvider(Protocol):
    """
    Abstract interface for corpus backends.

    Implementations can be virtual (filesystem-backed) or materialized
    (precomputed corpus store). Retrieval and agents should depend on this
    interface rather than concrete storage details.
    """

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
    ) -> Iterable[CorpusEntryRef]:
        ...

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        ...



