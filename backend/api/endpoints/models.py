"""
Models API Endpoint
Central place to get all available models from all services
"""
from fastapi import APIRouter
from services.registry import get_registry
from utils.response_models import ModelsResponse

router = APIRouter()

@router.get("/models", response_model=ModelsResponse)
async def get_all_models():
    """
    Get all available models from all services
    
    Returns models categorized by service type (llm, ocr) with full metadata
    """
    try:
        registry = get_registry()
        models = registry.get_all_models()
        
        return ModelsResponse(status="success", models=models)
    except Exception as e:
        return ModelsResponse(status="error", error=str(e))

@router.get("/models/{service_type}")
async def get_models_by_type(service_type: str):
    """
    Get models filtered by service type
    
    Args:
        service_type: "llm", "ocr", or "all"
    """
    try:
        registry = get_registry()
        all_models = registry.get_all_models()
        
        if service_type == "all":
            filtered_models = all_models
        else:
            filtered_models = {
                model_id: model_info 
                for model_id, model_info in all_models.items()
                if model_info.get("service_type") == service_type
            }
        
        return ModelsResponse(status="success", models=filtered_models)
    except Exception as e:
        return ModelsResponse(status="error", error=str(e)) 