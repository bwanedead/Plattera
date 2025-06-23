from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent.parent
sys.path.append(str(backend_dir))

from core.text_to_schema import LLMProcessor
from core.image_processor import ImageProcessor
from core.text_to_schema import LLMProfile

router = APIRouter()

class TextInput(BaseModel):
    text: str
    parcel_id: str = ""  # Optional, can be auto-generated
    options: Dict[str, Any] = {}

class ImageProcessRequest(BaseModel):
    extraction_mode: str = "legal_document"
    model: str = "gpt-4o"
    cleanup_after: bool = True

class CommitteeProcessRequest(BaseModel):
    extraction_mode: str = "legal_document"
    models: Optional[List[str]] = None  # If None, uses default committee
    cleanup_after: bool = True

class ParcelResponse(BaseModel):
    status: str
    parcel_data: Dict[str, Any] = None
    error: str = None

class ImageProcessResponse(BaseModel):
    status: str
    result: Dict[str, Any] = None
    error: str = None

# Initialize image processor
image_processor = ImageProcessor()

@router.post("/text-to-schema", response_model=ParcelResponse)
async def convert_text_to_schema(input_data: TextInput):
    """Convert legal description text into structured parcel JSON schema"""
    try:
        # Load the schema for LLM context
        schema_path = os.path.join(os.path.dirname(__file__), "../../schema/parcel_v0.1.json")
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        # Initialize LLM processor
        llm = LLMProcessor()
        
        # Convert text to structured JSON using the schema
        parcel_data = await llm.text_to_parcel_schema(
            text=input_data.text,
            schema=schema,
            parcel_id=input_data.parcel_id or "auto-generated"
        )
        
        return ParcelResponse(
            status="success",
            parcel_data=parcel_data
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to convert text to schema: {str(e)}"
        )

@router.post("/image-to-text", response_model=ImageProcessResponse)
async def process_image_to_text(
    file: UploadFile = File(...),
    request: ImageProcessRequest = ImageProcessRequest()
):
    """Process uploaded image to extract text using single model"""
    try:
        # Save uploaded file
        file_data = await file.read()
        success, error, saved_path = image_processor.save_uploaded_file(file_data, file.filename)
        
        if not success:
            raise HTTPException(status_code=400, detail=f"File upload failed: {error}")
        
        # Process image to text
        success, error, result = image_processor.process_image_to_text(
            saved_path,
            request.extraction_mode,
            request.model,
            request.cleanup_after
        )
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Image processing failed: {error}")
        
        return ImageProcessResponse(
            status="success",
            result=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

@router.post("/image-to-text-committee", response_model=ImageProcessResponse)
async def process_image_committee_mode(
    file: UploadFile = File(...),
    request: CommitteeProcessRequest = CommitteeProcessRequest()
):
    """Process uploaded image using committee of models for maximum accuracy"""
    try:
        # Save uploaded file
        file_data = await file.read()
        success, error, saved_path = image_processor.save_uploaded_file(file_data, file.filename)
        
        if not success:
            raise HTTPException(status_code=400, detail=f"File upload failed: {error}")
        
        # Process image using committee mode
        success, error, result = image_processor.process_image_committee_mode(
            saved_path,
            request.models,
            request.extraction_mode,
            request.cleanup_after
        )
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Committee processing failed: {error}")
        
        return ImageProcessResponse(
            status="success",
            result=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

@router.get("/available-models")
async def get_available_models():
    """Get list of available models for image processing"""
    try:
        models = image_processor.get_available_models()
        return {
            "status": "success",
            "models": models
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get available models: {str(e)}"
        )

@router.get("/processing-estimate/{filename}")
async def get_processing_estimate(filename: str):
    """Get processing estimates for an uploaded file"""
    try:
        file_path = image_processor.upload_dir / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        success, error, estimate = image_processor.get_processing_estimate(str(file_path))
        
        if not success:
            raise HTTPException(status_code=400, detail=f"Estimation failed: {error}")
        
        return {
            "status": "success",
            "estimate": estimate
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

@router.post("/geometry")
async def generate_geometry(structured_data: Dict[str, Any]):
    """Generate geometry from structured legal description"""
    # TODO: Implement geometry generation
    return {
        "status": "success", 
        "message": "Geometry generation endpoint ready"
    }

@router.get("/test-services")
async def test_all_services():
    """Test all pipeline components and services"""
    try:
        # Test image processing pipeline
        pipeline_results = image_processor.test_pipeline_components()
        
        # Test text processing
        text_results = {}
        try:
            from core.text_to_schema import LLMProcessor
            llm = LLMProcessor()
            
            if llm.llm_service.is_configured():
                success, error, result = llm.llm_service.make_text_call(
                    user_prompt="Say 'Text processing working!' if you can read this.",
                    profile=LLMProfile.FAST_PROCESSING
                )
                text_results['openai_text'] = {
                    'status': 'success' if success else 'error',
                    'error': error,
                    'result': result
                }
            else:
                text_results['openai_text'] = {
                    'status': 'error',
                    'error': 'OpenAI client not configured'
                }
        except Exception as e:
            text_results['openai_text'] = {
                'status': 'error',
                'error': str(e)
            }
        
        return {
            "status": "success",
            "results": {
                "image_pipeline": pipeline_results,
                "text_processing": text_results
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Service test failed: {str(e)}"
        )

@router.get("/test-openai")
async def test_openai_connection():
    """Test OpenAI API connection (legacy endpoint)"""
    try:
        from core.text_to_schema import LLMProcessor
        llm = LLMProcessor()
        
        if not llm.llm_service.is_configured():
            return {"status": "error", "message": "OpenAI client not configured"}
        
        # Use the LLM service for the test call
        success, error, result = llm.llm_service.make_text_call(
            user_prompt="Say 'Hello from OpenAI!' if you can read this.",
            profile=LLMProfile.FAST_PROCESSING
        )
        
        if not success:
            return {"status": "error", "message": f"OpenAI connection failed: {error}"}
        
        return {
            "status": "success",
            "message": "OpenAI connection working",
            "response": result['content'],
            "model": result.get('model', 'openai')
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"OpenAI connection failed: {str(e)}"
        } 