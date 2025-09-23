"""
Dossier Run Initialization API Endpoints
=========================================

Dedicated endpoints for initializing dossier run skeletons and managing run metadata.
Handles pre-processing setup for immediate UI feedback without actual processing.

🎯 RESPONSIBILITIES:
- Create dossier run skeletons with placeholder files
- Initialize run metadata and transcription associations
- Prepare UI for immediate feedback before processing starts
- Set up dossier structure for progressive draft saving

🔄 INTEGRATION POINTS:
- Creates dossier if it doesn't exist
- Generates transcription IDs and run metadata
- Sets up placeholder files for UI display
- Associates transcriptions with dossiers

📁 ENDPOINT STRUCTURE:
- POST /api/dossier-runs/init-run - Initialize run skeleton
- GET /api/dossier-runs/health - Health check endpoint

🚀 KEY FEATURES:
- Immediate UI feedback (placeholders created instantly)
- Skeleton creation without processing overhead
- Proper dossier and transcription setup
- Foundation for progressive processing workflow
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
from pathlib import Path
from datetime import datetime

from services.dossier.management_service import DossierManagementService
from services.dossier.association_service import TranscriptionAssociationService

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize services
management_service = DossierManagementService()
association_service = TranscriptionAssociationService()


class InitRunRequest(BaseModel):
    """Request model for initializing a dossier run skeleton"""
    dossier_id: Optional[str] = Field(None, description="Existing dossier ID (auto-create if None)")
    file_name: Optional[str] = Field(None, description="Original file name for transcription ID generation")
    transcription_id: Optional[str] = Field(None, description="Specific transcription ID (auto-generate if None)")
    model: str = Field(..., description="Image-to-text model being used")
    extraction_mode: str = Field(..., description="Extraction mode being used")
    redundancy_count: int = Field(1, ge=1, le=10, description="Number of redundant drafts")
    auto_llm_consensus: bool = Field(False, description="Whether to generate LLM consensus")
    llm_consensus_model: Optional[str] = Field("gpt-5-consensus", description="Consensus model to use")
    consensus_strategy: Optional[str] = Field("sequential", description="Consensus strategy for alignment")


class InitRunResponse(BaseModel):
    """Response model for run initialization"""
    success: bool
    dossier_id: str
    transcription_id: str
    data: Dict[str, Any] = Field(default_factory=dict)


@router.post("/init-run", response_model=InitRunResponse)
async def init_run(request: InitRunRequest):
    """
    Initialize a dossier run skeleton for immediate UI feedback.

    This creates the dossier (if needed), run metadata, and transcription association
    so that the Dossier Manager can display placeholders immediately while processing runs.
    """
    try:
        logger.info(f"🚀 API: Initializing run skeleton")
        logger.info(f"📁 Dossier ID: {request.dossier_id}")
        logger.info(f"📄 File name: {request.file_name}")
        logger.info(f"🆔 Transcription ID: {request.transcription_id}")

        # Step 1: Ensure dossier exists
        dossier_id = request.dossier_id
        if not dossier_id:
            logger.info("📝 Creating new dossier for run")
            # Use a more descriptive title based on the file name
            file_base = Path(request.file_name).stem if request.file_name else "Document"
            created_dossier = management_service.create_dossier(
                title=f"{file_base} - Processing...",
                description=f"Processing started at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            dossier_id = created_dossier.id
            logger.info(f"✅ Created dossier: {dossier_id}")

        # Step 2: Determine transcription ID
        transcription_id = request.transcription_id
        if not transcription_id:
            if request.file_name:
                stem = Path(request.file_name).stem
                transcription_id = f"draft_{stem}"
            else:
                transcription_id = f"draft_{int(datetime.now().timestamp())}"
            logger.info(f"🔖 Generated transcription ID: {transcription_id}")

        # Step 3: Create run metadata
        logger.info(f"📋 Creating run metadata for transcription: {transcription_id}")
        processing_params = {
            "model": request.model,
            "extraction_mode": request.extraction_mode,
            "redundancy_count": request.redundancy_count,
            "consensus_strategy": request.consensus_strategy,
            "auto_llm_consensus": request.auto_llm_consensus,
            "llm_consensus_model": request.llm_consensus_model
        }

        success = management_service.create_run_metadata(
            dossier_id=str(dossier_id),
            transcription_id=transcription_id,
            redundancy_count=request.redundancy_count,
            processing_params=processing_params
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to create run metadata")

        logger.info(f"✅ Created run metadata for {dossier_id}/{transcription_id}")

        # Step 4: Create placeholder JSON files for immediate UI feedback
        logger.info(f"📄 Creating placeholder draft files")
        try:
            import json
            from pathlib import Path as _Path

            backend_dir = _Path(__file__).resolve().parents[3]  # backend/
            base_root = backend_dir / "dossiers_data" / "views" / "transcriptions"
            run_root = base_root / str(dossier_id) / str(transcription_id)
            raw_dir = run_root / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            # Create placeholder files for each redundancy draft
            for i in range(request.redundancy_count):
                draft_id = f"{transcription_id}_v{i+1}"
                placeholder_file = raw_dir / f"{draft_id}.json"

                placeholder_data = {
                    "documentId": "processing",
                    "sections": [
                        {
                            "id": 1,
                            "body": f"Processing draft {i+1} of {request.redundancy_count}..."
                        }
                    ],
                    "_placeholder": True,
                    "_status": "processing",
                    "_draft_index": i,
                    "_created_at": datetime.now().isoformat()
                }

                with open(placeholder_file, 'w', encoding='utf-8') as f:
                    json.dump(placeholder_data, f, indent=2, ensure_ascii=False)

                logger.info(f"✅ Created placeholder: {placeholder_file}")

        except Exception as placeholder_error:
            logger.warning(f"⚠️ Failed to create placeholder files (non-critical): {placeholder_error}")

        # Step 5: Associate transcription so it appears in dossier hierarchy
        logger.info(f"🔗 Associating transcription with dossier")
        next_position = len(association_service.get_dossier_transcriptions(str(dossier_id))) + 1

        association_success = association_service.add_transcription(
            dossier_id=str(dossier_id),
            transcription_id=transcription_id,
            position=next_position,
            metadata={
                "processing_params": processing_params,
                "auto_added": True,
                "source": "dossier:init-run"
            }
        )

        if not association_success:
            raise HTTPException(status_code=500, detail="Failed to associate transcription")

        logger.info(f"✅ Associated transcription {transcription_id} with dossier {dossier_id}")

        # Step 6: Return success response
        return InitRunResponse(
            success=True,
            dossier_id=str(dossier_id),
            transcription_id=transcription_id,
            data={
                "created_at": datetime.now().isoformat(),
                "processing_params": processing_params
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Failed to initialize run: {e}")
        import traceback
        logger.error(f"❌ API: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize run: {str(e)}")


@router.get("/health")
async def dossier_runs_health_check():
    """Simple health check for dossier runs service"""
    return {"status": "healthy", "service": "dossier-runs"}


@router.post("/reconcile/{dossier_id}")
async def reconcile_dossier_runs(dossier_id: str):
    """
    Reconcile all runs in a dossier:
    - If all expected drafts exist for a run, mark it completed.
    - Log concise per-run status transitions.
    """
    try:
        from pathlib import Path as _Path
        backend_dir = _Path(__file__).resolve().parents[3]
        runs_root = backend_dir / "dossiers_data" / "views" / "transcriptions" / str(dossier_id)

        if not runs_root.exists():
            return {"success": True, "dossier_id": dossier_id, "reconciled": 0}

        reconciled = 0
        for run_dir in runs_root.iterdir():
            if not run_dir.is_dir():
                continue
            run_id = run_dir.name
            run_file = run_dir / "run.json"
            raw_dir = run_dir / "raw"
            if not run_file.exists() or not raw_dir.exists():
                continue

            try:
                import json as _json
                with open(run_file, 'r', encoding='utf-8') as f:
                    run_meta = _json.load(f)
                redundancy_count = int(run_meta.get('redundancy_count') or 0)
                current_status = run_meta.get('status')

                # Count versioned drafts that are non-placeholder (with real content)
                present = 0
                for i in range(1, redundancy_count + 1):
                    vf = raw_dir / f"{run_id}_v{i}.json"
                    if not vf.exists():
                        continue
                    try:
                        import json as _json2
                        with open(vf, 'r', encoding='utf-8') as _vf:
                            _content = _json2.load(_vf)
                        if isinstance(_content, dict) and not _content.get('_placeholder', False):
                            # Consider it present only if there is meaningful text
                            _txt = ''
                            if isinstance(_content.get('sections'), list):
                                _txt = " ".join(str(s.get('body','')) for s in _content['sections'] if isinstance(s, dict))
                            elif 'extracted_text' in _content:
                                _txt = str(_content.get('extracted_text',''))
                            elif 'text' in _content:
                                _txt = str(_content.get('text',''))
                            if _txt and _txt.strip():
                                present += 1
                    except Exception:
                        continue

                if redundancy_count > 0 and present >= redundancy_count and current_status != 'completed':
                    management_service.update_run_metadata(
                        dossier_id=dossier_id,
                        transcription_id=run_id,
                        updates={
                            "status": "completed",
                            "timestamps": {"finished_at": datetime.now().isoformat()}
                        }
                    )
                    reconciled += 1
            except Exception:
                continue

        return {"success": True, "dossier_id": dossier_id, "reconciled": reconciled}
    except Exception as e:
        logger.error(f"❌ Failed to reconcile dossier {dossier_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))