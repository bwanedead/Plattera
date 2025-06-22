from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import json
import os
import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent.parent
sys.path.append(str(backend_dir))

from core.text_to_schema import LLMProcessor

router = APIRouter()

class TextInput(BaseModel):
    text: str
    parcel_id: str = ""  # Optional, can be auto-generated
    options: Dict[str, Any] = {}

class ParcelResponse(BaseModel):
    status: str
    parcel_data: Dict[str, Any] = None
    error: str = None

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

@router.post("/geometry")
async def generate_geometry(structured_data: Dict[str, Any]):
    """Generate geometry from structured legal description"""
    # TODO: Implement geometry generation
    return {
        "status": "success", 
        "message": "Geometry generation endpoint ready"
    }

@router.get("/test-openai")
async def test_openai_connection():
    """Test OpenAI API connection"""
    try:
        from core.text_to_schema import LLMProcessor
        llm = LLMProcessor()
        
        if not llm.llm_service.is_configured():
            return {"status": "error", "message": "OpenAI client not configured"}
        
        # Use the LLM service for the test call
        success, error, result = llm.llm_service.make_text_call(
            user_prompt="Say 'Hello from OpenAI!' if you can read this.",
            profile=llm.llm_service.get_profile("FAST_PROCESSING"),
            max_tokens=50
        )
        
        if not success:
            return {"status": "error", "message": f"OpenAI connection failed: {error}"}
        
        return {
            "status": "success",
            "message": "OpenAI connection working",
            "response": result['content'],
            "model": result['usage'].get('model', 'openai')
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"OpenAI connection failed: {str(e)}"
        } 