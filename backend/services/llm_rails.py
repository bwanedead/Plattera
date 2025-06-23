"""
LLM Rails - Foundation setup for making API calls to different LLM providers
Handles the common boilerplate: client setup, authentication, error handling, response parsing
"""
import os
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI
from anthropic import Anthropic

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
    """Foundation setup for Anthropic API calls"""
    
    def __init__(self):
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Anthropic client with API key"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.client = Anthropic(api_key=api_key)
    
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
            Anthropic response object
        
        Raises:
            Exception: If API call fails
        """
        self._ensure_client()
        if not self.is_configured():
            raise Exception("Anthropic client not configured - API key missing")
        
        try:
            # Convert OpenAI-style messages to Anthropic format
            anthropic_messages = self._convert_messages_to_anthropic(messages)
            system_message = self._extract_system_message(messages)
            
            # Remove parameters that Anthropic doesn't support
            anthropic_params = self._convert_params_to_anthropic(params)
            
            response = self.client.messages.create(
                system=system_message,
                messages=anthropic_messages,
                **anthropic_params
            )
            return response
        except Exception as e:
            # Common error handling for all Anthropic calls
            raise Exception(f"Anthropic API call failed: {str(e)}")
    
    def _convert_messages_to_anthropic(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style messages to Anthropic format"""
        anthropic_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                continue  # System messages handled separately
            elif msg["role"] == "user":
                # Handle vision messages (images)
                if isinstance(msg.get("content"), list):
                    content = []
                    for item in msg["content"]:
                        if item["type"] == "text":
                            content.append({
                                "type": "text",
                                "text": item["text"]
                            })
                        elif item["type"] == "image_url":
                            # Extract base64 data and format
                            image_url = item["image_url"]["url"]
                            if image_url.startswith("data:image/"):
                                # Parse data URL: data:image/png;base64,<data>
                                header, data = image_url.split(",", 1)
                                media_type = header.split(";")[0].replace("data:", "")
                                
                                content.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": data
                                    }
                                })
                    anthropic_messages.append({
                        "role": "user",
                        "content": content
                    })
                else:
                    anthropic_messages.append({
                        "role": "user", 
                        "content": msg["content"]
                    })
            elif msg["role"] == "assistant":
                anthropic_messages.append({
                    "role": "assistant",
                    "content": msg["content"]
                })
        
        return anthropic_messages
    
    def _extract_system_message(self, messages: List[Dict[str, Any]]) -> str:
        """Extract system message for Anthropic"""
        for msg in messages:
            if msg["role"] == "system":
                return msg["content"]
        return ""
    
    def _convert_params_to_anthropic(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert OpenAI parameters to Anthropic format"""
        anthropic_params = {}
        
        # Map OpenAI params to Anthropic equivalents
        param_mapping = {
            "model": "model",
            "max_tokens": "max_tokens",
            "temperature": "temperature",
            "top_p": "top_p"
        }
        
        for openai_param, anthropic_param in param_mapping.items():
            if openai_param in params:
                anthropic_params[anthropic_param] = params[openai_param]
        
        # Set default max_tokens if not provided (required by Anthropic)
        if "max_tokens" not in anthropic_params:
            anthropic_params["max_tokens"] = 4000
        
        return anthropic_params
    
    def parse_response(self, response) -> Dict[str, Any]:
        """
        Parse Anthropic response into common format
        """
        content = response.content[0].text if response.content else ""
        
        # DEBUG: Check what we're getting
        print(f"DEBUG: Response model: {response.model}")
        print(f"DEBUG: Stop reason: {response.stop_reason}")
        print(f"DEBUG: Content type: {type(content)}")
        print(f"DEBUG: Content length: {len(content) if content else 'None'}")
        if content:
            print(f"DEBUG: Content preview: {repr(content[:100])}")
        else:
            print("DEBUG: Content is None or empty!")
        
        # Parse usage
        usage_data = {
            'prompt_tokens': response.usage.input_tokens,
            'completion_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens
        }
        
        return {
            'content': content,
            'model': response.model,
            'usage': usage_data
        }
    
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Test Anthropic connection"""
        try:
            response = self.make_completion_call(
                messages=[{"role": "user", "content": "Test connection - respond with 'OK'"}],
                model="claude-3-5-haiku-20241022",
                max_tokens=10,
                temperature=0
            )
            result = self.parse_response(response)
            return True, None, result
        except Exception as e:
            return False, str(e), None


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