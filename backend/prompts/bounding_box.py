"""
Bounding Box Detection Prompts
==============================

LLM prompts for word segmentation and bounding box detection.
These prompts are designed to work with vision APIs for precise word boundary detection.
"""

# Word segmentation prompt
WORD_SEGMENTATION_PROMPT = """
Analyze this legal document image with ruler overlays. The ruler shows exactly {num_lines} numbered horizontal lines.

TASK: Identify word boundaries within each numbered line.

OUTPUT: Return JSON only with exactly {num_lines} lines:
{{
  "lines": [
    {{
      "line_number": 1,
      "words": [
        ["word", 50, 80],
        ["next_word", 85, 120]
      ]
    }}
  ]
}}

CRITICAL RULES:
- Return exactly {num_lines} lines (no more, no less)
- Line numbers must match the ruler overlay numbers exactly
- Each word: ["text", start_pos, end_pos]
- Use ruler coordinates for positions
- Include all visible words
- Skip illegible text
- Return empty array for blank lines
- Do not create extra lines beyond what the ruler shows
"""

def get_word_segmentation_prompt(complexity: str = "standard", model: str = None, num_lines: int = None) -> str:
    """
    Get the word segmentation prompt
    
    Args:
        complexity: The complexity level (ignored, kept for compatibility)
        model: The model being used (ignored, kept for compatibility)
        num_lines: The exact number of lines detected by OpenCV
        
    Returns:
        str: The prompt text for word segmentation
    """
    if num_lines is None:
        num_lines = 22  # Default fallback
    
    return WORD_SEGMENTATION_PROMPT.format(num_lines=num_lines)

def get_available_complexity_levels() -> dict:
    """
    Get all available complexity levels with descriptions
    
    Returns:
        dict: Dictionary of complexity_id -> {name, description}
    """
    return {
        "standard": {
            "name": "Standard Word Segmentation", 
            "description": "Standard word segmentation with ruler overlay"
        }
    }
