"""
Alignment Configuration
=====================

Configuration constants for the semantic alignment system.
Supersedes earlier consensus implementations.
"""

# Alignment scoring configuration
ALIGN = {
    "MATCH": 5,
    "FUZZY": 3,
    "GAP": -4,
    "MISMATCH": -5,
    "ANCHOR_MISMATCH": -1000,
    "BAND_MIN": 50,
    "BAND_FRAC": 0.2
}

# System limits
LIMITS = {
    "MAX_DRAFTS": 10
}

# Fuzzy matching thresholds
FUZZY_THRESHOLDS = {
    "LEVENSHTEIN_MAX": 2,
    "COSINE_MIN": 0.85
}

# Anchor patterns for legal documents
ANCHOR_PATTERNS = {
    "NUM": r'\d+(?:\.\d+)?',
    "FRAC": r'\d+\s*/\s*\d+',
    "BEAR": r'(?:N|S|E|W)(?:\s*\d+°(?:\d+′\d+″)?(?:\s*[NSEW])?)',
    "DEG": r'\d+°(?:\d+′\d+″)?',
    "ID": r'(?:Township|Section|Range)\s+\d+',
    "WORD": r'[a-zA-Z]+(?:\'[a-zA-Z]+)?',
    "PUN": r'[.,;()]'
}

# Tokenization settings
TOKENIZATION = {
    "KEEP_PATTERNS": ["NUM", "FRAC", "BEAR", "DEG", "ID", "WORD"],
    "DROP_PATTERNS": ["PUN"],
    "MERGE_COMPOSITES": True  # Merge "Township 14" into single token
}
