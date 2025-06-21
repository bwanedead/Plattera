"""
LLM Profiles - Specific configurations for different types of API calls
Defines the exact parameters, models, and message formats for each use case
"""
from typing import Dict, Any, List
from enum import Enum

class LLMProfile(Enum):
    """Available LLM profiles for different use cases"""
    VISION_LEGAL_EXTRACTION = "vision_legal_extraction"
    TEXT_TO_SCHEMA = "text_to_schema"
    GENERAL_REASONING = "general_reasoning"
    FAST_PROCESSING = "fast_processing"

class ProfileConfig:
    """Configuration for LLM profiles"""
    
    # OpenAI profile configurations
    OPENAI_PROFILES = {
        LLMProfile.VISION_LEGAL_EXTRACTION: {
            "model": "o3",
            "temperature": 0.1,
            "max_tokens": 4000,
            "top_p": 0.95,
            "reasoning_effort": "high"
        },
        LLMProfile.TEXT_TO_SCHEMA: {
            "model": "gpt-4o-2024-08-06",
            "temperature": 0.0,
            "max_tokens": 2000,
            "top_p": 0.9
        },
        LLMProfile.GENERAL_REASONING: {
            "model": "o3",
            "temperature": 0.3,
            "max_tokens": 3000,
            "reasoning_effort": "medium"
        },
        LLMProfile.FAST_PROCESSING: {
            "model": "gpt-4o",
            "temperature": 0.1,
            "max_tokens": 1500
        }
    }
    
    # Future: Anthropic profile configurations
    ANTHROPIC_PROFILES = {
        # Will be added when we implement Anthropic
    }
    
    @classmethod
    def get_profile_config(cls, provider: str, profile: LLMProfile) -> Dict[str, Any]:
        """Get configuration for a specific provider and profile"""
        if provider == "openai":
            return cls.OPENAI_PROFILES.get(profile, cls.OPENAI_PROFILES[LLMProfile.GENERAL_REASONING]).copy()
        elif provider == "anthropic":
            return cls.ANTHROPIC_PROFILES.get(profile, {}).copy()
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    @classmethod
    def get_available_profiles(cls, provider: str) -> List[LLMProfile]:
        """Get list of available profiles for a provider"""
        if provider == "openai":
            return list(cls.OPENAI_PROFILES.keys())
        elif provider == "anthropic":
            return list(cls.ANTHROPIC_PROFILES.keys())
        else:
            return []

class MessageBuilder:
    """Helper class to build messages for different profile types"""
    
    @staticmethod
    def build_vision_messages(text_prompt: str, image_base64: str, system_prompt: str = None) -> List[Dict[str, Any]]:
        """Build messages for vision API calls"""
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": text_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                        "detail": "high"
                    }
                }
            ]
        })
        
        return messages
    
    @staticmethod
    def build_text_messages(user_prompt: str, system_prompt: str = None) -> List[Dict[str, Any]]:
        """Build messages for text-only API calls"""
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": user_prompt
        })
        
        return messages
    
    @staticmethod
    def build_schema_messages(text: str, schema: Dict[str, Any], system_prompt: str = None) -> List[Dict[str, Any]]:
        """Build messages for text-to-schema API calls"""
        import json
        
        if not system_prompt:
            system_prompt = f"""Convert the provided text into JSON that matches this schema:

{json.dumps(schema, indent=2)}

Return only valid JSON."""
        
        return MessageBuilder.build_text_messages(
            user_prompt=f"Text to convert:\n{text}",
            system_prompt=system_prompt
        ) 