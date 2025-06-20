"""
LLM Processor Module
Handles text interpretation, formatting, and multi-model comparison
"""
import os
import json
from openai import OpenAI
# from anthropic import Anthropic  # Uncomment when ready

class LLMProcessor:
    def __init__(self):
        # Initialize LLM clients with API keys from environment
        self.openai_client = None
        self.anthropic_client = None
        
        # OpenAI setup
        if os.getenv("OPENAI_API_KEY"):
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        else:
            print("Warning: OPENAI_API_KEY not found in environment")
            
        # Anthropic setup (for future use)
        # if os.getenv("ANTHROPIC_API_KEY"):
        #     self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    async def text_to_parcel_schema(self, text: str, schema: dict, parcel_id: str = None) -> dict:
        """Convert legal description text to structured parcel JSON schema"""
        if not self.openai_client:
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

FOR MISSING INFORMATION, USE THESE DEFAULTS:
- Numbers: Use 0 if not mentioned in the text
- Strings: Use empty string "" if not mentioned
- For origin.type: Use "local" if unclear
- For origin.corner: Use "NW" if not specified
- For legs.raw_text: Copy the relevant portion of the legal description

Example bearing formats: "North 45 degrees East" = 45, "South" = 180, "West" = 270

The goal is to extract what IS in the text and use sensible defaults for what ISN'T."""

        user_prompt = f"""Legal Description Text:
{text}

Parcel ID: {parcel_id}

Convert this to the required JSON schema format."""

        try:
            # Use gpt-4o (not mini) for structured outputs
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-2024-08-06",  # Correct model for structured outputs
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "parcel_schema",
                        "strict": True,  # Required for structured outputs
                        "schema": schema
                    }
                },
                max_tokens=2000,
                temperature=0.1
            )
            
            # Parse the response as JSON
            parcel_data = json.loads(response.choices[0].message.content)
            return parcel_data
            
        except Exception as e:
            raise Exception(f"Failed to process text with LLM: {str(e)}")
    
    def parse_legal_text(self, text: str) -> dict:
        """Parse legal description text using OpenAI"""
        if not self.openai_client:
            return {"error": "OpenAI client not configured"}
            
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert at parsing legal property descriptions. Extract structured data from metes and bounds descriptions."},
                    {"role": "user", "content": f"Parse this legal description: {text}"}
                ],
                max_tokens=1000
            )
            
            return {
                "parsed": response.choices[0].message.content,
                "model": "gpt-3.5-turbo",
                "success": True
            }
        except Exception as e:
            return {"error": str(e), "success": False}
    
    def compare_interpretations(self, text: str) -> dict:
        """Compare interpretations from multiple LLMs"""
        results = {}
        
        # OpenAI interpretation
        if self.openai_client:
            results["openai"] = self.parse_legal_text(text)
            
        # Future: Add Anthropic interpretation
        # if self.anthropic_client:
        #     results["anthropic"] = self.parse_with_anthropic(text)
            
        return {"comparisons": results} 