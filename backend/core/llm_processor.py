"""
LLM Processor Module
Handles text interpretation, formatting, and multi-model comparison
"""
import os
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