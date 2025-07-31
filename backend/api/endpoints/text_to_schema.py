"""
Text-to-Schema API Endpoints
Dedicated endpoints for converting text to structured parcel data
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class TextToSchemaRequest(BaseModel):
    """Request model for text-to-schema processing"""
    text: str
    parcel_id: Optional[str] = None
    model: Optional[str] = "gpt-4o"

class TextToSchemaResponse(BaseModel):
    """Response model for text-to-schema processing"""
    status: str
    structured_data: Optional[Dict[str, Any]] = None
    original_text: Optional[str] = None
    model_used: Optional[str] = None
    service_type: Optional[str] = None
    tokens_used: Optional[int] = None
    confidence_score: Optional[float] = None
    validation_warnings: Optional[list] = None
    metadata: Optional[Dict[str, Any]] = None

@router.post("/convert", response_model=TextToSchemaResponse)
async def convert_text_to_schema(request: TextToSchemaRequest):
    """
    Convert legal text to structured parcel schema
    
    Args:
        request: JSON request with text, optional parcel_id, and model selection
        
    Returns:
        TextToSchemaResponse with structured parcel data
    """
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(
                status_code=400, 
                detail="Text content is required"
            )
        
        logger.info(f"📝 Converting text to schema with model: {request.model}")
        logger.info(f"📏 Text content length: {len(request.text)} characters")
        
        # Add detailed import debugging
        try:
            logger.info("🔍 Attempting to import TextToSchemaPipeline...")
            from pipelines.text_to_schema.pipeline import TextToSchemaPipeline
            logger.info("✅ Successfully imported TextToSchemaPipeline")
            
            logger.info("🔍 Attempting to create pipeline instance...")
            pipeline = TextToSchemaPipeline()
            logger.info("✅ Successfully created pipeline instance")
            
        except Exception as import_error:
            logger.error(f"❌ Failed to import/create pipeline: {str(import_error)}")
            logger.exception("Full import traceback:")
            raise HTTPException(status_code=500, detail=f"Pipeline import failed: {str(import_error)}")
        
        # Process the text to extract structured data
        logger.info("🔍 Starting pipeline processing...")
        result = pipeline.process(request.text, request.model, request.parcel_id)
        logger.info(f"✅ Pipeline processing completed, success: {result.get('success', False)}")
        
        if not result.get("success", False):
            logger.error(f"❌ Pipeline failed: {result.get('error', 'Unknown error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
        
        logger.info("✅ Text-to-schema conversion completed successfully!")
        return TextToSchemaResponse(
            status="success",
            structured_data=result.get("structured_data"),
            original_text=request.text,
            model_used=result.get("model_used"),
            service_type=result.get("service_type"),
            tokens_used=result.get("tokens_used"),
            confidence_score=result.get("confidence_score"),
            validation_warnings=result.get("validation_warnings", []),
            metadata=result.get("metadata")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Text-to-schema conversion error: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Text-to-schema conversion failed: {str(e)}")

@router.get("/schema")
async def get_parcel_schema():
    """
    Get the parcel schema template
    
    Returns:
        The current parcel schema structure
    """
    try:
        from pipelines.text_to_schema.pipeline import TextToSchemaPipeline
        pipeline = TextToSchemaPipeline()
        
        schema = pipeline.get_schema_template()
        
        return {
            "status": "success",
            "schema": schema,
            "version": "parcel_v0.1"
        }
        
    except Exception as e:
        logger.error(f"💥 Error fetching schema: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch schema: {str(e)}")

@router.get("/models")
async def get_text_to_schema_models():
    """
    Get available models for text-to-schema processing
    
    Returns:
        Available models that support text-to-schema conversion
    """
    try:
        from pipelines.text_to_schema.pipeline import TextToSchemaPipeline
        pipeline = TextToSchemaPipeline()
        
        models = pipeline.get_available_models()
        
        return {
            "status": "success",
            "models": models
        }
        
    except Exception as e:
        logger.error(f"💥 Error fetching models: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}") 