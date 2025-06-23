"""
Shared Response Models
Consistent response formats across all pipelines
"""
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

class BaseResponse(BaseModel):
    """Base response format"""
    status: str  # "success" or "error"
    error: Optional[str] = None

class ModelsResponse(BaseResponse):
    """Response for /models endpoint"""
    models: Optional[Dict[str, Dict[str, Any]]] = None

class ProcessResponse(BaseResponse):
    """Response for processing endpoints"""
    model_config = {"protected_namespaces": ()}
    
    extracted_text: Optional[str] = None
    model_used: Optional[str] = None
    service_type: Optional[str] = None  # "llm" or "ocr"
    tokens_used: Optional[int] = None
    confidence_score: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class SchemaResponse(BaseResponse):
    """Response for schema conversion endpoints"""
    schema_data: Optional[Dict[str, Any]] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None 