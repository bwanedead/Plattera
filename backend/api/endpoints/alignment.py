"""
Alignment API Endpoints
======================

Dedicated endpoints for BioPython-based alignment engine functionality.
Handles legal document draft alignment, confidence analysis, and visualization.
"""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import json
import numpy as np
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime

# ABSOLUTE IMPORTS ONLY - never relative imports
from alignment.section_normalizer import SectionNormalizer
from alignment.biopython_engine import BioPythonAlignmentEngine
from alignment.alignment_utils import check_dependencies
from services.alignment_service import AlignmentService
from services.dossier.view_service import DossierViewService

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic Models
class JsonDraftBlock(BaseModel):
    """Model for a single block within a JSON draft"""
    id: str
    text: str


class JsonDraft(BaseModel):
    """Model for a single JSON draft"""
    draft_id: str
    blocks: List[JsonDraftBlock]


class AlignmentRequest(BaseModel):
    """Request model for BioPython alignment processing"""
    drafts: List[JsonDraft]
    generate_visualization: bool = True
    consensus_strategy: str = "highest_confidence"
    # Optional: when provided, backend will persist alignment consensus to dossier
    transcription_id: Optional[str] = None
    dossier_id: Optional[str] = None
    consensus_draft_id: Optional[str] = None


class AlignmentResponse(BaseModel):
    """Response model for BioPython alignment results"""
    success: bool
    processing_time: float
    summary: Dict[str, Any]
    consensus_text: Optional[str] = None
    visualization_html: Optional[str] = None
    error: Optional[str] = None
    per_draft_alignment_mapping: Optional[Dict[str, Any]] = None
    confidence_results: Optional[Dict[str, Any]] = None
    alignment_results: Optional[Dict[str, Any]] = None


class VisualizationRequest(BaseModel):
    """Request model for generating visualization from redundancy analysis data"""
    redundancy_analysis: Dict[str, Any]
    extracted_text: str


