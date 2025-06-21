"""
LLM Processor Module
Handles text interpretation, formatting, and multi-model comparison
"""
import json
from services.llm_service import get_llm_service
from services.llm_profiles import LLMProfile

class LLMProcessor:
    def __init__(self):
        self.llm_service = get_llm_service("openai")
    
    async def text_to_parcel_schema(self, text: str, schema: dict, parcel_id: str = None) -> dict:
        """Convert legal description text to structured parcel JSON schema"""
        if not self.llm_service.is_configured():
            raise Exception("OpenAI client not configured")
            
        # Generate parcel_id if not provided
        if not parcel_id or parcel_id == "auto-generated":
            import uuid
            parcel_id = f"parcel_{str(uuid.uuid4())[:8]}"
        
        # Create the system prompt
        system_prompt = f"""You are an expert at parsing legal property descriptions into structured data.

Convert the provided legal description text into JSON that EXACTLY matches this schema:

{json.dumps(schema, indent=2)}

CRITICAL REQUIREMENTS:
1. Extract bearing and distance from each boundary description
2. Use "LOCAL" for crs if coordinates are unclear
3. Set close to true if the description returns to the starting point
4. Include confidence scores (0.0-1.0) for each extracted leg based on clarity of the text
5. Use the provided parcel_id

FOR DISTANCE AND UNITS:
- Extract the EXACT distance value as stated (don't convert)
- Identify the unit: "feet", "meters", "yards", "chains", "rods", "miles", "kilometers"
- Example: "100 feet" → distance: 100, distance_units: "feet"

FOR MISSING INFORMATION, USE null:
- If a field is not mentioned in the text, set it to null
- Only provide actual values when they are explicitly stated or can be clearly inferred
- For origin.type: Use "local" if unclear about coordinate system
- For origin.corner: Use null if not specified (don't guess)
- For legs.raw_text: Copy the relevant portion of the legal description
- For distance_units: Use "feet" as default only if distance is given but unit is unclear

Example bearing formats: "North 45 degrees East" = 45, "South" = 180, "West" = 270

The goal is to extract what IS clearly stated in the text and use null for what ISN'T."""

        user_prompt = f"""Legal Description Text:
{text}

Parcel ID: {parcel_id}

Convert this to the required JSON schema format."""

        try:
            # Use the schema call method
            success, error, result = self.llm_service.make_schema_call(
                text=user_prompt,
                schema=schema,
                profile=LLMProfile.TEXT_TO_SCHEMA,
                system_prompt=system_prompt
            )
            
            if not success:
                raise Exception(f"LLM service error: {error}")
            
            # Return the structured data if available, otherwise parse from content
            if 'structured_data' in result:
                return result['structured_data']
            else:
                # Fallback: parse JSON from content
                parcel_data = json.loads(result['content'])
                return parcel_data
            
        except Exception as e:
            raise Exception(f"Failed to process text with LLM: {str(e)}")
    
    def parse_legal_text(self, text: str) -> dict:
        """Parse legal description text using OpenAI"""
        if not self.llm_service.is_configured():
            return {"error": "OpenAI client not configured"}
            
        try:
            success, error, result = self.llm_service.make_text_call(
                user_prompt=f"Parse this legal description: {text}",
                profile=LLMProfile.FAST_PROCESSING,
                system_prompt="You are an expert at parsing legal property descriptions. Extract structured data from metes and bounds descriptions."
            )
            
            if not success:
                return {"error": error, "success": False}
            
            return {
                "parsed": result['content'],
                "model": result['usage'].get('model', 'openai'),
                "success": True
            }
        except Exception as e:
            return {"error": str(e), "success": False}
    
    def compare_interpretations(self, text: str) -> dict:
        """Compare interpretations from multiple LLMs"""
        results = {}
        
        # OpenAI interpretation
        if self.llm_service.is_configured():
            results["openai"] = self.parse_legal_text(text)
            
        # Future: Add Anthropic interpretation
        # if self.anthropic_client:
        #     results["anthropic"] = self.parse_with_anthropic(text)
            
        return {"comparisons": results} 