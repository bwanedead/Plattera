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