# Endpoints
@router.post("/align-drafts", response_model=AlignmentResponse)
async def align_legal_drafts(request: AlignmentRequest):
    """
    BioPython-based alignment of multiple legal document drafts
    
    Performs consistency-based multiple sequence alignment to identify differences
    and generate confidence scores for legal document transcriptions.
    """
    logger.info(f"🧬 BIOPYTHON ALIGNMENT REQUEST ► Processing {len(request.drafts)} drafts")
    
    # Guard: alignment requires at least two drafts
    if len(request.drafts) < 2:
        raise HTTPException(status_code=400, detail="At least 2 drafts are required for alignment")
    
    try:
        # Convert Pydantic models to dictionaries
        draft_jsons = []
        for draft in request.drafts:
            draft_dict = {
                "draft_id": draft.draft_id,
                "blocks": [
                    {"id": block.id, "text": block.text}
                    for block in draft.blocks
                ]
            }
            draft_jsons.append(draft_dict)
        
        # Use the service layer for processing
        alignment_service = AlignmentService()
        results = alignment_service.process_alignment_request(
            draft_jsons=draft_jsons,
            generate_visualization=request.generate_visualization,
            consensus_strategy=request.consensus_strategy,
            save_context={
                "transcription_id": request.transcription_id or "",
                "dossier_id": request.dossier_id or "",
                "consensus_draft_id": request.consensus_draft_id or ""
            } if (request.transcription_id) else None
        )
        
        if not results['success']:
            logger.error(f"❌ Alignment processing failed: {results.get('error', 'Unknown error')}")
            return AlignmentResponse(
                success=False,
                processing_time=results.get('processing_time', 0.0),
                summary=results.get('summary', {}),
                error=results.get('error', 'Alignment failed')
            )
        
        logger.info(f"✅ BioPython alignment completed successfully in {results['processing_time']:.2f}s")
        
        # Persist alignment consensus draft if requested and available (structured path only)
        try:
            transcription_id = getattr(request, 'transcription_id', None)
            dossier_id = getattr(request, 'dossier_id', None)
            consensus_text = results.get('consensus_text')
            if transcription_id and isinstance(transcription_id, str) and transcription_id.strip() and consensus_text:
                backend_dir = Path(__file__).resolve().parents[2]
                transcriptions_root = backend_dir / "dossiers_data" / "views" / "transcriptions"

                if dossier_id:
                    run_dir = transcriptions_root / str(dossier_id) / str(transcription_id)
                else:
                    run_dir = transcriptions_root / "_unassigned" / str(transcription_id)

                consensus_dir = run_dir / "consensus"
                consensus_dir.mkdir(parents=True, exist_ok=True)
                consensus_file = consensus_dir / f"alignment_{transcription_id}.json"

                payload = {
                    "type": "alignment_consensus",
                    "model": "biopython_alignment",
                    "strategy": request.consensus_strategy,
                    "title": "Alignment Consensus",
                    "text": consensus_text,
                    "source_drafts": len(request.drafts),
                    "tokens_used": 0,
                    "created_at": datetime.now().isoformat(),
                    "metadata": {
                        "alignment_summary": results.get('summary', {}),
                        "processing_time": results.get('processing_time', 0)
                    }
                }
                try:
                    with open(consensus_file, 'w', encoding='utf-8') as cf:
                        json.dump(payload, cf, indent=2, ensure_ascii=False)
                    logger.info(f"💾 Persisted alignment consensus JSON: {consensus_file}")
                except Exception as se:
                    logger.warning(f"⚠️ Failed to persist alignment consensus JSON: {se}")
        except Exception as persist_err:
            logger.warning(f"⚠️ Consensus persistence step failed (non-critical): {persist_err}")

        return AlignmentResponse(
            success=True,
            processing_time=results['processing_time'],
            summary=results['summary'],
            consensus_text=results.get('consensus_text'),
            visualization_html=results.get('visualization_html'),
            per_draft_alignment_mapping=results.get('per_draft_alignment_mapping'),
            confidence_results=results.get('confidence_results'),
            alignment_results=results.get('alignment_results')
        )
        
    except Exception as e:
        logger.error(f"❌ Unexpected error in BioPython alignment: {e}")
        logger.exception("Full traceback:")
        return AlignmentResponse(
            success=False,
            processing_time=0.0,
            summary={},
            error=f"Alignment processing failed: {str(e)}"
        )


# ---------------- New: Backend-driven alignment by IDs ----------------
class AlignmentByIdsRequest(BaseModel):
    dossier_id: str
    transcription_id: str
    draft_indices: List[int]  # 1-based indices
    version_policy: str = "prefer_v2_else_v1"
    exclude_alignment_versions: bool = True


