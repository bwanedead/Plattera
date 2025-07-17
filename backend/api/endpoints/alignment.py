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
import asyncio
from fastapi.responses import JSONResponse

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
    image_path: Optional[str] = None  # Optional image path for bounding box detection


class BoundingBoxRequest(BaseModel):
    """Request model for bounding box detection"""
    image_path: str


class BoundingBoxResponse(BaseModel):
    """Response model for bounding box detection results"""
    success: bool
    processing_time: float
    bounding_boxes: List[Dict[str, Any]]
    stats: Dict[str, Any]
    error: Optional[str] = None


class AlignmentResponse(BaseModel):
    """Response model for BioPython alignment results"""
    success: bool
    processing_time: float
    summary: Dict[str, Any]
    consensus_text: Optional[str] = None
    visualization_html: Optional[str] = None
    error: Optional[str] = None
    per_draft_alignment_mapping: Optional[Dict[str, Any]] = None
    bounding_boxes: Optional[List[Dict[str, Any]]] = None  # Optional bounding box results
    bounding_box_stats: Optional[Dict[str, Any]] = None  # Optional bounding box statistics


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
    
    try:
        # Import BioPython engine
        from alignment import BioPythonAlignmentEngine, check_dependencies
        
        # Check dependencies
        dependencies_available, missing_packages = check_dependencies()
        if not dependencies_available:
            logger.error(f"❌ Missing BioPython dependencies: {missing_packages}")
            return AlignmentResponse(
                success=False,
                processing_time=0.0,
                summary={},
                error=f"Missing required dependencies: {', '.join(missing_packages)}. Install with: pip install {' '.join(missing_packages)}"
            )
        
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
        
        # Initialize BioPython engine
        engine = BioPythonAlignmentEngine()
        
        # Start parallel bounding box detection if image path provided
        bbox_task = None
        if request.image_path:
            try:
                from alignment.bounding_box import detect_with_stats_async
                logger.info(f"📦 Starting parallel bounding box detection for: {request.image_path}")
                bbox_task = asyncio.create_task(detect_with_stats_async(request.image_path))
            except ImportError as e:
                logger.warning(f"⚠️ Bounding box detection not available: {e}")
        
        # Perform alignment
        results = engine.align_drafts(
            draft_jsons, 
            generate_visualization=request.generate_visualization
        )
        
        if not results['success']:
            logger.error(f"❌ BioPython alignment failed: {results.get('error', 'Unknown error')}")
            return AlignmentResponse(
                success=False,
                processing_time=results.get('processing_time', 0.0),
                summary=results['summary'],
                error=results.get('error', 'Alignment failed')
            )
        
        # Generate consensus text if requested
        consensus_text = None
        if request.consensus_strategy:
            try:
                consensus_text = engine.generate_consensus_text(
                    results['alignment_results'],
                    results['confidence_results'],
                    consensus_strategy=request.consensus_strategy
                )
            except Exception as e:
                logger.warning(f"⚠️ Consensus generation failed: {e}")
        
        logger.info(f"✅ BioPython alignment completed successfully in {results['processing_time']:.2f}s")
        
        # Collect bounding box results if task was started
        bbox_results = None
        bbox_stats = None
        if bbox_task:
            try:
                logger.info("📦 Waiting for parallel bounding box detection to complete...")
                logger.info(f"📦 Task status: done={bbox_task.done()}, cancelled={bbox_task.cancelled()}")
                
                bbox_data = await bbox_task
                logger.info(f"📦 Received bbox_data type: {type(bbox_data)}")
                logger.info(f"📦 Received bbox_data keys: {list(bbox_data.keys()) if isinstance(bbox_data, dict) else 'Not a dict'}")
                
                bbox_results = bbox_data['bounding_boxes']
                bbox_stats = bbox_data['stats']
                logger.info(f"✅ Bounding box detection completed - Found {len(bbox_results)} boxes")
                logger.info(f"📦 Stats: {bbox_stats}")
            except Exception as e:
                logger.error(f"⚠️ Bounding box detection failed: {e}")
                logger.exception("Full bounding box task exception:")
        else:
            logger.info("📦 No bounding box task was started (image_path not provided)")
        
        logger.info("Alignment API response keys: %s", list(results.keys()))
        if results.get('per_draft_alignment_mapping'):
            sample_block = list(results['per_draft_alignment_mapping'].keys())[0]
            sample_draft = results['per_draft_alignment_mapping'][sample_block][0]
            mapping_length = len(sample_draft.get('original_to_alignment', []))
            # Removed repetitive log message that was spamming the terminal
        
        return AlignmentResponse(
            success=True,
            processing_time=results['processing_time'],
            summary=results['summary'],
            consensus_text=consensus_text,
            visualization_html=results['visualization_html'],
            per_draft_alignment_mapping=results.get('per_draft_alignment_mapping'),
            bounding_boxes=bbox_results,
            bounding_box_stats=bbox_stats
        )
        
    except ImportError as e:
        logger.error(f"❌ BioPython alignment module not available: {e}")
        return AlignmentResponse(
            success=False,
            processing_time=0.0,
            summary={},
            error=f"BioPython alignment engine not available: {e}"
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


@router.post("/detect-bounding-boxes", response_model=BoundingBoxResponse)
async def detect_bounding_boxes(request: BoundingBoxRequest):
    """
    Detect word-level bounding boxes in a scanned document image.
    
    This endpoint provides standalone bounding box detection functionality
    using OpenCV for word-level region identification.
    """
    logger.info(f"📦 BOUNDING BOX DETECTION ► Processing image: {request.image_path}")
    
    import time
    start_time = time.time()
    
    try:
        # Import bounding box detection
        from alignment.bounding_box import detect_with_stats_async
        
        # Perform async detection with statistics
        result = await detect_with_stats_async(request.image_path)
        
        processing_time = time.time() - start_time
        
        logger.info(f"✅ Bounding box detection completed in {processing_time:.2f}s - Found {len(result['bounding_boxes'])} boxes")
        
        return BoundingBoxResponse(
            success=True,
            processing_time=processing_time,
            bounding_boxes=result['bounding_boxes'],
            stats=result['stats']
        )
        
    except FileNotFoundError as e:
        logger.error(f"❌ Image file not found: {e}")
        return BoundingBoxResponse(
            success=False,
            processing_time=time.time() - start_time,
            bounding_boxes=[],
            stats={},
            error=f"Image file not found: {str(e)}"
        )
    except ImportError as e:
        logger.error(f"❌ Bounding box detection module not available: {e}")
        return BoundingBoxResponse(
            success=False,
            processing_time=time.time() - start_time,
            bounding_boxes=[],
            stats={},
            error=f"Bounding box detection not available: {e}. Make sure opencv-python is installed."
        )
    except Exception as e:
        logger.error(f"❌ Unexpected error in bounding box detection: {e}")
        logger.exception("Full traceback:")
        return BoundingBoxResponse(
            success=False,
            processing_time=time.time() - start_time,
            bounding_boxes=[],
            stats={},
            error=f"Bounding box detection failed: {str(e)}"
        ) 