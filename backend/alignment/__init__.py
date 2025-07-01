"""
Alignment and Consensus Processing Module
========================================

This module contains all alignment, consensus, and validation logic
for processing multiple drafts and determining the best consensus text.

Now includes BioPython-based consistency alignment engine for high-accuracy
multiple sequence alignment of legal document drafts.
"""

# Core alignment functionality
from .validate import (
    DocumentValidator,
    # extract_anchors_from_text, # This function does not exist in validate.py
    # validate_document_completeness # This function does not exist in validate.py
)

from .tokenise import (
    DocumentTokenizer,
    # tokenize_legal_document, # This function does not exist in tokenise.py
    # get_tokenization_stats # This function does not exist in tokenise.py
)

from .alignment_config import (
    ANCHOR_PATTERNS,
    TOKENIZATION,
    # VALIDATION_RULES # This does not exist in alignment_config.py
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
from .visualizer import BioPythonAlignmentVisualizer
from .alignment_utils import check_dependencies, AlignmentError

__all__ = [
    # Validation
    'DocumentValidator',
    # extract_anchors_from_text', 
    # validate_document_completeness',
    
    # Tokenization
    'DocumentTokenizer',
    # 'tokenize_legal_document',
    # 'get_tokenization_stats',
    
    # Configuration
    'ANCHOR_PATTERNS',
    'TOKENIZATION', 
    # 'VALIDATION_RULES',
    
    # BioPython Alignment Engine
    'BioPythonAlignmentEngine',
    'test_biopython_engine',
    'check_biopython_engine_status',
    
    # BioPython Components
    'JsonDraftTokenizer',
    'ConsistencyBasedAligner',
    'BioPythonConfidenceScorer',
    'BioPythonAlignmentVisualizer',
    
    # Utilities
    'create_sample_json_drafts',
    'validate_json_draft_format',
    'check_dependencies',
    'AlignmentError'
] 