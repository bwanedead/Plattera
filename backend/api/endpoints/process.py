from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter()

class TextInput(BaseModel):
    text: str
    options: Dict[str, Any] = {}

@router.post("/text")
async def process_legal_text(input_data: TextInput):
    """Process legal description text into structured data"""
    # TODO: Implement LLM processing
    return {
        "status": "success",
        "message": "Text processing endpoint ready",
        "input_length": len(input_data.text)
    }

@router.post("/geometry")
async def generate_geometry(structured_data: Dict[str, Any]):
    """Generate geometry from structured legal description"""
    # TODO: Implement geometry generation
    return {
        "status": "success", 
        "message": "Geometry generation endpoint ready"
    } 