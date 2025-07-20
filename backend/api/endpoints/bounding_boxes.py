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
import cv2
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
    temp_file_path = None
    
    try:
        # Validate file
        if not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Parse lines data
        try:
            lines_data = json.loads(lines)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid lines data format")
        
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            image_data = await image.read()
            temp_file.write(image_data)
            temp_file_path = temp_file.name
        
        try:
            # Get the image with line overlays from line detection
            from alignment.bounding_box.line_detector import detect_text_lines_with_ruler
            
            # Run line detection to get the overlay image
            line_result = detect_text_lines_with_ruler(temp_file_path, debug_mode=False)
            overlay_image = line_result.get('overlay_image')
            
            if overlay_image is None:
                raise ValueError("Could not generate overlay image")
            
            # Get the number of lines detected
            num_lines = len(line_result.get('lines', []))
            print(f"📏 Number of lines detected: {num_lines}")
            
            # Save overlay image to temporary file
            overlay_path = temp_file_path.replace('.jpg', '_overlay.jpg')
            cv2.imwrite(overlay_path, overlay_image)
            
            # Read overlay image for LLM
            with open(overlay_path, 'rb') as f:
                overlay_data = f.read()
            
            image_base64 = base64.b64encode(overlay_data).decode('utf-8')
            
            # Get appropriate prompt based on complexity and number of lines
            prompt = get_word_segmentation_prompt(complexity, model, num_lines)
            
            print(f"🤖 Calling LLM with model: {model}")
            print(f"📝 Prompt length: {len(prompt)} characters")
            print(f"️  Image size: {len(image_base64)} base64 characters")
            print(f"📁 Using overlay image: {overlay_path}")
            print(f"📏 Expecting exactly {num_lines} lines in response")
            
            # Call LLM for word segmentation (NOT async)
            llm_response = llm_service.call_vision(
                prompt=prompt,
                image_data=image_base64,
                model=model,
                max_tokens=8000  # Increased from 4000 to handle longer responses
            )
            
            print(f"🤖 LLM Response received: {llm_response.get('success', False)}")
            print(f" LLM Response keys: {list(llm_response.keys())}")
            
            # Check if LLM call was successful
            if not llm_response.get('success', False):
                print(f"❌ LLM call failed: {llm_response.get('error', 'Unknown error')}")
                return {
                    "success": False,
                    "error": f"LLM call failed: {llm_response.get('error', 'Unknown error')}",
                    "words_by_line": [],
                    "total_words": 0,
                    "processing_time": (time.time() - start_time) * 1000
                }
            
            # Get the content from LLM response (it's 'text', not 'content')
            content = llm_response.get('text', '')
            print(f" LLM Content length: {len(content)} characters")
            print(f"📄 LLM Content preview: {content[:200]}...")
            
            # Parse LLM response
            try:
                words_data = json.loads(content)
                print(f"✅ Successfully parsed JSON from LLM response")
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                print(f"📄 Full LLM content: {content}")
                
                # Try to extract JSON from response if it's wrapped
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    try:
                        words_data = json.loads(json_match.group())
                        print(f"✅ Successfully extracted JSON using regex")
                    except json.JSONDecodeError as e2:
                        print(f"❌ Regex extraction also failed: {e2}")
                        raise ValueError(f"Invalid JSON response from LLM. Content: {content[:500]}...")
                else:
                    print(f"❌ No JSON pattern found in response")
                    raise ValueError(f"Invalid JSON response from LLM. Content: {content[:500]}...")
            
            # Keep the simple format from LLM - no conversion needed
            words_by_line = words_data.get('lines', [])
            
            # Calculate total words
            total_words = sum(len(line.get('words', [])) for line in words_by_line)
            
            print(f"✅ Word detection successful: {total_words} words found")
            
            return {
                "success": True,
                "words_by_line": words_by_line,
                "total_words": total_words,
                "processing_time": (time.time() - start_time) * 1000,
                "model_used": model,
                "complexity_level": complexity,
                "tokens_used": llm_response.get('tokens_used', 0),
                "overlay_image_path": overlay_path  # Return path to overlay image
            }
            
        finally:
            # Clean up temporary files
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            if 'overlay_path' in locals() and os.path.exists(overlay_path):
                # Don't delete overlay_path yet - we need it for visualization
                pass
        
    except Exception as e:
        print(f"❌ Exception in word detection: {e}")
        import traceback
        traceback.print_exc()
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