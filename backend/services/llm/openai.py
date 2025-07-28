"""
OpenAI LLM Provider
Drop this file in services/llm/ and OpenAI models will automatically appear

🔴 CRITICAL REDUNDANCY IMPLEMENTATION DOCUMENTATION 🔴
=====================================================

THIS MODULE IS THE FINAL LINK IN THE CHAIN - PRESERVE ALL WIRING BELOW 🔴

CRITICAL INTEGRATION POINTS:
1. Pipeline calls: service.process_image_with_text()
2. This method wraps: call_vision()
3. call_vision() formats data for OpenAI API
4. OpenAI API returns text content
5. process_image_with_text() standardizes response

CRITICAL API WIRING:
- OpenAI vision API expects: data:image/jpeg;base64,{base64_string}
- Pipeline provides: clean base64 string (no prefix)
- This service adds: data URI prefix in call_vision()
- OpenAI returns: text content in response.choices[0].message.content

CRITICAL RESPONSE FORMAT:
process_image_with_text() MUST return:
{
    "success": True,
    "extracted_text": "...",  # CRITICAL: Frontend dependency
    "tokens_used": 6561,
    "model_used": "gpt-4o",
    "service_type": "llm",
    "confidence_score": 1.0,
    "metadata": {...}
}

ENHANCEMENT SAFETY RULES:
- NEVER change process_image_with_text() signature
- NEVER modify "extracted_text" field mapping
- NEVER change data URI prefix format
- ALWAYS preserve response standardization
- ALWAYS maintain backward compatibility

REDUNDANCY IMPLEMENTATION SAFETY RULES:
======================================

✅ SAFE FOR REDUNDANCY:
- process_image_with_text() is THREAD-SAFE for parallel calls
- call_vision() can be called multiple times simultaneously
- Response format is consistent across all calls
- Error handling is robust for individual call failures

❌ DO NOT MODIFY FOR REDUNDANCY:
- process_image_with_text() method signature
- call_vision() method signature  
- Response format structure
- Error handling patterns
- Data URI formatting logic

CRITICAL REDUNDANCY REQUIREMENTS:
================================
1. Service MUST handle multiple parallel calls to process_image_with_text()
2. Each call MUST be independent (no shared state)
3. Response format MUST be identical across all calls
4. Error handling MUST work for individual call failures
5. Token counting MUST be accurate for each call

THREADING SAFETY VERIFICATION:
=============================
- OpenAI client is thread-safe ✓
- No shared mutable state in methods ✓
- Each call creates independent request ✓
- Response processing is stateless ✓

TESTING CHECKPOINTS:
===================
After redundancy implementation, verify:
1. Single calls still work unchanged
2. Multiple parallel calls work correctly
3. Error handling works for individual failures
4. Token counting is accurate across calls
5. Response format remains consistent
"""
import os
import base64
import json
from typing import Dict, Any, List, Optional, Union
from services.llm.base import LLMService
from pydantic import BaseModel
import time
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

# Only import if available
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Remove the hardcoded Pydantic models (lines 103-133)
# class ParcelOrigin(BaseModel):  # DELETE THESE
# class ParcelLeg(BaseModel):     # DELETE THESE  
# class PlatteraParcel(BaseModel): # DELETE THESE

