"""
Dossier Image Processing Endpoints
==================================

Handles dossier-specific image processing operations with progressive draft saving.
Provides clean separation between general processing and dossier management.

🎯 RESPONSIBILITIES:
- Process images with dossier association and progressive saving
- Handle real-time draft saving as LLM results complete
- Manage dossier-specific image processing workflows
- Coordinate between processing pipeline and dossier services

🔄 INTEGRATION POINTS:
- Uses ImageToTextPipeline for core image processing
- Uses ProgressiveDraftSaver for real-time draft persistence
- Updates dossier metadata and run status progressively
- Triggers UI refresh events for real-time updates

📁 ENDPOINT STRUCTURE:
- POST /api/dossier/process - Process image with dossier association
- GET /api/dossier/{dossier_id}/transcription/{transcription_id}/status - Get processing status

🚀 KEY FEATURES:
- Progressive draft saving (drafts saved as they complete)
- Real-time UI updates via event system
- Fault-tolerant processing (failed drafts don't block others)
- Clean separation of concerns from general processing
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from utils.response_models import ProcessResponse
from utils.file_handler import save_uploaded_file, cleanup_temp_file, is_valid_image_file
from typing import Optional, Dict, Any
import logging

from config.paths import dossiers_views_root, dossier_run_root

logger = logging.getLogger(__name__)

router = APIRouter()


class DossierProcessRequest(BaseModel):
    """Request model for dossier processing"""
    model: str = "gpt-4o"
    extraction_mode: str = "legal_document_json"
    cleanup_after: str = "true"
    flow_to: Optional[str] = None
    parcel_id: Optional[str] = None
    dossier_id: str
    transcription_id: str
    # Enhancement settings
    contrast: str = "2.0"
    sharpness: str = "2.0"
    brightness: str = "1.5"
    color: str = "1.0"
    # Redundancy settings
    redundancy: str = "3"
    consensus_strategy: str = "sequential"
    # LLM consensus settings
    auto_llm_consensus: str = "false"
    llm_consensus_model: str = "gpt-5-consensus"


@router.post("/process", response_model=ProcessResponse)
async def process_with_dossier_association(
    file: UploadFile = File(...),
    # Dossier context (required for progressive saving)
    dossier_id: str = Form(...),
    transcription_id: Optional[str] = Form(None),
    # Processing parameters
    model: str = Form("gpt-4o"),
    extraction_mode: str = Form("legal_document_json"),
    cleanup_after: str = Form("true"),
    flow_to: Optional[str] = Form(None),
    parcel_id: Optional[str] = Form(None),
    # Enhancement settings
    contrast: str = Form("2.0"),
    sharpness: str = Form("2.0"),
    brightness: str = Form("1.5"),
    color: str = Form("1.0"),
    # Redundancy settings
    redundancy: str = Form("3"),
    consensus_strategy: str = Form("sequential"),
    # LLM consensus settings
    auto_llm_consensus: str = Form("false"),
    llm_consensus_model: str = Form("gpt-5-consensus"),
    # Optional user instruction appended to prompt
    user_instruction: Optional[str] = Form(None)
):
    """
    Process an image with dossier association and progressive draft saving.

    This endpoint provides the enhanced dossier processing experience with:
    - Progressive draft saving (real-time UI updates)
    - Dossier association and metadata management
    - Fault-tolerant processing
    - Clean separation of concerns

    Args:
        file: Image file to process
        dossier_id: Dossier to associate results with
        transcription_id: Transcription identifier (auto-generated if not provided)
        model: LLM model to use
        extraction_mode: Processing mode (legal_document_json, etc.)
        contrast/sharpness/brightness/color: Image enhancement settings
        redundancy: Number of parallel drafts (1-10)
        consensus_strategy: How to combine results
        auto_llm_consensus: Whether to generate LLM consensus
        llm_consensus_model: Model for consensus generation

    Returns:
        ProcessResponse with processing results and dossier context
    """
    # Add detailed logging
    logger.info("🔥 DOSSIER PROCESSING REQUEST RECEIVED:")
    logger.info(f"   📁 File: {file.filename} (size: {file.size if hasattr(file, 'size') else 'unknown'})")
    logger.info(f"   📋 Content-Type: {file.content_type}")
    logger.info(f"   🎯 Processing Type: {extraction_mode}")
    logger.info(f"   🤖 Model: {model}")
    logger.info(f"   📂 Dossier ID: {dossier_id}")
    logger.info(f"   🆔 Transcription ID: {transcription_id}")
    logger.info(f"   🎨 Enhancement Settings: contrast={contrast}, sharpness={sharpness}, brightness={brightness}, color={color}")
    logger.info(f"   🔄 Redundancy: {redundancy}")
    logger.info(f"   🧠 Consensus Strategy: {consensus_strategy}")
    logger.info(f"   🤝 Auto LLM Consensus: {auto_llm_consensus}")
    logger.info(f"   🤖 LLM Consensus Model: {llm_consensus_model}")

    # Check if we have the right parameters for progressive saving
    has_dossier_id = bool(dossier_id)
    has_transcription_id = bool(transcription_id)
    logger.info(f"   ⚡ Progressive Saving Ready: dossier_id={has_dossier_id}, transcription_id={has_transcription_id}")

    # Validate required dossier context
    if not dossier_id:
        raise HTTPException(
            status_code=400,
            detail="dossier_id is required for dossier processing"
        )

    # Parse and validate parameters (same as main processing endpoint)
    try:
        enhancement_settings = {
            'contrast': max(0.1, min(5.0, float(contrast))),
            'sharpness': max(0.1, min(5.0, float(sharpness))),
            'brightness': max(0.1, min(3.0, float(brightness))),
            'color': max(0.0, min(3.0, float(color)))
        }
        if user_instruction and user_instruction.strip():
            enhancement_settings['user_instruction'] = user_instruction.strip()
        logger.info(f"✅ Enhancement settings parsed: {enhancement_settings}")
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ Invalid enhancement parameters, using defaults: {e}")
        enhancement_settings = {
            'contrast': 1.5,
            'sharpness': 1.2,
            'brightness': 1.0,
            'color': 1.0
        }

    try:
        redundancy_count = max(1, min(10, int(redundancy)))
        logger.info(f"✅ Redundancy count parsed: {redundancy_count}")
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ Invalid redundancy parameter, using default: {e}")
        redundancy_count = 3

    valid_strategies = ['sequential', 'ngram_overlap', 'strict_majority', 'length_weighted', 'confidence_weighted']
    if consensus_strategy not in valid_strategies:
        logger.warning(f"⚠️ Invalid consensus strategy '{consensus_strategy}', using 'sequential'")
        consensus_strategy = 'sequential'

    try:
        auto_llm_consensus_flag = str(auto_llm_consensus).strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        auto_llm_consensus_flag = False

    temp_path = None

    try:
        # Validate image file
        logger.info(f"🔍 Validating image file: {file.filename}")
        if not is_valid_image_file(file.filename):
            logger.error(f"❌ Invalid file type: {file.filename}")
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Please upload an image file."
            )
        logger.info("✅ File type validation passed")

        # Save uploaded file temporarily
        logger.info("💾 Reading and saving file...")
        file_content = await file.read()
        logger.info(f"📏 File content size: {len(file_content)} bytes")

        success, error, temp_path = save_uploaded_file(file_content, file.filename)
        if not success:
            logger.error(f"❌ File save failed: {error}")
            raise HTTPException(status_code=400, detail=error)

        logger.info(f"✅ File saved to: {temp_path}")

        # Ensure we have a transcription_id BEFORE processing so progressive saving can activate
        try:
            from pathlib import Path as _Path
            if not transcription_id or not str(transcription_id).strip():
                stem = _Path(temp_path).stem if temp_path else (_Path(file.filename).stem if file and file.filename else None)
                transcription_id = f"draft_{stem}" if stem else f"draft_{int(__import__('time').time())}"
                logger.info(f"🆔 Generated transcription_id prior to processing: {transcription_id}")

            # Create run metadata up-front so progressive saver can append into an existing file
            try:
                from services.dossier.management_service import DossierManagementService as _DMS
                _ms = _DMS()
                _ms.create_run_metadata(
                    dossier_id=str(dossier_id),
                    transcription_id=str(transcription_id),
                    redundancy_count=redundancy_count,
                    processing_params={
                        "model": model,
                        "extraction_mode": extraction_mode,
                        "redundancy_count": redundancy_count,
                        "consensus_strategy": consensus_strategy,
                        "auto_llm_consensus": auto_llm_consensus_flag,
                        "llm_consensus_model": llm_consensus_model
                    }
                )
            except Exception as pre_meta_err:
                logger.warning(f"⚠️ Could not create run metadata before processing (non-critical): {pre_meta_err}")
        except Exception as tid_err:
            logger.warning(f"⚠️ Failed to ensure transcription_id prior to processing: {tid_err}")

        # Pre-associate transcription and create placeholders so UI can render immediately
        try:
            from services.dossier.association_service import TranscriptionAssociationService as _TAS
            _assoc = _TAS()
            if not _assoc.transcription_exists_in_dossier(str(dossier_id), str(transcription_id)):
                next_position = _assoc.get_transcription_count(str(dossier_id)) + 1
                _assoc.add_transcription(
                    dossier_id=str(dossier_id),
                    transcription_id=str(transcription_id),
                    position=next_position,
                    metadata={
                        "processing_params": {
                            "model": model,
                            "extraction_mode": extraction_mode,
                            "redundancy_count": redundancy_count,
                            "consensus_strategy": consensus_strategy,
                            "auto_llm_consensus": auto_llm_consensus_flag,
                            "llm_consensus_model": llm_consensus_model
                        },
                        "auto_added": True,
                        "source": "dossier:processing:pre"
                    }
                )
        except Exception as pre_assoc_err:
            logger.debug(f"(non-critical) Could not pre-associate transcription: {pre_assoc_err}")

        # Create placeholder drafts for all redundancy versions (idempotent)
        try:
            from pathlib import Path as _Path2
            import json as _json
            from datetime import datetime as _dt

            run_root = dossier_run_root(str(dossier_id), str(transcription_id))
            raw_dir = run_root / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            for i in range(1, redundancy_count + 1):
                pf = raw_dir / f"{transcription_id}_v{i}.json"
                if not pf.exists():
                    with open(pf, 'w', encoding='utf-8') as _f:
                        _json.dump({
                            "documentId": "processing",
                            "sections": [{"id": 1, "body": f"Processing draft {i} of {redundancy_count}..."}],
                            "_placeholder": True,
                            "_status": "processing",
                            "_draft_index": i - 1,
                            "_created_at": _dt.now().isoformat()
                        }, _f, indent=2, ensure_ascii=False)
            logger.info(f"VISIBILITY_PRIME dossier={dossier_id} transcription={transcription_id} placeholders={redundancy_count}")
        except Exception as pre_placeholder_err:
            logger.debug(f"(non-critical) Could not create placeholders: {pre_placeholder_err}")

        # Process with dossier association and progressive saving
        logger.info("🚀 Starting dossier processing with progressive saving...")
        from pipelines.image_to_text.pipeline import ImageToTextPipeline

        pipeline = ImageToTextPipeline()

        # Configure redundancy processor for LLM consensus if enabled
        if redundancy_count > 1:
            try:
                pipeline.redundancy_processor.auto_llm_consensus = auto_llm_consensus_flag
                pipeline.redundancy_processor.llm_consensus_model = llm_consensus_model
            except Exception as cfg_err:
                logger.warning(f"⚠️ Failed to configure LLM consensus options (non-critical): {cfg_err}")

        # Process with progressive saving enabled (offload to threadpool to avoid blocking the event loop)
        logger.info(f"🔄 Processing with progressive saving - dossier: {dossier_id}, transcription: {transcription_id}")
        result = await run_in_threadpool(lambda: pipeline.process_with_redundancy(
            temp_path,
            model,
            extraction_mode,
            enhancement_settings,
            redundancy_count,
            consensus_strategy,
            dossier_id=dossier_id,
            transcription_id=transcription_id
        ))

        if not result.get("success", False):
            logger.error(f"❌ Pipeline failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))

        logger.info("✅ Dossier processing completed successfully with progressive saving!")

        # Handle dossier association and metadata updates
        await _handle_dossier_association(
            dossier_id, transcription_id, result, temp_path,
            model, extraction_mode, redundancy_count, consensus_strategy,
            auto_llm_consensus_flag, llm_consensus_model, enhancement_settings,
            original_filename=(file.filename if hasattr(file, 'filename') else None)
        )

        # Persist LLM consensus output (if generated) so UI can mark consensus draft as completed
        try:
            ra = (result or {}).get('metadata', {}).get('redundancy_analysis', {}) or {}
            consensus_text = ra.get('consensus_text')
            logger.info(f"🔎 CONSENSUS SAVE CHECK ► enabled={auto_llm_consensus_flag} has_text={bool(consensus_text and str(consensus_text).strip())}")
            if auto_llm_consensus_flag and isinstance(consensus_text, str) and consensus_text.strip():
                from pathlib import Path as _PathSave
                from services.dossier.management_service import DossierManagementService as _DMS3

                base_root = dossiers_views_root()
                consensus_dir = base_root / str(dossier_id) / str(transcription_id) / "consensus"
                consensus_dir.mkdir(parents=True, exist_ok=True)
                consensus_file = consensus_dir / f"llm_{transcription_id}.json"
                with open(consensus_file, 'w', encoding='utf-8') as cf:
                    import json as _json
                    from datetime import datetime as _dt
                    _json.dump({
                        "type": "llm_consensus",
                        "model": ra.get('consensus_model') or llm_consensus_model,
                        "title": ra.get('consensus_title'),
                        "text": consensus_text,
                        "created_at": _dt.now().isoformat(),
                        "metadata": {}
                    }, cf, indent=2, ensure_ascii=False)
                logger.info(f"💾 Persisted LLM consensus JSON: {consensus_file}")

                # Update run metadata with consensus completion
                try:
                    _ms3 = _DMS3()
                    _ms3.update_run_metadata(
                        dossier_id=str(dossier_id),
                        transcription_id=str(transcription_id),
                        updates={
                            "has_llm_consensus": True,
                            "timestamps": {"last_update_at": _dt.now().isoformat()}
                        }
                    )
                except Exception as _eup:
                    logger.debug(f"(non-critical) Could not mark has_llm_consensus: {_eup}")
            elif auto_llm_consensus_flag:
                # Mark consensus attempt as failed for placeholder UI
                try:
                    from services.dossier.management_service import DossierManagementService as _DMS4
                    _ms4 = _DMS4()
                    _ms4.update_run_metadata(
                        dossier_id=str(dossier_id),
                        transcription_id=str(transcription_id),
                        updates={"llm_consensus_status": "failed"}
                    )
                    logger.info("📝 Marked LLM consensus status: failed")
                except Exception as _efail:
                    logger.debug(f"(non-critical) Could not mark LLM consensus as failed: {_efail}")
        except Exception as e:
            logger.warning(f"⚠️ LLM consensus persistence step failed (non-critical): {e}")

        # Return response with dossier context
        return ProcessResponse(
            status="success",
            extracted_text=result.get("extracted_text"),
            model_used=result.get("model_used"),
            service_type=result.get("service_type"),
            tokens_used=result.get("tokens_used"),
            confidence_score=result.get("confidence_score"),
            metadata={
                **result.get("metadata", {}),
                "dossier_id": dossier_id,
                "transcription_id": transcription_id,
                "progressive_saving_enabled": True,
                "processing_type": "dossier_with_progressive_saving"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Dossier processing error: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Dossier processing failed: {str(e)}")
    finally:
        # Always cleanup temp file
        if temp_path:
            logger.info(f"🧹 Cleaning up temp file: {temp_path}")
            cleanup_temp_file(temp_path)


async def _handle_dossier_association(
    dossier_id: str, transcription_id: str, result: dict, temp_path: str,
    model: str, extraction_mode: str, redundancy_count: int, consensus_strategy: str,
    auto_llm_consensus_flag: bool, llm_consensus_model: str, enhancement_settings: dict,
    original_filename: str = None
):
    """
    Handle dossier association, metadata updates, and provenance creation.

    This function manages all the dossier-specific post-processing steps
    after the main image processing is complete.
    """
    try:
        # Import required utilities
        from api.endpoints.dossier.dossier_utils import (
            extract_transcription_id_from_result,
            create_transcription_provenance
        )

        # Use provided transcription_id or extract/synthesize from result
        if not transcription_id:
            transcription_id = extract_transcription_id_from_result(result)
            if not transcription_id:
                from pathlib import Path
                stem = Path(temp_path).stem
                transcription_id = f"draft_{stem}"
            logger.info(f"📋 Generated transcription_id: {transcription_id}")

        # Ensure run metadata exists (do not overwrite progressive updates)
        processing_params = {
            "model": model,
            "extraction_mode": extraction_mode,
            "redundancy_count": redundancy_count,
            "consensus_strategy": consensus_strategy,
            "auto_llm_consensus": auto_llm_consensus_flag,
            "llm_consensus_model": llm_consensus_model
        }

        from services.dossier.management_service import DossierManagementService
        management_service = DossierManagementService()

        # Create run metadata only if it doesn't already exist (preserve progressive state)
        existing_run = management_service.get_run_metadata(dossier_id, transcription_id)
        if not existing_run:
            management_service.create_run_metadata(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                redundancy_count=redundancy_count,
                processing_params=processing_params
            )

        # Create provenance
        try:
            provenance = create_transcription_provenance(
                file_path=temp_path,
                model=model,
                extraction_mode=extraction_mode,
                result=result,
                transcription_id=transcription_id,
                enhancement_settings=enhancement_settings,
                save_images=True
            )
        except Exception as prov_error:
            logger.warning(f"⚠️ Provenance creation failed: {prov_error}")
            provenance = None

        # Prepare metadata
        metadata = {
            "auto_added": True,
            "source": "dossier:processing",
            "processing_params": processing_params
        }
        if provenance:
            metadata["provenance"] = provenance
            try:
                # Attach image metadata with public URLs for thumbnails/viewer
                import os as _os
                from pathlib import Path as _PURL
                images_meta = {}
                orig_path = provenance.get("enhancement", {}).get("original_image_path") if isinstance(provenance, dict) else None
                proc_path = provenance.get("enhancement", {}).get("processed_image_path") if isinstance(provenance, dict) else None
                if orig_path:
                    filename = _PURL(orig_path).name
                    images_meta["original_path"] = orig_path
                    _base = (_os.environ.get("PUBLIC_BACKEND_URL") or "http://localhost:8000").rstrip('/')
                    images_meta["original_url"] = f"{_base}/static/images/original/{filename}"
                if proc_path:
                    filename_p = _PURL(proc_path).name
                    images_meta["processed_path"] = proc_path
                    _base = (_os.environ.get("PUBLIC_BACKEND_URL") or "http://localhost:8000").rstrip('/')
                    images_meta["processed_url"] = f"{_base}/static/images/processed/{filename_p}"
                if images_meta:
                    metadata["images"] = images_meta
            except Exception as _eimg:
                logger.debug(f"(non-critical) Could not attach images metadata: {_eimg}")

        # Associate with dossier (update metadata if already associated)
        from services.dossier.association_service import TranscriptionAssociationService
        association_service = TranscriptionAssociationService()

        already_exists = association_service.transcription_exists_in_dossier(dossier_id, transcription_id)
        if already_exists:
            try:
                association_service.update_transcription_metadata(dossier_id, transcription_id, metadata)
                logger.info(f"📝 Updated existing association metadata for {transcription_id} in dossier {dossier_id}")
            except Exception as _uerr:
                logger.warning(f"⚠️ Failed to update existing association metadata: {_uerr}")
        else:
            next_position = len(association_service.get_dossier_transcriptions(dossier_id)) + 1
            success = association_service.add_transcription(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                position=next_position,
                metadata=metadata
            )
            if success:
                logger.info(f"📝 Associated transcription {transcription_id} with dossier {dossier_id}")
            else:
                logger.warning(f"⚠️ Failed to associate transcription {transcription_id} with dossier {dossier_id}")

        # Update dossier title only once (first segment wins)
        try:
            from pathlib import Path as _PathT
            from datetime import datetime as _DT

            current = management_service.get_dossier(dossier_id)
            current_title = (getattr(current, "title", "") or "").strip()
            allow_auto = (not current_title) or ("processing" in current_title.lower())

            if allow_auto:
                ra_for_title = result.get('metadata', {}).get('redundancy_analysis', {}) or {}
                consensus_title = ra_for_title.get('consensus_title')

                if consensus_title and str(consensus_title).strip():
                    management_service.update_dossier(dossier_id, {"title": str(consensus_title).strip()})
                    logger.info(f"🏷️ Updated dossier {dossier_id} title from LLM consensus: {consensus_title}")
                else:
                    # Fallback: use original uploaded filename if available; else temp file stem
                    if original_filename and str(original_filename).strip():
                        stem = _PathT(original_filename).stem
                    else:
                        stem = _PathT(temp_path).stem if temp_path else 'document'
                    timestamp = _DT.now().strftime('%Y-%m-%d %H:%M')
                    fallback_title = f"{stem} • {timestamp}"
                    management_service.update_dossier(dossier_id, {"title": fallback_title})
                    logger.info(f"🏷️ Updated dossier {dossier_id} title to fallback: {fallback_title}")
            else:
                logger.info(f"🏷️ Skipping auto title update for dossier {dossier_id}; title already set")
        except Exception as e:
            logger.debug(f"(non-critical) Could not update dossier title: {e}")

        # Mark run as completed
        from datetime import datetime as _DT2
        management_service.update_run_metadata(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            updates={
                "status": "completed",
                "timestamps": {"finished_at": _DT2.now().isoformat()}
            }
        )

        # If redundancy_count == 1, persist the final result as the v1 draft so UI loads real content.
        # NOTE: This must use the centralized path helpers so dev + frozen (PyInstaller) builds
        # read and write from the same physical location.
        try:
            if isinstance(result, dict) and int(redundancy_count) == 1:
                import json as _json

                # Use dossier_run_root so this matches the views/drafts path that the viewer reads.
                run_root = dossier_run_root(str(dossier_id), str(transcription_id))
                drafts_dir = run_root / "raw"
                drafts_dir.mkdir(parents=True, exist_ok=True)

                v1_path = drafts_dir / f"{transcription_id}_v1.json"
                base_path = drafts_dir / f"{transcription_id}.json"

                extracted_text = result.get("extracted_text", "")
                content: dict
                try:
                    if isinstance(extracted_text, str) and extracted_text.strip().startswith('{'):
                        parsed = _json.loads(extracted_text)
                        content = parsed if isinstance(parsed, dict) else {"text": extracted_text}
                    else:
                        content = {"text": extracted_text}
                except Exception:
                    content = {"text": str(extracted_text)}

                # Normalize: ensure not a placeholder, and set completion flags
                content.pop('_placeholder', None)
                content['_status'] = 'completed'
                content['_draft_index'] = 0

                with open(v1_path, 'w', encoding='utf-8') as vf:
                    _json.dump(content, vf, indent=2, ensure_ascii=False)
                with open(base_path, 'w', encoding='utf-8') as bf:
                    _json.dump(content, bf, indent=2, ensure_ascii=False)

                # Mark v1 completed in run metadata
                management_service.update_run_metadata(
                    dossier_id=dossier_id,
                    transcription_id=transcription_id,
                    updates={
                        "completed_drafts": f"{transcription_id}_v1",
                        "timestamps": {"last_update_at": _DT2.now().isoformat()}
                    }
                )
                logger.info(f"💾 Persisted final draft to {v1_path}")
        except Exception as _psave_err:
            logger.warning(f"⚠️ Failed to persist final v1 draft: {_psave_err}")

        logger.info(f"✅ Dossier association and metadata updates completed for {transcription_id}")

    except Exception as e:
        logger.warning(f"⚠️ Dossier association failed (non-critical): {e}")


@router.get("/status/{dossier_id}/{transcription_id}")
async def get_processing_status(dossier_id: str, transcription_id: str):
    """
    Get the current processing status for a transcription.

    Returns real-time information about draft completion status,
    useful for UI polling or status updates.
    """
    try:
        from services.dossier.progressive_draft_saver import ProgressiveDraftSaver

        saver = ProgressiveDraftSaver()
        status = saver.get_draft_status(dossier_id, transcription_id)

        return {
            "status": "success",
            "dossier_id": dossier_id,
            "transcription_id": transcription_id,
            "processing_status": status
        }

    except Exception as e:
        logger.error(f"❌ Failed to get processing status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


# Import datetime for timestamp handling
from datetime import datetime
