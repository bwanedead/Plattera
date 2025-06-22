"""
Text Cleaner Module
Cleans and normalizes outputs into usable internal structure
"""
import re

class TextCleaner:
    def __init__(self):
        pass
    
    def clean_extracted_text(self, raw_text: str) -> str:
        """Clean and normalize extracted text from OCR/vision processing"""
        if not raw_text:
            return ""
        
        # Remove extra whitespace and normalize line breaks
        cleaned = re.sub(r'\s+', ' ', raw_text.strip())
        
        # Fix common OCR errors in legal documents
        cleaned = self._fix_common_ocr_errors(cleaned)
        
        # Normalize legal document formatting
        cleaned = self._normalize_legal_formatting(cleaned)
        
        return cleaned
    
    def _fix_common_ocr_errors(self, text: str) -> str:
        """Fix common OCR misreads in legal documents"""
        # Common OCR corrections for legal documents
        corrections = {
            r'\bO\b': '0',  # O -> 0 in measurements
            r'\bl\b': '1',  # l -> 1 in measurements  
            r'°': ' degrees ',  # Normalize degree symbol
            r"'": ' minutes ',  # Normalize minute symbol
            r'"': ' seconds ',  # Normalize second symbol
            r'\bthence\b': 'thence',  # Ensure proper legal terms
            r'\bbeginning\b': 'beginning',
            r'\btownship\b': 'township',
            r'\brange\b': 'range',
            r'\bsection\b': 'section',
        }
        
        for pattern, replacement in corrections.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text
    
    def _normalize_legal_formatting(self, text: str) -> str:
        """Normalize formatting for legal descriptions"""
        # Ensure proper spacing around key legal terms
        legal_terms = [
            'beginning at', 'thence', 'north', 'south', 'east', 'west',
            'degrees', 'minutes', 'seconds', 'feet', 'chains', 'rods'
        ]
        
        for term in legal_terms:
            # Add proper spacing around terms
            pattern = r'\b' + re.escape(term) + r'\b'
            text = re.sub(pattern, f' {term} ', text, flags=re.IGNORECASE)
        
        # Clean up multiple spaces created by normalization
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def normalize_bearings(self, bearing_text: str) -> dict:
        """Convert bearing text to standardized format"""
        # TODO: Implement bearing normalization
        return {"normalized": "placeholder"}
    
    def normalize_distances(self, distance_text: str) -> dict:
        """Convert distance text to consistent units"""
        # TODO: Implement distance normalization  
        return {"normalized": "placeholder"} 