"""
Centralized Image-to-Text Prompts
Edit these prompts to adjust how LLMs extract text from images
"""

# ============================================================================
# CORE TRANSCRIPTION MODES
# ============================================================================

# Ultra-precise legal transcription (no sections)
ULTRA_PRECISE_LEGAL = """
Can you transcribe this legal deed text. I need very accurate transcription every number figure and detail to be preserved exactly into the plain text transcription. The numbers and figures and property description details are essential to have exactly correct no errors can be present or all downstream work is corrupted.

Return only the extracted text without any additional commentary or section markers.
"""

# Plain legal document transcription (no sections)
LEGAL_DOCUMENT_PLAIN = """
Transcribe all text from this legal document image.
Focus on accuracy and preserve important formatting.
Include all names, dates, property descriptions, and legal language.
Return only the extracted text without any additional commentary or section markers.
"""

# Legal document with section markers
LEGAL_DOCUMENT_SECTIONED = """
Transcribe all text from this legal document image.
Focus on accuracy and preserve important formatting.
Include all names, dates, property descriptions, and legal language.

When transcribing, identify natural sections or logical breaks in the document and mark them with section headers using this format:
DONUT-1
[first section content]
DONUT-2
[second section content]
DONUT-3
[third section content]
...and so on

Use your judgment to break the text into meaningful sections (paragraphs, clauses, different parts of the document, etc.). Each section should be substantial enough to be meaningful but not so large as to lose granularity.

Return only the extracted text with section markers, without any additional commentary.
"""

# JSON structured transcription
LEGAL_DOCUMENT_JSON = """
You are an expert legal transcriptionist. Output **ONLY** valid JSON conforming to the schema below. Do not wrap in markdown or add any other text.

Schema:
{
  "documentId": "<string>",
  "sections": [
    {
      "id": <int>,
      "body": "<string>"
    }
  ]
}

SECTIONING RULES:
1. Use consecutive integers starting at 1 for "id".
2. DO NOT INCLUDE DOCUMENT ID IN TEXT BODY! document ID is very unimportant for our purposes and its presence is more a nuisance than helpful just negate it entirely or apply it to the document id field never in the text body [this applies to the document id only].
3. **COMBINE HEADERS WITH FIRST SECTION**: Any document title, header, should be included at the beginning of section 1's body text. Do NOT create separate sections for headers, titles, or document identifiers.
4. **Section on natural breaks**: Create new sections based on:
   - Clear paragraph breaks and line breaks
   - Major clauses or distinct legal concepts
   - Logical content divisions in the document
   - Substantial changes in content flow
5. **Keep section boundaries consistent:** If you see a similar structure or repeated format, use the same sectioning logic for each occurrence.
6. Each "body" must contain the actual transcribed text content, preserving original line breaks.
7. Never insert or omit a section arbitrarily; reflect every change in the numbering.
8. Ensure ultra-precise transcription—every number, figure, and detail must be preserved exactly.
9. Do not insert hyphens to break words at line endings. Transcribe all words in full, without splitting or hyphenating them across lines.


**Consistency is critical:** Imagine that multiple experts are transcribing the same document in parallel. Your sectioning should be so clear and logical that all experts would produce the same number and boundaries of sections.

Transcribe this legal document image into the JSON format above. Focus on accuracy and preserve all names, dates, property descriptions, and legal language.
"""

def get_image_to_text_prompt(extraction_mode: str, model: str = None) -> str:
    """
    Get the appropriate prompt for the given extraction mode and model
    
    Args:
        extraction_mode: The mode of extraction 
        model: The model being used (optional, for model-specific prompts)
        
    Returns:
        str: The prompt text for the given mode and model
        
    Available modes:
        - ultra_precise_legal: Ultra-precise transcription without sections
        - legal_document_plain: Plain transcription without sections  
        - legal_document_sectioned: Transcription with DONUT section markers
        - legal_document_json: Structured JSON transcription
    """
    
    prompts = {
        "ultra_precise_legal": ULTRA_PRECISE_LEGAL,
        "legal_document_plain": LEGAL_DOCUMENT_PLAIN,
        "legal_document_sectioned": LEGAL_DOCUMENT_SECTIONED, 
        "legal_document_json": LEGAL_DOCUMENT_JSON
    }
    
    return prompts.get(extraction_mode, LEGAL_DOCUMENT_PLAIN)

def get_available_extraction_modes() -> dict:
    """
    Get all available extraction modes with descriptions
    
    Returns:
        dict: Dictionary of mode_id -> {name, description}
    """
    return {
        "ultra_precise_legal": {
            "name": "Ultra Precise Legal",
            "description": "Ultra-precise transcription without sections (maximum accuracy)"
        },
        "legal_document_plain": {
            "name": "Legal Document Plain", 
            "description": "Plain legal document transcription without section markers"
        },
        "legal_document_sectioned": {
            "name": "Legal Document Sectioned",
            "description": "Legal document transcription with DONUT section markers for alignment"
        },
        "legal_document_json": {
            "name": "Legal Document JSON",
            "description": "Structured JSON transcription with deterministic parsing (recommended for alignment)"
        }
    } 