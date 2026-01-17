from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusView

from ..lanes.semantic.index_builder import SemanticIndexBuilder
from ..lanes.semantic.persistent_store import PersistentVectorStore
from .diagnose import RuntimeIndexIdentity, SliceDiagnoser, SliceDiagnosis, SliceStatus


@dataclass(frozen=True)
class ExecuteResult:
    pool_identifier: str
    dossier_id: str
    entry_id: str
    status: SliceStatus
    deleted_count: int
    chunks_added: int
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
        view: CorpusView = CorpusView.FINAL_SEGMENTS,
    ):
        self.corpus_provider = corpus_provider
        self.vector_store = vector_store
        self.builder = builder
        self.runtime_identity = runtime_identity
        self.view = view

    def execute_entry(self, *, dossier_id: str, entry_id: str) -> ExecuteResult:
        diagnoser = SliceDiagnoser(
            corpus_provider=self.corpus_provider,
            metadata_store=self.vector_store.metadata_store,
            pool_identifier=self.vector_store.pool_identifier,
            runtime_identity=self.runtime_identity,
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
                reason="already_healthy",
            )

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
                reason="entry_ref_not_found",
            )

        build_result = self.builder.build_index_for_entry(
            vector_store=self.vector_store,
            ref=ref,
            embedding_model_fingerprint=self.runtime_identity.embedding_model_fingerprint,
        )

        status = SliceStatus.HEALTHY if not build_result.errors else diagnosis.status
        reason = None if not build_result.errors else "; ".join(build_result.errors)

        return ExecuteResult(
            pool_identifier=self.vector_store.pool_identifier,
            dossier_id=dossier_id,
            entry_id=entry_id,
            status=status,
            deleted_count=deleted_count,
            chunks_added=build_result.chunks_added,
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
