"""
Processing API Endpoint
Central hub that routes requests to appropriate pipelines

🔴 CRITICAL REDUNDANCY IMPLEMENTATION DOCUMENTATION 🔴
=====================================================

THIS FILE IS THE MAIN API GATEWAY - PRESERVE ALL WIRING BELOW WHEN ADDING REDUNDANCY

CURRENT WORKING STRUCTURE (DO NOT BREAK):
==========================================

1. ENDPOINT SIGNATURE:
   - process_content() accepts Form parameters
   - CRITICAL: All existing parameters MUST remain with same names/types
   - SAFE TO ADD: New redundancy parameter as Form field
   - PRESERVE: All current parameter validation and error handling

2. ROUTING LOGIC:
   - content_type routes to _process_image_to_text() or _process_text_to_schema()
   - CRITICAL: Keep routing logic intact
   - SAFE TO MODIFY: _process_image_to_text() function signature (add redundancy param)

3. ENHANCEMENT SETTINGS PARSING:
   - Current parsing with clamping MUST be preserved
   - CRITICAL: enhancement_settings dict format must remain unchanged
   - SAFE TO ADD: Similar parsing for redundancy parameter

4. ERROR HANDLING:
   - All try/catch blocks MUST remain intact
   - CRITICAL: HTTPException patterns must be preserved
   - SAFE TO ADD: Additional error handling for redundancy failures

5. RESPONSE FORMAT:
   - ProcessResponse model MUST remain unchanged
   - CRITICAL: All response fields must map correctly
   - SAFE TO ADD: Additional metadata fields for redundancy info

6. FILE HANDLING:
   - Temporary file management MUST remain intact
   - CRITICAL: cleanup_temp_file() must always be called in finally block
   - PRESERVE: All file validation logic

REDUNDANCY IMPLEMENTATION SAFETY RULES:
======================================

✅ SAFE TO MODIFY:
- Add redundancy: str = Form("3") parameter
- Add redundancy parsing with clamping
- Modify _process_image_to_text() signature to accept redundancy_count
- Pass redundancy_count to pipeline.process_with_redundancy()

❌ DO NOT MODIFY:
- Existing parameter names or types
- Enhancement settings parsing logic
- Error handling structure
- Response mapping to ProcessResponse
- File cleanup logic
- Routing logic structure

TESTING CHECKPOINTS:
===================
After redundancy implementation, verify:
1. Single file upload still works (redundancy=1)
2. Enhancement settings still work correctly
3. Error handling still functions properly  
4. File cleanup still happens in all cases
5. Response format matches frontend expectations

CRITICAL INTEGRATION POINTS:
============================
- Pipeline must have process_with_redundancy() method
- Method must return same format as process() method
- Frontend must send redundancy parameter
- All existing functionality must remain working
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
    contrast: str = Form("2.0"),
    sharpness: str = Form("2.0"),
    brightness: str = Form("1.5"),
    color: str = Form("1.0"),
    # Redundancy setting - optional
    redundancy: str = Form("3"),
    # Consensus strategy - optional
    consensus_strategy: str = Form("sequential")
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
        redundancy: Number of parallel API calls for redundancy (1 = no redundancy, 3 = default)
        consensus_strategy: Consensus algorithm to use ('sequential', 'ngram_overlap')
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
    logger.info(f"   🔄 Redundancy: {redundancy}")
    logger.info(f"   🧠 Consensus Strategy: {consensus_strategy}")
    
    # Parse enhancement settings with robust error handling
    try:
        enhancement_settings = {
            'contrast': max(0.1, min(5.0, float(contrast))),  # Clamp between 0.1-5.0
            'sharpness': max(0.1, min(5.0, float(sharpness))),  # Clamp between 0.1-5.0
            'brightness': max(0.1, min(3.0, float(brightness))),  # Clamp between 0.1-3.0
            'color': max(0.0, min(3.0, float(color)))  # Clamp between 0.0-3.0
        }
        logger.info(f"✅ Enhancement settings parsed: {enhancement_settings}")
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ Invalid enhancement parameters, using defaults: {e}")
        enhancement_settings = {
            'contrast': 1.5,
            'sharpness': 1.2,
            'brightness': 1.0,
            'color': 1.0
        }
    
    # Parse redundancy setting with robust error handling
    try:
        redundancy_count = max(1, min(10, int(redundancy)))  # Clamp between 1-10
        logger.info(f"✅ Redundancy count parsed: {redundancy_count}")
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ Invalid redundancy parameter, using default: {e}")
        redundancy_count = 3
    
    # Validate consensus strategy
    valid_strategies = ['sequential', 'ngram_overlap', 'strict_majority', 'length_weighted', 'confidence_weighted']
    if consensus_strategy not in valid_strategies:
        logger.warning(f"⚠️ Invalid consensus strategy '{consensus_strategy}', using 'sequential'")
        consensus_strategy = 'sequential'
    
    temp_path = None
    
    try:
        # Route to appropriate pipeline based on content_type
        if content_type == "image-to-text":
            logger.info("🖼️ Routing to image-to-text pipeline")
            return await _process_image_to_text(file, model, extraction_mode, enhancement_settings, redundancy_count, consensus_strategy)
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

async def _process_image_to_text(file: UploadFile, model: str, extraction_mode: str, enhancement_settings: dict = None, redundancy_count: int = 3, consensus_strategy: str = 'sequential') -> ProcessResponse:
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
        
        # Process the image with redundancy support
        logger.info(f"🔄 Processing with model: {model}, mode: {extraction_mode}, redundancy: {redundancy_count}, consensus: {consensus_strategy}")
        
        if redundancy_count > 1:
            result = pipeline.process_with_redundancy(temp_path, model, extraction_mode, enhancement_settings, redundancy_count, consensus_strategy)
        else:
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
    try:
        # Import here to avoid circular dependencies
        from prompts.image_to_text import get_available_extraction_modes
        
        extraction_modes = get_available_extraction_modes()
        print("DEBUG: extraction_modes from prompts module:", extraction_modes)
        print("DEBUG: type of extraction_modes:", type(extraction_modes))
        
        return {
            "status": "success",
            "processing_types": {
                "image-to-text": {
                    "description": "Extract text from images using LLM or OCR",
                    "supported_files": ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp"],
                    "extraction_modes": extraction_modes  # Dynamic from prompts module
                },
                "text-to-schema": {
                    "description": "Convert text to structured JSON schema",
                    "supported_files": ["txt", "pdf"],
                    "status": "coming_soon"
                }
            }
        }
    except Exception as e:
        print("DEBUG: Error importing extraction modes:", e)
        # Fallback in case of import error
        return {
            "status": "success", 
            "processing_types": {
                "image-to-text": {
                    "description": "Extract text from images using LLM or OCR",
                    "supported_files": ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp"],
                    "extraction_modes": {
                        "legal_document_plain": {"name": "Legal Document Plain", "description": "Fallback mode"}
                    }
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