class OpenAIService(LLMService):
    """OpenAI LLM service provider"""
    
    name = "openai"
    
    models = {
        "gpt-4o": {
            "name": "GPT-4o",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["vision", "text"],
            "description": "Most reliable for structured outputs and vision tasks",
            "verification_required": False
        },
        "gpt-o4-mini": {
            "name": "GPT-o4-mini",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["vision", "text"],
            "description": "Lightweight, fast model with reasoning capabilities",
            "verification_required": False,
            "api_model_name": "o4-mini-2025-04-16"
        },
        "o3": {
            "name": "o3", 
            "provider": "openai",
            "cost_tier": "premium",
            "capabilities": ["vision", "text", "reasoning"],
            "description": "Most advanced reasoning model with highest accuracy",
            "verification_required": True
        },
        "gpt-4": {
            "name": "GPT-4",
            "provider": "openai", 
            "cost_tier": "standard",
            "capabilities": ["text"],
            "description": "High-quality text processing model",
            "verification_required": False
        }
    }
    
    def __init__(self):
        self.client = None
        if self.is_available():
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def is_available(self) -> bool:
        """Check if OpenAI is available and configured"""
        return OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY") is not None
    
    def _get_api_model_name(self, model: str) -> str:
        """Get the actual API model name (some models have different display vs API names)"""
        model_info = self.models.get(model, {})
        return model_info.get("api_model_name", model)
    
    def call_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """Make text-only API call to OpenAI"""
        try:
            api_model_name = self._get_api_model_name(model)
            
            # Build parameters based on model type
            completion_params = {
                "model": api_model_name,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            # o4-mini has specific parameter requirements
            if "o4-mini" in api_model_name:
                # o4-mini only supports default temperature (1), so don't include it
                completion_params["max_completion_tokens"] = kwargs.get("max_tokens", 4000)
                # Set reasoning effort to high for maximum accuracy
                completion_params["reasoning_effort"] = "high"
            else:
                # Other models use standard parameters
                completion_params["temperature"] = kwargs.get("temperature", 0.1)
                completion_params["max_tokens"] = kwargs.get("max_tokens", 4000)
            
            response = self.client.chat.completions.create(**completion_params)
            
            return {
                "success": True,
                "text": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens,
                "model": model
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "model": model
            }
    
    def call_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> Dict[str, Any]:
        """Enhanced with improved retry logic, jitter, and detailed finish_reason logging"""
        # Validate inputs
        if not image_data or not image_data.strip():
            return {
                "success": False,
                "error": "Empty image data provided",
                "text": None,
                "model": model
            }
        
        if not prompt or not prompt.strip():
            return {
                "success": False,
                "error": "Empty prompt provided",
                "text": None,
                "model": model
            }
        
        # 🔧 IMPROVEMENT: Enhanced retry logic with exponential backoff + jitter
        max_retries = 4  # Increased from 3 to 4 for o4-mini reliability
        base_delay = 1.0
        
        logger.info(f"🤖 Starting OpenAI API call for {model} (max {max_retries} attempts)")
        
        for attempt in range(max_retries):
            try:
                # 🔧 IMPROVEMENT: Add pre-send jitter to prevent simultaneous backend hits
                if attempt > 0:
                    jitter = random.uniform(0.2, 0.5)
                    delay = base_delay * (2 ** (attempt - 1)) + jitter  # Exponential backoff + jitter
                    logger.info(f"🔄 Retry attempt {attempt + 1} after {delay:.2f}s delay")
                    time.sleep(delay)
                
                api_model_name = self._get_api_model_name(model)
                
                # CRITICAL: Build OpenAI vision API message format
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}",
                                    "detail": kwargs.get("detail", "high")
                                }
                            }
                        ]
                    }
                ]
                
                # Build parameters based on model type
                completion_params = {
                    "model": api_model_name,
                    "messages": messages
                }
                
                # 🔧 IMPROVEMENT: Explicit high max_tokens for all models to prevent cutoffs
                if "o4-mini" in api_model_name:
                    completion_params["max_completion_tokens"] = kwargs.get("max_tokens", 8000)  # Increased from 4000
                    completion_params["reasoning_effort"] = "high"
                    logger.info(f"🧠 Using o4-mini with high reasoning effort, max_tokens: {completion_params['max_completion_tokens']}")
                else:
                    completion_params["temperature"] = kwargs.get("temperature", 0.1)
                    completion_params["max_tokens"] = kwargs.get("max_tokens", 8000)  # Increased from 4000
                    logger.info(f"🤖 Using {api_model_name}, max_tokens: {completion_params['max_tokens']}")
                
                # CRITICAL: Add structured JSON response format for JSON extraction mode
                json_mode = kwargs.get("json_mode", False)
                if json_mode:
                    completion_params["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "document_transcription",
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "documentId": {"type": "string"},
                                    "sections": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "body": {"type": "string"}
                                            },
                                            "required": ["id", "body"],
                                            "additionalProperties": False
                                        }
                                    }
                                },
                                "required": ["documentId", "sections"],
                                "additionalProperties": False
                            },
                            "strict": True
                        }
                    }
                    logger.info("📋 Using structured JSON output mode")
                
                # CRITICAL: Make OpenAI API call
                logger.info(f"📡 Sending API request (attempt {attempt + 1}/{max_retries})...")
                response = self.client.chat.completions.create(**completion_params)
                
                # 🔧 IMPROVEMENT: Detailed logging of finish_reason for debugging
                finish_reason = response.choices[0].finish_reason if response.choices else None
                token_usage = response.usage.total_tokens if response.usage else 0
                logger.info(f"📨 API response received: finish_reason='{finish_reason}', tokens={token_usage}")
                
                # Check for problematic finish reasons
                if finish_reason == "length":
                    logger.warning(f"⚠️ Response truncated due to token limit - consider increasing max_tokens")
                elif finish_reason == "content_filter":
                    logger.warning(f"⚠️ Response blocked by content filter")
                elif finish_reason != "stop":
                    logger.warning(f"⚠️ Unexpected finish_reason: {finish_reason}")
                
                # Validate response
                if not response.choices or not response.choices[0].message.content:
                    logger.warning(f"❌ Empty response content (finish_reason: {finish_reason})")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return {
                            "success": False,
                            "error": f"OpenAI returned empty response after {max_retries} retries (finish_reason: {finish_reason})",
                            "text": None,
                            "model": model
                        }
                
                # CRITICAL: Extract text content from response
                extracted_text = response.choices[0].message.content.strip()
                
                if not extracted_text:
                    logger.warning(f"❌ Empty text content after strip (finish_reason: {finish_reason})")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return {
                            "success": False,
                            "error": f"OpenAI returned empty text content after {max_retries} retries (finish_reason: {finish_reason})",
                            "text": None,
                            "model": model
                        }
                
                # 🔧 IMPROVEMENT: Success logging with detailed metrics
                char_count = len(extracted_text)
                word_count = len(extracted_text.split())
                logger.info(f"✅ API call successful: {char_count} chars, {word_count} words, {token_usage} tokens, finish_reason: {finish_reason}")
                
                return {
                    "success": True,
                    "text": extracted_text,
                    "tokens_used": token_usage,
                    "model": model,
                    "finish_reason": finish_reason,  # 🔧 IMPROVEMENT: Include for debugging
                    "char_count": char_count,
                    "word_count": word_count
                }
                
            except Exception as e:
                logger.error(f"💥 API call attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(f"💥 All {max_retries} attempts failed for {model}")
                    return {
                        "success": False,
                        "error": f"OpenAI API failed after {max_retries} attempts: {str(e)}",
                        "text": None,
                        "model": model
                    }
    
    def process_image_with_text(self, image_data: str, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """
        Process image with text prompt (wrapper around call_vision for pipeline compatibility)
        
        🔴 CRITICAL PIPELINE INTERFACE - DO NOT MODIFY SIGNATURE 🔴
        
        Args:
            image_data: Base64 encoded image data (clean, no prefix)
            prompt: Text prompt for processing
            model: Model to use
            **kwargs: Additional parameters
        
        Returns:
            Standardized response format for pipelines
            
        CRITICAL RESPONSIBILITIES:
        1. Call call_vision() with correct parameters
        2. Convert response to pipeline-expected format
        3. Map "text" field to "extracted_text" field
        4. Preserve token usage and metadata
        """
        # CRITICAL: Call vision API with provided parameters
        result = self.call_vision(prompt, image_data, model, **kwargs)
        
        # CRITICAL: Convert to pipeline-expected format
        # Pipeline expects "extracted_text" field, call_vision returns "text"
        if result.get("success"):
            return {
                "success": True,
                "extracted_text": result.get("text", ""),  # CRITICAL: Field mapping
                "tokens_used": result.get("tokens_used"),
                "model_used": result.get("model"),
                "service_type": "llm",
                "confidence_score": 1.0,  # OpenAI doesn't provide confidence scores
                "metadata": {
                    "provider": "openai",
                    **kwargs
                }
            }
        else:
            # CRITICAL: Preserve error response format
            return result
    
    def call_structured_pydantic(self, prompt: str, input_text: str, model: str, parcel_id: Optional[str] = None, schema: dict = None, **kwargs) -> Dict[str, Any]:
        """Make structured output API call using dynamic schema (recommended approach)"""
        try:
            api_model_name = self._get_api_model_name(model)
            
            # Use provided schema or load default fallback (GENERIC)
            if schema:
                schema_dict = schema
            else:
                schema_dict = self._load_parcel_schema()  # Fallback
            
            # Create the proper OpenAI JSON schema structure
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "plattera_parcel",
                    "schema": schema_dict,
                    "strict": True
                }
            }
            
            # Create the full prompt
            full_prompt = f"{prompt}\n\nLegal Description Text:\n{input_text}"
            
            # Generate parcel ID if not provided
            if not parcel_id:
                parcel_id = f"parcel-{int(time.time() * 1000)}"
            
            # Make the API call
            completion = self.client.chat.completions.create(
                model=api_model_name,
                messages=[
                    {"role": "user", "content": full_prompt}
                ],
                response_format=response_format,
                temperature=0,
                max_tokens=4000
            )
            
            # Extract the response
            response_content = completion.choices[0].message.content
            
            # Parse the JSON response
            try:
                structured_data = json.loads(response_content)
                structured_data['parcel_id'] = parcel_id  # Ensure parcel_id is set
                
                # Return standardized response format
                return {
                    "success": True,
                    "structured_data": structured_data,
                    "text": response_content,
                    "tokens_used": completion.usage.total_tokens,
                    "model": model
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Failed to parse LLM response as JSON: {e}",
                    "text": response_content,
                    "model": model
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"OpenAI structured extraction failed: {str(e)}",
                "structured_data": None,
                "model": model
            }
    
    def _load_parcel_schema(self) -> dict:
        """Load the parcel schema as fallback (matches pipeline schema)"""
        try:
            # Updated to match pipeline schema file
            schema_path = Path(__file__).parent.parent.parent / "schema" / "plss_m_and_b.json"
            with open(schema_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Parcel schema file not found at {schema_path}")
            return {}
    
    def call_structured(self, prompt: str, input_text: str, schema: dict, model: str, **kwargs) -> Dict[str, Any]:
        """Make structured output API call using JSON schema (fallback method)"""
        try:
            api_model_name = self._get_api_model_name(model)
            
            # Create the full prompt
            full_prompt = f"{prompt}\n\nLegal Description Text:\n{input_text}"
            
            messages = [{"role": "user", "content": full_prompt}]
            
            # Use the passed-in schema parameter (dynamic) instead of hardcoded
            completion_params = {
                "model": api_model_name,
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": schema  # ✅ Use passed-in schema
                },
                "temperature": kwargs.get("temperature", 0.1),
                "max_tokens": kwargs.get("max_tokens", 4000)
            }
            
            response = self.client.chat.completions.create(**completion_params)
            
            # Parse the structured JSON response
            response_text = response.choices[0].message.content
            try:
                structured_data = json.loads(response_text)
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Failed to parse structured response: {str(e)}",
                    "text": response_text,
                    "model": model
                }
            
            return {
                "success": True,
                "structured_data": structured_data,
                "text": response_text,
                "tokens_used": response.usage.total_tokens,
                "model": model
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "structured_data": None,
                "model": model
            } 