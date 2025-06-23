"""
System API Endpoints
Health checks, service status, and system information
"""
from fastapi import APIRouter
from services.registry import get_registry

router = APIRouter()

@router.get("/health")
async def health_check():
    """System health check"""
    try:
        registry = get_registry()
        
        return {
            "status": "healthy",
            "service": "Plattera API",
            "version": "2.0.0",
            "services": {
                "llm_services": len(registry.llm_services),
                "ocr_services": len(registry.ocr_services),
                "total_models": len(registry.get_all_models())
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@router.get("/services")
async def get_service_status():
    """Get detailed service status"""
    try:
        registry = get_registry()
        
        return {
            "status": "success",
            "llm_services": {
                name: {
                    "available": True,
                    "models": list(service.get_models().keys())
                }
                for name, service in registry.llm_services.items()
            },
            "ocr_services": {
                name: {
                    "available": True,
                    "models": list(service.get_models().keys())
                }
                for name, service in registry.ocr_services.items()
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        } 