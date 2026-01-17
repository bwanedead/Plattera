from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusView

from ..lanes.semantic.index_builder import SemanticIndexBuilder
from ..lanes.semantic.persistent_store import PersistentVectorStore
from .diagnose import RuntimeIndexIdentity, SliceDiagnoser, SliceDiagnosis, SliceStatus
from .inventory_provider import resolve_view_for_pool_identifier


@dataclass(frozen=True)
class ExecuteResult:
    """
    Result of executing a slice rebuild operation.

    H2 INVARIANT: did_write_state is True ONLY if:
    - All vector upserts succeeded (chunks_added > 0)
    - indexed_entry_state was successfully written
    - status is HEALTHY
    """
    pool_identifier: str
    dossier_id: str
    entry_id: str
    status: SliceStatus
    deleted_count: int
    chunks_added: int
    did_write_state: bool
    reason: Optional[str] = None


class SliceExecutor:
    """
    Execute doc-slice maintenance actions explicitly.
    """

    def __init__(
        self,
        *,
        corpus_provider: CorpusProvider,
        vector_store: PersistentVectorStore,
        builder: SemanticIndexBuilder,
        runtime_identity: RuntimeIndexIdentity,
        view: Optional[CorpusView] = None,
    ):
        self.corpus_provider = corpus_provider
        self.vector_store = vector_store
        self.builder = builder
        self.runtime_identity = runtime_identity
        self.view = view or resolve_view_for_pool_identifier(vector_store.pool_identifier)

    def execute_entry(self, *, dossier_id: str, entry_id: str) -> ExecuteResult:
        diagnoser = SliceDiagnoser(
            corpus_provider=self.corpus_provider,
            metadata_store=self.vector_store.metadata_store,
            pool_identifier=self.vector_store.pool_identifier,
            runtime_identity=self.runtime_identity,
            view=self.view,
        )

        diagnosis = self._find_diagnosis(diagnoser, dossier_id=dossier_id, entry_id=entry_id)
        if diagnosis is None:
            return ExecuteResult(
                pool_identifier=self.vector_store.pool_identifier,
                dossier_id=dossier_id,
                entry_id=entry_id,
                status=SliceStatus.UNAVAILABLE,
                deleted_count=0,
                chunks_added=0,
                did_write_state=False,
                reason="entry_not_in_inventory",
            )

        if diagnosis.status == SliceStatus.UNAVAILABLE:
            return ExecuteResult(
                pool_identifier=diagnosis.pool_identifier,
                dossier_id=diagnosis.dossier_id,
                entry_id=diagnosis.entry_id,
                status=diagnosis.status,
                deleted_count=0,
                chunks_added=0,
                did_write_state=False,
                reason=diagnosis.reason,
            )

        if diagnosis.status == SliceStatus.HEALTHY:
            return ExecuteResult(
                pool_identifier=diagnosis.pool_identifier,
                dossier_id=diagnosis.dossier_id,
                entry_id=diagnosis.entry_id,
                status=diagnosis.status,
                deleted_count=0,
                chunks_added=0,
                did_write_state=False,  # No write happened (already healthy)
                reason="already_healthy",
            )

        # H2: Delete old vectors before rebuild
        deleted_count = self.vector_store.delete_entry_slice(
            dossier_id=dossier_id, entry_id=entry_id
        )

        ref = self._find_entry_ref(dossier_id=dossier_id, entry_id=entry_id)
        if ref is None:
            return ExecuteResult(
                pool_identifier=self.vector_store.pool_identifier,
                dossier_id=dossier_id,
                entry_id=entry_id,
                status=SliceStatus.UNAVAILABLE,
                deleted_count=deleted_count,
                chunks_added=0,
                did_write_state=False,
                reason="entry_ref_not_found",
            )

        # H2: Rebuild entry (will write state only if all chunks succeed)
        build_result = self.builder.build_index_for_entry(
            vector_store=self.vector_store,
            ref=ref,
            embedding_model_fingerprint=self.runtime_identity.embedding_model_fingerprint,
        )

        # H2 ENFORCEMENT: status is HEALTHY only if no errors
        # This means state was successfully written (per index_builder logic)
        status = SliceStatus.HEALTHY if not build_result.errors else diagnosis.status
        reason = None if not build_result.errors else "; ".join(build_result.errors)
        did_write_state = status == SliceStatus.HEALTHY and build_result.chunks_added > 0

        return ExecuteResult(
            pool_identifier=self.vector_store.pool_identifier,
            dossier_id=dossier_id,
            entry_id=entry_id,
            status=status,
            deleted_count=deleted_count,
            chunks_added=build_result.chunks_added,
            did_write_state=did_write_state,
            reason=reason,
        )

    def _find_entry_ref(self, *, dossier_id: str, entry_id: str):
        refs = self.corpus_provider.list_entry_refs(
            view=self.view,
            dossier_id=dossier_id,
        )
        for ref in refs:
            if ref.entry_id == entry_id:
                return ref
        return None

    @staticmethod
    def _find_diagnosis(
        diagnoser: SliceDiagnoser, *, dossier_id: str, entry_id: str
    ) -> Optional[SliceDiagnosis]:
        for diagnosis in diagnoser.diagnose(dossier_id=dossier_id):
            if diagnosis.entry_id == entry_id:
                return diagnosis
        return None
