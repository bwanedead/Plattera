"""
Bounding Box Detection Prompts
==============================

LLM prompts for word segmentation and bounding box detection.
These prompts are designed to work with vision APIs for precise word boundary detection.
"""

# ============================================================================
# WORD SEGMENTATION PROMPTS
# ============================================================================

# Standard word segmentation prompt
WORD_SEGMENTATION_STANDARD = """
You are analyzing a legal document image with ruler overlays. Each horizontal line of text has been numbered with grid coordinates.

TASK: Identify word boundaries within each numbered line section.

INPUT: Image with ruler overlay showing numbered horizontal lines.

OUTPUT: Return a JSON object with the following structure:

{
  "lines": [
    {
      "line_number": 1,
      "words": ["word", start_position, end_position, "word", start_position, end_position]
    }
  ]
}

RULES:
- Each line contains: word, start_position, end_position, next_word, start_position, end_position, etc.
- Positions are grid coordinates from the ruler overlay
- Include all visible words in each line
- Handle cursive handwriting and mixed fonts
- Skip any illegible or unclear text
- Use the exact line numbers shown in the ruler overlay
- Return empty array for lines with no visible text
"""

# Enhanced word segmentation for complex handwriting
WORD_SEGMENTATION_ENHANCED = """
You are analyzing a legal document image with ruler overlays. Each horizontal line of text has been numbered with grid coordinates.

TASK: Identify word boundaries within each numbered line section with high precision.

INPUT: Image with ruler overlay showing numbered horizontal lines.

OUTPUT: Return a JSON object with the following structure:

{
  "lines": [
    {
      "line_number": 1,
      "words": ["word", start_position, end_position, "word", start_position, end_position]
    }
  ]
}

RULES:
- Each line contains: word, start_position, end_position, next_word, start_position, end_position, etc.
- Positions are grid coordinates from the ruler overlay
- Include all visible words in each line
- Handle cursive handwriting and mixed fonts
- Skip any illegible or unclear text
- Use the exact line numbers shown in the ruler overlay
- Return empty array for lines with no visible text
- For complex handwriting, make best effort to identify word boundaries
- Account for connected letters and ligatures in cursive text
"""

# Simple word segmentation for clean text
WORD_SEGMENTATION_SIMPLE = """
You are analyzing a legal document image with ruler overlays. Each horizontal line of text has been numbered with grid coordinates.

TASK: Identify word boundaries within each numbered line section.

INPUT: Image with ruler overlay showing numbered horizontal lines.

OUTPUT: Return a JSON object with the following structure:

{
  "lines": [
    {
      "line_number": 1,
      "words": ["word", start_position, end_position, "word", start_position, end_position]
    }
  ]
}

RULES:
- Each line contains: word, start_position, end_position, next_word, start_position, end_position, etc.
- Positions are grid coordinates from the ruler overlay
- Include all visible words in each line
- Handle cursive handwriting and mixed fonts
- Skip any illegible or unclear text
- Use the exact line numbers shown in the ruler overlay
- Return empty array for lines with no visible text
"""

def get_word_segmentation_prompt(complexity: str = "standard", model: str = None) -> str:
    """
    Get the appropriate word segmentation prompt
    
    Args:
        complexity: The complexity level ("simple", "standard", "enhanced")
        model: The model being used (optional, for model-specific prompts)
        
    Returns:
        str: The prompt text for word segmentation
        
    Available complexity levels:
        - simple: Basic word detection for clean text
        - standard: Standard word segmentation with confidence
        - enhanced: Advanced analysis for complex handwriting
    """
    
    prompts = {
        "simple": WORD_SEGMENTATION_SIMPLE,
        "standard": WORD_SEGMENTATION_STANDARD,
        "enhanced": WORD_SEGMENTATION_ENHANCED
    }
    
    return prompts.get(complexity, WORD_SEGMENTATION_STANDARD)

def get_available_complexity_levels() -> dict:
    """
    Get all available complexity levels with descriptions
    
    Returns:
        dict: Dictionary of complexity_id -> {name, description}
    """
    return {
        "simple": {
            "name": "Simple Word Detection",
            "description": "Basic word boundary detection for clean, typed text"
        },
        "standard": {
            "name": "Standard Word Segmentation", 
            "description": "Standard word segmentation with confidence scoring"
        },
        "enhanced": {
            "name": "Enhanced Handwriting Analysis",
            "description": "Advanced analysis for complex cursive handwriting and challenging text"
        }
    }
