from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import json
import os
from ...core.llm_processor import LLMProcessor

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