from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusView

from ..lanes.semantic.metadata_store import VectorMetadataStore
from .inventory_provider import InventoryProvider, resolve_view_for_pool_identifier
from .reason_codes import DiagnosticReasonCode


class SliceStatus(str, Enum):
    MISSING = "missing"
    STALE_CONTENT = "stale_content"
    STALE_IDENTITY = "stale_identity"
    UNAVAILABLE = "unavailable"
    HEALTHY = "healthy"
    ORPHANED = "orphaned"


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
        view: Optional[CorpusView] = None,
    ):
        self.corpus_provider = corpus_provider
        self.metadata_store = metadata_store
        self.pool_identifier = pool_identifier
        self.runtime_identity = runtime_identity
        self.view = view or resolve_view_for_pool_identifier(pool_identifier)

    def diagnose(self, *, dossier_id: Optional[str] = None) -> List[SliceDiagnosis]:
        """
        Diagnose index health for doc slices.

        Returns SliceDiagnosis with stable reason codes for all failure modes.

        CRITICAL INVARIANT: Never returns HEALTHY unless:
        - desired_signature exists and matches indexed_signature
        - runtime_identity is available and matches indexed identity
        """
        inventory = InventoryProvider(
            corpus_provider=self.corpus_provider,
            view=self.view,
        ).list_slices(
            pool_identifier=self.pool_identifier,
            dossier_id=dossier_id,
            include_unavailable=True,
        )

        results: List[SliceDiagnosis] = []
        desired_keys: set[tuple[str, str]] = set()
        for inv in inventory:
            desired_keys.add((inv.dossier_id, inv.entry_id))
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

        indexed_keys = set(
            self.metadata_store.list_indexed_entry_keys(
                pool_identifier=self.pool_identifier,
                dossier_id=dossier_id,
            )
        )
        orphaned = sorted(indexed_keys - desired_keys)
        for orphan_dossier_id, orphan_entry_id in orphaned:
            state = self.metadata_store.get_indexed_entry_state(
                pool_identifier=self.pool_identifier,
                dossier_id=orphan_dossier_id,
                entry_id=orphan_entry_id,
            )
            results.append(
                SliceDiagnosis(
                    pool_identifier=self.pool_identifier,
                    dossier_id=orphan_dossier_id,
                    entry_id=orphan_entry_id,
                    status=SliceStatus.ORPHANED,
                    desired_signature=None,
                    indexed_signature=state.indexed_signature if state else None,
                    reason=DiagnosticReasonCode.ORPHANED_NOT_IN_INVENTORY.value,
                )
            )

        return results
