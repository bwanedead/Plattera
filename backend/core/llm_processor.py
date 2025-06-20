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
        
        # Create the prompt with schema context
        system_prompt = f"""You are an expert at parsing legal property descriptions into structured data.

Convert the provided legal description text into JSON that EXACTLY matches this schema:

{json.dumps(schema, indent=2)}

CRITICAL REQUIREMENTS:
1. Return ONLY valid JSON - no markdown, comments, or explanations
2. ALL required fields must be present: parcel_id, crs, origin, legs, close
3. Use "LOCAL" for crs if coordinates are unclear
4. Extract bearing and distance from each boundary description
5. Set close to true if the description returns to the starting point
6. Include confidence scores (0.0-1.0) for each extracted leg

Example bearing formats: "North 45 degrees East" = 45, "South" = 180, "West" = 270"""

        user_prompt = f"""Legal Description Text:
{text}

Parcel ID: {parcel_id}

Convert this to the required JSON schema format."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",  # Using GPT-4 for better structured output
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=2000,
                temperature=0.1  # Low temperature for consistent output
            )
            
            # Parse the response as JSON
            response_text = response.choices[0].message.content.strip()
            
            # Remove any markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            parcel_data = json.loads(response_text)
            return parcel_data
            
        except json.JSONDecodeError as e:
            raise Exception(f"LLM response was not valid JSON: {str(e)}")
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