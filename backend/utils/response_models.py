"""
Shared Response Models
Consistent response formats across all pipelines

🔴 CRITICAL REDUNDANCY IMPLEMENTATION DOCUMENTATION 🔴
=====================================================

THESE MODELS DEFINE API CONTRACTS - PRESERVE ALL FIELDS BELOW 🔴

CURRENT WORKING STRUCTURE (DO NOT BREAK):
==========================================

ProcessResponse is the CRITICAL model used by frontend:
- status: "success" or "error" (REQUIRED)
- extracted_text: Main text content (REQUIRED by frontend)
- model_used: Model identifier (REQUIRED)
- service_type: "llm" or "ocr" (REQUIRED)
- tokens_used: Token count (OPTIONAL but displayed)
- confidence_score: Confidence value (OPTIONAL but used)
- metadata: Additional data (OPTIONAL but extensible)

REDUNDANCY IMPLEMENTATION SAFETY RULES:
======================================

✅ SAFE TO EXTEND:
- Add new optional fields to ProcessResponse
- Extend metadata dict with redundancy info
- Add redundancy-specific response models if needed

❌ DO NOT MODIFY:
- Existing field names or types
- Required field status (don't make optional fields required)
- Field meanings or data formats
- Model inheritance structure

CRITICAL REDUNDANCY REQUIREMENTS:
================================
1. ProcessResponse MUST remain backward compatible
2. extracted_text MUST still contain the final consensus text
3. confidence_score MUST reflect overall confidence (not individual call confidence)
4. tokens_used MUST reflect total tokens across all redundancy calls
5. metadata CAN contain redundancy analysis data

SAFE REDUNDANCY EXTENSIONS:
==========================
metadata can safely include:
- "redundancy_enabled": bool
- "redundancy_count": int
- "consensus_analysis": dict
- "individual_results": list
- "word_confidence_map": dict

TESTING CHECKPOINTS:
===================
After redundancy implementation, verify:
1. Frontend still displays extracted_text correctly
2. All existing response fields still work
3. New redundancy metadata doesn't break anything
4. Response serialization/deserialization works
5. API documentation remains accurate
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