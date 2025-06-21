"""
LLM Service - High-level interface that combines rails and profiles
This is what the core processors will actually use
"""
from typing import Dict, Any, Optional, Tuple, List
from .llm_rails import get_llm_rails
from .llm_profiles import LLMProfile, ProfileConfig, MessageBuilder

class LLMService:
    """High-level LLM service that combines rails and profiles"""
    
    def __init__(self, provider: str = "openai"):
        self.provider = provider
        self.rails = get_llm_rails(provider)
    
    def is_configured(self) -> bool:
        """Check if service is configured"""
        return self.rails.is_configured()
    
    def make_vision_call(self, 
                        text_prompt: str,
                        image_base64: str,
                        profile: LLMProfile = LLMProfile.VISION_LEGAL_EXTRACTION,
                        system_prompt: str = None,
                        **overrides) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Make a vision API call"""
        try:
            # Get profile configuration
            config = ProfileConfig.get_profile_config(self.provider, profile)
            config.update(overrides)
            
            # Build messages
            messages = MessageBuilder.build_vision_messages(text_prompt, image_base64, system_prompt)
            
            # Make API call
            response = self.rails.make_completion_call(messages, **config)
            
            # Parse response
            result = self.rails.parse_response(response)
            
            return True, None, result
            
        except Exception as e:
            return False, str(e), None
    
    def make_text_call(self,
                      user_prompt: str,
                      profile: LLMProfile = LLMProfile.GENERAL_REASONING,
                      system_prompt: str = None,
                      **overrides) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Make a text-only API call"""
        try:
            # Get profile configuration
            config = ProfileConfig.get_profile_config(self.provider, profile)
            config.update(overrides)
            
            # Build messages
            messages = MessageBuilder.build_text_messages(user_prompt, system_prompt)
            
            # Make API call
            response = self.rails.make_completion_call(messages, **config)
            
            # Parse response
            result = self.rails.parse_response(response)
            
            return True, None, result
            
        except Exception as e:
            return False, str(e), None
    
    def make_schema_call(self,
                        text: str,
                        schema: Dict[str, Any],
                        profile: LLMProfile = LLMProfile.TEXT_TO_SCHEMA,
                        system_prompt: str = None,
                        **overrides) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Make a text-to-schema API call"""
        try:
            # Get profile configuration
            config = ProfileConfig.get_profile_config(self.provider, profile)
            config.update(overrides)
            
            # For structured output, add response format if using compatible model
            if config.get("model", "").startswith("gpt-4o") and "response_format" not in config:
                config["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "strict": True,
                        "schema": schema
                    }
                }
            
            # Build messages
            messages = MessageBuilder.build_schema_messages(text, schema, system_prompt)
            
            # Make API call
            response = self.rails.make_completion_call(messages, **config)
            
            # Parse response
            result = self.rails.parse_response(response)
            
            # Try to parse JSON content
            try:
                import json
                content = result['content'].strip()
                # Find JSON in response (handle cases where there might be extra text)
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = content[start_idx:end_idx]
                    structured_data = json.loads(json_str)
                else:
                    structured_data = json.loads(content)
                
                result['structured_data'] = structured_data
            except json.JSONDecodeError:
                # If JSON parsing fails, leave the raw content
                pass
            
            return True, None, result
            
        except Exception as e:
            return False, str(e), None
    
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Test the service connection"""
        return self.rails.test_connection()
    
    def get_available_profiles(self) -> List[LLMProfile]:
        """Get available profiles for this provider"""
        return ProfileConfig.get_available_profiles(self.provider)


# Global service instance (singleton pattern)
_llm_service = None

def get_llm_service(provider: str = "openai") -> LLMService:
    """Get the global LLM service instance"""
    global _llm_service
    if _llm_service is None or _llm_service.provider != provider:
        _llm_service = LLMService(provider)
    return _llm_service 