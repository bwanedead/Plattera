"""
Alignment and Consensus Processing Module
========================================

This module contains all alignment, consensus, and validation logic
for processing multiple drafts and determining the best consensus text.

Now includes BioPython-based consistency alignment engine for high-accuracy
multiple sequence alignment of legal document drafts.
"""

# Configuration
from .alignment_config import (
    ANCHOR_PATTERNS,
    TOKENIZATION,
)

# BioPython alignment engine
from .biopython_engine import (
    BioPythonAlignmentEngine,
    test_biopython_engine,
    check_biopython_engine_status
)

from .json_draft_tokenizer import (
    JsonDraftTokenizer,
    create_sample_json_drafts,
    validate_json_draft_format
)

from .consistency_aligner import ConsistencyBasedAligner
from .confidence_scorer import BioPythonConfidenceScorer
from .alignment_utils import check_dependencies, AlignmentError
from .section_normalizer import SectionNormalizer

__all__ = [
    # Configuration
    'ANCHOR_PATTERNS',
    'TOKENIZATION', 
    
    # BioPython Alignment Engine
    'BioPythonAlignmentEngine',
    'test_biopython_engine',
    'check_biopython_engine_status',
    
    # BioPython Components
    'JsonDraftTokenizer',
    'ConsistencyBasedAligner',
    'BioPythonConfidenceScorer',
    'SectionNormalizer',
    
    # Utilities
    'create_sample_json_drafts',
    'validate_json_draft_format',
    'check_dependencies',
    'AlignmentError'
] 