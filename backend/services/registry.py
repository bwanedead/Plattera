"""
Service Registry - Auto-discovers all available services
Drop providers in llm/ or ocr/ folders and they'll be automatically loaded
"""
import os
import importlib
import glob
import sys
from typing import Dict, Any, List, Union
import logging
from services.llm.base import LLMService
from services.ocr.base import OCRService

class ServiceRegistry:
    """Central registry that auto-discovers and manages all services"""
    
    def __init__(self):
        self.llm_services: Dict[str, LLMService] = {}
        self.ocr_services: Dict[str, OCRService] = {}
        self._discover_services()
    
    def _discover_services(self):
        """Auto-discover all available LLM and OCR services"""
        logger = logging.getLogger(__name__)
        logger.info("🔍 Discovering services...")
        
        # Discover LLM services
        self._discover_llm_services()
        
        # Discover OCR services  
        self._discover_ocr_services()
        
        logger.info(f"✅ Loaded {len(self.llm_services)} LLM services, {len(self.ocr_services)} OCR services")
    
    def _register_service_from_module(self, module_name: str, service_type: str):
        """Helper to inspect a module and register its service."""
        logger = logging.getLogger(__name__)
        try:
            package = f"services.{service_type}"
            full_module_name = f"{package}.{module_name}"
            module = importlib.import_module(full_module_name)

            base_class = LLMService if service_type == "llm" else OCRService
            target_dict = self.llm_services if service_type == "llm" else self.ocr_services

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, base_class)
                    and attr is not base_class
                ):
                    try:
                        service = attr()
                        if service.is_available():
                            target_dict[service.name] = service
                            logger.info(f"✅ {service_type.upper()}: {service.name}")
                        else:
                            logger.warning(f"⚠️  {service_type.upper()}: {service.name} (not configured)")
                    except Exception as e:
                        logger.error(f"❌ {service_type.upper()}: {module_name} failed to load: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to import {service_type.upper()} module {module_name}: {e}")
    
    def _discover_llm_services(self):
        """Discover all LLM providers in services/llm/"""
        # In frozen (PyInstaller) mode, .py files are not reliably visible on disk,
        # so we manually register known providers instead of globbing.
        if getattr(sys, "frozen", False):
            logging.getLogger(__name__).info("❄️ Running in frozen mode - manually registering LLM services")
            known_services = ["openai"]  # keep in sync with PyInstaller hidden-imports
            for module in known_services:
                self._register_service_from_module(module, "llm")
            return

        # DEV MODE: Use glob to find .py files
        llm_dir = os.path.join(os.path.dirname(__file__), "llm")
        provider_files = glob.glob(os.path.join(llm_dir, "*.py"))
        
        for file_path in provider_files:
            filename = os.path.basename(file_path)
            
            # Skip base.py and __init__.py
            if filename in ["base.py", "__init__.py"]:
                continue
            
            module_name = filename[:-3]  # Remove .py extension
            self._register_service_from_module(module_name, "llm")
    
    def _discover_ocr_services(self):
        """Discover all OCR providers in services/ocr/"""
        if getattr(sys, "frozen", False):
            logging.getLogger(__name__).info("❄️ Running in frozen mode - manually registering OCR services")
            known_services: List[str] = []  # add OCR providers here as needed
            for module in known_services:
                self._register_service_from_module(module, "ocr")
            return

        ocr_dir = os.path.join(os.path.dirname(__file__), "ocr")
        provider_files = glob.glob(os.path.join(ocr_dir, "*.py"))
        
        for file_path in provider_files:
            filename = os.path.basename(file_path)
            
            # Skip base.py and __init__.py
            if filename in ["base.py", "__init__.py"]:
                continue
                
            module_name = filename[:-3]  # Remove .py extension
            self._register_service_from_module(module_name, "ocr")
    
    def get_all_models(self) -> Dict[str, Dict[str, Any]]:
        """Get all models from all available services"""
        all_models = {}
        
        # Get LLM models
        for service in self.llm_services.values():
            try:
                models = service.get_models()
                for model_id, model_info in models.items():
                    model_info["service_type"] = "llm"
                    model_info["service_name"] = service.name
                    all_models[model_id] = model_info
            except Exception as e:
                logging.getLogger(__name__).error(f"Error getting models from LLM service {service.name}: {e}")
        
        # Get OCR models
        for service in self.ocr_services.values():
            try:
                models = service.get_models()
                for model_id, model_info in models.items():
                    model_info["service_type"] = "ocr"
                    model_info["service_name"] = service.name
                    all_models[model_id] = model_info
            except Exception as e:
                logging.getLogger(__name__).error(f"Error getting models from OCR service {service.name}: {e}")
        
        return all_models
    
    def get_service_for_model(self, model: str) -> Union[LLMService, OCRService, None]:
        """Find which service can handle a specific model"""
        # Check LLM services
        for service in self.llm_services.values():
            if model in service.get_models():
                return service
        
        # Check OCR services
        for service in self.ocr_services.values():
            if model in service.get_models():
                return service
        
        return None
    
    def get_llm_services(self) -> Dict[str, LLMService]:
        """Get all available LLM services with detailed info"""
        return self.llm_services.copy()
    
    def get_ocr_services(self) -> Dict[str, OCRService]:
        """Get all available OCR services with detailed info"""
        return self.ocr_services.copy()
    
    def get_service_info(self) -> Dict[str, Any]:
        """Get detailed information about all services for logging/debugging"""
        info = {
            "llm_services": {},
            "ocr_services": {},
            "total_models": 0
        }
        
        # Get LLM service info
        for name, service in self.llm_services.items():
            models = service.get_models()
            info["llm_services"][name] = {
                "available": service.is_available(),
                "model_count": len(models),
                "models": list(models.keys())
            }
            info["total_models"] += len(models)
        
        # Get OCR service info
        for name, service in self.ocr_services.items():
            models = service.get_models()
            info["ocr_services"][name] = {
                "available": service.is_available(),
                "model_count": len(models),
                "models": list(models.keys())
            }
            info["total_models"] += len(models)
        
        return info
    
    def process_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """Process text-only request (routes to appropriate LLM service)"""
        service = self.get_service_for_model(model)
        
        if not service:
            return {
                "success": False,
                "error": f"Model '{model}' not found in any service",
                "text": None
            }
        
        if not isinstance(service, LLMService):
            return {
                "success": False,
                "error": f"Model '{model}' is not a text processing model",
                "text": None
            }
        
        return service.call_text(prompt, model, **kwargs)
    
    def process_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> Dict[str, Any]:
        """Process vision request (routes to appropriate LLM service)"""
        service = self.get_service_for_model(model)
        
        if not service:
            return {
                "success": False,
                "error": f"Model '{model}' not found in any service",
                "text": None
            }
        
        if not isinstance(service, LLMService):
            return {
                "success": False,
                "error": f"Model '{model}' is not a vision model",
                "text": None
            }
        
        return service.call_vision(prompt, image_data, model, **kwargs)
    
    def process_ocr(self, image_path: str, model: str, **kwargs) -> Dict[str, Any]:
        """Process OCR request (routes to appropriate OCR service)"""
        service = self.get_service_for_model(model)
        
        if not service:
            return {
                "success": False,
                "error": f"Model '{model}' not found in any service",
                "text": None
            }
        
        if not isinstance(service, OCRService):
            return {
                "success": False,
                "error": f"Model '{model}' is not an OCR model",
                "text": None
            }
        
        return service.extract_text(image_path, model, **kwargs)


# Global registry instance
_registry = None

def get_registry() -> ServiceRegistry:
    """Get the global service registry instance"""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry 