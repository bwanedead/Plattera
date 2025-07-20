"""
Bounding Box Detection API Endpoints
===================================

Provides clean, organized endpoints for line detection and word segmentation
using OpenCV and LLM vision APIs. Maintains separation of concerns and
follows established API patterns.
"""

import tempfile
import os
import base64
import json
import time
from typing import Dict, Any, Optional
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

# Import detection modules
from alignment.bounding_box.line_detector import detect_text_lines_with_ruler
from alignment.bounding_box.box_detector import detect_word_bounding_boxes

# Import LLM service
from services.llm.openai import OpenAIService

# Import prompts
from prompts.bounding_box import get_word_segmentation_prompt

# Create router
router = APIRouter()

# Initialize LLM service
llm_service = OpenAIService()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _save_uploaded_file(upload_file: UploadFile) -> str:
    """Save uploaded file to temporary location and return path."""
    try:
        # Create temporary file with proper extension
        suffix = Path(upload_file.filename).suffix if upload_file.filename else '.jpg'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            content = upload_file.file.read()
            temp_file.write(content)
            return temp_file.name
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to save uploaded file: {str(e)}")


def _cleanup_temp_file(file_path: str) -> None:
    """Clean up temporary file."""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception:
        pass  # Ignore cleanup errors


def _format_lines_for_api(lines_data: Dict[str, Any]) -> list:
    """Format line detection results for API response."""
    formatted_lines = []
    for i, (y1, y2) in enumerate(lines_data.get('lines', [])):
        formatted_lines.append({
            'line_index': i,
            'bounds': {
                'y1': y1,
                'y2': y2,
                'x1': 0,  # Full width
                'x2': 1000  # Placeholder - will be updated with actual image width
            },
            'confidence': 0.9  # Default confidence for OpenCV detection
        })
    return formatted_lines


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/detect-lines")
async def detect_lines(
    image: UploadFile = File(..., description="Image file for line detection")
) -> Dict[str, Any]:
    """
    Detect text lines in an image using OpenCV.
    
    Returns line boundaries and processing statistics.
    """
    start_time = time.time()
    temp_file_path = None
    
    try:
        # Validate file
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Save uploaded file
        temp_file_path = _save_uploaded_file(image)
        
        # Detect lines using OpenCV
        lines_result = detect_text_lines_with_ruler(temp_file_path, debug_mode=False)
        
        # Format response
        formatted_lines = _format_lines_for_api(lines_result)
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "success": True,
            "lines": formatted_lines,
            "processing_time": processing_time,
            "total_lines": len(formatted_lines),
            "debug_info": {
                "image_path": temp_file_path,
                "ruler_positions": lines_result.get('ruler_positions', []),
                "cropped_region": lines_result.get('cropped_region', None)
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "lines": [],
            "processing_time": (time.time() - start_time) * 1000,
            "total_lines": 0
        }
    finally:
        if temp_file_path:
            _cleanup_temp_file(temp_file_path)


@router.post("/detect-words")
async def detect_words(
    image: UploadFile = File(..., description="Image file for word detection"),
    lines: str = Form(..., description="JSON string of detected lines"),
    model: str = Form("gpt-4o", description="LLM model to use"),
    complexity: str = Form("standard", description="Detection complexity level")
) -> Dict[str, Any]:
    """
    Detect words within detected lines using LLM vision API.
    
    Requires pre-detected lines from /detect-lines endpoint.
    """
    start_time = time.time()
    
    try:
        # Validate file
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Parse lines data
        try:
            lines_data = json.loads(lines)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid lines data format")
        
        # Read image data for LLM
        image_data = await image.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        # Get appropriate prompt based on complexity
        prompt = get_word_segmentation_prompt(complexity, model)
        
        # Call LLM for word segmentation
        llm_response = await llm_service.call_vision(
            prompt=prompt,
            image_data=image_base64,
            model=model,
            max_tokens=4000
        )
        
        # Parse LLM response
        try:
            words_data = json.loads(llm_response['content'])
        except (json.JSONDecodeError, KeyError):
            # Try to extract JSON from response if it's wrapped
            import re
            content = llm_response.get('content', '')
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                words_data = json.loads(json_match.group())
            else:
                raise ValueError("Invalid JSON response from LLM")
        
        # Format response
        processing_time = (time.time() - start_time) * 1000
        total_words = sum(len(line.get('words', [])) for line in words_data.get('lines', []))
        
        return {
            "success": True,
            "words_by_line": words_data.get('lines', []),
            "total_words": total_words,
            "processing_time": processing_time,
            "model_used": model,
            "complexity_level": complexity,
            "tokens_used": llm_response.get('tokens_used', 0)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "words_by_line": [],
            "total_words": 0,
            "processing_time": (time.time() - start_time) * 1000
        }


