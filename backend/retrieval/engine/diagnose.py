from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from corpus.interfaces import CorpusProvider

from ..lanes.semantic.metadata_store import VectorMetadataStore
from .inventory_provider import InventoryProvider


class SliceStatus(str, Enum):
    MISSING = "missing"
    STALE_CONTENT = "stale_content"
    STALE_IDENTITY = "stale_identity"
    UNAVAILABLE = "unavailable"
    HEALTHY = "healthy"


@dataclass(frozen=True)
class RuntimeIndexIdentity:
    embedding_model_fingerprint: str
    chunking_policy_id: str


@dataclass(frozen=True)
class SliceDiagnosis:
    pool_identifier: str
    dossier_id: str
    entry_id: str
    status: SliceStatus
    desired_signature: Optional[str] = None
    indexed_signature: Optional[str] = None
    reason: Optional[str] = None


class SliceDiagnoser:
    """
    Diagnose index health for doc slices by comparing desired vs indexed state.
    """

    def __init__(
        self,
        corpus_provider: CorpusProvider,
        metadata_store: VectorMetadataStore,
        *,
        pool_identifier: str = "FINAL_SEGMENTS",
        runtime_identity: Optional[RuntimeIndexIdentity] = None,
    ):
        self.corpus_provider = corpus_provider
        self.metadata_store = metadata_store
        self.pool_identifier = pool_identifier
        self.runtime_identity = runtime_identity

    def diagnose(self, *, dossier_id: Optional[str] = None) -> List[SliceDiagnosis]:
        inventory = InventoryProvider(
            corpus_provider=self.corpus_provider
        ).list_slices(
            pool_identifier=self.pool_identifier,
            dossier_id=dossier_id,
            include_unavailable=True,
        )

        results: List[SliceDiagnosis] = []
        for inv in inventory:
            if inv.unavailable_reason:
                results.append(
                    SliceDiagnosis(
                        pool_identifier=inv.pool_identifier,
                        dossier_id=inv.dossier_id,
                        entry_id=inv.entry_id,
                        status=SliceStatus.UNAVAILABLE,
                        desired_signature=None,
                        indexed_signature=None,
                        reason=inv.unavailable_reason,
                    )
                )
                continue

            state = self.metadata_store.get_indexed_entry_state(
                pool_identifier=inv.pool_identifier,
                dossier_id=inv.dossier_id,
                entry_id=inv.entry_id,
            )

            if state is None:
                results.append(
                    SliceDiagnosis(
                        pool_identifier=inv.pool_identifier,
                        dossier_id=inv.dossier_id,
                        entry_id=inv.entry_id,
                        status=SliceStatus.MISSING,
                        desired_signature=inv.desired_signature,
                        indexed_signature=None,
                        reason="missing_indexed_state",
                    )
                )
                continue

            if self.runtime_identity:
                if (
                    state.embedding_model_fingerprint != self.runtime_identity.embedding_model_fingerprint
                    or state.chunking_policy_id != self.runtime_identity.chunking_policy_id
                ):
                    results.append(
                        SliceDiagnosis(
                            pool_identifier=inv.pool_identifier,
                            dossier_id=inv.dossier_id,
                            entry_id=inv.entry_id,
                            status=SliceStatus.STALE_IDENTITY,
                            desired_signature=inv.desired_signature,
                            indexed_signature=state.indexed_signature,
                            reason="identity_mismatch",
                        )
                    )
                    continue

            if inv.desired_signature != state.indexed_signature:
                results.append(
                    SliceDiagnosis(
                        pool_identifier=inv.pool_identifier,
                        dossier_id=inv.dossier_id,
                        entry_id=inv.entry_id,
                        status=SliceStatus.STALE_CONTENT,
                        desired_signature=inv.desired_signature,
                        indexed_signature=state.indexed_signature,
                        reason="signature_mismatch",
                    )
                )
                continue

            results.append(
                SliceDiagnosis(
                    pool_identifier=inv.pool_identifier,
                    dossier_id=inv.dossier_id,
                    entry_id=inv.entry_id,
                    status=SliceStatus.HEALTHY,
                    desired_signature=inv.desired_signature,
                    indexed_signature=state.indexed_signature,
                    reason=None,
                )
            )

        return results
