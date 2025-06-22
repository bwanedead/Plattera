"""
LLM Rails - Foundation setup for making API calls to different LLM providers
Handles the common boilerplate: client setup, authentication, error handling, response parsing
"""
import os
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI
# from anthropic import Anthropic  # Future

class OpenAIRails:
    """Foundation setup for OpenAI API calls"""
    
    def __init__(self):
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize OpenAI client with API key"""
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key)
    
    def _ensure_client(self):
        """Ensure client is initialized, try to reinitialize if not"""
        if self.client is None:
            self._initialize_client()
    
    def is_configured(self) -> bool:
        """Check if client is properly configured"""
        self._ensure_client()
        return self.client is not None
    
    def make_completion_call(self, messages: List[Dict[str, Any]], **params) -> Any:
        """
        Make a completion API call with error handling
        
        Args:
            messages: List of message dictionaries
            **params: Model parameters (temperature, max_tokens, etc.)
        
        Returns:
            OpenAI response object
        
        Raises:
            Exception: If API call fails
        """
        self._ensure_client()
        if not self.is_configured():
            raise Exception("OpenAI client not configured - API key missing")
        
        try:
            response = self.client.chat.completions.create(
                messages=messages,
                **params
            )
            return response
        except Exception as e:
            # Common error handling for all OpenAI calls
            raise Exception(f"OpenAI API call failed: {str(e)}")
    
    def parse_response(self, response) -> Dict[str, Any]:
        """
        Parse OpenAI response into common format
        """
        choice = response.choices[0]
        content = choice.message.content
        
        # DEBUG: Check what we're getting
        print(f"DEBUG: Response model: {response.model}")
        print(f"DEBUG: Finish reason: {choice.finish_reason}")
        print(f"DEBUG: Content type: {type(content)}")
        print(f"DEBUG: Content length: {len(content) if content else 'None'}")
        if content:
            print(f"DEBUG: Content preview: {repr(content[:100])}")
        else:
            print("DEBUG: Content is None or empty!")
        
        # Handle None content
        if content is None:
            content = ""
        
        # Parse usage
        usage_data = {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
        
        # Add reasoning tokens if present (o3 models)
        if hasattr(response.usage, 'completion_tokens_details'):
            details = response.usage.completion_tokens_details
            if hasattr(details, 'reasoning_tokens'):
                usage_data['reasoning_tokens'] = details.reasoning_tokens
        
        return {
            'content': content,
            'model': response.model,
            'usage': usage_data
        }
    
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Test OpenAI connection"""
        try:
            response = self.make_completion_call(
                messages=[{"role": "user", "content": "Test connection - respond with 'OK'"}],
                model="gpt-4o-mini",
                max_tokens=10,
                temperature=0
            )
            result = self.parse_response(response)
            return True, None, result
        except Exception as e:
            return False, str(e), None


class AnthropicRails:
    """Foundation setup for Anthropic API calls (future implementation)"""
    
    def __init__(self):
        self.client = None
        # Future: Initialize Anthropic client
    
    def is_configured(self) -> bool:
        return False  # Not implemented yet
    
    def make_completion_call(self, messages: List[Dict[str, Any]], **params) -> Any:
        raise NotImplementedError("Anthropic integration not implemented yet")
    
    def parse_response(self, response) -> Dict[str, Any]:
        raise NotImplementedError("Anthropic integration not implemented yet")


# Factory function to get the right rails
def get_llm_rails(provider: str):
    """Get LLM rails for a specific provider"""
    rails_map = {
        "openai": OpenAIRails,
        "anthropic": AnthropicRails
    }
    
    if provider not in rails_map:
        raise ValueError(f"Unknown LLM provider: {provider}")
    
    return rails_map[provider]() 