@router.post("/align-drafts/by-ids", response_model=AlignmentResponse)
async def align_drafts_by_ids(req: AlignmentByIdsRequest):
    """
    Load raw drafts directly from the dossier (v2 if present, else v1) and run alignment.
    """
    logger.info(
        f"🧬 ALIGN BY IDS ► dossier={req.dossier_id} tid={req.transcription_id} indices={req.draft_indices}"
    )

    if not req.draft_indices or len(req.draft_indices) < 2:
        raise HTTPException(status_code=400, detail="At least 2 drafts are required for alignment")

    view = DossierViewService()
    draft_jsons: List[Dict[str, Any]] = []

    for n in req.draft_indices:
        base = f"{req.transcription_id}_v{n}"
        if req.version_policy == "prefer_v1_else_v2":
            candidates = [f"{base}_v1", f"{base}_v2"]
        else:
            candidates = [f"{base}_v2", f"{base}_v1"]

        content = None
        for did in candidates:
            content = view._load_transcription_content_scoped(did, req.dossier_id)
            if content:
                break

        if not content:
            logger.warning(f"⚠️ Missing content for draft index {n}; skipping")
            continue

        # Normalize to sectioned JSON expected by pipeline
        if isinstance(content, dict) and isinstance(content.get("sections"), list):
            draft_jsons.append(content)
        elif isinstance(content, dict) and isinstance(content.get("blocks"), list):
            blocks = content.get("blocks")
            sections = [{"id": i + 1, "body": str(b.get("text", ""))} for i, b in enumerate(blocks) if isinstance(b, dict)]
            draft_jsons.append({"documentId": content.get("documentId", "raw"), "sections": sections})
        else:
            # Fallback into single-section text (should be rare)
            try:
                text = str(content.get("text", "")) if isinstance(content, dict) else str(content)
            except Exception:
                text = ""
            draft_jsons.append({"documentId": "raw", "sections": [{"id": 1, "body": text}]})

    if len(draft_jsons) < 2:
        return AlignmentResponse(
            success=False,
            processing_time=0.0,
            summary={},
            error="At least 2 non-empty drafts are required for alignment",
        )

    alignment_service = AlignmentService()
    results = alignment_service.process_alignment_request(
        draft_jsons=draft_jsons,
        generate_visualization=True,
        consensus_strategy="highest_confidence",
        save_context={
            "transcription_id": req.transcription_id,
            "dossier_id": req.dossier_id,
        },
    )

    if not results.get("success"):
        logger.error(f"❌ Alignment processing failed: {results.get('error')}")
        return AlignmentResponse(
            success=False,
            processing_time=results.get("processing_time", 0.0),
            summary=results.get("summary", {}),
            error=results.get("error", "Alignment failed"),
        )

    logger.info("✅ Align-by-ids completed successfully")
    return AlignmentResponse(
        success=True,
        processing_time=results.get("processing_time", 0.0),
        summary=results.get("summary", {}),
        consensus_text=results.get("consensus_text"),
        visualization_html=results.get("visualization_html"),
        per_draft_alignment_mapping=results.get("per_draft_alignment_mapping"),
        confidence_results=results.get("confidence_results"),
        alignment_results=results.get("alignment_results"),
    )


@router.post("/generate-visualization")
@router.post("/generate-visualization/")
async def generate_visualization_from_redundancy(request: VisualizationRequest):
    """
    Generate BioPython alignment visualization from existing redundancy analysis data
    
    This endpoint takes redundancy analysis data from your existing processing results
    and generates our new BioPython alignment visualization.
    """
    logger.info("🎨 VISUALIZATION REQUEST ► Generating BioPython alignment visualization")
    
    try:
        # Import BioPython engine
        from alignment import BioPythonAlignmentEngine, check_dependencies
        
        # Check dependencies
        dependencies_available, missing_packages = check_dependencies()
        if not dependencies_available:
            logger.error(f"❌ Missing BioPython dependencies: {missing_packages}")
            return Response(
                content=f"<html><body><h1>Missing Dependencies</h1><p>Install: pip install {' '.join(missing_packages)}</p></body></html>",
                media_type="text/html"
            )
        
        # Convert redundancy analysis to draft format
        draft_jsons = []
        redundancy_data = request.redundancy_analysis
        
        # Extract individual drafts from redundancy analysis
        individual_results = redundancy_data.get('individual_results', [])
        for i, result in enumerate(individual_results):
            if result.get('success', False):
                draft_jsons.append({
                    "draft_id": f"Draft_{i+1}",
                    "blocks": [
                        {"id": "legal_text", "text": result.get('text', '')}
                    ]
                })
        
        # If we have fewer than 2 drafts, create a demo
        if len(draft_jsons) < 2:
            logger.info("🎭 Creating demo data for visualization")
            draft_jsons = [
                {
                    "draft_id": "Draft_1",
                    "blocks": [
                        {"id": "legal_text", "text": request.extracted_text}
                    ]
                },
                {
                    "draft_id": "Draft_2", 
                    "blocks": [
                        {"id": "legal_text", "text": request.extracted_text.replace("the", "this").replace("and", "plus")}
                    ]
                }
            ]
        
        # Initialize BioPython engine
        engine = BioPythonAlignmentEngine()
        
        # Perform alignment
        results = engine.align_drafts(draft_jsons, generate_visualization=True)
        
        if not results['success']:
            logger.error(f"❌ BioPython alignment failed: {results.get('error', 'Unknown error')}")
            return Response(
                content=f"<html><body><h1>Alignment Failed</h1><p>{results.get('error', 'Unknown error')}</p></body></html>",
                media_type="text/html"
            )
        
        # Return the HTML visualization
        html_content = results.get('visualization_html', '<html><body><h1>No visualization generated</h1></body></html>')
        
        logger.info(f"✅ BioPython visualization generated successfully")
        
        return Response(content=html_content, media_type="text/html")
        
    except ImportError as e:
        logger.error(f"❌ BioPython alignment module not available: {e}")
        return Response(
            content=f"<html><body><h1>BioPython Not Available</h1><p>{e}</p></body></html>",
            media_type="text/html"
        )
    except Exception as e:
        logger.error(f"❌ Unexpected error in visualization generation: {e}")
        logger.exception("Full traceback:")
        return Response(
            content=f"<html><body><h1>Visualization Error</h1><p>{str(e)}</p></body></html>",
            media_type="text/html"
        )


