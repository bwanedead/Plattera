"""
Processing API Endpoint
Central hub that routes requests to appropriate pipelines
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from utils.response_models import ProcessResponse
from utils.file_handler import save_uploaded_file, cleanup_temp_file, is_valid_image_file
from typing import Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class TextToSchemaRequest(BaseModel):
    """Request model for text-to-schema processing"""
    text: str
    parcel_id: Optional[str] = None
    model: Optional[str] = "gpt-4o"

@router.post("/process", response_model=ProcessResponse)
async def process_content(
    file: UploadFile = File(...),
    content_type: str = Form(...),  # "image-to-text", "text-to-schema", etc.
    model: str = Form("gpt-4o"),
    extraction_mode: str = Form("legal_document"),
    cleanup_after: str = Form("true"),
    flow_to: str = Form(None),
    parcel_id: str = Form(None),
    # Enhancement settings - optional
    contrast: str = Form("1.3"),
    sharpness: str = Form("1.2"),
    brightness: str = Form("1.0"),
    color: str = Form("1.0")
):
    """
    Universal processing endpoint that routes to appropriate pipeline
    
    Args:
        file: Content file to process
        content_type: Type of processing ("image-to-text", "text-to-schema", etc.)
        model: Model to use for processing
        extraction_mode: Mode of extraction/processing
        cleanup_after: Cleanup after processing
        contrast: Image contrast enhancement (1.0 = no change)
        sharpness: Image sharpness enhancement (1.0 = no change)
        brightness: Image brightness enhancement (1.0 = no change)
        color: Image color saturation enhancement (1.0 = no change)
    """
    # Add detailed logging
    logger.info(f"🔥 PROCESSING REQUEST RECEIVED:")
    logger.info(f"   📁 File: {file.filename} (size: {file.size if hasattr(file, 'size') else 'unknown'})")
    logger.info(f"   📋 Content-Type: {file.content_type}")
    logger.info(f"   🎯 Processing Type: {content_type}")
    logger.info(f"   🤖 Model: {model}")
    logger.info(f"   ⚙️ Extraction Mode: {extraction_mode}")
    logger.info(f"   🧹 Cleanup After: {cleanup_after}")
    logger.info(f"   🎨 Enhancement Settings: contrast={contrast}, sharpness={sharpness}, brightness={brightness}, color={color}")
    
    # Parse enhancement settings
    enhancement_settings = {
        'contrast': float(contrast),
        'sharpness': float(sharpness),
        'brightness': float(brightness),
        'color': float(color)
    }
    
    temp_path = None
    
    try:
        # Route to appropriate pipeline based on content_type
        if content_type == "image-to-text":
            logger.info("🖼️ Routing to image-to-text pipeline")
            return await _process_image_to_text(file, model, extraction_mode, enhancement_settings)
        elif content_type == "text-to-schema":
            logger.info("📝 Routing to text-to-schema pipeline")
            return await _process_text_to_schema(file, model)
        else:
            logger.error(f"❌ Unknown content_type: {content_type}")
            raise HTTPException(
                status_code=400, 
                detail=f"Unknown content_type: {content_type}. Supported: image-to-text, text-to-schema"
            )
            
    except HTTPException as he:
        logger.error(f"❌ HTTP Exception: {he.detail}")
        raise
    except Exception as e:
        logger.error(f"💥 Unexpected error: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

async def _process_image_to_text(file: UploadFile, model: str, extraction_mode: str, enhancement_settings: dict = None) -> ProcessResponse:
    """Route to image-to-text pipeline"""
    temp_path = None
    
    try:
        logger.info(f"🔍 Validating image file: {file.filename}")
        
        # Validate file type
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
        
        # Import and use pipeline
        logger.info("🚀 Starting image-to-text pipeline...")
        from pipelines.image_to_text.pipeline import ImageToTextPipeline
        pipeline = ImageToTextPipeline()
        
        # Process the image
        logger.info(f"🔄 Processing with model: {model}, mode: {extraction_mode}")
        result = pipeline.process(temp_path, model, extraction_mode, enhancement_settings)
        logger.info(f"📊 Pipeline result: {result}")
        
        if not result.get("success", False):
            logger.error(f"❌ Pipeline failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
        
        logger.info("✅ Processing completed successfully!")
        return ProcessResponse(
            status="success",
            extracted_text=result.get("extracted_text"),
            model_used=result.get("model_used"),
            service_type=result.get("service_type"),
            tokens_used=result.get("tokens_used"),
            confidence_score=result.get("confidence_score"),
            metadata=result.get("metadata")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Image processing error: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")
    finally:
        # Always cleanup temp file
        if temp_path:
            logger.info(f"🧹 Cleaning up temp file: {temp_path}")
            cleanup_temp_file(temp_path)

async def _process_text_to_schema(file: UploadFile, model: str) -> ProcessResponse:
    """Route to text-to-schema pipeline (placeholder for future implementation)"""
    raise HTTPException(
        status_code=501, 
        detail="Text-to-schema pipeline not yet implemented"
    )

@router.post("/process/text-to-schema", response_model=ProcessResponse)
async def process_text_to_schema_direct(request: TextToSchemaRequest):
    """
    Direct text-to-schema processing endpoint for JSON requests
    
    Args:
        request: JSON request with text and optional parcel_id
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(
                status_code=400, 
                detail="Text content is required"
            )
        
        # TODO: Implement actual text-to-schema pipeline
        # For now, return a placeholder response
        return ProcessResponse(
            status="success",
            extracted_text=request.text,
            model_used=request.model,
            service_type="text-to-schema",
            tokens_used=0,
            confidence_score=1.0,
            metadata={
                "parcel_id": request.parcel_id,
                "processing_type": "text-to-schema",
                "note": "Text-to-schema pipeline not yet implemented - returning input text"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.get("/process/types")
async def get_processing_types():
    """Get available processing types"""
    return {
        "status": "success",
        "processing_types": {
            "image-to-text": {
                "description": "Extract text from images using LLM or OCR",
                "supported_files": ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp"],
                "extraction_modes": ["legal_document", "simple_ocr", "handwritten", "property_deed"]
            },
            "text-to-schema": {
                "description": "Convert text to structured JSON schema",
                "supported_files": ["txt", "pdf"],
                "status": "coming_soon"
            }
        }
    }

# Add this test endpoint to see if the basic structure works
@router.post("/process/test")
async def test_process(
    file: UploadFile = File(...),
    content_type: str = Form(...),
    model: str = Form("gpt-4o"),
    extraction_mode: str = Form("legal_document"),
    cleanup_after: str = Form("true")
):
    """Test endpoint to debug 422 issues"""
    logger.info("🔥 TEST ENDPOINT HIT!")
    logger.info(f"File: {file.filename}")
    logger.info(f"Content Type: {content_type}")
    logger.info(f"Model: {model}")
    logger.info(f"Extraction Mode: {extraction_mode}")
    logger.info(f"Cleanup After: {cleanup_after}")
    
    return {
        "status": "success",
        "message": "Test endpoint working!",
        "received": {
            "filename": file.filename,
            "content_type": content_type,
            "model": model,
            "extraction_mode": extraction_mode,
            "cleanup_after": cleanup_after
        }
    } 