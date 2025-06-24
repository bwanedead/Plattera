"""
Centralized Image-to-Text Prompts
Edit these prompts to adjust how LLMs extract text from images
"""

# Main legal document extraction prompt
LEGAL_DOCUMENT = """
Transcribe all text from this legal document image.
Focus on accuracy and preserve important formatting.
Include all names, dates, property descriptions, and legal language.
Return only the extracted text without any additional commentary.
"""

# Ultra-precise legal deed transcription (for o4-mini)
ULTRA_PRECISE_LEGAL = """
Can you transcribe this legal deed text. I need very accurate transcription every number figure and detail to be preserved exactly into the plain text transcription. The numbers and figures and property description details are essential to have exactly correct no errors can be present or all downstream work is corrupted.
"""

# Simple OCR-style extraction
SIMPLE_OCR = """
Extract all visible text from this image.
Transcribe exactly what you see, preserving line breaks where appropriate.
Do not add any interpretation or commentary.
"""

# Handwritten document extraction
HANDWRITTEN = """
Carefully transcribe this handwritten document.
Pay special attention to unclear characters and use context to resolve ambiguities.
Preserve the original structure and formatting where possible.
If any text is unclear, indicate with [unclear] but continue transcribing.
"""

# Property deed specific extraction
PROPERTY_DEED = """
This is a property deed or similar legal document. Extract all text including:
- All names of parties involved
- All dates and locations
- Complete property descriptions and legal boundaries
- All legal language and clauses
- Signatures and notary information

Preserve the document structure and return only the transcribed text.
"""

# Court document extraction
COURT_DOCUMENT = """
This is a court document. Extract all text including:
- Case numbers and court information
- All party names and legal representation
- All dates and deadlines
- Complete legal arguments and rulings
- All procedural information

Maintain the formal structure of the document.
"""

# Contract extraction
CONTRACT = """
This is a legal contract. Extract all text including:
- All party information
- Contract terms and conditions
- Dates, amounts, and specific obligations
- Signatures and witness information
- All legal clauses and provisions

Preserve the contract structure and hierarchy.
"""

def get_image_to_text_prompt(extraction_mode: str, model: str = None) -> str:
    """
    Get the appropriate prompt for the given extraction mode and model
    
    Args:
        extraction_mode: The mode of extraction (legal_document, simple_ocr, etc.)
        model: The model being used (optional, for model-specific prompts)
        
    Returns:
        str: The prompt text for the given mode and model
    """
    # Use ultra-precise prompt for o4-mini model with legal documents
    if model == "gpt-o4-mini" and extraction_mode == "legal_document":
        return ULTRA_PRECISE_LEGAL
    
    prompts = {
        "legal_document": LEGAL_DOCUMENT,
        "simple_ocr": SIMPLE_OCR,
        "handwritten": HANDWRITTEN,
        "property_deed": PROPERTY_DEED,
        "court_document": COURT_DOCUMENT,
        "contract": CONTRACT
    }
    
    return prompts.get(extraction_mode, LEGAL_DOCUMENT) 