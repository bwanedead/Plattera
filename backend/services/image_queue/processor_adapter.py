from __future__ import annotations

from typing import Dict, Any


class ImageToTextProcessorAdapter:
    """
    Thin wrapper over the existing pipelines.image_to_text.pipeline.ImageToTextPipeline
    to keep queue service decoupled from pipeline implementation details.
    """

    def process(self, job: Dict[str, Any]) -> Dict[str, Any]:
        from pipelines.image_to_text.pipeline import ImageToTextPipeline

        pipeline = ImageToTextPipeline()

        model = job.get("model", "gpt-4o")
        extraction_mode = job.get("extraction_mode", "legal_document_json")
        enhancement_settings = job.get("enhancement_settings") or {}
        redundancy_count = int(job.get("redundancy_count") or 1)
        consensus_strategy = job.get("consensus_strategy", "sequential")
        dossier_id = job.get("dossier_id")
        transcription_id = job.get("transcription_id")
        auto_llm_consensus = bool(job.get("auto_llm_consensus") or False)
        llm_consensus_model = job.get("llm_consensus_model") or "gpt-5-consensus"
        auto_per_file = bool(job.get("auto_create_dossier_per_file") or False)

        # If per-file auto create is requested and no dossier assigned yet, create on demand now
        if auto_per_file:
            try:
                from services.dossier.management_service import DossierManagementService
                ms = DossierManagementService()
                from pathlib import Path as _Path
                title = f"{_Path(job.get('source_filename') or 'document').stem} - Processing..."
                new_dossier = ms.create_dossier(title=title, description=f"Processing started at {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
                dossier_id = new_dossier.id
            except Exception:
                dossier_id = None
        # Always synthesize a per-file transcription id if dossier is present
        if dossier_id and not transcription_id:
            try:
                from pathlib import Path as _P
                transcription_id = f"draft_{_P(job.get('source_filename') or 'document').stem}"
            except Exception:
                transcription_id = None

        # Ensure dossier run metadata and association exist before processing so UI can populate immediately
        if dossier_id and transcription_id:
            try:
                # Create run metadata
                from services.dossier.management_service import DossierManagementService as _DMS
                _ms = _DMS()
                processing_params = {
                    "model": model,
                    "extraction_mode": extraction_mode,
                    "redundancy_count": redundancy_count,
                    "consensus_strategy": consensus_strategy,
                    "auto_llm_consensus": auto_llm_consensus,
                    "llm_consensus_model": llm_consensus_model,
                }
                _ms.create_run_metadata(
                    dossier_id=str(dossier_id),
                    transcription_id=str(transcription_id),
                    redundancy_count=redundancy_count,
                    processing_params=processing_params,
                )
                # Associate transcription to dossier
                from services.dossier.association_service import TranscriptionAssociationService as _TAS
                _assoc = _TAS()
                if not _assoc.transcription_exists_in_dossier(str(dossier_id), str(transcription_id)):
                    pos = _assoc.get_transcription_count(str(dossier_id)) + 1
                    _assoc.add_transcription(
                        dossier_id=str(dossier_id),
                        transcription_id=str(transcription_id),
                        position=pos,
                        metadata={"processing_params": processing_params, "auto_added": True, "source": "batch:worker:pre"},
                    )
                # Create placeholder drafts
                try:
                    from pathlib import Path as _Path2
                    import json as _json
                    from datetime import datetime as _dt
                    _BACKEND_DIR = _Path2(__file__).resolve().parents[2]
                    raw_dir = _BACKEND_DIR / "dossiers_data" / "views" / "transcriptions" / str(dossier_id) / str(transcription_id) / "raw"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    total = max(1, redundancy_count)
                    for i in range(1, total + 1):
                        pf = raw_dir / f"{transcription_id}_v{i}.json"
                        if not pf.exists():
                            with open(pf, 'w', encoding='utf-8') as _f:
                                _json.dump({
                                    "documentId": "processing",
                                    "sections": [{"id": 1, "body": f"Processing draft {i} of {total}..."}],
                                    "_placeholder": True,
                                    "_status": "processing",
                                    "_draft_index": i - 1,
                                    "_created_at": _dt.now().isoformat(),
                                }, _f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
            except Exception:
                pass

        if redundancy_count > 1:
            try:
                pipeline.redundancy_processor.auto_llm_consensus = auto_llm_consensus
                pipeline.redundancy_processor.llm_consensus_model = llm_consensus_model
            except Exception:
                pass

        if redundancy_count > 1:
            result = pipeline.process_with_redundancy(
                job["source_path"],
                model,
                extraction_mode,
                enhancement_settings,
                redundancy_count,
                consensus_strategy,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
            )
        else:
            # For single draft, we still want dossier progressive saving if dossier_id/transcription_id provided
            if dossier_id and transcription_id:
                result = pipeline.process_with_redundancy(
                    job["source_path"],
                    model,
                    extraction_mode,
                    enhancement_settings,
                    1,
                    "sequential",
                    dossier_id=dossier_id,
                    transcription_id=transcription_id,
                )
            else:
                result = pipeline.process(
                    job["source_path"],
                    model,
                    extraction_mode,
                    enhancement_settings,
                )

        # Ensure metadata includes dossier/transcription for downstream persistence
        try:
            if isinstance(result, dict):
                meta = result.get("metadata") or {}
                if dossier_id:
                    meta["dossier_id"] = dossier_id
                if transcription_id:
                    meta["transcription_id"] = transcription_id
                result["metadata"] = meta
        except Exception:
            pass

        return result


