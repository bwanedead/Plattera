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
import re

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
            
            # Get the prompt for parcel extraction (dynamic from text_to_schema.py)
            prompt = get_text_to_schema_prompt("parcel", model)
            
            # Always reload schema from disk to get latest version
            current_schema = self._load_parcel_schema()
            
            # Process using structured outputs
            if hasattr(service, 'call_structured_pydantic'):
                # Use the new Pydantic-based structured output method (preferred)
                result = service.call_structured_pydantic(
                    prompt=prompt,
                    input_text=text,
                    model=model,
                    parcel_id=parcel_id,
                    schema=current_schema  # Pass schema to service
                )
            elif hasattr(service, 'call_structured'):
                # Fallback to JSON schema structured output
                result = service.call_structured(
                    prompt=prompt,
                    input_text=text,
                    schema=self._convert_to_strict_schema(current_schema),
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
            
            # Apply completeness validation AFTER LLM processing
            if result.get("success") and "structured_data" in result:
                result["structured_data"] = self._validate_and_mark_completeness(result["structured_data"])
                
                # Validate against schema
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
        """Load the parcel schema from plss_m_and_b.json (dynamic schema loading)"""
        try:
            # Use more robust path resolution
            current_file = Path(__file__)
            backend_dir = current_file.parent.parent.parent  # Go up to backend/
            schema_path = backend_dir / "schema" / "plss_m_and_b.json"
            
            # Ensure the path is absolute and resolved
            schema_path = schema_path.resolve()
            
            logger.debug(f"Loading parcel schema from: {schema_path}")
            
            if not schema_path.exists():
                logger.error(f"Schema file does not exist: {schema_path}")
                return {}
                
            with open(schema_path, 'r') as f:
                schema_data = json.load(f)
                logger.debug(f"Loaded schema with {len(schema_data)} keys")
                return schema_data
                
        except FileNotFoundError:
            logger.error(f"Parcel schema file not found at {schema_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema file: {str(e)}")
            return {}
        except Exception as e:
            logger.error(f"Error loading parcel schema: {str(e)}")
            return {}
    
    def _validate_and_mark_completeness(self, parcel_data: dict) -> dict:
        """
        Validate and mark completeness for all descriptions in a parcel
        This is the business logic for completeness - not hardcoded in OpenAI service
        """
        if 'descriptions' not in parcel_data:
            return parcel_data
            
        ESSENTIAL_PLSS = ["state", "county", "principal_meridian",
                          "township_number", "township_direction",
                          "range_number", "range_direction", "section_number"]
        
        for desc in parcel_data['descriptions']:
            if 'plss' in desc and 'metes_and_bounds' in desc:
                # Check PLSS completeness
                plss_ok = all(desc["plss"].get(k) is not None for k in ESSENTIAL_PLSS)
                
                # Check metes and bounds completeness (need at least 3 courses for polygon)
                mb_ok = len(desc["metes_and_bounds"].get("boundary_courses", [])) >= 3
                
                # Check POB completeness
                sp = desc["plss"]["starting_point"]
                pob_ok = sp["pob_status"] in {"explicit", "deducible", "resolved"}

                # Add QC advisories (non-blocking)
                qc_advisories = []
                if pob_ok and sp["pob_status"] == "deducible" and sp.get("tie_to_corner"):
                    main_range = desc["plss"].get("range_number")
                    tie_corner = sp["tie_to_corner"].get("corner_label", "")
                    
                    # Extract range from corner label (e.g., "NW corner Sec 2 T14N R74W")
                    range_match = re.search(r'R(\d+)W', tie_corner)
                    if range_match and main_range:
                        tie_range = int(range_match.group(1))
                        range_diff = abs(tie_range - main_range)
                        
                        if range_diff == 1:
                            # Adjacent range - normal survey practice
                            qc_advisories.append({
                                "type": "range_adjacent",
                                "severity": "info",
                                "field": "starting_point.tie_to_corner",
                                "message": f"POB tied to adjacent range corner (R{tie_range}W) while parcel is in R{main_range}W—normal survey practice",
                                "blocking": False
                            })
                        elif range_diff > 1:
                            # Potentially problematic range difference
                            qc_advisories.append({
                                "type": "range_mismatch",
                                "severity": "warning", 
                                "field": "starting_point.tie_to_corner",
                                "message": f"Range difference of {range_diff} between PLSS (R{main_range}W) and tie corner (R{tie_range}W)—review if unexpected",
                                "blocking": False
                            })

                # Add advisories to description (non-blocking)
                if qc_advisories:
                    desc["qc_advisories"] = qc_advisories

                # Update completeness flag (advisories don't affect completeness)
                desc["is_complete"] = plss_ok and mb_ok and pob_ok
                
                logger.info(f"Description {desc.get('description_id')}: PLSS={plss_ok}, M&B={mb_ok}, POB={pob_ok}, Complete={desc['is_complete']}")
        
        return parcel_data
    
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
        """Basic validation of parcel data against NEW v0.2 schema requirements"""
        errors = []
        warnings = []
        
        # Check required fields from NEW schema (v0.2)
        required_fields = ["parcel_id", "descriptions", "source"]
        
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Validate descriptions array
        if "descriptions" in data and isinstance(data["descriptions"], list):
            if len(data["descriptions"]) == 0:
                errors.append("Descriptions array cannot be empty")
            
            for i, desc in enumerate(data["descriptions"]):
                if not isinstance(desc, dict):
                    errors.append(f"Description {i} must be an object")
                    continue
                
                # Check required description fields
                desc_required = ["description_id", "is_complete", "plss", "metes_and_bounds"]
                for field in desc_required:
                    if field not in desc:
                        errors.append(f"Description {i} missing required field: {field}")
                
                # Validate PLSS structure
                if "plss" in desc and isinstance(desc["plss"], dict):
                    plss_required = ["state", "county", "principal_meridian", "township_number", 
                                   "township_direction", "range_number", "range_direction", 
                                   "section_number", "starting_point", "raw_text"]
                    for field in plss_required:
                        if field not in desc["plss"]:
                            errors.append(f"Description {i} PLSS missing required field: {field}")
                
                # Validate metes_and_bounds structure
                if "metes_and_bounds" in desc and isinstance(desc["metes_and_bounds"], dict):
                    if "boundary_courses" not in desc["metes_and_bounds"]:
                        errors.append(f"Description {i} metes and bounds missing boundary_courses")
                    elif not isinstance(desc["metes_and_bounds"]["boundary_courses"], list):
                        errors.append(f"Description {i} boundary courses must be an array")
                    else:
                        for j, course in enumerate(desc["metes_and_bounds"]["boundary_courses"]):
                            if not isinstance(course, dict):
                                errors.append(f"Description {i} boundary course {j} must be an object")
                                continue
                                
                            course_required = ["course", "distance", "distance_units", "raw_text"]
                            for field in course_required:
                                if field not in course:
                                    errors.append(f"Description {i} boundary course {j} missing required field: {field}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def _standardize_response(self, result: dict, model: str, service) -> dict:
        """Standardize response format across different services"""
        if not result.get("success", False):
            return result
        
        # Get completeness summary for metadata
        completeness_summary = self._get_completeness_summary(result.get("structured_data", {}))
            
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
                "schema_version": "parcel_v0.2",
                "completeness_summary": completeness_summary,
                "processing_time": result.get("processing_time"),
                **result.get("metadata", {})
            }
        }
    
    def _get_completeness_summary(self, parcel_data: dict) -> dict:
        """Get summary of completeness status for all descriptions"""
        if 'descriptions' not in parcel_data:
            return {"total_descriptions": 0, "complete_descriptions": 0, "incomplete_descriptions": 0}
        
        total = len(parcel_data['descriptions'])
        complete = sum(1 for desc in parcel_data['descriptions'] if desc.get('is_complete', False))
        incomplete = total - complete
        incomplete_ids = [desc.get('description_id') for desc in parcel_data['descriptions'] 
                         if not desc.get('is_complete', False)]
        
        return {
            "total_descriptions": total,
            "complete_descriptions": complete,
            "incomplete_descriptions": incomplete,
            "incomplete_ids": incomplete_ids,
            "all_complete": incomplete == 0
        }
    
    def get_schema_template(self) -> dict:
        """Get the parcel schema template"""
        # Reload schema from disk to get latest version
        return self._load_parcel_schema()
    
    def get_available_models(self) -> dict:
        """Get models available for text-to-schema processing"""
        all_models = self.registry.get_all_models()
        
        # Filter for models that can process text
        text_models = {}
        for model_id, model_info in all_models.items():
            if "text" in model_info.get("capabilities", []):
                text_models[model_id] = model_info
                
        return text_models 