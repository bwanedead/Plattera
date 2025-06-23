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
    
    # Base profile configurations (model-agnostic)
    BASE_PROFILES = {
        LLMProfile.VISION_LEGAL_EXTRACTION: {
            "temperature": 0.1,
            "max_tokens": 8000,
            "top_p": 0.95
        },
        LLMProfile.TEXT_TO_SCHEMA: {
            "temperature": 0.0,
            "max_tokens": 2000,
            "top_p": 0.9
        },
        LLMProfile.GENERAL_REASONING: {
            "temperature": 0.3,
            "max_tokens": 3000
        },
        LLMProfile.FAST_PROCESSING: {
            "temperature": 0.1,
            "max_tokens": 1500
        }
    }
    
    # Model-specific parameters and restrictions
    MODEL_SPECIFIC_PARAMS = {
        "o3": {
            "reasoning_effort": {
                LLMProfile.VISION_LEGAL_EXTRACTION: "low",
                LLMProfile.TEXT_TO_SCHEMA: "medium", 
                LLMProfile.GENERAL_REASONING: "medium",
                LLMProfile.FAST_PROCESSING: "low"
            },
            # o3 restrictions: only these parameters are allowed
            "allowed_params": ["model", "max_completion_tokens", "reasoning_effort"],
            "token_param": "max_completion_tokens",
            "fixed_params": {
                "temperature": 1.0,  # Default, cannot be changed
                "top_p": 1.0        # Default, cannot be changed
            }
        },
        "gpt-4o": {
            "token_param": "max_tokens",
            "allowed_params": ["model", "temperature", "max_tokens", "top_p"]
        },
        "gpt-4o-2024-08-06": {
            "token_param": "max_tokens", 
            "allowed_params": ["model", "temperature", "max_tokens", "top_p"]
        }
    }
    
    @classmethod
    def get_profile_config(cls, provider: str, profile: LLMProfile, model: str = None) -> Dict[str, Any]:
        """Get configuration for a specific provider, profile, and model"""
        if provider != "openai":
            raise ValueError(f"Unknown provider: {provider}")
        
        # Start with base profile config
        config = cls.BASE_PROFILES.get(profile, cls.BASE_PROFILES[LLMProfile.GENERAL_REASONING]).copy()
        
        # Set default model if none provided
        if not model:
            model = "gpt-4o"  # Default to gpt-4o
        
        config["model"] = model
        
        # Handle model-specific parameters and restrictions
        if model in cls.MODEL_SPECIFIC_PARAMS:
            model_params = cls.MODEL_SPECIFIC_PARAMS[model]
            
            # Handle token parameter naming (o3 uses max_completion_tokens)
            if "token_param" in model_params:
                token_param = model_params["token_param"]
                if token_param != "max_tokens" and "max_tokens" in config:
                    # Move max_tokens to the correct parameter name for this model
                    config[token_param] = config.pop("max_tokens")
            
            # Apply fixed parameters (like temperature=1.0 for o3)
            if "fixed_params" in model_params:
                config.update(model_params["fixed_params"])
            
            # Add reasoning_effort for o3 models
            if "reasoning_effort" in model_params and profile in model_params["reasoning_effort"]:
                config["reasoning_effort"] = model_params["reasoning_effort"][profile]
            
            # Filter to only allowed parameters for this model
            if "allowed_params" in model_params:
                allowed = model_params["allowed_params"]
                config = {k: v for k, v in config.items() if k in allowed}
        
        return config
    
    @classmethod
    def get_available_profiles(cls, provider: str) -> List[LLMProfile]:
        """Get list of available profiles for a provider"""
        if provider == "openai":
            return list(cls.BASE_PROFILES.keys())
        else:
            return []
    
    @classmethod
    def get_supported_models(cls) -> Dict[str, Dict[str, Any]]:
        """Get list of supported models with their capabilities"""
        return {
            "gpt-4o": {
                "name": "GPT-4o",
                "description": "Fast, cost-effective vision model optimized for document OCR",
                "capabilities": ["vision", "text", "fast_processing"],
                "cost_tier": "standard",
                "verification_required": False,
                "supports_reasoning_effort": False
            },
            "gpt-4o-2024-08-06": {
                "name": "GPT-4o (August 2024)",
                "description": "Stable version with consistent performance and structured output support",
                "capabilities": ["vision", "text", "structured_output"],
                "cost_tier": "standard", 
                "verification_required": False,
                "supports_reasoning_effort": False
            },
            "o3": {
                "name": "o3",
                "description": "Most advanced reasoning model with highest accuracy",
                "capabilities": ["vision", "text", "advanced_reasoning", "high_accuracy"],
                "cost_tier": "premium",
                "verification_required": True,
                "supports_reasoning_effort": True
            }
        }

class MessageBuilder:
    """Helper class to build messages for different profile types"""
    
    @staticmethod
    def build_vision_messages(text_prompt: str, image_base64: str, system_prompt: str = None, image_format: str = "jpeg") -> List[Dict[str, Any]]:
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
                        "url": f"data:image/{image_format};base64,{image_base64}",
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