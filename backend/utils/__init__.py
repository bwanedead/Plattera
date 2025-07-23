"""
Utility modules for the Plattera backend.
"""

from utils.file_handler import cleanup_temp_file, save_uploaded_file, encode_image_to_base64, is_valid_image_file
from utils.response_models import ProcessResponse, BaseResponse
from utils.text_utils import is_json_result, are_json_results, is_llm_refusal_or_failed, filter_valid_extractions, calculate_text_similarity
from utils.health_monitor import HealthMonitor, get_health_monitor, check_health, perform_cleanup

__all__ = [
    'cleanup_temp_file',
    'save_uploaded_file',
    'encode_image_to_base64',
    'is_valid_image_file',
    'ProcessResponse',
    'BaseResponse',
    'is_json_result',
    'are_json_results',
    'is_llm_refusal_or_failed',
    'filter_valid_extractions',
    'calculate_text_similarity',
    'HealthMonitor',
    'get_health_monitor',
    'check_health',
    'perform_cleanup'
] 