@router.post("/pipeline")
async def run_bounding_box_pipeline(
    image: UploadFile = File(..., description="Image file for complete bounding box analysis"),
    model: str = Form("gpt-4o", description="LLM model to use"),
    complexity: str = Form("standard", description="Detection complexity level")
) -> Dict[str, Any]:
    """
    Run complete bounding box pipeline: line detection + word segmentation.
    
    This is the main endpoint for full bounding box analysis.
    """
    start_time = time.time()
    temp_file_path = None
    
    try:
        # Validate file
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Save uploaded file
        temp_file_path = _save_uploaded_file(image)
        
        # Stage 1: Line detection
        line_result = await detect_lines(image)
        
        if not line_result["success"]:
            return {
                "success": False,
                "error": f"Line detection failed: {line_result.get('error', 'Unknown error')}",
                "lines": [],
                "words_by_line": [],
                "total_processing_time": (time.time() - start_time) * 1000,
                "total_words": 0
            }
        
        # Stage 2: Word segmentation
        # Reset file position for second read
        await image.seek(0)
        
        word_result = await detect_words(
            image=image,
            lines=json.dumps(line_result["lines"]),
            model=model,
            complexity=complexity
        )
        
        if not word_result["success"]:
            return {
                "success": False,
                "error": f"Word detection failed: {word_result.get('error', 'Unknown error')}",
                "lines": line_result["lines"],
                "words_by_line": [],
                "total_processing_time": (time.time() - start_time) * 1000,
                "total_words": 0
            }
        
        # Calculate total processing time
        total_processing_time = (time.time() - start_time) * 1000
        
        return {
            "success": True,
            "lines": line_result["lines"],
            "words_by_line": word_result["words_by_line"],
            "total_processing_time": total_processing_time,
            "total_words": word_result["total_words"],
            "stage_times": {
                "line_detection": line_result["processing_time"],
                "word_segmentation": word_result["processing_time"]
            },
            "model_used": model,
            "complexity_level": complexity,
            "tokens_used": word_result.get("tokens_used", 0)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "lines": [],
            "words_by_line": [],
            "total_processing_time": (time.time() - start_time) * 1000,
            "total_words": 0
        }
    finally:
        if temp_file_path:
            _cleanup_temp_file(temp_file_path)


@router.get("/status")
async def get_bounding_box_status() -> Dict[str, Any]:
    """
    Get status of bounding box detection services.
    
    Returns service availability and endpoint information.
    """
    try:
        # Check OpenCV availability
        import cv2
        opencv_version = cv2.__version__
        opencv_status = "available"
    except ImportError:
        opencv_version = "not installed"
        opencv_status = "unavailable"
    
    # Check LLM service availability
    llm_status = "available" if llm_service.is_available() else "unavailable"
    
    return {
        "success": True,
        "services": {
            "opencv": {
                "status": opencv_status,
                "version": opencv_version
            },
            "llm_service": {
                "status": llm_status,
                "provider": llm_service.name
            }
        },
        "endpoints": {
            "detect_lines": "/api/bounding-boxes/detect-lines",
            "detect_words": "/api/bounding-boxes/detect-words",
            "pipeline": "/api/bounding-boxes/pipeline",
            "status": "/api/bounding-boxes/status"
        },
        "complexity_levels": ["simple", "standard", "enhanced"],
        "supported_models": list(llm_service.models.keys())
    } 