@router.get("/align-drafts/status")
async def get_alignment_engine_status():
    """
    Get status and availability of the BioPython alignment engine
    
    Returns:
        Dict with engine status, dependencies, and capabilities
    """
    try:
        from alignment import check_biopython_engine_status
        
        status = check_biopython_engine_status()
        return status
        
    except ImportError:
        return {
            'status': 'unavailable',
            'error': 'BioPython alignment engine not installed'
        }
    except Exception as e:
        logger.error(f"❌ Error checking alignment engine status: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }


@router.post("/align-drafts/test")
async def test_alignment_engine():
    """
    Test the BioPython alignment engine with sample data
    
    Returns:
        Dict with test results and sample alignment data
    """
    try:
        from alignment import test_biopython_engine
        
        logger.info("🧪 Testing BioPython alignment engine...")
        results = test_biopython_engine()
        
        if results['success']:
            logger.info("✅ BioPython alignment engine test passed")
        else:
            logger.error(f"❌ BioPython alignment engine test failed: {results.get('error', 'Unknown')}")
        
        return results
        
    except ImportError as e:
        logger.error(f"❌ BioPython alignment engine not available for testing: {e}")
        return {
            'success': False,
            'error': f'BioPython alignment engine not available: {e}'
        }
    except Exception as e:
        logger.error(f"❌ Unexpected error in alignment engine testing: {e}")
        logger.exception("Full traceback:")
        return {
            'success': False,
            'error': f'Alignment engine test failed: {str(e)}'
        }


@router.get("/test-visualization")
async def test_visualization_endpoint():
    """
    Simple test endpoint to verify routing is working
    """
    html_content = """
    <html>
    <head>
        <title>BioPython Visualization Test</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
            .test-success { color: green; font-size: 24px; }
            .info { background: white; padding: 15px; border-radius: 8px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <h1 class="test-success">✅ BioPython Visualization Endpoint Working!</h1>
        <div class="info">
            <h3>🎉 Success!</h3>
            <p>The BioPython alignment visualization endpoint is properly routed and accessible.</p>
            <p><strong>Endpoint:</strong> /api/alignment/test-visualization</p>
            <p><strong>Status:</strong> Routing ✅ | HTML Generation ✅</p>
        </div>
        <div class="info">
            <h3>🔥 What's Next?</h3>
            <p>Now you can test the full visualization with real data using the fire button!</p>
        </div>
    </body>
    </html>
    """
    
    return Response(content=html_content, media_type="text/html") 


def debug_log_complex_dict(data, path=""):
    """Recursively log types in a complex dictionary to find non-serializable data."""
    logger = logging.getLogger(__name__)
    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{path}.{k}" if path else k
            debug_log_complex_dict(v, new_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}[{i}]"
            debug_log_complex_dict(item, new_path)
    else:
        # Log the type of every leaf node for thoroughness
        logger.info(f"DEBUG_TYPE: Path='{path}', Type='{type(data).__name__}'")

# Custom JSON encoder to handle NumPy types
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj) 