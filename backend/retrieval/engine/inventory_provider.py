from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusView

from .reason_codes import DiagnosticReasonCode


@dataclass(frozen=True)
class InventorySlice:
    """
    Desired inventory slice for a doc-level entry.
    """

    pool_identifier: str
    dossier_id: str
    entry_id: str
    desired_signature: Optional[str]
    unavailable_reason: Optional[str] = None


class InventoryProvider:
    """
    Enumerate desired doc slices for a corpus view.

    v0: FINAL_SEGMENTS only, desired_signature comes from entry.content_hash.
    """

    def __init__(self, corpus_provider: CorpusProvider, view: CorpusView = CorpusView.FINAL_SEGMENTS):
        self.corpus_provider = corpus_provider
        self.view = view

    def list_slices(
        self,
        *,
        pool_identifier: str = "FINAL_SEGMENTS",
        dossier_id: Optional[str] = None,
        include_unavailable: bool = False,
    ) -> List[InventorySlice]:
        slices: List[InventorySlice] = []

        refs = list(self.corpus_provider.list_entry_refs(view=self.view, dossier_id=dossier_id))
        for ref in refs:
            if not ref.dossier_id:
                continue
            entry = self.corpus_provider.hydrate_entry(ref)
            desired_signature, unavailable_reason = self._desired_signature(entry)
            if unavailable_reason:
                if include_unavailable:
                    slices.append(
                        InventorySlice(
                            pool_identifier=pool_identifier,
                            dossier_id=ref.dossier_id,
                            entry_id=ref.entry_id,
                            desired_signature=None,
                            unavailable_reason=unavailable_reason,
                        )
                    )
                continue
            if desired_signature:
                slices.append(
                    InventorySlice(
                        pool_identifier=pool_identifier,
                        dossier_id=ref.dossier_id,
                        entry_id=ref.entry_id,
                        desired_signature=desired_signature,
                    )
                )

        return slices

    @staticmethod
    def _desired_signature(entry: CorpusEntry) -> Tuple[Optional[str], Optional[str]]:
        """
        Compute desired signature for an entry.

        Returns (signature, unavailable_reason) where unavailable_reason is a
        stable DiagnosticReasonCode if the entry cannot be indexed.
        """
        # Hydration failed or other provenance error
        if entry.provenance and entry.provenance.get("error"):
            return None, DiagnosticReasonCode.UNAVAILABLE_HYDRATION_FAILED.value

        # Preferred: use content_hash if available
        if entry.content_hash:
            return entry.content_hash, None

        # Fallback: compute from text
        text = entry.text or ""
        if not text:
            return None, DiagnosticReasonCode.UNAVAILABLE_MISSING_CONTENT_HASH.value

        return hashlib.sha256(text.encode("utf-8")).hexdigest(), None
