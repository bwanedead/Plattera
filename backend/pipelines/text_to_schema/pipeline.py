"""
Text to Schema Processing Pipeline
Converts plain text to structured JSON using OpenAI's structured outputs
"""
from services.registry import get_registry
from prompts.text_to_schema import get_text_to_schema_prompt
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class TextToSchemaPipeline:
    """
    Pipeline for converting text to structured parcel data using structured outputs
    """
    
    def __init__(self):
        self.registry = get_registry()
        self.parcel_schema = self._load_parcel_schema()
    
    def process(self, text: str, model: str = "gpt-4o", parcel_id: Optional[str] = None) -> dict:
        """
        Process text to extract structured parcel data
        
        Args:
            text: Input text to process (legal description)
            model: Model identifier to use for processing (recommend gpt-4o for structured outputs)
            parcel_id: Optional parcel ID for the output
            
        Returns:
            dict: Processing result with structured parcel data and metadata
        """
        try:
            # Get the appropriate service for this model
            service = self._get_service_for_model(model)
            if not service:
                return {
                    "success": False,
                    "error": f"No service available for model: {model}"
                }
            
            # Get the prompt for parcel extraction
            prompt = get_text_to_schema_prompt("parcel", model)
            
            # Process using structured outputs
            if hasattr(service, 'call_structured_pydantic'):
                # Use the new Pydantic-based structured output method (preferred)
                result = service.call_structured_pydantic(
                    prompt=prompt,
                    input_text=text,
                    model=model,
                    parcel_id=parcel_id
                )
            elif hasattr(service, 'call_structured'):
                # Fallback to JSON schema structured output
                result = service.call_structured(
                    prompt=prompt,
                    input_text=text,
                    schema=self._convert_to_strict_schema(self.parcel_schema),
                    model=model
                )
                
                # Add parcel_id if provided
                if result.get("success") and parcel_id and "structured_data" in result:
                    if not result["structured_data"].get("parcel_id"):
                        result["structured_data"]["parcel_id"] = parcel_id
            else:
                return {
                    "success": False,
                    "error": f"Service {service.__class__.__name__} doesn't support structured outputs"
                }
            
            # Validate against schema
            if result.get("success") and "structured_data" in result:
                validation_result = self._validate_parcel_data(result["structured_data"])
                if not validation_result["valid"]:
                    logger.warning(f"Schema validation warnings: {validation_result['errors']}")
                    result["validation_warnings"] = validation_result["errors"]
            
            # Standardize the response
            return self._standardize_response(result, model, service)
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _load_parcel_schema(self) -> dict:
        """Load the parcel schema from parcel_v0.1.json"""
        try:
            schema_path = Path(__file__).parent.parent.parent / "schema" / "parcel_v0.1.json"
            with open(schema_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Parcel schema file not found at {schema_path}")
            return {}
    
    def _convert_to_strict_schema(self, schema: dict) -> dict:
        """Convert the parcel schema to strict structured output format"""
        def make_strict(obj):
            if isinstance(obj, dict):
                if obj.get("type") == "object":
                    obj["additionalProperties"] = False
                    if "properties" in obj:
                        for prop in obj["properties"].values():
                            make_strict(prop)
                elif obj.get("type") == "array" and "items" in obj:
                    make_strict(obj["items"])
            return obj
        
        strict_schema = json.loads(json.dumps(schema))  # Deep copy
        return make_strict(strict_schema)
    
    def _get_service_for_model(self, model: str):
        """Find the appropriate service for a given model"""
        all_models = self.registry.get_all_models()
        
        if model not in all_models:
            return None
            
        model_info = all_models[model]
        service_type = model_info.get("service_type")
        service_name = model_info.get("service_name")
        
        if service_type == "llm":
            return self.registry.llm_services.get(service_name)
        
        return None
    
    def _validate_parcel_data(self, data: dict) -> dict:
        """Basic validation of parcel data against schema requirements"""
        errors = []
        warnings = []
        
        # Check required fields from schema
        required_fields = ["parcel_id", "crs", "origin", "legs", "close", "stated_area_ac", "source"]
        
        for field in required_fields:
            if field not in data or data[field] is None:
                if field in ["parcel_id", "crs", "origin", "legs", "close"]:
                    errors.append(f"Missing required field: {field}")
                else:
                    warnings.append(f"Missing optional field: {field}")
        
        # Validate legs array
        if "legs" in data and isinstance(data["legs"], list):
            if len(data["legs"]) < 1:
                errors.append("Legs array must have at least 1 item")
            
            for i, leg in enumerate(data["legs"]):
                if not isinstance(leg, dict):
                    errors.append(f"Leg {i} must be an object")
                    continue
                    
                leg_required = ["bearing_deg", "distance", "distance_units", "distance_sigma", "raw_text", "confidence"]
                for field in leg_required:
                    if field not in leg:
                        errors.append(f"Leg {i} missing required field: {field}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def _standardize_response(self, result: dict, model: str, service) -> dict:
        """Standardize response format across different services"""
        if not result.get("success", False):
            return result
            
        return {
            "success": True,
            "structured_data": result.get("structured_data", {}),
            "model_used": model,
            "service_type": "llm",
            "service_name": service.__class__.__name__.lower().replace('service', ''),
            "tokens_used": result.get("tokens_used"),
            "confidence_score": result.get("confidence_score", 0.8),
            "validation_warnings": result.get("validation_warnings", []),
            "metadata": {
                "schema_version": "parcel_v0.1",
                "processing_time": result.get("processing_time"),
                **result.get("metadata", {})
            }
        }
    
    def get_schema_template(self) -> dict:
        """Get the parcel schema template"""
        return self.parcel_schema
    
    def get_available_models(self) -> dict:
        """Get models available for text-to-schema processing"""
        all_models = self.registry.get_all_models()
        
        # Filter for models that can process text
        text_models = {}
        for model_id, model_info in all_models.items():
            if "text" in model_info.get("capabilities", []):
                text_models[model_id] = model_info
                
        return text_models 