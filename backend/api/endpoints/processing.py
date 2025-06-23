"""
Processing API Endpoint
Central hub that routes requests to appropriate pipelines
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from utils.response_models import ProcessResponse
from utils.file_handler import save_uploaded_file, cleanup_temp_file, is_valid_image_file

router = APIRouter()

@router.post("/process", response_model=ProcessResponse)
async def process_content(
    file: UploadFile = File(...),
    content_type: str = Form(...),  # "image-to-text", "text-to-schema", etc.
    model: str = Form("gpt-4o"),
    extraction_mode: str = Form("legal_document"),
    **kwargs
):
    """
    Universal processing endpoint that routes to appropriate pipeline
    
    Args:
        file: Content file to process
        content_type: Type of processing ("image-to-text", "text-to-schema", etc.)
        model: Model to use for processing
        extraction_mode: Mode of extraction/processing
        **kwargs: Additional pipeline-specific parameters
    """
    temp_path = None
    
    try:
        # Route to appropriate pipeline based on content_type
        if content_type == "image-to-text":
            return await _process_image_to_text(file, model, extraction_mode)
        elif content_type == "text-to-schema":
            return await _process_text_to_schema(file, model, **kwargs)
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Unknown content_type: {content_type}. Supported: image-to-text, text-to-schema"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

async def _process_image_to_text(file: UploadFile, model: str, extraction_mode: str) -> ProcessResponse:
    """Route to image-to-text pipeline"""
    temp_path = None
    
    try:
        # Validate file type
        if not is_valid_image_file(file.filename):
            raise HTTPException(
                status_code=400, 
                detail="Invalid file type. Please upload an image file."
            )
        
        # Save uploaded file temporarily
        file_content = await file.read()
        success, error, temp_path = save_uploaded_file(file_content, file.filename)
        
        if not success:
            raise HTTPException(status_code=400, detail=error)
        
        # Import and use pipeline
        from pipelines.image_to_text.pipeline import ImageToTextPipeline
        pipeline = ImageToTextPipeline()
        
        # Process the image
        result = pipeline.process(temp_path, model, extraction_mode)
        
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
        
        return ProcessResponse(
            status="success",
            extracted_text=result.get("extracted_text"),
            model_used=result.get("model_used"),
            service_type=result.get("service_type"),
            tokens_used=result.get("tokens_used"),
            confidence_score=result.get("confidence_score"),
            metadata=result.get("metadata")
        )
        
    finally:
        # Always cleanup temp file
        if temp_path:
            cleanup_temp_file(temp_path)

async def _process_text_to_schema(file: UploadFile, model: str, **kwargs) -> ProcessResponse:
    """Route to text-to-schema pipeline (placeholder for future implementation)"""
    raise HTTPException(
        status_code=501, 
        detail="Text-to-schema pipeline not yet implemented"
    )

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