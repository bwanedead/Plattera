# Prompts package

# Import all prompt modules
from . import image_to_text
from . import text_to_schema
from . import bounding_box

# Re-export key functions for easy access
from .image_to_text import get_image_to_text_prompt, get_available_extraction_modes
from .text_to_schema import get_text_to_schema_prompt
from .bounding_box import get_word_segmentation_prompt, get_available_complexity_levels

__all__ = [
    # Image to text prompts
    'get_image_to_text_prompt',
    'get_available_extraction_modes',
    
    # Text to schema prompts
    'get_text_to_schema_prompt',
    
    # Bounding box prompts
    'get_word_segmentation_prompt',
    'get_available_complexity_levels'
] 