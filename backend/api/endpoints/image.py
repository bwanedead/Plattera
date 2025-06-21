"""
Image Processing API Endpoints
Handles image upload, processing, and text extraction
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import os
from pathlib import Path

from core.image_processor import ImageProcessor

# Initialize router
router = APIRouter(tags=["image"])

# Initialize image processor
image_processor = ImageProcessor()

# Request/Response models
class ImageProcessRequest(BaseModel):
    extraction_mode: str = "legal_document"
    cleanup_after: bool = True

class ImageProcessResponse(BaseModel):
    status: str
    extracted_text: Optional[str] = None
    file_info: Optional[dict] = None
    processing_info: Optional[dict] = None
    pipeline_stats: Optional[dict] = None
    error: Optional[str] = None

class ProcessingEstimateResponse(BaseModel):
    status: str
    file_info: Optional[dict] = None
    processing_needed: Optional[bool] = None
    estimated_cost_usd: Optional[float] = None
    supported_extraction_modes: Optional[dict] = None
    error: Optional[str] = None

@router.post("/upload", response_model=dict)
async def upload_image(file: UploadFile = File(...)):
    """
    Upload an image file for processing
    
    Accepts: JPEG, PNG, WEBP, PDF files up to 20MB
    Returns: Upload confirmation with file info
    """
    try:
        # Check file size (20MB limit)
        MAX_SIZE = 20 * 1024 * 1024  # 20MB
        
        # Read file content
        content = await file.read()
        
        if len(content) > MAX_SIZE:
            raise HTTPException(
                status_code=413, 
                detail=f"File too large: {len(content) / (1024*1024):.1f}MB (max 20MB)"
            )
        
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        # Save uploaded file
        success, error, saved_path = image_processor.save_uploaded_file(content, file.filename)
        
        if not success:
            raise HTTPException(status_code=500, detail=error)
        
        # Get file info and processing estimate
        estimate_success, estimate_error, estimate_info = image_processor.get_processing_estimate(saved_path)
        
        response_data = {
            "status": "uploaded",
            "filename": file.filename,
            "saved_path": saved_path,
            "size_mb": len(content) / (1024*1024),
            "content_type": file.content_type
        }
        
        if estimate_success:
            response_data["processing_estimate"] = estimate_info
        else:
            response_data["estimate_error"] = estimate_error
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/process", response_model=ImageProcessResponse)
async def process_image(
    file: UploadFile = File(...),
    extraction_mode: str = Form("legal_document"),
    cleanup_after: bool = Form(True)
):
    """
    Upload and process image in one step
    
    Accepts: Image file + processing parameters
    Returns: Extracted text and processing details
    """
    try:
        # First upload the file
        content = await file.read()
        
        # Check file size
        MAX_SIZE = 20 * 1024 * 1024  # 20MB
        if len(content) > MAX_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {len(content) / (1024*1024):.1f}MB (max 20MB)"
            )
        
        # Save uploaded file
        success, error, saved_path = image_processor.save_uploaded_file(content, file.filename)
        if not success:
            raise HTTPException(status_code=500, detail=f"File save failed: {error}")
        
        try:
            # Process the image
            success, error, result = image_processor.process_image_to_text(
                saved_path, extraction_mode, cleanup_after
            )
            
            if not success:
                return ImageProcessResponse(
                    status="error",
                    error=error
                )
            
            return ImageProcessResponse(
                status="success",
                extracted_text=result['extracted_text'],
                file_info=result['file_info'],
                processing_info=result['processing_info'],
                pipeline_stats=result['pipeline_stats']
            )
            
        finally:
            # Always cleanup uploaded file
            try:
                os.unlink(saved_path)
            except:
                pass
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.post("/process-file", response_model=ImageProcessResponse)
async def process_uploaded_file(
    file_path: str,
    extraction_mode: str = "legal_document",
    cleanup_after: bool = True
):
    """
    Process a previously uploaded file
    
    Args:
        file_path: Path to uploaded file
        extraction_mode: Type of extraction to perform
        cleanup_after: Whether to clean up processed files
    
    Returns: Extracted text and processing details
    """
    try:
        # Verify file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Process the image
        success, error, result = image_processor.process_image_to_text(
            file_path, extraction_mode, cleanup_after
        )
        
        if not success:
            return ImageProcessResponse(
                status="error",
                error=error
            )
        
        return ImageProcessResponse(
            status="success",
            extracted_text=result['extracted_text'],
            file_info=result['file_info'],
            processing_info=result['processing_info'],
            pipeline_stats=result['pipeline_stats']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.get("/estimate/{file_path:path}", response_model=ProcessingEstimateResponse)
async def get_processing_estimate(file_path: str):
    """
    Get processing estimates for an uploaded file
    
    Args:
        file_path: Path to the uploaded file
    
    Returns: Processing estimates including cost and token usage
    """
    try:
        # Verify file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        success, error, estimate_info = image_processor.get_processing_estimate(file_path)
        
        if not success:
            return ProcessingEstimateResponse(
                status="error",
                error=error
            )
        
        return ProcessingEstimateResponse(
            status="success",
            file_info=estimate_info['file_info'],
            processing_needed=estimate_info['processing_needed'],
            estimated_cost_usd=estimate_info['estimated_cost_usd'],
            supported_extraction_modes=estimate_info['supported_extraction_modes']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Estimation failed: {str(e)}")

@router.get("/test", response_model=dict)
async def test_image_pipeline():
    """
    Test all image processing pipeline components
    
    Returns: Status of each component
    """
    try:
        test_results = image_processor.test_pipeline_components()
        
        # Determine overall status
        overall_status = "healthy"
        for component, result in test_results.items():
            if result.get('status') != 'success':
                overall_status = "degraded"
                break
        
        return {
            "status": overall_status,
            "components": test_results,
            "ready_for_processing": overall_status == "healthy"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "ready_for_processing": False
        }

@router.post("/cleanup")
async def cleanup_old_files(max_age_hours: int = 24):
    """
    Clean up old processed and temporary files
    
    Args:
        max_age_hours: Maximum age of files to keep (default 24 hours)
    
    Returns: Cleanup statistics
    """
    try:
        cleanup_stats = image_processor.cleanup_old_files(max_age_hours)
        
        return {
            "status": "success",
            "cleanup_stats": cleanup_stats,
            "max_age_hours": max_age_hours
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@router.get("/extraction-modes")
async def get_extraction_modes():
    """
    Get available text extraction modes
    
    Returns: Dictionary of extraction modes and their descriptions
    """
    try:
        modes = image_processor.vision_processor.get_supported_extraction_modes()
        
        return {
            "status": "success",
            "extraction_modes": modes,
            "default_mode": "legal_document"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        } 