"""
Alignment Configuration
======================

Regex patterns and configuration for legal document alignment and tokenization.
"""

# Anchor patterns for legal document elements
ANCHOR_PATTERNS = {
    "NUM": r'\b\d+(?:\.\d+)?\b',                                    # Numbers: 123, 45.67
    "FRAC": r'\b\d+/\d+\b',                                         # Fractions: 1/2, 3/4
    "BEAR": r'\b(?:N|S|E|W)\s*\d+°\s*(?:\d+′\s*)?(?:\d+″\s*)?(?:E|W)?\b',  # Bearings: N 10° E, S 45°30′15″ W
    "DEG": r'\b\d+°(?:\d+′)?(?:\d+″)?\b',                          # Degrees: 10°, 45°30′, 45°30′15″
    "ID": r'\b(?:Township|Section|Range|Lot|Block|Parcel)\s+\d+\b', # Identifiers: Township 1, Section 2
    "WORD": r'\b[A-Za-z]+\b',                                       # Regular words
    "PUN": r'[.,;:!?()[\]{}"\'-]'                                   # Punctuation
}

# Tokenization configuration
TOKENIZATION = {
    "KEEP_PATTERNS": ["NUM", "FRAC", "BEAR", "DEG", "ID", "WORD"],
    "DROP_PATTERNS": ["PUN"]  # Punctuation is dropped during tokenization
} 