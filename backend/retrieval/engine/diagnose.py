from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from corpus.interfaces import CorpusProvider

from ..lanes.semantic.metadata_store import VectorMetadataStore
from .inventory_provider import InventoryProvider
from .reason_codes import DiagnosticReasonCode


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
        """
        Diagnose index health for doc slices.

        Returns SliceDiagnosis with stable reason codes for all failure modes.

        CRITICAL INVARIANT: Never returns HEALTHY unless:
        - desired_signature exists and matches indexed_signature
        - runtime_identity is available and matches indexed identity
        """
        inventory = InventoryProvider(
            corpus_provider=self.corpus_provider
        ).list_slices(
            pool_identifier=self.pool_identifier,
            dossier_id=dossier_id,
            include_unavailable=True,
        )

        results: List[SliceDiagnosis] = []
        for inv in inventory:
            # Handle unavailable slices from inventory (hydration failures, missing content, etc.)
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

            # Missing indexed state
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
                        reason=DiagnosticReasonCode.MISSING_INDEX_STATE.value,
                    )
                )
                continue

            # H4: Cannot evaluate staleness without runtime identity
            # NEVER mark healthy if we can't verify identity checks
            if self.runtime_identity is None:
                results.append(
                    SliceDiagnosis(
                        pool_identifier=inv.pool_identifier,
                        dossier_id=inv.dossier_id,
                        entry_id=inv.entry_id,
                        status=SliceStatus.UNAVAILABLE,
                        desired_signature=inv.desired_signature,
                        indexed_signature=state.indexed_signature,
                        reason=DiagnosticReasonCode.UNAVAILABLE_RUNTIME_IDENTITY_MISSING.value,
                    )
                )
                continue

            # Identity mismatch (stale model or policy)
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
                        reason=DiagnosticReasonCode.STALE_IDENTITY_MISMATCH.value,
                    )
                )
                continue

            # Content signature mismatch (stale content)
            if inv.desired_signature != state.indexed_signature:
                results.append(
                    SliceDiagnosis(
                        pool_identifier=inv.pool_identifier,
                        dossier_id=inv.dossier_id,
                        entry_id=inv.entry_id,
                        status=SliceStatus.STALE_CONTENT,
                        desired_signature=inv.desired_signature,
                        indexed_signature=state.indexed_signature,
                        reason=DiagnosticReasonCode.STALE_SIGNATURE_MISMATCH.value,
                    )
                )
                continue

            # All checks passed: mark as HEALTHY
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
